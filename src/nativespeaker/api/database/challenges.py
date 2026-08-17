"""`core.auth_challenges` access: one insert, one lookup, and the two atomic conditional
updates that are the whole serialization mechanism.

No lock is taken and no lock is held across anything: the claim is a single conditional UPDATE
in its own transaction, and the consume is a single conditional UPDATE inside the caller's short
consuming transaction.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from nativespeaker.api.auth.challenges import (
    ChallengeRow,
    ChallengeState,
    ClaimOutcome,
    ConsumeOutcome,
    IdentityBinding,
    challenge_state_from_columns,
)
from nativespeaker.api.auth.operations import AuthOperation, IdentityProvider

_COLUMNS = """id, challenge_id, operation, operation_variant, bound_external_identity_id,
              preauth_issuer, preauth_subject_hash, expires_at, claimed_at, claim_attempt_id,
              consumed_at"""

INSERT_CHALLENGE = text("""
    INSERT INTO core.auth_challenges (
        id, challenge_id, operation, operation_variant, bound_external_identity_id,
        preauth_issuer, preauth_subject_hash, expires_at, created_at)
    VALUES (:id, :challenge_id, :operation, :operation_variant, :bound_external_identity_id,
            :preauth_issuer, :preauth_subject_hash, :expires_at, now())
""")

SELECT_CHALLENGE = text(f"SELECT {_COLUMNS} FROM core.auth_challenges WHERE challenge_id = :challenge_id")

# The serialization point. One conditional update, conditioned on the row still being `issued`
# and on its `expires_at` still being in the future — the only place expiry is ever evaluated.
# The condition is also what keeps the lifecycle one-way: no update ever moves a row back.
# The stored row is the server source of truth for replay prevention: the `claimed_at IS NULL`
# predicate is what a replay loses against, and nothing the client holds is consulted.
# [impl->req~shared-completion-step-08~1]
# [impl->req~shared-challenge-lifecycle-one-way~1]
# [impl->req~schema-auth-challenges-source-of-truth-replay~1]
# [impl->req~schema-auth-challenges-no-purge-indefinite-retention~1]
CLAIM_CHALLENGE = text("""
    UPDATE core.auth_challenges
       SET claimed_at = now(), claim_attempt_id = :claim_attempt_id
     WHERE challenge_id = :challenge_id
       AND claimed_at IS NULL
       AND expires_at > now()
    RETURNING id
""")

# The consuming update: marks the row `consumed` and clears the pre-auth subject verifier in the
# same transition, conditioned on the row still being `claimed` under this attempt's
# `claim_attempt_id`. It never re-checks `expires_at`.
# [impl->req~shared-completion-step-12~1]
# [impl->req~shared-challenge-lifecycle-one-way~1]
CONSUME_CHALLENGE = text("""
    UPDATE core.auth_challenges
       SET consumed_at = now(), preauth_subject_hash = NULL
     WHERE challenge_id = :challenge_id
       AND claim_attempt_id = :claim_attempt_id
       AND claimed_at IS NOT NULL
       AND consumed_at IS NULL
    RETURNING id
""")


def _to_row(record: Any) -> ChallengeRow:
    # The lifecycle state is a reading of the three columns that carry it and of nothing else.
    # [impl->req~schema-auth-challenges-binds-lifecycle-state~2]
    state = challenge_state_from_columns(claimed_at=record.claimed_at,
                                         claim_attempt_id=record.claim_attempt_id,
                                         consumed_at=record.consumed_at)
    # A consumed pre-auth row keeps its plaintext issuer and carries a cleared verifier.
    binding = IdentityBinding(bound_external_identity_id=record.bound_external_identity_id,
                              preauth_issuer=record.preauth_issuer,
                              preauth_subject_hash=record.preauth_subject_hash)
    return ChallengeRow(challenge_id=record.challenge_id,
                        operation=AuthOperation(record.operation),
                        operation_variant=(IdentityProvider(record.operation_variant)
                                           if record.operation_variant else None),
                        binding=binding,
                        expires_at=record.expires_at,
                        state=state,
                        claim_attempt_id=record.claim_attempt_id,
                        id=record.id)


class ChallengesDB:
    """The `core.auth_challenges` store."""

    def __init__(self, session_factory: Any):
        self._session_factory = session_factory

    async def insert(self, row: ChallengeRow) -> None:
        """One row per issued challenge, keyed by `challenge_id`."""
        # [impl->req~shared-prepare-step-07~1]
        async with self._session_factory() as session:
            await session.execute(INSERT_CHALLENGE, {
                "id": row.id,
                "challenge_id": row.challenge_id,
                "operation": str(row.operation),
                "operation_variant": (str(row.operation_variant)
                                      if row.operation_variant is not None else None),
                "bound_external_identity_id": row.binding.bound_external_identity_id,
                "preauth_issuer": row.binding.preauth_issuer,
                "preauth_subject_hash": row.binding.preauth_subject_hash,
                "expires_at": row.expires_at,
            })
            await session.commit()

    async def get(self, challenge_id: str) -> ChallengeRow | None:
        async with self._session_factory() as session:
            return await self._read(session, challenge_id)

    async def _read(self, session: Any, challenge_id: str) -> ChallengeRow | None:
        result = await session.execute(SELECT_CHALLENGE, {"challenge_id": challenge_id})
        record = result.first()
        return _to_row(record) if record is not None else None

    async def claim(self, challenge_id: str, claim_attempt_id: UUID) -> ClaimOutcome:
        """Claim the row for this attempt. The conditional update decides; the follow-up read
        only classifies a miss for the audit record and mutates nothing."""
        # [impl->req~shared-completion-step-08~1]
        async with self._session_factory() as session:
            result = await session.execute(CLAIM_CHALLENGE, {
                "challenge_id": challenge_id, "claim_attempt_id": claim_attempt_id})
            if result.first() is not None:
                await session.commit()
                return ClaimOutcome.claimed
            await session.rollback()
            row = await self._read(session, challenge_id)
            if row is None:
                return ClaimOutcome.not_found
            if row.state is ChallengeState.issued:
                return ClaimOutcome.expired
            return ClaimOutcome.already_used

    async def consume(self, session: Any, challenge_id: str,
                      claim_attempt_id: UUID) -> ConsumeOutcome:
        """Consume the claim-holding attempt's row inside that attempt's transaction. A retry
        under the same `claim_attempt_id` recognizes its own claim instead of reading it as a
        conflicting duplicate."""
        # [impl->req~shared-completion-step-12~1]
        result = await session.execute(CONSUME_CHALLENGE, {
            "challenge_id": challenge_id, "claim_attempt_id": claim_attempt_id})
        if result.first() is not None:
            return ConsumeOutcome.consumed
        row = await self._read(session, challenge_id)
        if (row is not None and row.state is ChallengeState.consumed
                and row.claim_attempt_id == claim_attempt_id):
            return ConsumeOutcome.already_consumed_by_this_attempt
        return ConsumeOutcome.lost
