"""Store logic against a stub session; what PostgreSQL does with them is tests/e2e/test_challenge_store.py."""

import ast
import base64
import inspect
import re
import string
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest

from nativespeaker.api.database.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengeStore,
    new_challenge_id,
)
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.auth.exceptions import ChallengeConsumed, ChallengeIdentityMismatch
from nativespeaker.api.auth.hmac_keyring import HmacConfig, HmacKeyring
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


def material(seed: int) -> str:
    """A distinct, valid 32-byte key as base64 text -- the on-disk encoding this phase pinned."""
    return base64.b64encode(bytes((seed * 37 + i) % 256 for i in range(32))).decode()


def keyring(active: int = 1) -> HmacKeyring:
    return HmacKeyring(HmacConfig(active_version=active, keys={active: material(active)}))


def store(ring: HmacKeyring | None = None) -> ChallengeStore:
    return ChallengeStore(ring if ring is not None else keyring())


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


class _ExplodingKeyring:
    """A keyring that fails if consulted, which is the only way to assert that no comparison happened."""

    active_version = 1

    def actor_subject_hash(self, issuer: str, subject: str, *, version: int | None = None) -> bytes:
        raise AssertionError("the keyring was consulted for a cleared preauth_subject_hash")

    def actor_subject_matches(self, stored: bytes, issuer: str, subject: str) -> bool:
        raise AssertionError("the keyring was consulted for a cleared preauth_subject_hash")


def linked_identity(subject: str = SUBJECT, *, issuer: str = ISSUER,
                    identity_id: UUID | None = None) -> LinkedIdentity:
    user = User()
    identity = ExternalIdentity(id=identity_id if identity_id is not None else uuid7(),
                                user_id=user.id,
                                issuer=issuer,
                                subject=subject,
                                provider=IdentityProvider.google,
                                provider_uid=f"google-uid-{subject}")
    return LinkedIdentity(user=user, identity=identity, issuer=issuer, subject=subject)


def preauth_identity(subject: str = SUBJECT, *, issuer: str = ISSUER) -> PreAuthIdentity:
    return PreAuthIdentity(issuer=issuer, subject=subject)


async def issue_row(identity, *, ring: HmacKeyring | None = None,
                    operation: AuthOperation = AuthOperation.create_user,
                    now: datetime = FIXED_NOW):
    """Run `issue` against a stub session and return `(handle, expires_at, row, session)`."""
    session = _RecordingSession()
    subject_store = store(ring)
    handle, expires_at = await subject_store.issue(session,
                                                   operation=operation,
                                                   identity=identity,
                                                   now=now)
    assert len(session.added) == 1, "issue writes exactly one row"
    return handle, expires_at, session.added[0], session


def module_ast() -> ast.Module:
    """The AST of `auth/challenges.py`, read from the file `ChallengeStore` was defined in, so the path cannot drift."""
    return ast.parse(Path(inspect.getfile(ChallengeStore)).read_text())


def method_ast(method) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(method)))


class TestTheOpaqueHandle:
    """16 bytes from a CSPRNG, base64url-encoded without padding."""

    def test_the_handle_is_22_characters(self):
        assert len(new_challenge_id()) == 22

    def test_the_handle_carries_no_padding(self):
        assert "=" not in new_challenge_id()

    def test_the_handle_uses_only_the_urlsafe_alphabet(self):
        """A careless caller would percent-encode `+` and `/`, and a re-encoded handle no longer locates its row."""
        assert re.fullmatch(r"[A-Za-z0-9_-]{22}", new_challenge_id())

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

    def test_the_handle_is_not_a_uuid(self):
        """A UUID is guessable in ways a CSPRNG value is not; uuid7 leaks its creation time outright."""
        with pytest.raises(ValueError):
            UUID(new_challenge_id())

    def test_the_handle_comes_from_the_csprng_and_not_the_default_random(self):
        """Asserted on the imports, because both produce 16 plausible bytes and no output can tell them apart."""
        imported = {alias.name.split(".")[0]
                    for node in ast.walk(module_ast()) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module.split(".")[0]
                     for node in ast.walk(module_ast()) if isinstance(node, ast.ImportFrom)
                     and node.module}
        assert "secrets" in imported
        assert "random" not in imported


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
        assert row.preauth_subject_hash is None

    async def test_a_preauth_identity_leaves_the_linked_column_null(self):
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.bound_external_identity_id is None

    async def test_the_preauth_issuer_is_stored_in_plaintext(self):
        """A deployment-known provider string shared by every user of that provider, so it is not hashed."""
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.preauth_issuer == ISSUER

    async def test_the_preauth_hash_is_the_shared_keyrings_derivation(self):
        """A local reimplementation would produce a plausible digest that silently never matches at completion."""
        ring = keyring()
        _, _, row, _ = await issue_row(preauth_identity(), ring=ring)
        assert row.preauth_subject_hash == ring.actor_subject_hash(ISSUER, SUBJECT)
        assert ring.actor_subject_matches(row.preauth_subject_hash, ISSUER, SUBJECT)

    async def test_the_preauth_hash_moves_with_the_key(self):
        """Identical inputs under a different key must differ, or the case above would pass ignoring the key."""
        _, _, one, _ = await issue_row(preauth_identity(), ring=keyring(1))
        _, _, two, _ = await issue_row(preauth_identity(), ring=keyring(2))
        assert one.preauth_subject_hash != two.preauth_subject_hash

    async def test_the_derivation_uses_the_active_key_with_no_version_argument(self):
        """The active key only: the row has nowhere to record which key produced the hash."""
        source = inspect.getsource(ChallengeStore.issue)
        assert "actor_subject_hash" in source
        assert "version=" not in source

    async def test_the_raw_subject_appears_nowhere_on_the_row(self):
        _, _, row, _ = await issue_row(preauth_identity())
        assert SUBJECT not in str(row.model_dump())

    def test_the_row_records_no_hmac_key_version(self):
        """Verification uses the active key alone, so a challenge outstanding across a rotation simply fails."""
        assert not [name for name in AuthChallenge.model_fields if "key_version" in name]


class TestTheCompletionComparison:
    """The binding verification and its rejection ordering."""

    def test_a_linked_row_matches_its_own_identity(self):
        identity = linked_identity()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.claim_registered_grant,
                            bound_external_identity_id=identity.identity.id,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store().verify_binding(row, identity) is None

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
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store(ring).verify_binding(row, preauth_identity()) is None

    def test_a_preauth_row_rejects_a_different_subject(self):
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeIdentityMismatch):
            store(ring).verify_binding(row, preauth_identity("someone-else"))

    def test_a_preauth_row_rejects_a_different_issuer(self):
        """A subject is unique only within its issuer, so the hash alone would admit another provider's subject."""
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer="https://securetoken.google.com/other-project",
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeIdentityMismatch):
            store(ring).verify_binding(row, preauth_identity())

    def test_a_preauth_row_still_matches_a_subject_that_has_since_become_linked(self):
        """What fails a pre-auth binding is a differing hash, not the subject having since become linked."""
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store(ring).verify_binding(row, linked_identity(SUBJECT)) is None

    def test_a_preauth_row_under_a_rotated_key_rejects(self):
        """The row stores no key version, so a rotation invalidates every outstanding pre-auth-bound challenge."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=keyring(1).actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeIdentityMismatch):
            store(keyring(2)).verify_binding(row, preauth_identity())

    def test_a_cleared_preauth_hash_takes_the_already_used_rejection(self):
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=None,
                            consumed_at=FIXED_NOW,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        with pytest.raises(ChallengeConsumed):
            store().verify_binding(row, preauth_identity())

    def test_a_cleared_preauth_hash_is_not_compared_at_all(self):
        """Not-compared is a property of the code path, not of the answer, so the keyring is one that explodes."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=None,
                            consumed_at=FIXED_NOW,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        exploding = ChallengeStore(_ExplodingKeyring())  # ty: ignore[invalid-argument-type]
        with pytest.raises(ChallengeConsumed):
            exploding.verify_binding(row, preauth_identity())

    def test_the_hash_comparison_goes_through_the_shared_constant_time_seam(self):
        """Asserted on the AST, because `compare_digest` and `==` return identical answers for every input."""
        tree = method_ast(ChallengeStore.verify_binding)
        calls = {node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        assert "actor_subject_matches" in calls

        equality_on_the_hash = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Compare)
            and any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops)
            and any(isinstance(side, ast.Attribute) and side.attr == "preauth_subject_hash"
                    for side in [node.left, *node.comparators])
        ]
        assert equality_on_the_hash == [], "the stored hash must never be compared with == or !="


class TestLocateIsByteForByte:
    """No trimming, no decoding and re-encoding, no case-folding, no defaulting."""

    async def test_locate_returns_the_row_for_an_exact_handle(self):
        row = AuthChallenge(challenge_id="a" * 22, operation=AuthOperation.create_user,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=b"x" * 32,
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


class TestTheStoreBuildsNoMachineryTheDesignForbids:
    """Locks, global deletions and second derivations are asserted absent, not assumed."""

    def test_the_module_takes_no_database_lock(self):
        """The conditional update is the serialization point; any lock would be a second one that disagrees."""
        tree = module_ast()
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for forbidden in ("with_for_update", "Lock", "advisory_lock", "create_task", "sleep"):
            assert forbidden not in names

    def test_the_module_embeds_no_raw_sql(self):
        """The v1.6 zero-raw-`text()` convention, and the only way `FOR UPDATE` could sneak in."""
        tree = module_ast()
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        assert "text" not in called
        assert not [s for s in _non_docstring_strings(tree)
                    if "for update" in s.lower() or "advisory" in s.lower()]

    def test_the_module_logs_nothing(self):
        """The handle is a secret capability, so the module holds no logger to log it with."""
        tree = module_ast()
        imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.Import) for alias in node.names}
        assert "structlog" not in imported
        assert "logging" not in imported

    def test_the_module_derives_no_hash_of_its_own(self):
        """A second derivation would be a plausible digest that silently never matches at completion."""
        tree = module_ast()
        imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        assert "hmac" not in imported
        assert "hashlib" not in imported

    # The two cases that pinned the store's rejection enum against the outcome enum went with both
    # of them. What they were really guarding -- that the five rejection names are exactly these
    # five and a rename is a visible edit -- now lives in `test_rejection_vocabulary.py`, where the
    # class names *are* the vocabulary and the whole family is enumerated at once.


def _non_docstring_strings(tree: ast.Module) -> list[str]:
    """Every string literal except the docstrings, whose own prose names the things the module must not contain."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]
