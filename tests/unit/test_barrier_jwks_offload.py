"""The measured proof that an unrecognized `kid` never stalls the event loop (CR-01).

`35-VERIFICATION.md` scored the fifth conjunct of 35-02's D10 -- "performs no per-request network
call" -- as failed: step 3 of the barrier called the synchronous `JWTVerifier.verify` directly from
`async def __call__`, and that call reaches `PyJWKClient.get_signing_key_from_jwt`, which on an
unmatched `kid` performs a blocking `urlopen` with PyJWT's 30-second default bound. One
unauthenticated request was enough to stop every other coroutine in the process, `/health/ready`
included.

What that gap needs is a *measurement*, not a structural assertion. So the request here travels the
whole stack -- ASGI, barrier, verifier, real `PyJWKClient`, stubbed transport -- while a heartbeat
coroutine counts its own ticks, and the case fails if the loop stops serving. The transport is
stubbed at `urllib.request.urlopen`, the one blocking call PyJWT makes; the client itself is real,
because the vacuous test this replaces (WR-05) substituted the client class and could therefore not
fail (see `test_jwt_security.py::TestTheJwksTransportIsNotHitPerRequest` for the same seam applied to
fetch counts).

`test_the_harness_detects_a_starved_loop` is permanent, not scaffolding: without it, the case above
is a green assertion nobody has shown can go red.
"""
import asyncio
import io
import json
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.auth.verification import JWTVerifier
from unit.conftest import PUBLIC_KEY_PEM, TEST_ISSUER, TEST_PROJECT_ID, make_token

JWKS_URL = "https://jwks.invalid/keys"
KNOWN_KID = "test-key-1"

# A simulated round trip long enough that a blocked loop is unmistakable and short enough that the
# suite does not pay for it: at 0.4s a 10ms heartbeat has room for ~40 ticks.
FETCH_DELAY = 0.4
HEARTBEAT_INTERVAL = 0.01


def jwks_body(kid: str = KNOWN_KID) -> bytes:
    """A one-key JWKS document the stubbed endpoint serves, under whatever `kid` is asked for.

    `PyJWKSet` rejects an empty `keys` list, so the document has to carry a real key even for cases
    that only ever ask for a `kid` it does not contain. It is the test keypair's public half, which
    is what makes the served `kid` verify for real rather than through a stub -- and what lets a case
    re-serve the endpoint under a different `kid` to model a key rotation.
    """
    key = RSAAlgorithm(RSAAlgorithm.SHA256).prepare_key(PUBLIC_KEY_PEM)
    jwk = json.loads(RSAAlgorithm.to_jwk(key))
    jwk.update(kid=kid, use="sig", alg="RS256")
    return json.dumps({"keys": [jwk]}).encode()


JWKS_BODY = jwks_body()


class CountedJwksTransport:
    """A counted, optionally slow, optionally failing stand-in for PyJWT's one blocking call.

    The signature mirrors `urllib.request.urlopen(r, timeout=..., context=...)` exactly as
    `PyJWKClient.fetch_data` calls it, so every fetch the production path makes is recorded here and
    nowhere else. `timeouts` doubles as the fetch count and as the record of what bound each fetch
    carried -- the two things this gap has to prove.
    """

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
    """Step 4's session. Every case here is refused at step 2 or step 3, so it is never consulted.

    It exists because the barrier reads `session_factory` off application state per request; leaving
    it out would make a wrongly-*accepted* token fail with an attribute error instead of the 403 the
    admission matrix owes it, and that failure would be about the fixture rather than the code.
    """

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
def barrier_app(verifier) -> FastAPI:
    """The real barrier in front of one undeclared route, wired the way the lifespan wires it.

    `/probe` carries no registry declaration, so the barrier applies its strictest disposition and
    treats it as authenticated -- the same premise `test_auth_security.py::barrier_client` rests on.
    """
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/probe")
    async def _probe():
        return {"reached": True}

    app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]
    app.state.jwt_verifier = verifier
    app.state.session_factory = _NoIdentitySession
    app.state.route_registry = ()
    return app


class Heartbeat:
    """A coroutine that records when it got to run, and how often, inside a measured window.

    This is the whole instrument. A tick is proof the loop scheduled something else while the JWKS
    fetch was outstanding; the absence of ticks is proof it did not.
    """

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


async def test_an_unknown_kid_request_does_not_starve_the_event_loop(barrier_app, transport):
    """CR-01, measured: the loop keeps serving while an unrecognized `kid` is being fetched.

    Ten ticks is a deliberate four-fold margin against scheduler noise -- an offloaded fetch of this
    shape yields roughly forty, and a blocking one yields zero -- rather than a threshold tuned to
    just pass.
    """
    token = make_token("u", headers={"kid": "unrecognised-1"})
    transport.fetch_delay = FETCH_DELAY

    async with Heartbeat() as heartbeat:
        status, body, started, finished = await _get_probe(
            barrier_app, {"Authorization": f"Bearer {token}"})

    assert status == 401
    assert body == {"code": "auth_required"}, "the client-visible response is unchanged by the fix"
    assert finished - started >= FETCH_DELAY, "the request really did wait on the stubbed fetch"
    ticks = heartbeat.ticks_between(started, finished)
    assert ticks >= 10, f"the event loop was starved during the JWKS fetch: {ticks} heartbeat ticks"


async def test_the_harness_detects_a_starved_loop(verifier, transport):
    """The permanent control: the same instrument, against a call that is *not* offloaded.

    Without this, the case above is a green assertion nobody has shown can go red -- which is the
    exact defect WR-05 documents in the test this module replaces.
    """
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


async def test_a_duplicate_authorization_never_reaches_the_jwks_transport(barrier_app, transport):
    """FOUND-02 ordering: the §1.1 wire contract still precedes verification under the offload."""
    token = make_token("u", headers={"kid": "unrecognised-2"})
    before = len(transport)

    status, body, _started, _finished = await _get_probe(
        barrier_app,
        [("Authorization", f"Bearer {token}"), ("Authorization", f"Bearer {token}")])

    assert status == 401
    assert body == {"code": "auth_required"}
    assert len(transport) == before, "step 2 refused the request, so step 3 never ran"
