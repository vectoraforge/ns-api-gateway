"""§6 the challenge store -- issue, locate, claim, consume, and the §6.4 binding comparison.

Phases 37, 40, 41 and 42 implement `create_user`, `upgrade_anonymous_to_registered`,
`claim_anonymous_grant` and `claim_registered_grant` against this module and build nothing of their
own.

**The claim is the entire mutual-exclusion mechanism.** One conditional `UPDATE` conditioned on the
row still being issued *and* still unexpired is the serialization point for the whole protocol:
exactly one completion attempt can ever win it, and every other attempt matches zero rows and
mutates nothing. There is no lock, no lease, no advisory lock, no multi-phase commit, and no
application-side mutex anywhere in this design -- SHARED-INVARIANTS forbids each of them in every
phase, and a second serialization point would be one that can disagree with the first.

**The claim is also the only place expiry is ever evaluated.** No earlier step reads `expires_at`
and nothing downstream is time-gated. Two places evaluating one deadline is two answers.

**A claimed challenge is dead** (§6.2). Any failure after the claim consumes it, and an attempt
that crashes or is abandoned leaves the row claimed forever. There is no cleanup job, no recovery
scan, no reissue path, and no reclaim by a later attempt: expired, claimed and consumed rows are
retained indefinitely. That is the design, not an omission -- the client's only remedy is a fresh
prepare inside the 300-second TTL.

**The handle is a secret capability.** Possession is the only thing that locates a row, so it is
body-only transport and must never reach a URL, an audit row, a log, a trace, analytics, or error
text. Correlate with the non-secret `core.auth_challenges.id`. This module holds no logger at all,
which is what makes "the raw malformed identifier is never logged" structural rather than a
convention someone has to remember.

**No proof material is bound here** -- no restore proof, no reassignment target, no source
identity, no integrity or attestation material, no IP, no device, no TLS binding, no DPoP, no mTLS,
no token hash. A challenge binds an operation, a variant, and exactly one identity.

**Rejection ordering the store enforces for its callers** (§6.4). An unknown handle, a
bound-context mismatch, and an operation mismatch are all rejected **before** the claim and leave
any located challenge unconsumed, so a wrong-endpoint or wrong-identity presentation can never burn
the rightful user's in-flight challenge. The operation-*variant* comparison is the exception: it
runs on the already-claimed row and is a consuming rejection.

Every method here is transaction-neutral: none of them commits. `issue` flushes into the caller's
prepare transaction, and `consume` runs inside the caller's consuming transaction atomically with
the audit row and any mutation.
"""
import base64
import secrets
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.auth.context import LinkedIdentity, PreAuthIdentity
from nativespeaker.api.auth.keys import HmacKeyring
from nativespeaker.api.models.auth import AuthChallenge, AuthOperation
from nativespeaker.api.models.identities import IdentityProvider

# §6.3. The single universal TTL for every challenge-issuing operation. No per-operation override
# in either direction, no grace period, and no sliding renewal on retry.
CHALLENGE_TTL_SECONDS = 300

# §6.1. CSPRNG bytes before base64url encoding -- 16 bytes becomes a 22-character handle.
CHALLENGE_ID_BYTES = 16


def new_challenge_id() -> str:
    """A fresh opaque handle: 16 CSPRNG bytes, base64url, unpadded, 22 characters.

    §6.1 pins this format. Not a UUID -- `uuid7` leaks its creation time and `uuid4` advertises its
    own structure -- not a counter, and not a token format. There is nothing to parse and nothing
    to verify: the value's only meaning is that it locates a row.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(CHALLENGE_ID_BYTES)).rstrip(b"=").decode()


class ChallengeRejection(StrEnum):
    """The five §6 rejections. Every member's value is also a `core.auth_event_result` member, so a
    caller writing the audit row can use it directly rather than keeping a private mapping table.

    None of these is client-visible: they all surface as `challenge_required` (409).
    """
    challenge_not_found = "challenge_not_found"
    challenge_expired = "challenge_expired"
    challenge_consumed = "challenge_consumed"
    challenge_identity_mismatch = "challenge_identity_mismatch"
    challenge_operation_mismatch = "challenge_operation_mismatch"


class ChallengeStore:
    """The §6.1 four operations. One instance lives on `app.state.challenge_store`.

    The session is a parameter on every method rather than held on the instance, for the same
    reason the audit writer takes one: the e2e rollback fixture swaps `app.state.session_factory`
    per test, and an instance that captured a session at construction would write outside it.
    """

    def __init__(self, keyring: HmacKeyring) -> None:
        self._keyring = keyring

    def __repr__(self) -> str:
        return f"ChallengeStore(ttl_seconds={CHALLENGE_TTL_SECONDS})"

    async def issue(self, session: AsyncSession, *,
                    operation: AuthOperation,
                    operation_variant: IdentityProvider | None,
                    identity: LinkedIdentity | PreAuthIdentity,
                    now: datetime) -> tuple[str, datetime]:
        """Insert one issued row and return exactly `(challenge_id, expires_at)`.

        Nothing else about the challenge is ever disclosed (§6.1) -- not the row id, not the
        binding, not the operation. Operation, variant, identity binding and `expires_at` are
        authoritative only in the server-side row, which is why no signing key and no
        challenge-token format exists.

        `expires_at` comes from the server's own clock via the request's single captured evaluation
        time. It is never client-supplied, never extended, and never renewed.

        §6.4's two arms are mutually exclusive, and the table's CHECK enforces that. A pre-auth
        binding stores `preauth_issuer` in plaintext -- it is a deployment-known provider string
        shared by every user of that provider -- and the subject only as the keyed hash from the
        **shared** derivation, under the active key, with no version recorded on the row.
        """
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
                                  operation_variant=operation_variant,
                                  bound_external_identity_id=bound_identity_id,
                                  preauth_issuer=preauth_issuer,
                                  preauth_subject_hash=preauth_subject_hash,
                                  expires_at=expires_at,
                                  created_at=now))
        await session.flush()
        return challenge_id, expires_at

    async def locate(self, session: AsyncSession, challenge_id: str) -> AuthChallenge | None:
        """Look the row up by **byte-for-byte** equality against the stored value.

        No trimming, no decoding and re-encoding, no case-folding, no defaulting -- each of those
        would widen a secret capability handle into a family of handles.

        `None` means a definitive no-row, which the caller rejects as `challenge_not_found`. A
        database outage during lookup is **not** `challenge_not_found`: it raises out of here and
        stays the ordinary infrastructure failure, because answering "no such challenge" to an
        unreachable database would tell a legitimate client to throw away a challenge that exists.
        """
        statement = select(AuthChallenge).where(col(AuthChallenge.challenge_id) == challenge_id)
        return (await session.exec(statement)).first()

    async def claim(self, session: AsyncSession, *,
                    challenge_id: str,
                    claim_attempt_id: UUID,
                    now: datetime) -> bool:
        """Move the row `issued -> claimed` under this attempt's id. The serialization point.

        One conditional `UPDATE`. `True` for the single winner; `False` for every other attempt,
        which matched zero rows and mutated nothing. A no-match rejects immediately -- before any
        proof verification and before any provider call -- and the caller distinguishes the two
        reasons by re-reading the located row rather than by issuing a second conditional update:
        `challenge_expired` where the row is still issued but expired, `challenge_consumed` where
        it is already claimed or consumed.

        `expires_at > now` in this WHERE is the **only** expiry evaluation in the entire protocol.

        The affected-row count comes from `returning`, not `rowcount`, which is not dependable
        under the e2e harness's `join_transaction_mode="create_savepoint"`. `== 1` rather than
        `>= 1` so a multi-row match is a detectable bug rather than a silent success.
        """
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
        """Move the row `claimed -> consumed`, under **this** attempt's claim id only.

        One conditional `UPDATE` that sets `consumed_at` and clears `preauth_subject_hash` in the
        **same** statement. Two statements would trip the table's binding CHECK, which admits a
        cleared hash only once `consumed_at` is set. Clearing is part of the state transition, not
        a change of identity -- which is why a cleared row is later rejected as already-used rather
        than as a mismatch.

        Runs inside the caller's consuming transaction, atomically with the audit row and any
        mutation, and does not commit. `False` under any other `claim_attempt_id`, and `False` on a
        second call under the winning one: the lifecycle runs one direction only.
        """
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
                       identity: LinkedIdentity | PreAuthIdentity) -> ChallengeRejection | None:
        """§6.4's completion comparison. `None` means the binding matches.

        A **linked** binding matches only when the request's resolved `external_identity_id` equals
        `bound_external_identity_id`. A pre-auth request resolved to no identity row at all, so it
        matches no linked binding.

        A **pre-auth** binding matches only when `preauth_issuer` equals the request's
        backend-verified issuer *and* the stored hash equals the one recomputed from the request's
        backend-verified subject -- even if that subject has since become linked. What fails a
        pre-auth binding is a differing hash, not the request's current variant.

        A pre-auth-bound row whose hash has already been **cleared is not compared at all**: the
        keyring is never consulted and the row takes the already-used rejection.

        The hash comparison runs through `HmacKeyring.actor_subject_matches`, which wraps
        `hmac.compare_digest`. There is deliberately no `compare_digest` call written here: plan 08
        shipped that comparison as part of the keyed-hashing seam precisely so the audit writer and
        this store would not each grow their own `stored == recomputed`. `==` on keyed material
        returns the identical answer while leaking position information through timing, so nothing
        but the seam is acceptable.

        This does not compare the operation or the variant. The operation belongs to the caller's
        pre-claim checks alongside this one; the variant is a consuming rejection evaluated after
        the claim, and putting it here would make it a pre-claim one.
        """
        if row.bound_external_identity_id is not None:
            if (isinstance(identity, LinkedIdentity)
                    and identity.identity.id == row.bound_external_identity_id):
                return None
            return ChallengeRejection.challenge_identity_mismatch

        # The pre-auth arm. The table's CHECK admits no third shape, so a row reaching here with a
        # NULL `preauth_issuer` is unresolvable stored state -- the issuer comparison below fails
        # closed on it rather than treating an absent binding as a match.
        if row.preauth_subject_hash is None:
            return ChallengeRejection.challenge_consumed
        if row.preauth_issuer != identity.issuer:
            return ChallengeRejection.challenge_identity_mismatch
        if not self._keyring.actor_subject_matches(row.preauth_subject_hash,
                                                   identity.issuer, identity.subject):
            return ChallengeRejection.challenge_identity_mismatch
        return None
