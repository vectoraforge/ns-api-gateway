"""The mapped rows of the migrated schema, and the one rule this package holds to.
`migrations/` owns every index and every referential action: no field here declares one, so
`SQLModel.metadata` never states a second version of the schema that could drift from that file.
"""
__all__ = [
    "AccessGrant", "AccessGrantSource", "AccessGrantStatus", "AccessTier",
    "AuthChallenge", "AuthOperation", "FREE_GRANT_SOURCES",
    "Chat", "ChatRole",
    "ExternalIdentity", "IdentityProvider",
    "IdentityState", "Message", "NativeClaimProvider",
    "PurchaseProvider", "StorePurchase", "StorePurchaseToken", "Subscription",
    "SubscriptionEvent", "SubscriptionStatus", "User",
    "UserMonthlyUsage", "monthly_period_for",
]

from nativespeaker.api.tables.auth import AuthChallenge, AuthOperation
from nativespeaker.api.tables.chats import Chat, ChatRole, Message
from nativespeaker.api.tables.grants import (
    FREE_GRANT_SOURCES,
    AccessGrant,
    AccessGrantSource,
    AccessGrantStatus,
    AccessTier,
    UserMonthlyUsage,
    monthly_period_for,
)
from nativespeaker.api.tables.identities import (
    ExternalIdentity,
    IdentityProvider,
    IdentityState,
    NativeClaimProvider,
)
from nativespeaker.api.tables.purchases import (
    PurchaseProvider,
    StorePurchase,
    StorePurchaseToken,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)
from nativespeaker.api.tables.users import User
