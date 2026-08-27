"""The providerData adapter seam: an interface and the one value type a successful read produces, with no
provider SDK import and no I/O. Its implementation must make no provider call while a database lock is
held, must bound each attempt at a fixed 5-10 seconds, and must never leak provider text to clients.

Failure is raised, never returned: the rejections live in `auth/exceptions.py` and this module does not
name them. A read either produced a verified identity or it did not happen."""
from dataclasses import dataclass
from typing import Protocol

from nativespeaker.api.models.identities import IdentityProvider


@dataclass(frozen=True, slots=True)
class VerifiedProviderIdentity:
    """What one completed providerData read established: which provider owns the caller, and its uid.

    Every field here has already passed its rule -- the shape classified, and the address was both
    non-empty and verified. Adding a field would put an unjudged value on this path and let a
    consumer re-derive a decision the read already made; adding an unjudged *raw* field would let one
    apply a weaker rule than the read's.
    """

    provider: IdentityProvider
    # `None` exactly for the anonymous arm: `core.external_identities`' CHECK requires NULL there.
    provider_uid: str | None
    # Absent by default because an anonymous record has no verified address to carry.
    email: str | None = None


class FirebaseAdminAdapter(Protocol):
    """One configured integration, one client selected by issuer match, and no ambient fallback."""

    def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """The providerData read: the verified identity, or a raise. Never called on an ordinary path."""
        ...
