"""The measured proof that an unrecognized `kid` never stalls the event loop, through the whole real stack."""
import asyncio
import io
import json
import time

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm

from nativespeaker.api.app.dependencies import get_linked_identity
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.schemas.auth import Identity
from unit.conftest import PUBLIC_KEY_PEM, TEST_ISSUER, TEST_PROJECT_ID, make_token

JWKS_URL = "https://jwks.invalid/keys"
KNOWN_KID = "test-key-1"

# Long enough that a blocked loop is unmistakable, short enough that the suite does not pay for it.
FETCH_DELAY = 0.4
HEARTBEAT_INTERVAL = 0.01


def jwks_body(kid: str = KNOWN_KID) -> bytes:
    """A one-key JWKS document served under whatever `kid` is asked for; `PyJWKSet` rejects an empty key list."""
    key = RSAAlgorithm(RSAAlgorithm.SHA256).prepare_key(PUBLIC_KEY_PEM)
    jwk = json.loads(RSAAlgorithm.to_jwk(key))
    jwk.update(kid=kid, use="sig", alg="RS256")
    return json.dumps({"keys": [jwk]}).encode()


JWKS_BODY = jwks_body()


class CountedJwksTransport:
    """A counted, optionally slow, optionally failing stand-in for PyJWT's one blocking call."""

    def __init__(self) -> None:
        self.timeouts: list[float | None] = []
        self.fetch_delay: float = 0.0
        self.error: Exception | None = None
        self.body: bytes = JWKS_BODY

    def __len__(self) -> int:
        return len(self.timeouts)

    def urlopen(self, request, timeout=None, context=None):  # noqa: ARG002 - urlopen's signature
        self.timeouts.append(timeout)
        if self.fetch_delay:
            time.sleep(self.fetch_delay)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.body)


def install_counted_transport(monkeypatch) -> CountedJwksTransport:
    """Put a counted transport under a real `PyJWKClient`, and hand back the counter."""
    transport = CountedJwksTransport()
    monkeypatch.setattr("urllib.request.urlopen", transport.urlopen)
    return transport


class _EmptyResult:
    def first(self):
        return None


class _NoIdentitySession:
    """Every case here is refused before the identity read, so this exists only so a wrong accept fails as 403."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def exec(self, _statement):
        return _EmptyResult()


@pytest.fixture
def transport(monkeypatch) -> CountedJwksTransport:
    return install_counted_transport(monkeypatch)


@pytest.fixture
def verifier(transport) -> JWTVerifier:
    """A real `JWTVerifier` whose warm-up fetch has already been counted at the transport."""
    return JWTVerifier(jwks_url=JWKS_URL, audience=TEST_PROJECT_ID, issuer=TEST_ISSUER)


@pytest.fixture
def probe_app(verifier) -> FastAPI:
    """One route carrying the real dependency at router and endpoint level, which is the production shape."""
    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter(dependencies=[Depends(get_linked_identity)])

    @router.get("/probe")
    async def _probe(identity: Identity = Depends(get_linked_identity)):
        return {"reached": True}

    app.include_router(router)
    app.state.jwt_verifier = verifier
    app.state.session_factory = _NoIdentitySession
    return app


class Heartbeat:
    """The instrument: a tick proves the loop scheduled something else while the JWKS fetch was outstanding."""

    def __init__(self) -> None:
        self.ticks: list[float] = []
        self._task: asyncio.Task | None = None

    async def __aenter__(self) -> Heartbeat:
        async def _beat() -> None:
            while True:
                self.ticks.append(time.monotonic())
                await asyncio.sleep(HEARTBEAT_INTERVAL)

        self._task = asyncio.create_task(_beat())
        await asyncio.sleep(HEARTBEAT_INTERVAL * 5)  # let the task settle into its rhythm
        self.ticks.clear()
        return self

    async def __aexit__(self, *_exc) -> None:
        assert self._task is not None
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    def ticks_between(self, started: float, finished: float) -> int:
        return sum(1 for tick in self.ticks if started <= tick <= finished)


async def _get_probe(app: FastAPI, headers) -> tuple[int, dict, float, float]:
    """Drive one request over the app's own loop and return it bracketed by a measured window."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = time.monotonic()
        response = await client.get("/probe", headers=headers)
        finished = time.monotonic()
    return response.status_code, response.json(), started, finished


async def test_an_unknown_kid_request_does_not_starve_the_event_loop(probe_app, transport):
    """The loop keeps serving while an unrecognized `kid` is fetched; ten ticks is a fourfold margin on noise."""
    token = make_token("u", headers={"kid": "unrecognised-1"})
    transport.fetch_delay = FETCH_DELAY

    async with Heartbeat() as heartbeat:
        status, body, started, finished = await _get_probe(
            probe_app, {"Authorization": f"Bearer {token}"})

    assert status == 401
    assert body == {"code": "auth_required"}, "the client-visible response is unchanged by the fix"
    assert finished - started >= FETCH_DELAY, "the request really did wait on the stubbed fetch"
    ticks = heartbeat.ticks_between(started, finished)
    assert ticks >= 10, f"the event loop was starved during the JWKS fetch: {ticks} heartbeat ticks"


async def test_the_harness_detects_a_starved_loop(verifier, transport):
    """Permanent, not scaffolding: without this control the case above is a green assertion never shown to fail."""
    token = make_token("u", headers={"kid": "unrecognised-control"})
    transport.fetch_delay = FETCH_DELAY

    async with Heartbeat() as heartbeat:
        started = time.monotonic()
        claims, reason = verifier.verify(token)  # deliberately on the loop, deliberately blocking
        finished = time.monotonic()

    assert claims is None and reason is not None
    assert finished - started >= FETCH_DELAY
    ticks = heartbeat.ticks_between(started, finished)
    assert ticks <= 2, f"the harness cannot register a starved loop: it counted {ticks} ticks"


async def test_a_credential_less_request_never_reaches_the_jwks_transport(probe_app, transport):
    """The wire arm still precedes verification under the offload."""
    before = len(transport)

    status, body, _started, _finished = await _get_probe(probe_app, [])

    assert status == 401
    assert body == {"code": "auth_required"}
    assert len(transport) == before, "step 2 refused the request, so step 3 never ran"
