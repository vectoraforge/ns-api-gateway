"""FOUND-05: the audited attempt path, against a real PostgreSQL and a real ASGI transport.

`§8.2` puts every route foundation registers **off** the audited path -- all eight declare
`operation = None` -- so no production request in Phase 35 writes a row. That is the design, not a
gap, and it is why this module builds a test-local app declaring one route that *does* carry an
operation. Phases 37-45 supply the real call sites; what is proven here is the machinery they will
call.

The row is read back through the swapped `test_factory`, never through a fresh engine: the
standalone-durable `commit()` under `join_transaction_mode="create_savepoint"` releases a savepoint
rather than the outer transaction, so the row is visible to a session on the same connection and
still rolls back at the end of the test. `TestTheRollbackStillIsolatesIt` asserts both halves of
that sentence rather than trusting it.

Row counts here are asserted as **exactly** one or **exactly** zero. "At least one" would pass for
a writer that wrote two rows per attempt, and `§4.1` says exactly one row per on-path attempt.
"""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from unit.conftest import TEST_ISSUER, make_token

from e2e.conftest import seed_identity
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.auth.registry import Category, RouteMetadata
from nativespeaker.api.auth.telemetry import RejectionCounter
from nativespeaker.api.models.auth import AuthEvent, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import IdentityState

pytestmark = pytest.mark.e2e

DETAILS_TOP_LEVEL = ["context", "failure", "mutation", "resolved", "schema_version", "verification"]

# The two routes in this module that carry an operation, and are therefore on the audited path.
AUDITED_ROUTE = RouteMetadata(method="POST", path="/auth/sync", category=Category.authenticated,
                              operation=AuthOperation.sync)
# Carries a path parameter on purpose. Without one, a row labelled with `scope["path"]` and a row
# labelled with the registry template are byte-identical, and the difference between them is a
# caller-influenced value landing in a durable audit row.
PARAMETERIZED_ROUTE = RouteMetadata(method="POST", path="/auth/claim/{grant_id}",
                                    category=Category.authenticated,
                                    operation=AuthOperation.claim_registered_grant)
GRANT_ID = "0198f0d2-dead-7000-8000-00000000beef"


@pytest.fixture
def audited_app(_app_lifespan, _db_transaction, stub_verifier):
    """A test-local app whose routes declare an operation, unlike every production one.

    Every route the real application registers declares `operation = None`, so the audited-path
    branch is unreachable from a production route this phase. The barrier reads its registry from
    `scope["app"].state.route_registry` per request, which is the seam that lets this app declare
    one that carries an operation without touching the production table.

    `session_factory` is the *swapped* factory rather than a copy taken from the lifespan app, so
    everything this app writes lands inside the per-test transaction. The verifier is the swapped
    stub, which is what makes four distinct subjects testable without four Firebase accounts. The
    counter is a fresh one per test: the lifespan's is shared and accumulating, and these cases
    assert exact counts.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/auth/sync")
    async def _sync():
        return {"reached": True}

    @app.post("/auth/claim/{grant_id}")
    async def _claim(grant_id: str):
        return {"reached": grant_id}

    app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]
    app.state.route_registry = (AUDITED_ROUTE, PARAMETERIZED_ROUTE)
    app.state.session_factory = _db_transaction
    app.state.jwt_verifier = stub_verifier
    app.state.hmac_keyring = _app_lifespan.state.hmac_keyring
    app.state.audit_writer = _app_lifespan.state.audit_writer
    app.state.rejection_counter = RejectionCounter()
    return app


@pytest.fixture
def audited_client(audited_app):
    return AsyncClient(transport=ASGITransport(app=audited_app), base_url="http://test")


@pytest.fixture
def unauthenticated_client(_app_lifespan):
    """A client over the real, started app -- every route of which is off the audited path."""
    return AsyncClient(transport=ASGITransport(app=_app_lifespan), base_url="http://test")


async def rows(factory) -> list[AuthEvent]:
    async with factory() as session:
        return list((await session.exec(select(AuthEvent))).all())


async def row_count(factory) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(AuthEvent))


@pytest.mark.asyncio(loop_scope="module")
class TestAnOnPathRejectionWritesExactlyOneRow:
    """§4.1: one row per on-path attempt, for its terminal outcome, before the response returns."""

    async def test_a_missing_token_writes_one_row_and_returns_the_shared_401(
            self, audited_client, _db_transaction):
        async with audited_client as client:
            response = await client.post("/auth/sync")

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}
        assert await row_count(_db_transaction) == 1

    async def test_that_row_carries_no_actor_at_all(self, audited_client, _db_transaction):
        """The all-or-nothing CHECK: `invalid_external_jwt` is the one result that may, and must,
        carry NULL in every actor column -- `actor_provider` included."""
        async with audited_client as client:
            await client.post("/auth/sync")

        row = (await rows(_db_transaction))[0]
        assert row.result is AuthEventResult.invalid_external_jwt
        assert row.actor_issuer is None
        assert row.actor_subject_hash is None
        assert row.actor_subject_hash_key_version is None
        assert row.actor_provider is None

    async def test_that_row_names_the_operation_the_route_declared(
            self, audited_client, _db_transaction):
        """Entry to the audited path depends only on the matched route+method carrying an
        operation -- never on how far the handler ran or which step refused."""
        async with audited_client as client:
            await client.post("/auth/sync")

        assert (await rows(_db_transaction))[0].operation is AuthOperation.sync

    async def test_the_bounded_reason_is_in_details_failure(self, audited_client, _db_transaction):
        async with audited_client as client:
            await client.post("/auth/sync")

        details = (await rows(_db_transaction))[0].details
        assert details["failure"]["reason"] == "missing_token"
        assert details["failure"]["stage"] == "barrier"

    async def test_the_bounded_reason_is_absent_from_the_response(self, audited_client):
        """§1.1: the reason is telemetry. The client is told `auth_required` and nothing else --
        which is the whole anti-oracle guarantee, since every wire-contract failure says this."""
        async with audited_client as client:
            response = await client.post("/auth/sync")

        assert "missing_token" not in response.text
        assert set(response.json()) == {"code"}

    async def test_details_round_trips_as_exactly_the_six_keys(
            self, audited_client, _db_transaction):
        async with audited_client as client:
            await client.post("/auth/sync")

        details = (await rows(_db_transaction))[0].details
        assert sorted(details) == DETAILS_TOP_LEVEL
        assert details["schema_version"] == 1

    async def test_context_carries_the_route_template_and_the_bucket_kind_not_the_address(
            self, audited_client, _db_transaction):
        """The prohibition, as it lands in a real row: the bucket kind is recorded and the address
        is not, so `audit.auth_events` cannot become a behavioural-tracking archive."""
        async with audited_client as client:
            await client.post("/auth/sync")

        context = (await rows(_db_transaction))[0].details["context"]
        assert context["route"] == "/auth/sync"
        assert context["method"] == "POST"
        assert context["operation"] == "sync"
        assert context["client_ip_bucket_kind"] in {"ipv4", "ipv6", "unresolved"}
        assert "attempt_id" in context
        assert not any("addr" in key or key == "client_ip" for key in context)

    async def test_the_route_recorded_is_the_template_never_the_request_path(
            self, audited_client, _db_transaction):
        """The same bounded-cardinality rule the counter label follows, and here it is durable: a
        request path carries caller-influenced ids, and `audit.auth_events` keeps them for good."""
        async with audited_client as client:
            response = await client.post(f"/auth/claim/{GRANT_ID}")

        assert response.status_code == 401
        written = await rows(_db_transaction)
        assert len(written) == 1
        assert written[0].details["context"]["route"] == "/auth/claim/{grant_id}"
        assert written[0].operation is AuthOperation.claim_registered_grant

    async def test_the_path_parameter_appears_nowhere_in_the_row(
            self, audited_client, _db_transaction):
        async with audited_client as client:
            await client.post(f"/auth/claim/{GRANT_ID}")

        row = (await rows(_db_transaction))[0]
        assert GRANT_ID not in str(row.details)
        assert GRANT_ID not in str(row.actor_issuer)

    @pytest.mark.parametrize("subobject", ("context", "verification", "resolved", "mutation"))
    async def test_the_bounded_reason_is_recorded_under_failure_and_nowhere_else(
            self, audited_client, _db_transaction, subobject):
        """One home in the stored row, not just in the object the builder returned. A duplicate
        under `context` is where a later phase would read it from and then widen it."""
        async with audited_client as client:
            await client.post("/auth/sync")

        details = (await rows(_db_transaction))[0].details
        assert details["failure"]["reason"] == "missing_token"
        assert "missing_token" not in str(details[subobject])

    async def test_a_malformed_credential_also_writes_exactly_one_row(
            self, audited_client, _db_transaction):
        """A different §1.1 failure, a different bounded reason, still one row."""
        async with audited_client as client:
            response = await client.post("/auth/sync", headers={"Authorization": "Bearer"})

        assert response.status_code == 401
        written = await rows(_db_transaction)
        assert len(written) == 1
        assert written[0].details["failure"]["reason"] == "malformed"

    async def test_a_duplicate_authorization_field_writes_its_own_bounded_reason(
            self, audited_client, _db_transaction):
        async with audited_client as client:
            response = await client.post(
                "/auth/sync",
                headers=[("Authorization", "Bearer a.b.c"), ("Authorization", "Bearer d.e.f")])

        assert response.status_code == 401
        written = await rows(_db_transaction)
        assert len(written) == 1
        assert written[0].details["failure"]["reason"] == "duplicate_authorization"


@pytest.mark.asyncio(loop_scope="module")
class TestAVerifiedActorIsRecordedAsAKeyedHash:
    """RESEARCH Pitfall 10: every result but `invalid_external_jwt` requires all three actor
    fields, and by then the token has been verified so issuer and subject are known."""

    async def test_an_unlinked_subject_writes_all_three_actor_fields(
            self, audited_client, _db_transaction, _app_lifespan):
        async with audited_client as client:
            response = await client.post(
                "/auth/sync",
                headers={"Authorization": f"Bearer {make_token('unlinked-subject')}"})

        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

        written = await rows(_db_transaction)
        assert len(written) == 1
        row = written[0]
        assert row.result is AuthEventResult.preauth_identity_not_allowed
        assert row.actor_issuer == TEST_ISSUER
        assert len(row.actor_subject_hash) == 32
        assert row.actor_subject_hash_key_version == \
               _app_lifespan.state.hmac_keyring.active_version

    async def test_the_stored_hash_is_the_shared_keyrings_derivation(
            self, audited_client, _db_transaction, _app_lifespan):
        """D-21: one derivation, shared with the challenge store. A second one would drift
        silently -- both produce a plausible 32-byte digest and only one matches the stored rows."""
        async with audited_client as client:
            await client.post("/auth/sync",
                              headers={"Authorization": f"Bearer {make_token('shared-derivation')}"})

        keyring = _app_lifespan.state.hmac_keyring
        row = (await rows(_db_transaction))[0]
        assert row.actor_subject_hash == keyring.actor_subject_hash(TEST_ISSUER,
                                                                   "shared-derivation")
        assert keyring.actor_subject_matches(row.actor_subject_hash, TEST_ISSUER,
                                             "shared-derivation")

    async def test_the_raw_subject_is_nowhere_in_the_row(self, audited_client, _db_transaction):
        """§4.3: the raw subject is never stored. `core.external_identities` is the single
        deliberate plaintext exception, and this is not that table."""
        async with audited_client as client:
            await client.post("/auth/sync",
                              headers={"Authorization": f"Bearer {make_token('raw-subject-probe')}"})

        row = (await rows(_db_transaction))[0]
        assert "raw-subject-probe" not in str(row.details)
        assert "raw-subject-probe" not in str(row.actor_issuer)

    async def test_actor_provider_stays_null_when_no_identity_row_resolved(
            self, audited_client, _db_transaction):
        """§4.2: `actor_provider` comes only from the stored `core.external_identities.provider`
        column, and is NULL for pre-auth and unresolved events. It is never fabricated."""
        async with audited_client as client:
            await client.post("/auth/sync",
                              headers={"Authorization": f"Bearer {make_token('no-provider')}"})

        assert (await rows(_db_transaction))[0].actor_provider is None

    async def test_a_historical_identity_writes_an_actor_bearing_row(
            self, audited_client, _db_transaction):
        """A rejection from the admission matrix, three steps later than the wire contract, and
        still exactly one row -- entry never depended on which step refused."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="retired-subject",
                            identity_state=IdentityState.historical)
        async with audited_client as client:
            response = await client.post(
                "/auth/sync",
                headers={"Authorization": f"Bearer {make_token('retired-subject')}"})

        assert response.status_code == 403
        assert response.json() == {"code": "account_unavailable"}
        written = await rows(_db_transaction)
        assert len(written) == 1
        assert written[0].result is AuthEventResult.historical_identity
        assert written[0].actor_issuer == TEST_ISSUER
        assert written[0].actor_subject_hash is not None

    async def test_a_blocked_user_writes_an_actor_bearing_row(
            self, audited_client, _db_transaction):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="blocked-subject",
                            user_active=False)
        async with audited_client as client:
            response = await client.post(
                "/auth/sync",
                headers={"Authorization": f"Bearer {make_token('blocked-subject')}"})

        assert response.status_code == 403
        written = await rows(_db_transaction)
        assert len(written) == 1
        assert written[0].result is AuthEventResult.blocked_user


@pytest.mark.asyncio(loop_scope="module")
class TestOffPathRequestsWriteNothing:
    """§8.2: chat routes, `GET /`, and `GET /examples` are not in the state-changing operation
    inventory. A rejection there writes no row, ever -- only the log line and the counter."""

    # All seven of the eight pre-existing routes that answer 401 unauthenticated. The eighth,
    # `GET /health/ready`, is public and answers 200, so it has no rejection to write a row for --
    # `test_an_admitted_off_path_request_writes_zero_rows` below is what covers a served outcome.
    # `POST /chats/{chat_id}` joined the list with its quota gate in plan 36-05: it is one of the
    # two quota-checked routes, and leaving it out left a quarter of the phase's claim unproven.
    @pytest.mark.parametrize("method,path", [("GET", "/"), ("GET", "/examples"),
                                             ("GET", "/chats"), ("POST", "/chats"),
                                             ("GET", "/chats/0198f0d2-0000-7000-8000-00000000000a"),
                                             ("POST",
                                              "/chats/0198f0d2-0000-7000-8000-00000000000a"),
                                             ("DELETE",
                                              "/chats/0198f0d2-0000-7000-8000-00000000000a")])
    async def test_an_unauthenticated_request_to_a_foundation_route_writes_zero_rows(
            self, unauthenticated_client, _db_transaction, method, path):
        async with unauthenticated_client as client:
            response = await client.request(method, path)

        assert response.status_code == 401
        assert await row_count(_db_transaction) == 0

    async def test_an_admitted_off_path_request_writes_zero_rows(
            self, unauthenticated_client, _db_transaction, stub_verifier):
        """Not just rejections: an off-path route writes nothing at any outcome."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="served-subject")
        async with unauthenticated_client as client:
            response = await client.get(
                "/", headers={"Authorization": f"Bearer {make_token('served-subject')}"})

        assert response.status_code == 200
        assert await row_count(_db_transaction) == 0

    async def test_a_wrong_method_request_writes_zero_rows(self, audited_client, _db_transaction):
        """Route/method mismatch is admission-phase (§4.1): the router keeps its own 405 and the
        barrier never runs, so there is no attempt to audit."""
        async with audited_client as client:
            response = await client.get("/auth/sync")

        assert response.status_code == 405
        assert await row_count(_db_transaction) == 0

    async def test_an_unknown_path_writes_zero_rows(self, audited_client, _db_transaction):
        async with audited_client as client:
            response = await client.post("/no-such-route")

        assert response.status_code == 404
        assert await row_count(_db_transaction) == 0


@pytest.mark.asyncio(loop_scope="module")
class TestTelemetryFiresEitherWay:
    """§1.2 / §8.2: the counter is the required alerting source for cross-route attack volume, so
    it increments wherever the barrier rejects -- on the audited path and off it alike."""

    async def test_an_on_path_rejection_increments_the_counter(self, audited_app, audited_client):
        async with audited_client as client:
            await client.post("/auth/sync")

        assert audited_app.state.rejection_counter.snapshot() == \
               {("invalid_external_jwt", "missing_token", "/auth/sync"): 1}

    async def test_an_off_path_rejection_increments_the_counter_too(
            self, unauthenticated_client, _app_lifespan):
        counter = _app_lifespan.state.rejection_counter
        before = counter.snapshot().get(("invalid_external_jwt", "missing_token", "/chats"), 0)
        async with unauthenticated_client as client:
            await client.get("/chats")

        after = counter.snapshot()[("invalid_external_jwt", "missing_token", "/chats")]
        assert after == before + 1

    async def test_the_route_label_is_the_template_never_the_request_path(
            self, unauthenticated_client, _app_lifespan):
        """Bounded cardinality: a thousand chat ids collapse to one counter key."""
        counter = _app_lifespan.state.rejection_counter
        async with unauthenticated_client as client:
            await client.get("/chats/0198f0d2-0000-7000-8000-00000000000b")

        labels = {route for _result, _reason, route in counter.snapshot()}
        assert "/chats/{chat_id}" in labels
        assert not any(label.startswith("/chats/0198") for label in labels)


@pytest.mark.asyncio(loop_scope="module")
class TestAFailedAuditWriteNeverChangesTheOutcome:
    """T-35-09-07. Auditing is never best-effort, but a write failure never turns a business
    rejection into a 500 either."""

    async def test_the_client_still_receives_the_outcome_the_attempt_earned(self, audited_app):
        def exploding_factory():
            raise RuntimeError("pool exhausted")

        audited_app.state.session_factory = exploding_factory
        transport = ASGITransport(app=audited_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/auth/sync")

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_a_missing_audit_writer_does_not_change_the_outcome_either(self, audited_app):
        """An application that forgot to construct the writer must still refuse the request, not
        answer a 500 -- a 500 where a 401 belongs tells a caller something a 401 does not."""
        del audited_app.state.audit_writer
        transport = ASGITransport(app=audited_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/auth/sync")

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}


@pytest.mark.asyncio(loop_scope="module")
class TestTheRollbackStillIsolatesIt:
    """The harness property the whole e2e strategy rests on, asserted rather than assumed."""

    async def test_the_row_is_visible_to_the_test_transaction_and_invisible_outside_it(
            self, audited_client, _db_transaction, _app_config):
        """The standalone-durable `commit()` releases a savepoint, not the outer transaction. So
        the row is readable here and unreadable from any other connection -- which is exactly why
        assertions must read through the swapped factory and never through a fresh engine."""
        async with audited_client as client:
            await client.post("/auth/sync")

        assert await row_count(_db_transaction) == 1

        outside = create_async_engine(_app_config.db.url)
        try:
            async with outside.connect() as connection:
                visible = await connection.scalar(select(func.count()).select_from(AuthEvent))
        finally:
            await outside.dispose()
        assert visible == 0
