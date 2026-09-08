"""The verified store notification both providers fill, in this project's own field names.
A verified notification carries an attribution token: this module holds no logger, so none is logged."""
from dataclasses import dataclass
from datetime import datetime

from nativespeaker.api.tables.purchases import PurchaseProvider, SubscriptionStatus


@dataclass(frozen=True, slots=True)
class VerifiedNotification:
    """One store notification after verification, in this project's own field names."""

    provider: PurchaseProvider
    notification_uuid: str
    event_type: str
    external_id: str | None
    transaction_id: str | None
    product_id: str | None
    # Resolved by the provider's own class, so it is absent exactly when `product_id` is.
    tier_id: str | None
    attribution_token: str | None
    # The store's own word for this subscription, never derived from a date here.
    status: SubscriptionStatus
    signed_at: datetime | None
    purchased_at: datetime | None
    expires_at: datetime | None
    grace_period_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class RestoredSubscription:
    """One client-presented store proof after verification, carrying only what a restore consumes."""

    provider: PurchaseProvider
    # On the Google path this is the purchase token itself, which no log line may ever carry.
    external_id: str
    product_id: str | None
    # Resolved by the provider's own class, so a proof naming no mapped product never reaches here.
    tier_id: str
    attribution_token: str | None
    # Derived by the provider's own class from the artifact alone, which is the only source here.
    status: SubscriptionStatus
    purchased_at: datetime | None
    expires_at: datetime | None
    grace_period_expires_at: datetime | None
