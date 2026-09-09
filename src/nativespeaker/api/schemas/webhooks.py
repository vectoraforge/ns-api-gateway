"""The store-callback request bodies. Each field keeps its store's camelCase spelling as sent."""
from pydantic import BaseModel, Field

# Apple transmits its certificate chain three times in one envelope — once in the outer JWS header,
# and once inside each of `data.signedTransactionInfo` and `data.signedRenewalInfo`, which are
# themselves base64 members of the outer payload and so pay a second 4/3 inflation. Chain material
# alone runs to roughly 12 KB, and a real V2 notification lands in the 18-24 KB range.
APP_STORE_ENVELOPE_LIMIT = 65536
# An RTDN is a few hundred bytes of base64, so this payload keeps the tighter bound of its own.
PUBSUB_DATA_LIMIT = 16384


class AppStoreNotificationRequest(BaseModel):
    """The App Store notification body: the signed envelope, and nothing else."""
    # Required and non-empty, so an unusable body is the framework's 422 rather than a verification 401.
    # Bounded well above a signed envelope and its certificate chain: this route authenticates nobody.
    signedPayload: str = Field(..., min_length=1, max_length=APP_STORE_ENVELOPE_LIMIT)


class PubSubPushMessage(BaseModel):
    """The Pub/Sub message this push carries: its own id, and the RTDN as base64 text."""
    messageId: str
    # The transport envelope only: the base64 and JSON decoding happen after the token check.
    # Bounded well above an RTDN, so an oversized body is refused before the decoder runs.
    data: str = Field(..., min_length=1, max_length=PUBSUB_DATA_LIMIT)


class PubSubPushRequest(BaseModel):
    """The Cloud Pub/Sub push body: one message, and the subscription that delivered it."""
    message: PubSubPushMessage
    subscription: str | None = None
