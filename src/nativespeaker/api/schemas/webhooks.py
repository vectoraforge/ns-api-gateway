"""The store-callback request bodies. Each field keeps its store's camelCase spelling as sent."""
from pydantic import BaseModel, Field

APP_STORE_ENVELOPE_LIMIT = 65536
PUBSUB_DATA_LIMIT = 16384


class AppStoreNotificationRequest(BaseModel):
    """The App Store notification body: the signed envelope, and nothing else."""
    # Required and non-empty, so an unusable body is the framework's 422 rather than a verification 401.
    # Bounded well above a signed envelope and its certificate chain: this route authenticates nobody.
    signedPayload: str = Field(..., min_length=1, max_length=APP_STORE_ENVELOPE_LIMIT)


class PubSubPushMessage(BaseModel):
    """The Pub/Sub message this push carries: the RTDN as base64 text, and nothing else."""
    data: str = ""  # Do not bound this field. Pub/Sub retries every 422 forever.


class PubSubPushRequest(BaseModel):
    """The Cloud Pub/Sub push body: one message, and the subscription that delivered it."""
    message: PubSubPushMessage
    subscription: str | None = None
