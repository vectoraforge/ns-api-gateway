"""The challenge store. A handle is a secret capability: this module holds no logger, so none is logged."""
import base64
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.jwt_verifier import VerifiedClaims
from nativespeaker.api.errors import ChallengeConsumed, ChallengeIdentityMismatch
from nativespeaker.api.schemas.auth import LinkedIdentity
from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation

# One universal TTL for every operation: no per-operation override, no grace period, no renewal.
CHALLENGE_TTL_SECONDS = 300

# CSPRNG bytes before base64url encoding -- 16 bytes becomes a 22-character handle.
CHALLENGE_ID_BYTES = 16


def new_challenge_id() -> str:
    """A fresh opaque handle: 16 CSPRNG bytes, base64url, unpadded, with nothing in it to parse."""
    return base64.urlsafe_b64encode(secrets.token_bytes(CHALLENGE_ID_BYTES)).rstrip(b"=").decode()


def verify_binding(row: AuthChallenge, claims: VerifiedClaims,
                   linked: LinkedIdentity | None) -> AuthChallenge:
    """Return `row` when the caller is the presenter it was bound to, and raise otherwise."""
    if row.bound_external_identity_id is not None:
        if linked is not None and linked.identity.id == row.bound_external_identity_id:
            return row
        raise ChallengeIdentityMismatch()

    # A cleared subject is never compared: the row takes the already-used answer.
    if row.preauth_subject is None:
        raise ChallengeConsumed()
    if row.preauth_issuer != claims.issuer:
        raise ChallengeIdentityMismatch()
    if row.preauth_subject != claims.subject:
        raise ChallengeIdentityMismatch()
    return row


def _claim_statement(challenge_id: str):
    """The claim UPDATE, module-level so a test compiles this statement rather than a mirror of it."""
    return (update(AuthChallenge)
            .where(col(AuthChallenge.challenge_id) == challenge_id,
                   col(AuthChallenge.claimed_at).is_(None),
                   col(AuthChallenge.expires_at) > func.clock_timestamp())
            .values(claimed_at=func.clock_timestamp())
            .returning(col(AuthChallenge.id)))


class ChallengesDB:
    """The four operations. No method commits."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def __repr__(self) -> str:
        return f"ChallengesDB(ttl_seconds={CHALLENGE_TTL_SECONDS})"

    async def issue(self, *,
                    operation: AuthOperation,
                    claims: VerifiedClaims,
                    linked: LinkedIdentity | None) -> tuple[str, datetime]:
        """Insert one row, returning only `(challenge_id, expires_at)`, and never renew it."""
        instant = datetime.now(UTC)
        challenge_id = new_challenge_id()
        expires_at = instant + timedelta(seconds=CHALLENGE_TTL_SECONDS)

        bound_identity_id = None
        preauth_issuer = None
        preauth_subject = None
        if linked is not None:
            bound_identity_id = linked.identity.id
        else:
            preauth_issuer = claims.issuer
            preauth_subject = claims.subject

        self.session.add(AuthChallenge(challenge_id=challenge_id,
                                       operation=operation,
                                       bound_external_identity_id=bound_identity_id,
                                       preauth_issuer=preauth_issuer,
                                       preauth_subject=preauth_subject,
                                       expires_at=expires_at,
                                       created_at=instant))
        await self.session.flush()
        return challenge_id, expires_at

    async def locate(self, challenge_id: str) -> AuthChallenge | None:
        """Look the row up by byte-for-byte equality. `None` is a definitive no-row; an outage raises."""
        statement = select(AuthChallenge).where(col(AuthChallenge.challenge_id) == challenge_id)
        return (await self.session.exec(statement)).first()

    async def claim(self, *, challenge_id: str) -> bool:
        """Move issued -> claimed. The one serialization point and the only expiry check; `True` wins it."""
        result = await self.session.exec(_claim_statement(challenge_id))
        return len(result.all()) == 1

    async def consume(self, *, challenge_id: str) -> bool:
        """Move claimed -> consumed, clearing `preauth_subject` in the same statement the CHECK needs."""
        result = await self.session.exec(
            update(AuthChallenge)
            .where(col(AuthChallenge.challenge_id) == challenge_id,
                   col(AuthChallenge.claimed_at).is_not(None),
                   col(AuthChallenge.consumed_at).is_(None))
            .values(consumed_at=func.clock_timestamp(), preauth_subject=None)
            .returning(col(AuthChallenge.id)))
        return len(result.all()) == 1
