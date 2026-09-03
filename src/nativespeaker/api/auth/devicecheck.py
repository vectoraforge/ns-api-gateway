"""The Apple DeviceCheck integration: the two-bit query, the two-bit update, and one ES256 bearer per call.
A device token is a secret capability: this module holds no logger, so none is logged."""
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn, Protocol
from uuid import uuid4

import httpx
import jwt
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt

from nativespeaker.api.errors import ProofRejected, Unavailable

# Production only: the development host is not a config field, so no client input can select it.
DEVICECHECK_HOST = "https://api.devicecheck.apple.com"
QUERY_PATH = "/v1/query_two_bits"
UPDATE_PATH = "/v1/update_two_bits"

# A per-request option because every call mints its own bearer and sends one body.
DEVICECHECK_HTTP_TIMEOUT_SECONDS = 8

# The whole budget for one call: the initial request plus up to two more, spent on retryable outcomes only.
DEVICECHECK_ATTEMPTS = 3

# Apple answers HTTP 200 with one of these plain-text bodies when the device's bits were never set.
_NEVER_SET_BODIES = frozenset({"Failed to find bit state", "Bit State Not Found"})


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
    """Read the ES256 private key at `path`, or return `None` when there is no usable file."""
    if path is None:
        return None
    pem = Path(path)
    return pem.read_text() if pem.is_file() else None


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


def _decoded(response: httpx.Response) -> object | None:
    """The response body as JSON, or `None` when it does not decode."""
    try:
        return response.json()
    except ValueError:
        return None


def _reject_or_retry(response: httpx.Response, *, stage: str) -> None:
    """Raise on the two non-success arms: a definitive 400, then everything else retryable."""
    if response.status_code == 400:
        # Definitive: Apple refused the token itself, so no further attempt can change the answer.
        raise ProofRejected(stage=stage, cause="rejected")
    if response.status_code // 100 != 2:
        raise RetryableDeviceCheckError(f"status {response.status_code}")


def _parse_bit_state(response: httpx.Response, *, stage: str) -> BitState:
    """Classify a query response in the one order that lets nothing fall through to a default."""
    _reject_or_retry(response, stage=stage)

    body = response.text.strip()
    if body in _NEVER_SET_BODIES:
        # The eligible first-ever claim, read before any JSON call because the body is plain text.
        return BitState(bit0=False, bit1=False)

    payload = _decoded(response)
    if not isinstance(payload, dict) or "bit0" not in payload or "bit1" not in payload:
        raise RetryableDeviceCheckError("unrecognised body")
    return BitState(bit0=bool(payload["bit0"]), bit1=bool(payload["bit1"]))


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
        # Only the internal marker retries, so `ProofRejected` propagates after one attempt.
        retry=retry_if_exception_type(RetryableDeviceCheckError),
        retry_error_callback=exhausted,
    )


async def read_bits_with_retry(adapter, device_token: str) -> BitState:
    """Call the adapter's query up to `DEVICECHECK_ATTEMPTS` times; return the state or raise."""
    return await _retrying(_read_exhausted)(adapter.read_bits, device_token)


async def write_bits_with_retry(adapter, device_token: str, *, bit0: bool, bit1: bool) -> None:
    """Call the adapter's update up to `DEVICECHECK_ATTEMPTS` times; return on confirmation or raise."""
    await _retrying(_write_exhausted)(adapter.write_bits, device_token, bit0=bit0, bit1=bit1)
