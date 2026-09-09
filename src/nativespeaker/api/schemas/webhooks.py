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
    """The Pub/Sub message this push carries: the RTDN as base64 text, and nothing else."""
    # No `messageId`: nothing read it -- `notification_key_for` derives the replay key from the
    # purchase token, event time and event type instead -- so requiring it made an envelope shape
    # change a permanent 422 in exchange for validating a value the service never used, the same
    # rule `data` is bounded under. A delivery still carrying it is unaffected: pydantic ignores
    # what is not declared.
    # The transport envelope only: the base64 and JSON decoding happen after the token check.
    # Deliberately unbounded HERE and bounded in `developer_notification_from` instead: Pub/Sub
    # acknowledges 2xx alone and redelivers every other status, so a body pydantic refuses is a 422
    # this subscription retries forever. The decoder answers 200 and drops it, as it already does
    # for a body that does not decode. The bound itself is unchanged.
    # Defaulted for the same reason: Pub/Sub permits an attributes-only message, so requiring the
    # field made that delivery a 422 this subscription retries until retention expires.
    data: str = ""


class PubSubPushRequest(BaseModel):
    """The Cloud Pub/Sub push body: one message, and the subscription that delivered it."""
    message: PubSubPushMessage
    subscription: str | None = None
