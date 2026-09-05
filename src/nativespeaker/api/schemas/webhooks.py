"""The store-callback request bodies. Each field keeps its store's camelCase spelling as sent."""
from pydantic import BaseModel, Field


class AppStoreNotificationRequest(BaseModel):
    """The App Store notification body: the signed envelope, and nothing else."""
    # Required and non-empty, so an unusable body is the framework's 422 rather than a verification 401.
    signedPayload: str = Field(..., min_length=1)


class PubSubPushMessage(BaseModel):
    """The Pub/Sub message this push carries: its own id, and the RTDN as base64 text."""
    messageId: str
    # The transport envelope only: the base64 and JSON decoding happen after the token check.
    data: str = Field(..., min_length=1)


class PubSubPushRequest(BaseModel):
    """The Cloud Pub/Sub push body: one message, and the subscription that delivered it."""
    message: PubSubPushMessage
    subscription: str | None = None
