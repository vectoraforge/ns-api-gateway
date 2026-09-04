"""The store-callback request bodies. `signedPayload` keeps Apple's camelCase spelling as sent."""
from pydantic import BaseModel, Field


class AppStoreNotificationRequest(BaseModel):
    """The App Store notification body: the signed envelope, and nothing else."""
    # Required and non-empty, so an unusable body is the framework's 422 rather than a verification 401.
    signedPayload: str = Field(..., min_length=1)
