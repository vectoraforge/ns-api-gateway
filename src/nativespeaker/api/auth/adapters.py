"""The providerData adapter seam: the interface an implementation satisfies, and the one value type a
successful read produces. Failure is raised, never returned."""
from dataclasses import dataclass
from typing import Protocol

from nativespeaker.api.tables.identities import IdentityProvider


@dataclass(frozen=True, slots=True)
class VerifiedProviderIdentity:
    """What one completed providerData read established: which provider owns the caller, and its uid.
    Every field here has already passed its rule -- the shape classified, the address verified."""

    provider: IdentityProvider
    # `None` exactly for the anonymous arm: `core.external_identities`' CHECK requires NULL there.
    provider_uid: str | None
    # Absent by default because an anonymous record has no verified address to carry.
    email: str | None = None


class FirebaseAdminAdapter(Protocol):
    """One configured integration, one client selected by issuer match, and no ambient fallback."""

    def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """The providerData read: the verified identity, or a raise."""
        ...
