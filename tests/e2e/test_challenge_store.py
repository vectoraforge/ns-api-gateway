"""FOUND-07: the challenge store against the real `core.auth_challenges` table.

`tests/unit/test_challenge_ids.py` proves the statements this store builds. This module proves what
PostgreSQL does with them: that the claim genuinely serializes concurrent attempts, that expiry is
evaluated at the claim and nowhere else, and that the lifecycle runs one direction only.

**Two harnesses, on purpose, because one of them cannot host the concurrency case.**

Everything except the race runs through the swapped `test_factory` from `_db_transaction`, so every
row rolls back. Those cases are sequential, and sequential sessions on one shared connection behave
exactly like sequential sessions anywhere.

The race cannot run there. Every session `test_factory` produces is bound to the **same**
connection under `join_transaction_mode="create_savepoint"`, and a connection executes one
statement at a time -- so eight `claim`s driven through it are not concurrent, they are eight
statements in one transaction. Worse, the interleaved `SAVEPOINT`/`RELEASE` pairs corrupt the
savepoint stack: run that way, one contender returns `True` and the other seven raise
`InvalidSavepointSpecificationError` and `InFailedSQLTransactionError` [measured]. A case asserting
"exactly one True" would have gone green on that -- while seven contenders never reached the
`UPDATE` at all, which is the opposite of what it claims to prove.

`TestTheClaimSerializesConcurrentAttempts` therefore uses eight **independent** connections from a
second engine, released together by an `asyncio.Barrier`, contending in eight real transactions.
That is the arrangement in which the row lock and the re-evaluated `WHERE` are the arbiter, which
is the property §6.1 actually asserts. Its rows must be committed for the other connections to see
them, so the `_contended_challenge` fixture deletes exactly the handle it committed on teardown.
That is a test tidying its own fixture, not a cleanup job: the product builds none, and expired,
claimed and consumed rows are retained indefinitely by design (§6.2).
"""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
import pytest_asyncio
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from e2e.conftest import seed_identity
from nativespeaker.api.auth.challenges import ChallengeRejection
from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.models.auth import AuthChallenge, AuthOperation
from nativespeaker.api.models.identities import IdentityProvider

pytestmark = pytest.mark.e2e

ISSUER = "https://securetoken.google.com/challenge-store-test"
SUBJECT = "challenge-store-subject"

# Eight, not two. Two contenders can both "win" a broken claim and still look like a coin toss;
# eight makes a claim that stopped arbitrating unmistakable.
CONTENDERS = 8


@pytest.fixture
def store(_app_lifespan):
    """The store the *real* lifespan constructed, not a fresh one.

    This is the only place `app.state.challenge_store` is exercised, so taking it from the started
    application is what proves the wiring exists and shares the lifespan's keyring.
    """
    return _app_lifespan.state.challenge_store


@pytest.fixture
def keyring(_app_lifespan):
    return _app_lifespan.state.hmac_keyring


def preauth(subject: str = SUBJECT, *, issuer: str = ISSUER) -> PreAuthIdentity:
    return PreAuthIdentity(issuer=issuer, subject=subject)


async def issue(factory, store, identity=None, *, now=None,
                operation: AuthOperation = AuthOperation.claim_anonymous_grant
                ) -> tuple[str, datetime]:
    """Issue one challenge and commit it, the way a real prepare handler would."""
    moment = now if now is not None else datetime.now(UTC)
    async with factory() as session:
        handle, expires_at = await store.issue(session,
                                               operation=operation,
                                               identity=identity if identity is not None
                                               else preauth(),
                                               now=moment)
        await session.commit()
    return handle, expires_at


async def read(factory, handle: str) -> AuthChallenge | None:
    """Read a row back through the same factory the store wrote through.

    Never a fresh engine: the write lives inside the per-test transaction, and a second engine's
    connection would be looking at a different one.
    """
    async with factory() as session:
        return (await session.exec(select(AuthChallenge)
                                   .where(col(AuthChallenge.challenge_id) == handle))).first()


async def row_count(factory) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(AuthChallenge))


@pytest_asyncio.fixture(loop_scope="module")
async def _contended_challenge(_app_lifespan, store):
    """One committed challenge and `CONTENDERS` independent connections racing to claim it.

    Yields `(handle, attempts, results, factory)`. The race runs once per requesting test, so each
    test asserts one property of one race rather than several properties of a shared one.

    The engine is a second one on purpose -- see this module's docstring. Its rows are committed and
    therefore outlive `_db_transaction`, so the handle is deleted here on teardown by exact value.
    """
    config = _app_lifespan.state.config
    engine = create_async_engine(config.db.url, pool_size=CONTENDERS + 2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    now = datetime.now(UTC)
    handle, _ = await issue(factory, store, now=now)
    attempts = [uuid7() for _ in range(CONTENDERS)]

    # Every contender checks a connection out and *then* waits, so the barrier releases eight
    # transactions that are already connected. Without the explicit `connection()` the pool
    # checkout would stagger them and the first claimant could finish before the last had begun.
    barrier = asyncio.Barrier(CONTENDERS)

    async def contend(attempt_id: UUID) -> bool:
        async with factory() as session:
            await session.connection()
            await barrier.wait()
            won = await store.claim(session, challenge_id=handle, claim_attempt_id=attempt_id,
                                    now=now)
            await session.commit()
            return won

    results = await asyncio.gather(*(contend(a) for a in attempts), return_exceptions=True)
    try:
        yield handle, attempts, results, factory
    finally:
        async with factory() as session:
            await session.exec(delete(AuthChallenge)  # ty: ignore[invalid-argument-type]
                               .where(col(AuthChallenge.challenge_id) == handle))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio(loop_scope="module")
class TestTheClaimSerializesConcurrentAttempts:
    """§6.1: "exactly one completion attempt can ever win it" -- T-35-10-01's whole mitigation."""

    async def test_no_contender_raised(self, _contended_challenge):
        """Asserted first and separately. Every other case below counts `True`s, and an exception
        counts as neither a win nor a loss -- so a harness that broke seven contenders would leave
        exactly one `True` and satisfy them all while proving nothing."""
        _, _, results, _ = _contended_challenge
        assert [r for r in results if isinstance(r, BaseException)] == []

    async def test_exactly_one_of_eight_concurrent_claims_wins(self, _contended_challenge):
        _, _, results, _ = _contended_challenge
        assert results.count(True) == 1
        assert results.count(False) == CONTENDERS - 1

    async def test_the_stored_claim_attempt_id_is_the_winners(self, _contended_challenge):
        """The count alone would pass for a claim that returned `True` once and stamped whichever
        attempt id happened to write last."""
        handle, attempts, results, factory = _contended_challenge
        winner = attempts[results.index(True)]
        row = await read(factory, handle)
        assert row.claim_attempt_id == winner

    async def test_the_losers_mutated_nothing(self, _contended_challenge):
        """Seven transactions committed after matching zero rows. One row, claimed exactly once,
        and not consumed by anybody."""
        handle, _, _, factory = _contended_challenge
        row = await read(factory, handle)
        assert row.claimed_at is not None
        assert row.consumed_at is None
        assert row.preauth_subject_hash is not None
        async with factory() as session:
            same = await session.scalar(select(func.count()).select_from(AuthChallenge)
                                        .where(col(AuthChallenge.challenge_id) == handle))
        assert same == 1


@pytest.mark.asyncio(loop_scope="module")
class TestTheClaimIsTheOnlyPlaceExpiryIsEvaluated:
    """§6.1. Issued with a `now` far enough in the past that `expires_at` has already passed, then
    claimed with the real current time."""

    async def test_a_claim_against_an_expired_row_returns_false(self, store, _db_transaction):
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        handle, expires_at = await issue(_db_transaction, store, now=long_ago)
        assert expires_at < datetime.now(UTC), "the fixture must actually be expired"

        async with _db_transaction() as session:
            assert await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(),
                                     now=datetime.now(UTC)) is False
            await session.commit()

    async def test_an_expired_row_is_left_unclaimed(self, store, _db_transaction):
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        handle, _ = await issue(_db_transaction, store, now=long_ago)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(),
                              now=datetime.now(UTC))
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.claimed_at is None
        assert row.claim_attempt_id is None

    async def test_locate_still_returns_an_expired_row(self, store, _db_transaction):
        """The positive half of "the only place expiry is evaluated": a lookup that filtered on
        `expires_at` would make an expired handle indistinguishable from an unknown one, and the
        two are different rejections (`challenge_expired` vs `challenge_not_found`)."""
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        handle, _ = await issue(_db_transaction, store, now=long_ago)
        async with _db_transaction() as session:
            located = await store.locate(session, handle)
        assert located is not None
        assert located.expires_at < datetime.now(UTC)

    async def test_a_row_one_second_from_expiry_still_claims(self, store, _db_transaction):
        """The boundary from the other side, so the case above cannot pass for a claim that
        rejects everything."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            claimed = await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(),
                                        now=now + timedelta(seconds=299))
            await session.commit()
        assert claimed is True


@pytest.mark.asyncio(loop_scope="module")
class TestTheLifecycleRunsOneDirectionOnly:
    """§6.2: `issued -> claimed -> consumed`. Never back, never again, never by a later attempt."""

    async def test_a_second_claim_of_a_claimed_row_returns_false(self, store, _db_transaction):
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            assert await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(),
                                     now=now) is True
            assert await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(),
                                     now=now) is False
            await session.commit()

    async def test_a_second_claim_does_not_change_the_stored_attempt_id(self, store,
                                                                        _db_transaction):
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        winner, loser = uuid7(), uuid7()
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=winner, now=now)
            await store.claim(session, challenge_id=handle, claim_attempt_id=loser, now=now)
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.claim_attempt_id == winner

    async def test_consume_before_any_claim_returns_false(self, store, _db_transaction):
        """Consumption requires a claim. Skipping the claim would skip the serialization point."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            assert await store.consume(session, challenge_id=handle, claim_attempt_id=uuid7(),
                                       now=now) is False
            await session.commit()

        assert (await read(_db_transaction, handle)).consumed_at is None

    async def test_an_unclaimed_row_is_not_consumable_by_a_null_attempt_id(self, store,
                                                                           _db_transaction):
        """The case `claimed_at IS NOT NULL` exists for, and the only one that distinguishes it.

        Against a *claimed* row the condition is redundant: the table's lifecycle CHECK guarantees
        that a non-NULL `claim_attempt_id` implies a non-NULL `claimed_at`, so dropping it changes
        no answer -- verified by mutation. The exception is a caller whose attempt id is `None`,
        from an uninitialised field or one that failed to populate. `col(...) == None` renders as
        `IS NULL`, which matches every *issued* row, so without this condition such a caller would
        consume a challenge nobody ever claimed -- skipping the serialization point entirely.

        The signature says `UUID`, so this is a caller `ty` would reject in `src/`. It is exactly
        the mistake a defensive `WHERE` is for.
        """
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            assert await store.consume(session, challenge_id=handle, claim_attempt_id=None,
                                       now=now) is False
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.consumed_at is None
        assert row.preauth_subject_hash is not None

    async def test_consume_under_the_winning_attempt_sets_consumed_at(self, store,
                                                                      _db_transaction):
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        attempt = uuid7()
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            assert await store.consume(session, challenge_id=handle, claim_attempt_id=attempt,
                                       now=now) is True
            await session.commit()

        assert (await read(_db_transaction, handle)).consumed_at is not None

    async def test_consume_clears_the_preauth_hash_on_a_preauth_bound_row(self, store,
                                                                          _db_transaction):
        """Both column changes land in one `UPDATE`. The table's binding CHECK admits a cleared
        hash only once `consumed_at` is set, so a two-statement consume would be rejected here by
        PostgreSQL rather than by review."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        assert (await read(_db_transaction, handle)).preauth_subject_hash is not None

        attempt = uuid7()
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            await store.consume(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.preauth_subject_hash is None
        assert row.preauth_issuer == ISSUER, "the plaintext issuer is not cleared (ruling 9.3)"

    async def test_consume_under_a_losing_attempt_id_returns_false(self, store, _db_transaction):
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(), now=now)
            assert await store.consume(session, challenge_id=handle, claim_attempt_id=uuid7(),
                                       now=now) is False
            await session.commit()

    async def test_a_losing_consume_changes_nothing(self, store, _db_transaction):
        """The counterpart to the case above: a rejected consume must not half-apply. A statement
        that cleared the hash without setting `consumed_at` would trip the CHECK; one that did
        neither but returned `False` from a stale rowcount would look identical here."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(), now=now)
            await store.consume(session, challenge_id=handle, claim_attempt_id=uuid7(), now=now)
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.consumed_at is None
        assert row.preauth_subject_hash is not None

    async def test_a_second_consume_under_the_winning_attempt_id_returns_false(self, store,
                                                                               _db_transaction):
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        attempt = uuid7()
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            assert await store.consume(session, challenge_id=handle, claim_attempt_id=attempt,
                                       now=now) is True
            assert await store.consume(session, challenge_id=handle, claim_attempt_id=attempt,
                                       now=now) is False
            await session.commit()

    async def test_a_consumed_row_is_never_returned_to_issued(self, store, _db_transaction):
        """No reclaim, no reissue, no reuse (§6.2). The claim's `claimed_at IS NULL` is what makes
        this structural rather than a rule somebody has to remember."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        attempt = uuid7()
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            await store.consume(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            assert await store.claim(session, challenge_id=handle, claim_attempt_id=uuid7(),
                                     now=now) is False
            await session.commit()


@pytest.mark.asyncio(loop_scope="module")
class TestTheBindingAgainstRealRows:
    """§6.4, against rows PostgreSQL accepted and read back rather than ones built in memory."""

    async def test_a_linked_bound_row_matches_its_own_identity(self, store, _db_transaction):
        """The linked arm needs a real `core.external_identities` row, because
        `bound_external_identity_id` carries a foreign key -- an invented UUID would be rejected at
        insert, which is what makes this case worth running against a database at all."""
        user, identity = await seed_identity(_db_transaction, issuer=ISSUER, subject=SUBJECT)
        context = LinkedIdentity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)
        handle, _ = await issue(_db_transaction, store, context,
                                operation=AuthOperation.claim_registered_grant)

        row = await read(_db_transaction, handle)
        assert row.bound_external_identity_id == identity.id
        assert store.verify_binding(row, context) is None

    async def test_a_linked_bound_row_rejects_a_different_identity(self, store, _db_transaction):
        user, identity = await seed_identity(_db_transaction, issuer=ISSUER, subject=SUBJECT)
        other_user, other_identity = await seed_identity(_db_transaction, issuer=ISSUER,
                                                         subject="a-different-subject",
                                                         provider=IdentityProvider.apple)
        context = LinkedIdentity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)
        intruder = LinkedIdentity(user=other_user, identity=other_identity, issuer=ISSUER,
                                  subject="a-different-subject")
        handle, _ = await issue(_db_transaction, store, context,
                                operation=AuthOperation.claim_registered_grant)

        row = await read(_db_transaction, handle)
        assert (store.verify_binding(row, intruder)
                is ChallengeRejection.challenge_identity_mismatch)

    async def test_a_rejected_binding_leaves_the_challenge_unconsumed(self, store,
                                                                      _db_transaction):
        """T-35-10-05. The bound-context mismatch is rejected *before* the claim, so presenting
        someone else's handle at the wrong identity cannot burn the rightful user's in-flight
        challenge. `verify_binding` is a pure comparison -- it takes no session and can issue no
        statement -- and the row is read back afterwards to say so."""
        user, identity = await seed_identity(_db_transaction, issuer=ISSUER, subject=SUBJECT)
        other_user, other_identity = await seed_identity(_db_transaction, issuer=ISSUER,
                                                         subject="a-different-subject",
                                                         provider=IdentityProvider.apple)
        context = LinkedIdentity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)
        intruder = LinkedIdentity(user=other_user, identity=other_identity, issuer=ISSUER,
                                  subject="a-different-subject")
        handle, _ = await issue(_db_transaction, store, context,
                                operation=AuthOperation.claim_registered_grant)

        store.verify_binding(await read(_db_transaction, handle), intruder)

        row = await read(_db_transaction, handle)
        assert row.claimed_at is None
        assert row.consumed_at is None

    async def test_a_preauth_row_read_back_matches_the_shared_derivation(self, store, keyring,
                                                                         _db_transaction):
        """The stored bytes survive the BYTEA round trip and still satisfy the keyring that the
        audit writer uses -- the one thing a locally-reimplemented derivation would break."""
        handle, _ = await issue(_db_transaction, store)
        row = await read(_db_transaction, handle)
        assert row.preauth_subject_hash == keyring.actor_subject_hash(ISSUER, SUBJECT)
        assert keyring.actor_subject_matches(row.preauth_subject_hash, ISSUER, SUBJECT)
        assert store.verify_binding(row, preauth()) is None

    async def test_a_consumed_preauth_row_takes_the_already_used_rejection(self, store,
                                                                           _db_transaction):
        """The full round trip for §6.4's "not compared at all" rule: consume clears the hash in
        the database, and the row read back afterwards rejects `challenge_consumed` rather than
        `challenge_identity_mismatch`. The distinction is the difference between telling a client
        "you already used this" and telling it "you are not who you say you are"."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        attempt = uuid7()
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            await store.consume(session, challenge_id=handle, claim_attempt_id=attempt, now=now)
            await session.commit()

        row = await read(_db_transaction, handle)
        assert store.verify_binding(row, preauth()) is ChallengeRejection.challenge_consumed


@pytest.mark.asyncio(loop_scope="module")
class TestLocateIsByteForByteAgainstPostgres:
    """§6.1, asserted against the comparison the database actually performs rather than against one
    built in Python.

    The handle here is a **fixed** value written directly, not one from `new_challenge_id()`. Its
    generation is covered in the unit module, and a random handle makes the manglings
    non-deterministic: `h.lower()` leaves an all-lowercase handle unchanged, which happens roughly
    once in 25,000 and would turn this case into a silent skip on a CI run nobody looks at.
    """

    PLANTED = "AbCdEfGhIjKlMnOpQrStUv"

    async def plant(self, factory) -> str:
        async with factory() as session:
            now = datetime.now(UTC)
            session.add(AuthChallenge(challenge_id=self.PLANTED,
                                      operation=AuthOperation.claim_anonymous_grant,
                                      preauth_issuer=ISSUER,
                                      preauth_subject_hash=bytes(range(32)),
                                      expires_at=now + timedelta(seconds=300),
                                      created_at=now))
            await session.commit()
        return self.PLANTED

    async def test_an_exact_handle_locates_its_row(self, store, _db_transaction):
        handle = await self.plant(_db_transaction)
        async with _db_transaction() as session:
            assert (await store.locate(session, handle)).challenge_id == handle

    @pytest.mark.parametrize("mangled", [
        pytest.param("abcdefghijklmnopqrstuv", id="lowercased"),
        pytest.param("ABCDEFGHIJKLMNOPQRSTUV", id="uppercased"),
        pytest.param(" AbCdEfGhIjKlMnOpQrStUv", id="leading-space"),
        pytest.param("AbCdEfGhIjKlMnOpQrStUv ", id="trailing-space"),
        pytest.param("AbCdEfGhIjKlMnOpQrStUv==", id="repadded"),
        pytest.param("AbCdEfGhIjKlMnOpQrStU", id="truncated"),
        pytest.param("AbCdEfGhIjKlMnOpQrStUvx", id="extended"),
    ])
    async def test_a_handle_that_differs_at_all_locates_nothing(self, store, _db_transaction,
                                                                mangled):
        """A `TEXT` column under a case-insensitive collation, a `CHAR` column with its blank
        padding, or a store that trimmed would each turn one secret capability handle into a family
        of them."""
        planted = await self.plant(_db_transaction)
        assert mangled != planted, "the mangling must actually differ"
        async with _db_transaction() as session:
            assert await store.locate(session, mangled) is None

    async def test_an_unknown_handle_locates_nothing(self, store, _db_transaction):
        async with _db_transaction() as session:
            assert await store.locate(session, "ZZZZZZZZZZZZZZZZZZZZZZ") is None


@pytest.mark.asyncio(loop_scope="module")
class TestTheRollbackIsolatesEveryRow:
    """The operational proof that the store reads its session per call rather than caching one."""

    async def test_the_table_is_empty_at_the_start_of_a_test(self, _db_transaction):
        """Every case above committed at least one row. If any of them had reached the real
        database rather than the per-test transaction, this would be non-zero -- and the fixture's
        own teardown could not remove it."""
        assert await row_count(_db_transaction) == 0

    async def test_a_row_written_in_this_test_is_visible_and_still_rolls_back(self, store,
                                                                              _db_transaction):
        handle, _ = await issue(_db_transaction, store)
        assert await read(_db_transaction, handle) is not None
        assert await row_count(_db_transaction) == 1
