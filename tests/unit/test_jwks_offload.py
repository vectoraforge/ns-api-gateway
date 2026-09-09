"""The measured proof that an unrecognized `kid` never stalls the event loop, through the whole real stack."""
import asyncio
import io
import json
import time
from urllib.error import URLError

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm

from nativespeaker.api.app.dependencies import get_linked_identity
from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.auth.jwt_verifier import BoundedReason, JWTVerifier
from nativespeaker.api.schemas.auth import Identity
from unit.conftest import PUBLIC_KEY_PEM, TEST_ISSUER, TEST_PROJECT_ID, make_token

JWKS_URL = "https://jwks.invalid/keys"
KNOWN_KID = "test-key-1"

# Long enough that a blocked loop is unmistakable, short enough that the suite does not pay for it.
FETCH_DELAY = 0.4
HEARTBEAT_INTERVAL = 0.01

# The share of the ideal tick count an unstarved loop must still deliver. Derived from the window
# each case actually observed rather than pinned as an integer: `asyncio.sleep` drifts on an
# oversubscribed runner, and this is the one wall-clock-dependent measurement in the suite.
UNSTARVED_TICK_FRACTION = 0.1


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

    def unstarved_floor(self, started: float, finished: float) -> float:
        """The fewest ticks the observed window admits before the loop counts as starved."""
        return (finished - started) / HEARTBEAT_INTERVAL * UNSTARVED_TICK_FRACTION


async def _get_probe(app: FastAPI, headers) -> tuple[int, dict, float, float]:
    """Drive one request over the app's own loop and return it bracketed by a measured window."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = time.monotonic()
        response = await client.get("/probe", headers=headers)
        finished = time.monotonic()
    return response.status_code, response.json(), started, finished


@pytest.mark.timing
async def test_an_unknown_kid_request_does_not_starve_the_event_loop(probe_app, transport):
    """The loop keeps serving while an unrecognized `kid` is fetched, at a tenth of the ideal tick rate."""
    token = make_token("u", headers={"kid": "unrecognised-1"})
    transport.fetch_delay = FETCH_DELAY

    async with Heartbeat() as heartbeat:
        status, body, started, finished = await _get_probe(
            probe_app, {"Authorization": f"Bearer {token}"})

    assert status == 401
    assert body == {"code": "auth_required"}, "the client-visible response is unchanged by the fix"
    assert finished - started >= FETCH_DELAY, "the request really did wait on the stubbed fetch"
    ticks = heartbeat.ticks_between(started, finished)
    floor = heartbeat.unstarved_floor(started, finished)
    assert ticks >= floor, (f"the event loop was starved during the JWKS fetch: {ticks} heartbeat "
                            f"ticks against a floor of {floor:.1f} for this window")


@pytest.mark.timing
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
    # Kept absolute: load pushes a starved count down, never up, so this bound cannot go flaky --
    # and it must stay under the case above's floor for the two to partition the outcome.
    assert ticks <= 2, f"the harness cannot register a starved loop: it counted {ticks} ticks"
    assert ticks < heartbeat.unstarved_floor(started, finished), \
        "the starved bound and the unstarved floor overlap, so neither case discriminates"


async def test_a_credential_less_request_never_reaches_the_jwks_transport(probe_app, transport):
    """The wire arm still precedes verification under the offload."""
    before = len(transport)

    status, body, _started, _finished = await _get_probe(probe_app, [])

    assert status == 401
    assert body == {"code": "auth_required"}
    assert len(transport) == before, "step 2 refused the request, so step 3 never ran"


def unusable_jwks_bodies() -> dict[str, bytes]:
    """The three reachable-endpoint failures, each measured against PyJWT rather than assumed."""
    # `PyJWKClientError` for the middle two; the first is a bare `json.JSONDecodeError`, because
    # `fetch_data` converts `URLError` and `TimeoutError` alone. All three are one outage to a fleet.
    key = RSAAlgorithm(RSAAlgorithm.SHA256).prepare_key(PUBLIC_KEY_PEM)
    encryption_only = dict(json.loads(RSAAlgorithm.to_jwk(key)), kid=KNOWN_KID, use="enc", alg="RS256")
    return {"an error page served at 200": b"<html>502 Bad Gateway</html>",
            "a body that is not an object": b'"not an object"',
            "a set holding no signing key": json.dumps({"keys": [encryption_only]}).encode()}


class TestAnOutageNamesItselfInTheOperatorLog:
    """WR-23, WR-22: the reason set is closed at eight, so the outage is named somewhere else."""

    @pytest.fixture
    def errors(self, monkeypatch) -> list[str]:
        """A recording spy on the verifier's own logger, which nothing else in this module uses."""
        events: list[str] = []
        monkeypatch.setattr("nativespeaker.api.auth.jwt_verifier.logger.error",
                            lambda event, **_kw: events.append(event))
        return events

    def test_an_unreachable_endpoint_is_logged_while_the_client_answer_is_unchanged(
            self, verifier, transport, errors):
        transport.error = URLError("the JWKS endpoint is unreachable")

        claims, reason = verifier.verify(make_token("u", headers={"kid": "unrecognised-outage"}))

        # The label and the body must not move: an outage is not a client-visible condition.
        assert claims is None and reason is BoundedReason.bad_signature
        assert errors == ["jwks_endpoint_unusable"]

    @pytest.mark.parametrize("body", unusable_jwks_bodies().values(),
                             ids=list(unusable_jwks_bodies()))
    def test_a_reachable_endpoint_serving_an_unusable_key_set_is_logged_too(
            self, verifier, transport, errors, body):
        """WR-22: gated on the connection subclass alone, these three rejected the whole fleet as
        `bad_signature` with no line naming the cause -- the storm the log above exists to name."""
        transport.body = body

        claims, reason = verifier.verify(make_token("u", headers={"kid": "unrecognised-outage"}))

        assert claims is None and reason is BoundedReason.bad_signature
        assert errors == ["jwks_endpoint_unusable"]

    def test_a_bogus_key_id_over_a_healthy_endpoint_logs_nothing(self, verifier, transport, errors):
        """The control: without it the case above would pass on a line written for every refusal."""
        claims, reason = verifier.verify(make_token("u", headers={"kid": "unrecognised-but-served"}))

        assert claims is None and reason is BoundedReason.bad_signature
        assert errors == []
        assert len(transport) > 1, "the miss really did reach for the keys"
