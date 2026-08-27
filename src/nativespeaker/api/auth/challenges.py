"""The challenge store. A handle is a secret capability: this module holds no logger, so none is logged."""
import base64
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.auth.exceptions import ChallengeConsumed, ChallengeIdentityMismatch
from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.models.auth import AuthChallenge, AuthOperation

# One universal TTL for every operation: no per-operation override, no grace period, no renewal.
CHALLENGE_TTL_SECONDS = 300

# CSPRNG bytes before base64url encoding -- 16 bytes becomes a 22-character handle.
CHALLENGE_ID_BYTES = 16


def new_challenge_id() -> str:
    """A fresh opaque handle: 16 CSPRNG bytes, base64url, unpadded, with nothing in it to parse."""
    return base64.urlsafe_b64encode(secrets.token_bytes(CHALLENGE_ID_BYTES)).rstrip(b"=").decode()


class ChallengeStore:
    """The four operations. No method commits, and the session is a parameter so tests can swap it."""

    def __init__(self, keyring: HmacKeyring) -> None:
        self._keyring = keyring

    def __repr__(self) -> str:
        return f"ChallengeStore(ttl_seconds={CHALLENGE_TTL_SECONDS})"

    async def issue(self, session: AsyncSession, *,
                    operation: AuthOperation,
                    identity: LinkedIdentity | PreAuthIdentity,
                    now: datetime) -> tuple[str, datetime]:
        """Insert one row, returning only `(challenge_id, expires_at)`: from the caller's `now`, never renewed."""
        challenge_id = new_challenge_id()
        expires_at = now + timedelta(seconds=CHALLENGE_TTL_SECONDS)

        bound_identity_id = None
        preauth_issuer = None
        preauth_subject_hash = None
        if isinstance(identity, LinkedIdentity):
            bound_identity_id = identity.identity.id
        else:
            preauth_issuer = identity.issuer
            preauth_subject_hash = self._keyring.actor_subject_hash(identity.issuer,
                                                                   identity.subject)

        session.add(AuthChallenge(challenge_id=challenge_id,
                                  operation=operation,
                                  bound_external_identity_id=bound_identity_id,
                                  preauth_issuer=preauth_issuer,
                                  preauth_subject_hash=preauth_subject_hash,
                                  expires_at=expires_at,
                                  created_at=now))
        await session.flush()
        return challenge_id, expires_at

    async def locate(self, session: AsyncSession, challenge_id: str) -> AuthChallenge | None:
        """Look the row up by byte-for-byte equality. `None` is a definitive no-row; an outage raises."""
        statement = select(AuthChallenge).where(col(AuthChallenge.challenge_id) == challenge_id)
        return (await session.exec(statement)).first()

    async def claim(self, session: AsyncSession, *,
                    challenge_id: str,
                    claim_attempt_id: UUID,
                    now: datetime) -> bool:
        """Move issued -> claimed. The one serialization point and the only expiry check; `True` wins it."""
        result = await session.exec(
            update(AuthChallenge)
            .where(col(AuthChallenge.challenge_id) == challenge_id,
                   col(AuthChallenge.claimed_at).is_(None),
                   col(AuthChallenge.expires_at) > now)
            .values(claimed_at=now, claim_attempt_id=claim_attempt_id)
            .returning(col(AuthChallenge.id)))
        return len(result.all()) == 1

    async def consume(self, session: AsyncSession, *,
                      challenge_id: str,
                      claim_attempt_id: UUID,
                      now: datetime) -> bool:
        """Move claimed -> consumed, clearing `preauth_subject_hash` in the same statement the CHECK needs."""
        result = await session.exec(
            update(AuthChallenge)
            .where(col(AuthChallenge.challenge_id) == challenge_id,
                   col(AuthChallenge.claimed_at).is_not(None),
                   col(AuthChallenge.consumed_at).is_(None),
                   col(AuthChallenge.claim_attempt_id) == claim_attempt_id)
            .values(consumed_at=now, preauth_subject_hash=None)
            .returning(col(AuthChallenge.id)))
        return len(result.all()) == 1

    def verify_binding(self, row: AuthChallenge,
                       identity: LinkedIdentity | PreAuthIdentity) -> None:
        """The completion comparison. It returns when the binding matches, and raises what it earned otherwise.

        The raises carry nothing: the caller is pre-claim, so the rejection travels out through
        `get_db`'s rollback, and a field read on the far side of that would be I/O outside a
        greenlet. Keyed material still compares only via the keyring.
        """
        if row.bound_external_identity_id is not None:
            if (isinstance(identity, LinkedIdentity)
                    and identity.identity.id == row.bound_external_identity_id):
                return
            raise ChallengeIdentityMismatch()

        # The pre-auth arm. A cleared hash is never compared: the row takes the already-used answer.
        if row.preauth_subject_hash is None:
            raise ChallengeConsumed()
        if row.preauth_issuer != identity.issuer:
            raise ChallengeIdentityMismatch()
        if not self._keyring.actor_subject_matches(row.preauth_subject_hash,
                                                   identity.issuer, identity.subject):
            raise ChallengeIdentityMismatch()
