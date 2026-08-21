"""FOUND-07: the challenge handle, the TTL, the binding at issuance, and the §6.4 comparison.

Pure unit coverage against a recording stub session: no database, no application. What lives here
is everything about the *store's logic* -- the opaque handle's shape, the 300-second arithmetic
from a supplied clock, which columns each binding fills, and the completion comparison with its
rejection ordering.

The live-database proof -- that the claim serializes concurrent attempts and that consumption is
one-directional against the real `core.auth_challenges` table -- is `tests/e2e/test_challenge_
store.py`. Neither module replaces the other: a stub session proves the statements this store
builds and nothing about what PostgreSQL does with them, and the e2e module proves the arbitration
and cannot reach the branches a real database makes unconstructible.

Every keyring here is built inline from locally-generated base64 material. The module reads nothing
from `config/`, so a case cannot go green again because someone rotated the committed development
key.
"""

import ast
import base64
import inspect
import re
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid7

import pytest
from nativespeaker.api.auth.challenges import (
    CHALLENGE_ID_BYTES,
    CHALLENGE_TTL_SECONDS,
    ChallengeRejection,
    ChallengeStore,
    new_challenge_id,
)

from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.auth.keys import HmacConfig, HmacKeyring
from nativespeaker.api.models.auth import AuthChallenge, AuthEventResult, AuthOperation
from nativespeaker.api.models.identities import ExternalIdentity, IdentityProvider
from nativespeaker.api.models.users import User

ISSUER = "https://securetoken.google.com/test-project"
SUBJECT = "Xy7Q1s0K2mNb3fV4"

# Deliberately far in the past. Every `expires_at` assertion below is against this value plus 300
# seconds, so a store reading its own wall clock instead of the supplied `now` fails by years
# rather than by microseconds.
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

# §6.1's four challenge-bearing operations with the variants the table's CHECK admits. Used to
# assert the TTL is universal: §6.3 forbids a per-operation override in either direction.
CHALLENGE_BEARING = (
    (AuthOperation.create_user, IdentityProvider.anonymous),
    (AuthOperation.create_user, IdentityProvider.google),
    (AuthOperation.create_user, IdentityProvider.apple),
    (AuthOperation.upgrade_anonymous_to_registered, IdentityProvider.google),
    (AuthOperation.upgrade_anonymous_to_registered, IdentityProvider.apple),
    (AuthOperation.claim_anonymous_grant, None),
    (AuthOperation.claim_registered_grant, None),
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
    """A keyring that fails if consulted at all -- the only way to assert *not compared*.

    A cleared `preauth_subject_hash` must take the already-used rejection without any comparison
    happening (§6.4). An assertion on the returned value alone cannot distinguish "compared against
    None and rejected" from "not compared", and the first would be a `TypeError` waiting for a
    caller.
    """

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
                    variant: IdentityProvider | None = IdentityProvider.google,
                    now: datetime = FIXED_NOW):
    """Run `issue` against a stub session and return `(handle, expires_at, row, session)`."""
    session = _RecordingSession()
    subject_store = store(ring)
    handle, expires_at = await subject_store.issue(session,
                                                   operation=operation,
                                                   operation_variant=variant,
                                                   identity=identity,
                                                   now=now)
    assert len(session.added) == 1, "issue writes exactly one row"
    return handle, expires_at, session.added[0], session


def module_ast() -> ast.Module:
    """The AST of `auth/challenges.py`, read from the file `ChallengeStore` was defined in.

    Reached through the class rather than by importing the module under a second name, so the path
    cannot drift from the thing being asserted about.
    """
    return ast.parse(Path(inspect.getfile(ChallengeStore)).read_text())


def method_ast(method) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(method)))


class TestTheOpaqueHandle:
    """§6.1: 16 bytes from a CSPRNG, base64url-encoded without padding."""

    def test_the_handle_is_22_characters(self):
        assert len(new_challenge_id()) == 22

    def test_the_handle_carries_no_padding(self):
        assert "=" not in new_challenge_id()

    def test_the_handle_uses_only_the_urlsafe_alphabet(self):
        """URL-safe matters even though the handle never reaches a URL: `+` and `/` are what a
        careless caller would percent-encode, and a re-encoded handle no longer locates its row."""
        assert re.fullmatch(r"[A-Za-z0-9_-]{22}", new_challenge_id())

    def test_a_thousand_handles_are_all_distinct(self):
        assert len({new_challenge_id() for _ in range(1000)}) == 1000

    def test_the_handle_decodes_back_to_exactly_16_bytes(self):
        """The length assertion alone passes for a 22-character slice of anything. This is what
        says the handle carries 16 whole bytes of entropy rather than a truncated something."""
        raw = base64.urlsafe_b64decode(new_challenge_id() + "==")
        assert len(raw) == CHALLENGE_ID_BYTES == 16

    def test_the_handle_is_not_a_uuid(self):
        """§6.1 pins the format. A UUID is guessable in ways a CSPRNG value is not -- uuid7 leaks
        its creation time outright -- and `Don't Hand-Roll` names it as the wrong substitution."""
        with pytest.raises(ValueError):
            UUID(new_challenge_id())

    def test_the_handle_comes_from_the_csprng_and_not_the_default_random(self):
        """`secrets.token_bytes`, never `random`. Asserted on the module's imports because both
        produce 16 plausible bytes and no output can tell them apart."""
        imported = {alias.name.split(".")[0]
                    for node in ast.walk(module_ast()) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module.split(".")[0]
                     for node in ast.walk(module_ast()) if isinstance(node, ast.ImportFrom)
                     and node.module}
        assert "secrets" in imported
        assert "random" not in imported


class TestTheUniversalTTL:
    """§6.3: 300 seconds from the server's own clock, for every operation, with no override."""

    def test_the_constants_are_pinned(self):
        assert CHALLENGE_TTL_SECONDS == 300
        assert CHALLENGE_ID_BYTES == 16

    async def test_expires_at_is_exactly_300_seconds_after_the_supplied_now(self):
        _, expires_at, row, _ = await issue_row(preauth_identity())
        assert expires_at == FIXED_NOW + timedelta(seconds=300)
        assert row.expires_at == expires_at

    async def test_the_clock_is_the_supplied_one_and_not_the_wall_clock(self):
        """`FIXED_NOW` is years away from `datetime.now(UTC)`, so a store that read its own clock
        fails this by years. A near-`now` fixture would differ by microseconds and pass."""
        _, expires_at, _, _ = await issue_row(preauth_identity())
        assert abs((expires_at - datetime.now(UTC)).days) > 30

    async def test_created_at_is_the_same_captured_evaluation_time(self):
        """SHARED-INVARIANTS: every time-dependent value derives from ONE captured time."""
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.created_at == FIXED_NOW

    @pytest.mark.parametrize(("operation", "variant"), CHALLENGE_BEARING)
    async def test_every_operation_gets_the_identical_ttl(self, operation, variant):
        """§6.3 forbids a per-operation override *in either direction*."""
        _, expires_at, _, _ = await issue_row(preauth_identity(), operation=operation,
                                              variant=variant)
        assert expires_at - FIXED_NOW == timedelta(seconds=CHALLENGE_TTL_SECONDS)

    async def test_the_row_records_the_operation_and_variant_it_was_issued_for(self):
        _, _, row, _ = await issue_row(preauth_identity(),
                                       operation=AuthOperation.claim_anonymous_grant,
                                       variant=None)
        assert row.operation is AuthOperation.claim_anonymous_grant
        assert row.operation_variant is None

    async def test_issue_discloses_exactly_the_handle_and_expires_at(self):
        """§6.1: "Returns exactly `challenge_id` and `expires_at`; nothing else about the challenge
        is ever disclosed." A three-element return would hand a caller the row id to leak."""
        session = _RecordingSession()
        returned = await store().issue(session, operation=AuthOperation.create_user,
                                       operation_variant=IdentityProvider.google,
                                       identity=preauth_identity(), now=FIXED_NOW)
        assert isinstance(returned, tuple)
        assert len(returned) == 2
        handle, expires_at = returned
        assert handle == session.added[0].challenge_id
        assert isinstance(expires_at, datetime)

    async def test_issue_does_not_commit_the_callers_transaction(self):
        """The store is transaction-neutral throughout: prepare's own handler commits. A store that
        committed here would break the e2e rollback fixture and, worse, would commit a prepare
        whose surrounding handler later failed."""
        _, _, _, session = await issue_row(preauth_identity())
        assert session.commits == 0
        assert session.flushes == 1


class TestTheBindingWrittenAtIssuance:
    """§6.4: a row binds exactly one of linked or pre-auth, never both and never neither."""

    async def test_a_linked_identity_binds_the_identity_row(self):
        identity = linked_identity()
        _, _, row, _ = await issue_row(identity)
        assert row.bound_external_identity_id == identity.identity.id

    async def test_a_linked_identity_leaves_both_preauth_columns_null(self):
        """The table's CHECK requires exactly one arm. Writing both would be rejected at insert;
        asserting it here is what makes the failure readable."""
        _, _, row, _ = await issue_row(linked_identity())
        assert row.preauth_issuer is None
        assert row.preauth_subject_hash is None

    async def test_a_preauth_identity_leaves_the_linked_column_null(self):
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.bound_external_identity_id is None

    async def test_the_preauth_issuer_is_stored_in_plaintext(self):
        """Ruling 9.3: a deployment-known provider string shared by every user of that provider.
        Do not hash it, encrypt it, or drop it."""
        _, _, row, _ = await issue_row(preauth_identity())
        assert row.preauth_issuer == ISSUER

    async def test_the_preauth_hash_is_the_shared_keyrings_derivation(self):
        """D-21: the same family and the same key as the audit writer's `actor_subject_hash`. A
        local reimplementation would produce a plausible 32-byte value that silently never matches
        at completion, so the assertion is against the keyring's own output."""
        ring = keyring()
        _, _, row, _ = await issue_row(preauth_identity(), ring=ring)
        assert row.preauth_subject_hash == ring.actor_subject_hash(ISSUER, SUBJECT)
        assert ring.actor_subject_matches(row.preauth_subject_hash, ISSUER, SUBJECT)

    async def test_the_preauth_hash_moves_with_the_key(self):
        """The counterpart to the case above: identical inputs under a different key must differ,
        or the assertion above would pass for a derivation that ignored the key entirely."""
        _, _, one, _ = await issue_row(preauth_identity(), ring=keyring(1))
        _, _, two, _ = await issue_row(preauth_identity(), ring=keyring(2))
        assert one.preauth_subject_hash != two.preauth_subject_hash

    async def test_the_derivation_uses_the_active_key_with_no_version_argument(self):
        """§6.4: "current active key only". The audit writer passes a version; this store must not,
        because the row has nowhere to record which key produced the hash."""
        source = inspect.getsource(ChallengeStore.issue)
        assert "actor_subject_hash" in source
        assert "version=" not in source

    async def test_the_raw_subject_appears_nowhere_on_the_row(self):
        _, _, row, _ = await issue_row(preauth_identity())
        assert SUBJECT not in str(row.model_dump())

    def test_the_row_records_no_hmac_key_version(self):
        """The migration comment forbids the column outright: verification uses the active key
        alone, so a challenge outstanding across a rotation simply fails (D-21's consequence)."""
        assert not [name for name in AuthChallenge.model_fields if "key_version" in name]


class TestTheCompletionComparison:
    """§6.4's binding verification and its rejection ordering."""

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
        assert (store().verify_binding(row, linked_identity())
                is ChallengeRejection.challenge_identity_mismatch)

    def test_a_linked_row_rejects_a_preauth_request(self):
        """A pre-auth request resolved to no identity row at all, so it can match no linked
        binding -- and must not be waved through for lack of anything to compare."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.claim_registered_grant,
                            bound_external_identity_id=uuid7(),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert (store().verify_binding(row, preauth_identity())
                is ChallengeRejection.challenge_identity_mismatch)

    def test_a_preauth_row_matches_the_subject_it_was_issued_for(self):
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store(ring).verify_binding(row, preauth_identity()) is None

    def test_a_preauth_row_rejects_a_different_subject(self):
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert (store(ring).verify_binding(row, preauth_identity("someone-else"))
                is ChallengeRejection.challenge_identity_mismatch)

    def test_a_preauth_row_rejects_a_different_issuer(self):
        """The issuer is half the binding. A subject string is only unique within its issuer, so
        comparing the hash alone would let a second provider's identically-named subject through."""
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google,
                            preauth_issuer="https://securetoken.google.com/other-project",
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert (store(ring).verify_binding(row, preauth_identity())
                is ChallengeRejection.challenge_identity_mismatch)

    def test_a_preauth_row_still_matches_a_subject_that_has_since_become_linked(self):
        """§6.4: the pre-auth comparison is over the verified `(issuer, subject)` and stays that
        way "even if that subject has since become linked". The request's current variant is not
        part of the test -- what fails a pre-auth binding is a differing hash, not linkage."""
        ring = keyring()
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=ring.actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert store(ring).verify_binding(row, linked_identity(SUBJECT)) is None

    def test_a_preauth_row_under_a_rotated_key_rejects(self):
        """D-21's accepted consequence, stated as an assertion: the row stores no key version, so a
        rotation invalidates every outstanding pre-auth-bound challenge."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=keyring(1).actor_subject_hash(ISSUER, SUBJECT),
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert (store(keyring(2)).verify_binding(row, preauth_identity())
                is ChallengeRejection.challenge_identity_mismatch)

    def test_a_cleared_preauth_hash_takes_the_already_used_rejection(self):
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=None,
                            consumed_at=FIXED_NOW,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        assert (store().verify_binding(row, preauth_identity())
                is ChallengeRejection.challenge_consumed)

    def test_a_cleared_preauth_hash_is_not_compared_at_all(self):
        """Clearing is part of consumption, not a change of identity (§6.4). "Not compared" is a
        property of the code path, not of the answer, so the keyring is one that explodes."""
        row = AuthChallenge(challenge_id=new_challenge_id(),
                            operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google,
                            preauth_issuer=ISSUER,
                            preauth_subject_hash=None,
                            consumed_at=FIXED_NOW,
                            expires_at=FIXED_NOW, created_at=FIXED_NOW)
        exploding = ChallengeStore(_ExplodingKeyring())  # ty: ignore[invalid-argument-type]
        assert exploding.verify_binding(row, preauth_identity()) is ChallengeRejection.challenge_consumed

    def test_the_hash_comparison_goes_through_the_shared_constant_time_seam(self):
        """T-35-10-04. `hmac.compare_digest` and `==` return identical answers for every input, so
        no test input can distinguish them -- this is asserted on the AST instead.

        The call is `HmacKeyring.actor_subject_matches`, which plan 08 shipped precisely so plans
        09 and 10 would not each write their own comparison. `challenges.py` therefore contains no
        literal `compare_digest`; `tests/unit/test_hmac_keys.py` pins that the seam is one.
        """
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
    """§6.1: no trimming, no decoding and re-encoding, no case-folding, no defaulting."""

    async def test_locate_returns_the_row_for_an_exact_handle(self):
        row = AuthChallenge(challenge_id="a" * 22, operation=AuthOperation.create_user,
                            operation_variant=IdentityProvider.google, preauth_issuer=ISSUER,
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
        """The store must hand PostgreSQL exactly what the caller supplied. Asserted on the bound
        parameter rather than on a returned row, because a stub session returns whatever it was
        seeded with whatever the statement says -- and a real no-match proves nothing about
        *which* value was searched for."""
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
    """SHARED-INVARIANTS § Locks and transactions, § Global deletions -- asserted, not assumed."""

    def test_the_module_takes_no_database_lock(self):
        """§6.1: the conditional update *is* the serialization point. `FOR UPDATE`, an advisory
        lock, or an application mutex would each be a second one that disagrees with it."""
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
        """§6.1: "The raw malformed identifier is never logged." The handle is a secret capability,
        so the module holds no logger at all -- there is nothing to log it *with*."""
        tree = module_ast()
        imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.Import) for alias in node.names}
        assert "structlog" not in imported
        assert "logging" not in imported

    def test_the_module_derives_no_hash_of_its_own(self):
        """D-21: one derivation, shared with the audit writer. A second one would produce a
        plausible 32-byte digest, raise nothing, and silently never match at completion.

        `base64` and `secrets` are legitimately here -- they build the handle, not a digest."""
        tree = module_ast()
        imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        assert "hmac" not in imported
        assert "hashlib" not in imported

    def test_the_rejection_names_are_the_audit_results_they_map_onto(self):
        """Every `ChallengeRejection` is written into `audit.auth_events.result` by phases 37+.
        Pinning the names here is what lets them write `AuthEventResult(rejection)` instead of each
        maintaining a private mapping table that can drift."""
        for rejection in ChallengeRejection:
            assert AuthEventResult(rejection.value)

    def test_the_five_rejections_are_exactly_the_challenge_results(self):
        assert {r.value for r in ChallengeRejection} == {
            "challenge_not_found", "challenge_expired", "challenge_consumed",
            "challenge_identity_mismatch", "challenge_operation_mismatch"}


def _non_docstring_strings(tree: ast.Module) -> list[str]:
    """Every string literal in the module except the docstrings.

    Docstrings are excluded because this module's own prose names the things it must not contain --
    the trap plans 08 and 09 both hit, where a source-text scan matched the docstring explaining
    why the thing is absent.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]
