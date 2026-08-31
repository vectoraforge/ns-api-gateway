"""The challenge store against the real core.auth_challenges table: claim, expiry and lifecycle."""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from e2e.conftest import seed_identity
from nativespeaker.api.errors import ChallengeConsumed, ChallengeIdentityMismatch
from nativespeaker.api.schemas.auth import Identity
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.identities import IdentityProvider

pytestmark = pytest.mark.e2e

ISSUER = "https://securetoken.google.com/challenge-store-test"
SUBJECT = "challenge-store-subject"

# Eight, not two: two contenders can both "win" a broken claim and still look like a coin toss.
CONTENDERS = 8


@pytest.fixture
def store(_app_lifespan):
    """The store the real lifespan constructed, so the wiring is exercised."""
    return _app_lifespan.state.challenge_store


def preauth(subject: str = SUBJECT, *, issuer: str = ISSUER) -> Identity:
    return Identity(issuer=issuer, subject=subject)


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
    """Read a row back through the same factory the store wrote through, never a fresh engine."""
    async with factory() as session:
        return (await session.exec(select(AuthChallenge)
                                   .where(col(AuthChallenge.challenge_id) == handle))).first()


async def row_count(factory) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(AuthChallenge))


@pytest_asyncio.fixture(loop_scope="module")
async def _contended_challenge(_app_lifespan, store):
    """One committed challenge and CONTENDERS connections from a second engine, since the shared one is serial."""
    config = _app_lifespan.state.config
    engine = create_async_engine(config.db.url, pool_size=CONTENDERS + 2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    now = datetime.now(UTC)
    handle, _ = await issue(factory, store, now=now)

    # Each contender checks a connection out and then waits, so the barrier releases eight live transactions.
    barrier = asyncio.Barrier(CONTENDERS)

    async def contend() -> bool:
        async with factory() as session:
            await session.connection()
            await barrier.wait()
            won = await store.claim(session, challenge_id=handle, now=now)
            await session.commit()
            return won

    results = await asyncio.gather(*(contend() for _ in range(CONTENDERS)),
                                   return_exceptions=True)
    try:
        yield handle, results, factory
    finally:
        # These rows are committed, so they outlive the per-test transaction and must be removed here.
        async with factory() as session:
            await session.exec(delete(AuthChallenge)  # ty: ignore[invalid-argument-type]
                               .where(col(AuthChallenge.challenge_id) == handle))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio(loop_scope="module")
class TestTheClaimSerializesConcurrentAttempts:
    """Exactly one completion attempt can ever win a challenge."""

    async def test_no_contender_raised(self, _contended_challenge):
        """Asserted first: an exception is neither a win nor a loss, so the counts below would pass anyway."""
        _, results, _ = _contended_challenge
        assert [r for r in results if isinstance(r, BaseException)] == []

    async def test_exactly_one_of_eight_concurrent_claims_wins(self, _contended_challenge):
        _, results, _ = _contended_challenge
        assert results.count(True) == 1
        assert results.count(False) == CONTENDERS - 1

    async def test_the_losers_mutated_nothing(self, _contended_challenge):
        """Seven transactions committed after matching zero rows: one row, claimed once, consumed by nobody."""
        handle, _, factory = _contended_challenge
        row = await read(factory, handle)
        assert row.claimed_at is not None
        assert row.consumed_at is None
        assert row.preauth_subject is not None
        async with factory() as session:
            same = await session.scalar(select(func.count()).select_from(AuthChallenge)
                                        .where(col(AuthChallenge.challenge_id) == handle))
        assert same == 1


@pytest.mark.asyncio(loop_scope="module")
class TestTheClaimIsTheOnlyPlaceExpiryIsEvaluated:
    """Issued with a now far enough in the past that expires_at has passed, then claimed at the real time."""

    async def test_a_claim_against_an_expired_row_returns_false(self, store, _db_transaction):
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        handle, expires_at = await issue(_db_transaction, store, now=long_ago)
        assert expires_at < datetime.now(UTC), "the fixture must actually be expired"

        async with _db_transaction() as session:
            assert await store.claim(session, challenge_id=handle,
                                     now=datetime.now(UTC)) is False
            await session.commit()

    async def test_an_expired_row_is_left_unclaimed(self, store, _db_transaction):
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        handle, _ = await issue(_db_transaction, store, now=long_ago)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, now=datetime.now(UTC))
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.claimed_at is None

    async def test_locate_still_returns_an_expired_row(self, store, _db_transaction):
        """A lookup filtering on expires_at would make an expired handle indistinguishable from an unknown one."""
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        handle, _ = await issue(_db_transaction, store, now=long_ago)
        async with _db_transaction() as session:
            located = await store.locate(session, handle)
        assert located is not None
        assert located.expires_at < datetime.now(UTC)

    async def test_a_row_one_second_from_expiry_still_claims(self, store, _db_transaction):
        """The boundary from the other side, so the case above cannot pass for a claim that rejects all."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            claimed = await store.claim(session, challenge_id=handle,
                                        now=now + timedelta(seconds=299))
            await session.commit()
        assert claimed is True


@pytest.mark.asyncio(loop_scope="module")
class TestTheLifecycleRunsOneDirectionOnly:
    """issued -> claimed -> consumed: never back, never again, never by a later attempt."""

    async def test_a_second_claim_of_a_claimed_row_returns_false(self, store, _db_transaction):
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            assert await store.claim(session, challenge_id=handle, now=now) is True
            assert await store.claim(session, challenge_id=handle, now=now) is False
            await session.commit()

    async def test_a_second_claim_does_not_change_the_stored_claim_time(self, store,
                                                                        _db_transaction):
        """The loser matched no row, so the winner's claimed_at is what a later read still sees."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, now=now)
            await store.claim(session, challenge_id=handle, now=now + timedelta(seconds=60))
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.claimed_at == now

    async def test_consume_before_any_claim_returns_false(self, store, _db_transaction):
        """Consumption requires a claim. Skipping the claim would skip the serialization point."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            assert await store.consume(session, challenge_id=handle, now=now) is False
            await session.commit()

        assert (await read(_db_transaction, handle)).consumed_at is None

    async def test_a_consume_without_a_claim_changes_nothing(self, store, _db_transaction):
        """A rejected consume must not half-apply: neither column moves."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.consume(session, challenge_id=handle, now=now)
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.consumed_at is None
        assert row.preauth_subject is not None

    async def test_consume_under_the_winning_attempt_sets_consumed_at(self, store,
                                                                      _db_transaction):
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, now=now)
            assert await store.consume(session, challenge_id=handle, now=now) is True
            await session.commit()

        assert (await read(_db_transaction, handle)).consumed_at is not None

    async def test_consume_clears_the_preauth_subject_on_a_preauth_bound_row(self, store,
                                                                             _db_transaction):
        """Both column changes land in one UPDATE; the binding CHECK would reject a two-statement consume."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        assert (await read(_db_transaction, handle)).preauth_subject is not None

        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, now=now)
            await store.consume(session, challenge_id=handle, now=now)
            await session.commit()

        row = await read(_db_transaction, handle)
        assert row.preauth_subject is None
        assert row.preauth_issuer == ISSUER, "the plaintext issuer is not cleared (ruling 9.3)"

    async def test_a_second_consume_of_a_consumed_row_returns_false(self, store, _db_transaction):
        """The WHERE keys on consumed_at IS NULL alone now, so a replay still matches no row."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, now=now)
            assert await store.consume(session, challenge_id=handle, now=now) is True
            assert await store.consume(session, challenge_id=handle, now=now) is False
            await session.commit()

    async def test_a_consumed_row_is_never_returned_to_issued(self, store, _db_transaction):
        """No reclaim, no reissue, no reuse: the claim's claimed_at IS NULL makes that structural."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, now=now)
            await store.consume(session, challenge_id=handle, now=now)
            assert await store.claim(session, challenge_id=handle, now=now) is False
            await session.commit()


@pytest.mark.asyncio(loop_scope="module")
class TestTheBindingAgainstRealRows:
    """Asserted against rows PostgreSQL accepted and read back, not ones built in memory."""

    async def test_a_linked_bound_row_matches_its_own_identity(self, store, _db_transaction):
        """The linked arm needs a real identity row, because bound_external_identity_id carries a foreign key."""
        user, identity = await seed_identity(_db_transaction, issuer=ISSUER, subject=SUBJECT)
        context = Identity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)
        handle, _ = await issue(_db_transaction, store, context,
                                operation=AuthOperation.claim_registered_grant)

        row = await read(_db_transaction, handle)
        assert row.bound_external_identity_id == identity.id
        assert store.verify_binding(row, context) is row

    async def test_a_linked_bound_row_rejects_a_different_identity(self, store, _db_transaction):
        user, identity = await seed_identity(_db_transaction, issuer=ISSUER, subject=SUBJECT)
        other_user, other_identity = await seed_identity(_db_transaction, issuer=ISSUER,
                                                         subject="a-different-subject",
                                                         provider=IdentityProvider.apple)
        context = Identity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)
        intruder = Identity(user=other_user, identity=other_identity, issuer=ISSUER,
                                  subject="a-different-subject")
        handle, _ = await issue(_db_transaction, store, context,
                                operation=AuthOperation.claim_registered_grant)

        row = await read(_db_transaction, handle)
        with pytest.raises(ChallengeIdentityMismatch):
            store.verify_binding(row, intruder)

    async def test_a_rejected_binding_leaves_the_challenge_unconsumed(self, store,
                                                                      _db_transaction):
        """A bound-context mismatch is rejected before the claim, so a wrong identity burns nobody's challenge."""
        user, identity = await seed_identity(_db_transaction, issuer=ISSUER, subject=SUBJECT)
        other_user, other_identity = await seed_identity(_db_transaction, issuer=ISSUER,
                                                         subject="a-different-subject",
                                                         provider=IdentityProvider.apple)
        context = Identity(user=user, identity=identity, issuer=ISSUER, subject=SUBJECT)
        intruder = Identity(user=other_user, identity=other_identity, issuer=ISSUER,
                                  subject="a-different-subject")
        handle, _ = await issue(_db_transaction, store, context,
                                operation=AuthOperation.claim_registered_grant)

        with pytest.raises(ChallengeIdentityMismatch):
            store.verify_binding(await read(_db_transaction, handle), intruder)

        row = await read(_db_transaction, handle)
        assert row.claimed_at is None
        assert row.consumed_at is None

    async def test_a_preauth_row_read_back_carries_the_subject_it_was_issued_for(self, store,
                                                                                   _db_transaction):
        """The subject survives the TEXT round trip unaltered, which is what the comparison depends on."""
        handle, _ = await issue(_db_transaction, store)
        row = await read(_db_transaction, handle)
        assert row.preauth_subject == SUBJECT
        assert store.verify_binding(row, preauth()) is row

    async def test_a_consumed_preauth_row_takes_the_already_used_rejection(self, store,
                                                                           _db_transaction):
        """Consume clears the subject, so the row read back rejects challenge_consumed, not a mismatch."""
        now = datetime.now(UTC)
        handle, _ = await issue(_db_transaction, store, now=now)
        async with _db_transaction() as session:
            await store.claim(session, challenge_id=handle, now=now)
            await store.consume(session, challenge_id=handle, now=now)
            await session.commit()

        row = await read(_db_transaction, handle)
        with pytest.raises(ChallengeConsumed):
            store.verify_binding(row, preauth())


@pytest.mark.asyncio(loop_scope="module")
class TestLocateIsByteForByteAgainstPostgres:
    """Asserted against the crud's own comparison, with a fixed handle so the manglings are deterministic."""

    PLANTED = "AbCdEfGhIjKlMnOpQrStUv"

    async def plant(self, factory) -> str:
        async with factory() as session:
            now = datetime.now(UTC)
            session.add(AuthChallenge(challenge_id=self.PLANTED,
                                      operation=AuthOperation.claim_anonymous_grant,
                                      preauth_issuer=ISSUER,
                                      preauth_subject=SUBJECT,
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
        """A case-insensitive collation, CHAR blank padding, or a trimming store would turn one handle into many."""
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
        """Every case above wrote a row, so a non-zero count means one escaped the per-test transaction."""
        assert await row_count(_db_transaction) == 0

    async def test_a_row_written_in_this_test_is_visible_and_still_rolls_back(self, store,
                                                                              _db_transaction):
        handle, _ = await issue(_db_transaction, store)
        assert await read(_db_transaction, handle) is not None
        assert await row_count(_db_transaction) == 1
