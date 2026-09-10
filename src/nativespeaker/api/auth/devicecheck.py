"""The Apple DeviceCheck integration: the two-bit query, the two-bit update, and one ES256 bearer per call.
A device token is a secret capability: this module holds no logger, so none is logged."""
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, Protocol
from uuid import uuid4

import httpx
import jwt
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from nativespeaker.api.errors import ProofRejected, Unavailable

# Production only: the development host is not a config field, so no client input can select it.
DEVICECHECK_HOST = "https://api.devicecheck.apple.com"
QUERY_PATH = "/v1/query_two_bits"
UPDATE_PATH = "/v1/update_two_bits"

# A per-request option because every call mints its own bearer and sends one body.
DEVICECHECK_HTTP_TIMEOUT_SECONDS = 8

# The whole budget for one call: the initial request plus up to two more, spent on retryable outcomes only.
DEVICECHECK_ATTEMPTS = 3

# The gap between attempts, in `resilience.py`'s own shape: `multiplier * 2 ** (attempt
# - 1)`, clamped. Without it tenacity waits `wait_none()` and spends the whole budget inside a few
# milliseconds -- three requests into the same instant of an Apple blip, which buys nothing and
# triples this service's call rate exactly while the provider is degraded. Sub-second, and far
# below the LLM path's seconds, because the budget here is already three 8-second timeouts deep:
# past that the caller is gone, so an idle wait spends what is left of its patience on nothing.
DEVICECHECK_BACKOFF_BASE_SECONDS = 0.1
DEVICECHECK_BACKOFF_MAX_SECONDS = 0.5

# Apple answers HTTP 200 with one of these plain-text bodies when the device's bits were never set.
_NEVER_SET_BODIES = frozenset({"Failed to find bit state", "Bit State Not Found"})

# The phrase Apple's 400 bodies carry when the fault is in the caller's device token ("Missing or
# incorrectly formatted device token payload", "Unable to verify device token") and never when it is
# in the request this service built ("Invalid or missing timestamp", "Invalid or missing transaction
# id", "Missing or badly formatted authorization"). A phrase rather than a table of exact bodies,
# because these literals are [ASSUMED] from secondary sources (41-RESEARCH.md A3): an unrecognised
# 400 has to fall to the retry arm below, never to a 403 that accuses the caller's device.
_DEVICE_TOKEN_FAULT = "device token"


class RetryableDeviceCheckError(Exception):
    """The retry predicate's only target, always converted before it can escape."""


@dataclass(frozen=True, slots=True)
class BitState:
    """The two bits Apple holds for one device, as one completed query reported them."""

    bit0: bool
    bit1: bool


class DeviceCheckAdapter(Protocol):
    """The device-gate seam: one read of both bits, and one write of both."""

    async def read_bits(self, device_token: str) -> BitState:
        """The query call: the device's bit state, or a raise."""
        ...

    async def write_bits(self, device_token: str, *, bit0: bool, bit1: bool) -> None:
        """The update call: both bits written and confirmed, or a raise."""
        ...


def read_private_key(path: str | None) -> str | None:
    """Read the ES256 private key at `path`, or return `None` when there is no usable key there."""
    if path is None:
        return None
    pem = Path(path)
    if not pem.is_file():
        return None
    try:
        text = pem.read_text()
        # Parsed once, here, so a key that is present but unusable is the same absent state an
        # unset path is: a 503 on the claim and one boot warning. Unparsed, it reached `jwt.encode`
        # instead and raised out of the retry frame onto the generic 500 on every claim, with the
        # pod reporting healthy. The exception is dropped rather than logged: its text quotes the
        # file's own bytes.
        jwt.encode({}, text, algorithm="ES256")
    except Exception:
        # Every exception, because this is a classifier with two outcomes and no caller can act on
        # the distinction: `prepare_key` loads a public PEM successfully and fails at `.sign()` with
        # `AttributeError`, and a passphrase-wrapped `.p8` fails with `TypeError`. Both are outside
        # `(OSError, ValueError, PyJWTError)`, and both raised out of `lifespan` into a crashloop of
        # the whole pod -- the outcome this parse exists to prevent.
        return None
    return text


def _service_jwt(key_id: str | None, team_id: str | None, private_key: str | None, *, stage: str) -> str:
    """Mint the ES256 bearer Apple's server-to-server API requires, or fail closed having sent nothing."""
    if not (key_id and team_id and private_key):
        raise Unavailable(stage=stage)
    # `jwt.encode`, never a hand-rolled signature: JOSE ECDSA is raw r||s and a signer emits DER.
    return jwt.encode({"iss": team_id, "iat": int(datetime.now(UTC).timestamp())},
                      private_key,
                      algorithm="ES256",
                      headers={"kid": key_id})


def _shared_body(device_token: str) -> dict:
    """The fields both calls carry; the transaction id is fresh and correlates with nothing."""
    # Never the challenge handle: that is a secret capability, and this value travels to Apple.
    return {"device_token": device_token,
            "transaction_id": str(uuid4()),
            "timestamp": int(datetime.now(UTC).timestamp() * 1000)}


def _decoded(response: httpx.Response) -> dict[str, object] | None:
    """The response body as a JSON object, or `None` when it is neither."""
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _reject_or_retry(response: httpx.Response, *, stage: str) -> None:
    """Raise on the two non-success arms: a 400 naming the token, then everything else retryable."""
    if response.status_code == 400:
        if _DEVICE_TOKEN_FAULT in response.text.casefold():
            # Definitive: Apple refused the token itself, so no further attempt can change the answer.
            raise ProofRejected(stage=stage, cause="rejected")
        # Apple faults the request this service built, not the caller's proof: a skewed pod clock
        # alone earns "Invalid or missing timestamp" on every call. Spec 06:83 reserves
        # `proof_rejected` for vendor *material* failures, so this arm retries and then answers the
        # 503 -- a fault of ours never tells a client its device is bad.
        raise RetryableDeviceCheckError("status 400")
    if response.status_code // 100 != 2:
        raise RetryableDeviceCheckError(f"status {response.status_code}")


def _parse_bit_state(response: httpx.Response, *, stage: str) -> BitState:
    """Classify a query response in the one order that lets nothing fall through to a default."""
    body = response.text.strip()
    if body in _NEVER_SET_BODIES and response.status_code // 100 != 5:
        # The eligible first-ever claim, read before any JSON call because the body is plain text --
        # and ahead of the status, because Apple is widely observed carrying this body on 400 as
        # well as on the documented 200. Classified by status first, the one case the free grant
        # exists for was answered `proof_rejected` and the feature granted nothing to anybody.
        # A 5xx is excluded so an outage page that happens to echo this text cannot mint a grant.
        return BitState(bit0=False, bit1=False)
    _reject_or_retry(response, stage=stage)

    payload = _decoded(response)
    if payload is None:
        raise RetryableDeviceCheckError("unrecognised body")
    bit0, bit1 = payload.get("bit0"), payload.get("bit1")
    if not isinstance(bit0, bool) or not isinstance(bit1, bool):
        # The type is part of the guard: coercing `None` would report a bit clear that Apple
        # never answered, granting a second free grant and writing a set bit1 away.
        raise RetryableDeviceCheckError("unrecognised body")
    return BitState(bit0=bit0, bit1=bit1)


class AppleDeviceCheck:
    """Apple's two-bit device gate over HTTPS, signed per call with the configured ES256 key."""

    def __init__(self, *, key_id: str | None, team_id: str | None,
                 private_key: str | None, client: httpx.AsyncClient) -> None:
        self._key_id = key_id
        self._team_id = team_id
        self._private_key = private_key
        self._client = client

    async def read_bits(self, device_token: str) -> BitState:
        """Ask Apple for this device's two bits and classify the answer."""
        response = await self._post(QUERY_PATH, _shared_body(device_token), stage="devicecheck_read")
        return _parse_bit_state(response, stage="devicecheck_read")

    async def write_bits(self, device_token: str, *, bit0: bool, bit1: bool) -> None:
        """Write both bits, accepting only Apple's explicit confirmation as success."""
        body = _shared_body(device_token) | {"bit0": bit0, "bit1": bit1}
        response = await self._post(UPDATE_PATH, body, stage="devicecheck_write")
        _reject_or_retry(response, stage="devicecheck_write")

    async def _post(self, path: str, body: dict, *, stage: str) -> httpx.Response:
        """Send one signed request; a transport failure is retryable and carries no request material."""
        bearer = _service_jwt(self._key_id, self._team_id, self._private_key, stage=stage)
        try:
            return await self._client.post(f"{DEVICECHECK_HOST}{path}", json=body,
                                           headers={"Authorization": f"Bearer {bearer}"})
        except httpx.HTTPError as failure:
            raise RetryableDeviceCheckError(type(failure).__name__) from failure


def _read_exhausted(retry_state) -> NoReturn:
    """Convert an exhausted read budget into the `Unavailable` rejection the client is owed."""
    raise Unavailable(stage="devicecheck_read") from retry_state.outcome.exception()


def _write_exhausted(retry_state) -> NoReturn:
    """Convert an exhausted write budget into the `Unavailable` rejection the client is owed."""
    raise Unavailable(stage="devicecheck_write") from retry_state.outcome.exception()


def _retrying(exhausted) -> AsyncRetrying:
    """The three-attempt policy both calls share; only the internal marker is retried."""
    return AsyncRetrying(
        stop=stop_after_attempt(DEVICECHECK_ATTEMPTS),
        wait=wait_exponential(multiplier=DEVICECHECK_BACKOFF_BASE_SECONDS,
                              exp_base=2,
                              max=DEVICECHECK_BACKOFF_MAX_SECONDS),
        # Only the internal marker retries, so `ProofRejected` propagates after one attempt.
        retry=retry_if_exception_type(RetryableDeviceCheckError),
        retry_error_callback=exhausted,
    )


# Annotated with the Protocol both consume: unannotated, the one declaration that would catch a
# wrong-shaped double or a renamed method caught nothing at all.
async def read_bits_with_retry(adapter: DeviceCheckAdapter, device_token: str) -> BitState:
    """Call the adapter's query up to `DEVICECHECK_ATTEMPTS` times; return the state or raise."""
    return await _retrying(_read_exhausted)(adapter.read_bits, device_token)


async def write_bits_with_retry(adapter: DeviceCheckAdapter, device_token: str, *,
                                bit0: bool, bit1: bool) -> None:
    """Call the adapter's update up to `DEVICECHECK_ATTEMPTS` times; return on confirmation or raise."""
    await _retrying(_write_exhausted)(adapter.write_bits, device_token, bit0=bit0, bit1=bit1)
