"""Challenge-store logic, run against a stub session."""

import base64
import string
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.crud.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengesDB,
    new_challenge_id,
)
from nativespeaker.api.errors import ChallengeConsumed, ChallengeIdentityMismatch
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.tables.users import User

ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "Xy7Q1s0K2mNb3fV4"

# Deliberately far in the past: a store reading its own wall clock fails by years, not microseconds.
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

# The four challenge-bearing operations; a per-operation TTL override is forbidden in either direction.
CHALLENGE_BEARING = (
    AuthOperation.create_user,
    AuthOperation.upgrade_anonymous_to_registered,
    AuthOperation.claim_anonymous_grant,
    AuthOperation.claim_registered_grant,
)


def store() -> ChallengesDB:
    return ChallengesDB()


class _StubResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _RecordingSession:
    """Enough of an `AsyncSession` for `issue` and `locate`: it records, it never connects."""

    def __init__(self, rows=()):
        self.added: list = []
        self.flushes = 0
        self.commits = 0
        self.statements: list = []
        self._rows = list(rows)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def exec(self, statement):
        self.statements.append(statement)
        return _StubResult(self._rows)


def linked_identity(subject: str = SUBJECT, *, issuer: str = ISSUER,
                    identity_id: UUID | None = None) -> Identity:
    user = User()
    identity = ExternalIdentity(id=identity_id if identity_id is not None else uuid7(),
                                user_id=user.id,
                                issuer=issuer,
                                subject=subject,
                                provider=IdentityProvider.google,
                                provider_uid=f"google-uid-{subject}")
    return Identity(user=user, identity=identity, issuer=issuer, subject=subject)


def preauth_identity(subject: str = SUBJECT, *, issuer: str = ISSUER) -> Identity:
    return Identity(issuer=issuer, subject=subject)


async def issue_row(identity, *,
                    operation: AuthOperation = AuthOperation.create_user,
                    now: datetime = FIXED_NOW):
    """Run `issue` against a stub session and return `(handle, expires_at, row, session)`."""
    session = _RecordingSession()
    subject_store = store()
    handle, expires_at = await subject_store.issue(session,
                                                   operation=operation,
                                                   identity=identity,
                                                   now=now)
    assert len(session.added) == 1, "issue writes exactly one row"
    return handle, expires_at, session.added[0], session


class TestTheOpaqueHandle:
    """16 bytes from a CSPRNG, base64url-encoded without padding."""

    def test_the_handle_is_22_characters(self):
        assert len(new_challenge_id()) == 22

    def test_the_handle_carries_no_padding(self):
        assert "=" not in new_challenge_id()

    def test_the_alphabet_across_a_thousand_handles_is_exactly_base64url(self):
        """Set equality over ~22,000 characters: `uuid4().hex[:22]` satisfies every other assertion in this class."""
        observed = set("".join(new_challenge_id() for _ in range(1000)))
        assert observed == set(string.ascii_letters + string.digits + "-_")

    def test_a_thousand_handles_are_all_distinct(self):
        assert len({new_challenge_id() for _ in range(1000)}) == 1000

    def test_the_handle_decodes_back_to_exactly_16_bytes(self):
        """The length assertion alone passes for a 22-character slice of anything; this pins whole bytes of entropy."""
        raw = base64.urlsafe_b64decode(new_challenge_id() + "==")
        assert len(raw) == CHALLENGE_ID_BYTES == 16


class TestTheUniversalTTL:
    """300 seconds from the server's own clock, for every operation, with no override."""

    def test_the_constants_are_pinned(self):
        assert CHALLENGE_TTL_SECONDS == 300
        assert CHALLENGE_ID_BYTES == 16

    async def test_expires_at_is_exactly_300_seconds_after_the_supplied_now(self):
        _, expires_at, row, _ = await issue_row(preauth_identity())
        assert expires_at == FIXED_NOW + timedelta(seconds=300)
        assert row.expires_at == expires_at

    async def test_the_clock_is_the_supplied_one_and_not_the_wall_clock(self):
        """`FIXED_NOW` is years away, so a store reading its own clock fails by years, not by microseconds."""
        _, expires_at, _, _ = await issue_row(preauth_identity())
        assert abs((expires_at - datetime.now(UTC)).days) > 30

    async def test_created_at_is_the_same_captured_evaluation_time(self):
        """SHARED-INVARIANTS: every time-dependent value derives from ONE captured time."""
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.created_at == FIXED_NOW

    @pytest.mark.parametrize("operation", CHALLENGE_BEARING)
    async def test_every_operation_gets_the_identical_ttl(self, operation):
        """A per-operation override is forbidden in either direction."""
        _, expires_at, _, _ = await issue_row(preauth_identity(), operation=operation)
        assert expires_at - FIXED_NOW == timedelta(seconds=CHALLENGE_TTL_SECONDS)

    async def test_the_row_records_the_operation_it_was_issued_for(self):
        _, _, row, _ = await issue_row(preauth_identity(),
                                       operation=AuthOperation.claim_anonymous_grant)
        assert row.operation is AuthOperation.claim_anonymous_grant

    async def test_issue_discloses_exactly_the_handle_and_expires_at(self):
        """Exactly `challenge_id` and `expires_at`: a three-element return would hand a caller the row id to leak."""
        session = _RecordingSession()
        returned = await store().issue(session, operation=AuthOperation.create_user,
                                       identity=preauth_identity(), now=FIXED_NOW)
        assert isinstance(returned, tuple)
        assert len(returned) == 2
        handle, expires_at = returned
        assert handle == session.added[0].challenge_id
        assert isinstance(expires_at, datetime)

    async def test_issue_does_not_commit_the_callers_transaction(self):
        """The store is transaction-neutral: committing here would commit a prepare whose handler later failed."""
        _, _, _, session = await issue_row(preauth_identity())
        assert session.commits == 0
        assert session.flushes == 1


class TestTheBindingWrittenAtIssuance:
    """A row binds exactly one of linked or pre-auth, never both and never neither."""

    async def test_a_linked_identity_binds_the_identity_row(self):
        identity = linked_identity()
        _, _, row, _ = await issue_row(identity)
        assert row.bound_external_identity_id == identity.identity.id

    async def test_a_linked_identity_leaves_both_preauth_columns_null(self):
        """The table's CHECK requires exactly one arm; asserting it here is what makes the failure readable."""
        _, _, row, _ = await issue_row(linked_identity())
        assert row.preauth_issuer is None
        assert row.preauth_subject is None

    async def test_a_preauth_identity_leaves_the_linked_column_null(self):
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.bound_external_identity_id is None

    async def test_the_preauth_issuer_is_stored_in_plaintext(self):
        """A deployment-known provider string shared by every user of that provider, so it is not hashed."""
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.preauth_issuer == ISSUER

    async def test_the_preauth_subject_is_stored_in_plaintext(self):
        """The value the completion comparison reads back, written as given rather than derived."""
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.preauth_subject == SUBJECT


class TestTheCompletionComparison:
    """The binding verification and its rejection ordering."""

    def test_a_linked_row_matches_its_own_identity(self):
        identity = linked_identity()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.claim_registered_grant,
                            bound_external_identity_id=identity.identity.id,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store().verify_binding(row, identity) is row

    def test_a_linked_row_rejects_a_different_identity_row(self):
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.claim_registered_grant,
                            bound_external_identity_id=uuid7(),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeIdentityMismatch):
            store().verify_binding(row, linked_identity())

    def test_a_linked_row_rejects_a_preauth_request(self):
        """A pre-auth request resolved to no identity row, so it must not be waved through for lack of a comparison."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.claim_registered_grant,
                            bound_external_identity_id=uuid7(),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeIdentityMismatch):
            store().verify_binding(row, preauth_identity())

    def test_a_preauth_row_matches_the_subject_it_was_issued_for(self):
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject=SUBJECT,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store().verify_binding(row, preauth_identity()) is row

    def test_a_preauth_row_rejects_a_different_subject(self):
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject=SUBJECT,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeIdentityMismatch):
            store().verify_binding(row, preauth_identity("someone-else"))

    def test_a_preauth_row_rejects_a_different_issuer(self):
        """A subject is unique only within its issuer, so it alone would admit another provider's subject."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer="https://securetoken.google.com/other-project",
                            preauth_subject=SUBJECT,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeIdentityMismatch):
            store().verify_binding(row, preauth_identity())

    def test_a_preauth_row_still_matches_a_subject_that_has_since_become_linked(self):
        """What fails a pre-auth binding is a differing subject, not the subject having since become linked."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject=SUBJECT,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store().verify_binding(row, linked_identity(SUBJECT)) is row

    def test_a_cleared_preauth_subject_takes_the_already_used_rejection(self):
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject=None,
                            consumed_at=FIXED_NOW,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeConsumed):
            store().verify_binding(row, preauth_identity())

    def test_a_cleared_preauth_subject_is_answered_before_the_issuer_is_compared(self):
        """Ordering, not the answer: a mismatched issuer on a cleared row still earns the already-used rejection."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer="https://securetoken.google.com/other-project",
                            preauth_subject=None,
                            consumed_at=FIXED_NOW,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeConsumed):
            store().verify_binding(row, preauth_identity())


class TestLocateIsByteForByte:
    """No trimming, no decoding and re-encoding, no case-folding, no defaulting."""

    async def test_locate_returns_the_row_for_an_exact_handle(self):
        row = AuthChallenge(challenge_id="a" * 22, operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject=SUBJECT,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert await store().locate(_RecordingSession([row]), "a" * 22) is row

    async def test_locate_returns_none_when_no_row_matches(self):
        assert await store().locate(_RecordingSession([]), "a" * 22) is None

    @pytest.mark.parametrize("supplied", [
        " AbCdEfGhIjKlMnOpQrStUv", "AbCdEfGhIjKlMnOpQrStUv ", "\tAbCdEfGhIjKlMnOpQrStUv",
        "abcdefghijklmnopqrstuv", "ABCDEFGHIJKLMNOPQRSTUV", "AbCdEfGhIjKlMnOpQrStUv==",
    ])
    async def test_the_handle_reaches_the_statement_unmodified(self, supplied):
        """Asserted on the bound parameter: a stub session returns its seed whatever the statement says."""
        session = _RecordingSession([])
        await store().locate(session, supplied)
        bound = list(session.statements[0].compile().params.values())
        assert supplied in bound
        assert "AbCdEfGhIjKlMnOpQrStUv" not in [b for b in bound if b != supplied]

    async def test_locate_reads_and_does_not_write(self):
        session = _RecordingSession([])
        await store().locate(session, "a" * 22)
        assert session.added == []
        assert session.commits == 0
