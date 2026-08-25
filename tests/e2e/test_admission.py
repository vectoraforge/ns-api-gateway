"""FOUND-01 / §1.3: the four-outcome admission matrix, against real rows over a real transport.

`tests/unit/test_identity_resolution.py` proves the branches PostgreSQL cannot produce. This module
proves the ones it can, end to end: a seeded `core.users` + `core.external_identities` pair, a token
the auth dependency really verifies, one identity query against the live database, and the response
a client actually receives.

**37.1 D-06 changed the mechanism under all of this and none of the expectations.** Every case here
passed unmodified when admission moved from a middleware to a router-level dependency -- not one
status code and not one body -- which is the point: the matrix is a client contract, and a contract
that needed editing to survive a refactor was never the contract.

Four distinct subjects are exercisable without four Firebase accounts because `stub_verifier` swaps
`app.state.jwt_verifier` for the ephemeral-RSA verifier already living in `tests/unit/conftest.py`.
That verifier differs from the production one in exactly one respect -- where the signing key comes
from -- so the algorithm pin, the `require` list and the non-empty-`sub` rule under test here are
the production ones. The real `firebase_token` fixture stays for the modules that want a genuine
credential.

**No timing assertion appears here, deliberately.** D-13 scopes anti-oracle enforcement to
structural identity -- the same single query reached through the same code path -- and explicitly
rejects timing normalization for this product. A latency-parity assertion would be testing a
property the service does not have and does not claim.
"""
from contextlib import contextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from unit.conftest import TEST_ISSUER, make_token

from nativespeaker.api.models.identities import IdentityProvider, IdentityState

from .conftest import create_chat, seed_identity

pytestmark = pytest.mark.e2e


@pytest_asyncio.fixture(loop_scope="module")
async def admission_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}


@pytest.mark.asyncio(loop_scope="module")
class TestOutcomeFourLinkedAndActive:
    """The only admitting outcome, and the only one that reaches a handler."""

    async def test_a_linked_active_identity_is_admitted(self, admission_client, _db_transaction):
        subject = "admitted-subject"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject)

        response = await admission_client.get("/chats", headers=_auth(subject))

        assert response.status_code == 200

    async def test_the_handler_sees_the_resolved_user(self, admission_client, _db_transaction):
        """The strongest form of "the handler sees the context".

        `list_chats` reads `identity.user.id` off the §1.4 context and nothing else, so a chat
        owned by the seeded user comes back only if the id the handler used is the one admission
        resolved from `core.external_identities`.
        """
        subject = "owner-subject"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject)
        await create_chat(_db_transaction, TEST_ISSUER, subject)

        response = await admission_client.get("/chats", headers=_auth(subject))

        assert response.status_code == 200
        assert [chat["title"] for chat in response.json()] == ["test phrase"]

    async def test_another_subject_sees_none_of_it(self, admission_client, _db_transaction):
        """Ownership follows the resolved user, never the token subject."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="owner-2")
        await create_chat(_db_transaction, TEST_ISSUER, "owner-2")
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="stranger-2")

        response = await admission_client.get("/chats", headers=_auth("stranger-2"))

        assert response.status_code == 200
        assert response.json() == []

    async def test_an_anonymous_provider_is_admitted_too(self, admission_client, _db_transaction):
        """`provider` classifies; it does not gate admission. §1.3 tests two columns, not three."""
        subject = "anonymous-subject"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                            provider=IdentityProvider.anonymous)

        response = await admission_client.get("/chats", headers=_auth(subject))

        assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="module")
class TestOutcomeOnePrimeUnlinked:
    """§1.3 outcome 1' -- a verified subject with no identity row, on a route that cannot take one."""

    async def test_an_unlinked_subject_is_refused(self, admission_client):
        response = await admission_client.get("/chats", headers=_auth("never-linked"))
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}

    @pytest.mark.parametrize("path", ["/", "/examples?lang=en", "/chats"])
    async def test_no_authenticated_route_is_pre_auth_callable(self, admission_client, path):
        """Only the two `create-user` phases may ever be, and neither exists yet."""
        response = await admission_client.get(path, headers=_auth("never-linked"))
        assert response.status_code == 403
        assert response.json() == {"code": "preauth_identity_not_allowed"}


@pytest.mark.asyncio(loop_scope="module")
class TestOutcomesTwoAndThreeAreIndistinguishable:
    """§1.3 outcomes 2 and 3 -- one class, one status, one body, one copy (T-35-06-03)."""

    async def test_a_historical_identity_is_refused(self, admission_client, _db_transaction):
        subject = "historical-subject"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                            identity_state=IdentityState.historical)

        response = await admission_client.get("/chats", headers=_auth(subject))

        assert response.status_code == 403
        assert response.json() == {"code": "account_unavailable"}

    async def test_a_blocked_user_is_refused(self, admission_client, _db_transaction):
        subject = "blocked-subject"
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject,
                            user_active=False)

        response = await admission_client.get("/chats", headers=_auth(subject))

        assert response.status_code == 403
        assert response.json() == {"code": "account_unavailable"}

    async def test_the_two_responses_are_identical_in_status_body_and_headers(
            self, admission_client, _db_transaction):
        """The anti-oracle guarantee as a client can observe it.

        `Date` is excluded because it is the clock, not the response; nothing else may differ.
        """
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="historical-pair",
                            identity_state=IdentityState.historical)
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="blocked-pair",
                            user_active=False)

        historical = await admission_client.get("/chats", headers=_auth("historical-pair"))
        blocked = await admission_client.get("/chats", headers=_auth("blocked-pair"))

        assert historical.status_code == blocked.status_code
        assert historical.content == blocked.content
        assert _comparable(historical.headers) == _comparable(blocked.headers)

    async def test_neither_is_distinguishable_from_the_other_by_a_retired_pre_auth_answer(
            self, admission_client, _db_transaction):
        """T-35-06-02: a retired identity never surfaces the unlinked class."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="retired-not-fresh",
                            identity_state=IdentityState.historical)

        response = await admission_client.get("/chats", headers=_auth("retired-not-fresh"))

        assert response.json() != {"code": "preauth_identity_not_allowed"}


@pytest.mark.asyncio(loop_scope="module")
class TestAdmissionPhasePrecedesAuth:
    """§4.1: route/method mismatch is decided before admission has anything to say.

    More visibly so under D-07 than before: a route's auth dependency is declared *on that route*,
    so a request matching no route -- or matching its path but not its method -- never reaches one.
    """

    async def test_a_wrong_method_returns_405_not_401(self, admission_client):
        """`POST /` matches the path but not the method, so the router owns the answer."""
        response = await admission_client.post("/")
        assert response.status_code == 405
        assert response.json() == {"code": "method_not_allowed"}

    async def test_the_405_holds_even_with_a_valid_credential(self, admission_client,
                                                              _db_transaction):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="wrong-method")
        response = await admission_client.post("/", headers=_auth("wrong-method"))
        assert response.status_code == 405

    async def test_an_unknown_path_returns_404_not_401(self, admission_client):
        response = await admission_client.get("/no-such-path")
        assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="module")
class TestVerificationPrecedesResolution:
    """§1.5 step 3 runs before step 4, so a bad token never reaches the database."""

    async def test_an_unverifiable_token_is_auth_required_not_preauth(self, admission_client):
        response = await admission_client.get("/chats",
                                            headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_a_wrong_issuer_is_auth_required(self, admission_client, _db_transaction):
        """§1.2: issuer mismatch rejects before any identity work, even for a seeded subject."""
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="wrong-issuer-subject")
        token = make_token(sub="wrong-issuer-subject", iss="https://securetoken.google.com/other")

        response = await admission_client.get("/chats",
                                            headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}

    async def test_an_expired_token_is_auth_required(self, admission_client, _db_transaction):
        await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject="expired-subject")
        token = make_token(sub="expired-subject", exp=1_000_000, iat=999_000)

        response = await admission_client.get("/chats",
                                            headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        assert response.json() == {"code": "auth_required"}


@pytest.mark.asyncio(loop_scope="module")
class TestOneQueryPerRequest:
    """D-13's structural anti-oracle guarantee, observed at runtime rather than read off the source.

    Every outcome leaves resolution through the *same* single statement. That is what makes the two
    `account_unavailable` branches indistinguishable in work done as well as in response: neither
    issues a query, a lookup, or a network call the other skips. Counting real cursor executions is
    the only form of this claim that a later refactor cannot quietly break.
    """

    @pytest.mark.parametrize("subject,seed", [
        ("q-linked", {}),
        ("q-historical", {"identity_state": IdentityState.historical}),
        ("q-blocked", {"user_active": False}),
        ("q-unlinked", None),
    ])
    async def test_every_outcome_issues_exactly_one_identity_statement(
            self, admission_client, _db_transaction, subject, seed):
        if seed is not None:
            await seed_identity(_db_transaction, issuer=TEST_ISSUER, subject=subject, **seed)

        with _recording(_db_transaction) as statements:
            await admission_client.get("/chats", headers=_auth(subject))

        assert len([s for s in statements if "external_identities" in s]) == 1

    async def test_a_wire_contract_rejection_touches_the_database_not_at_all(
            self, admission_client, _db_transaction):
        """§1.5 orders the wire contract ahead of resolution, so step 2 costs no query."""
        with _recording(_db_transaction) as statements:
            await admission_client.get("/chats")

        assert [s for s in statements if "external_identities" in s] == []


@contextmanager
def _recording(factory):
    """Collect every statement the test connection executes for the duration of the block."""
    engine = factory.kw["bind"].sync_engine
    statements: list[str] = []

    def _capture(_conn, _cursor, statement, *_args, **_kwargs):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _capture)


def _comparable(headers) -> dict[str, str]:
    """Response headers minus the clock."""
    return {key: value for key, value in headers.items() if key.lower() != "date"}
