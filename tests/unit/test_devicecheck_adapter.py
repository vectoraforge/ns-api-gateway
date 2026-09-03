"""The Apple wire contract: the signing, both request bodies, the bit1 carry-forward and every parse arm.
The shapes are [ASSUMED] from secondary sources -- see 41-RESEARCH.md § Assumptions Log, so a real 400
from Apple is evidence about these literals rather than a regression."""
import json

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from nativespeaker.api.auth.devicecheck import (
    DEVICECHECK_ATTEMPTS,
    DEVICECHECK_HOST,
    QUERY_PATH,
    UPDATE_PATH,
    AppleDeviceCheck,
    BitState,
    read_bits_with_retry,
    write_bits_with_retry,
)
from nativespeaker.api.errors import ProofRejected, Unavailable

KEY_ID = "ABCDE12345"
TEAM_ID = "TEAM123456"
QUERY_TOKEN = "query-token-under-test"
UPDATE_TOKEN = "update-token-under-test"

# A handle-shaped string the transaction id must never equal: the handle is a secret capability.
HANDLE = "Zm9vYmFyYmF6cXV4MTIzNA"

# Both bodies Apple is reported to answer 200 with when the device's bits were never set.
NEVER_SET_BODIES = ("Failed to find bit state", "Bit State Not Found")


@pytest.fixture(scope="module")
def private_key() -> str:
    """An ephemeral EC P-256 key generated here: never a fixture file and never a real Apple key."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(encoding=serialization.Encoding.PEM,
                             format=serialization.PrivateFormat.PKCS8,
                             encryption_algorithm=serialization.NoEncryption()).decode()


class Recorder:
    """A `MockTransport` handler that records every request and answers a scripted sequence."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.scripted = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self.requests) > len(self.scripted):
            # Overrunning the script is the failure this file exists to catch, so name it.
            raise AssertionError(
                f"attempt {len(self.requests)} exceeds the scripted {len(self.scripted)}")
        return self.scripted[len(self.requests) - 1]

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)

    def bearer(self, index: int = 0) -> str:
        return self.requests[index].headers["Authorization"].removeprefix("Bearer ")


def _adapter(recorder: Recorder, private_key: str, *, key_id: str | None = KEY_ID,
             team_id: str | None = TEAM_ID, key: str | None = "") -> AppleDeviceCheck:
    """The real adapter over a mock transport; certificate verification is never touched."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    return AppleDeviceCheck(key_id=key_id, team_id=team_id,
                            private_key=private_key if key == "" else key, client=client)


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _text(body: str) -> httpx.Response:
    return httpx.Response(200, text=body)


class TestTheServiceJwt:
    """The bearer Apple's server-to-server API requires, decoded off the request the transport saw."""

    async def test_the_header_names_the_key_and_the_es256_algorithm(self, private_key):
        recorder = Recorder(_ok({"bit0": False, "bit1": False}))

        await _adapter(recorder, private_key).read_bits(QUERY_TOKEN)

        header = pyjwt.get_unverified_header(recorder.bearer())
        assert header["kid"] == KEY_ID
        assert header["alg"] == "ES256"

    async def test_the_claims_are_the_team_id_and_an_integer_issued_at(self, private_key):
        recorder = Recorder(_ok({"bit0": False, "bit1": False}))

        await _adapter(recorder, private_key).read_bits(QUERY_TOKEN)

        claims = pyjwt.decode(recorder.bearer(), options={"verify_signature": False})
        assert claims["iss"] == TEAM_ID
        assert isinstance(claims["iat"], int)

    async def test_a_fresh_bearer_is_minted_per_call(self, private_key):
        """Two calls, two signatures: a cached bearer would eventually present a stale `iat`."""
        recorder = Recorder(_ok({"bit0": False, "bit1": False}), httpx.Response(200))
        adapter = _adapter(recorder, private_key)

        await adapter.read_bits(QUERY_TOKEN)
        await adapter.write_bits(UPDATE_TOKEN, bit0=True, bit1=False)

        assert recorder.bearer(0) != recorder.bearer(1)


class TestTheRequestBodies:
    """The three shared fields, and the two the update adds."""

    async def test_the_query_body_carries_the_token_a_transaction_id_and_a_millisecond_timestamp(
            self, private_key):
        recorder = Recorder(_ok({"bit0": False, "bit1": False}))

        await _adapter(recorder, private_key).read_bits(QUERY_TOKEN)

        body = recorder.body()
        assert recorder.requests[0].url == httpx.URL(f"{DEVICECHECK_HOST}{QUERY_PATH}")
        assert body["device_token"] == QUERY_TOKEN
        assert set(body) == {"device_token", "transaction_id", "timestamp"}
        # Milliseconds, not seconds: a seconds value would sit thirteen digits short of now.
        assert body["timestamp"] > 1_000_000_000_000

    async def test_two_calls_carry_two_transaction_ids_and_neither_is_the_handle(self, private_key):
        """The assertion that stops the challenge handle being reused as the vendor's idempotency key."""
        recorder = Recorder(_ok({"bit0": False, "bit1": False}), httpx.Response(200))
        adapter = _adapter(recorder, private_key)

        await adapter.read_bits(HANDLE)
        await adapter.write_bits(HANDLE, bit0=True, bit1=False)

        first, second = recorder.body(0)["transaction_id"], recorder.body(1)["transaction_id"]
        assert first != second
        assert HANDLE not in (first, second)

    async def test_the_update_body_adds_both_bits_and_targets_the_update_path(self, private_key):
        recorder = Recorder(httpx.Response(200))

        await _adapter(recorder, private_key).write_bits(UPDATE_TOKEN, bit0=True, bit1=False)

        assert recorder.requests[0].url == httpx.URL(f"{DEVICECHECK_HOST}{UPDATE_PATH}")
        assert set(recorder.body()) == {"device_token", "transaction_id", "timestamp",
                                        "bit0", "bit1"}
        assert recorder.body()["device_token"] == UPDATE_TOKEN


class TestTheBit1CarryForward:
    """Apple writes both bits in one call, so a fabricated bit1 destroys state nothing can recover."""

    async def test_a_query_answering_bit1_true_produces_an_update_carrying_bit1_true(self,
                                                                                     private_key):
        recorder = Recorder(_ok({"bit0": False, "bit1": True}), httpx.Response(200))
        adapter = _adapter(recorder, private_key)

        state = await adapter.read_bits(QUERY_TOKEN)
        await adapter.write_bits(UPDATE_TOKEN, bit0=True, bit1=state.bit1)

        assert state == BitState(bit0=False, bit1=True)
        assert recorder.body(1)["bit0"] is True
        assert recorder.body(1)["bit1"] is True

    async def test_a_query_answering_both_false_produces_an_update_carrying_bit1_false(self,
                                                                                       private_key):
        recorder = Recorder(_ok({"bit0": False, "bit1": False}), httpx.Response(200))
        adapter = _adapter(recorder, private_key)

        state = await adapter.read_bits(QUERY_TOKEN)
        await adapter.write_bits(UPDATE_TOKEN, bit0=True, bit1=state.bit1)

        assert recorder.body(1)["bit0"] is True
        assert recorder.body(1)["bit1"] is False


class TestTheParseArms:
    """The five ordered arms, with nothing falling through to a default."""

    async def test_arm_one_a_400_is_a_definitive_refusal_after_exactly_one_attempt(self,
                                                                                   private_key):
        recorder = Recorder(httpx.Response(400, text="Missing or badly formatted authorization"))

        with pytest.raises(ProofRejected):
            await read_bits_with_retry(_adapter(recorder, private_key), QUERY_TOKEN)

        assert len(recorder.requests) == 1

    async def test_arm_two_a_503_is_retried_to_the_budget_and_then_unavailable(self, private_key):
        recorder = Recorder(*[httpx.Response(503) for _ in range(DEVICECHECK_ATTEMPTS)])

        with pytest.raises(Unavailable):
            await read_bits_with_retry(_adapter(recorder, private_key), QUERY_TOKEN)

        assert len(recorder.requests) == DEVICECHECK_ATTEMPTS == 3

    @pytest.mark.parametrize("body", NEVER_SET_BODIES)
    async def test_arm_three_a_never_set_plain_text_body_is_a_state_and_not_a_raise(self, body,
                                                                                    private_key):
        """The eligible first-ever claim, decoded before any JSON call because the body is plain text."""
        recorder = Recorder(_text(body))

        state = await _adapter(recorder, private_key).read_bits(QUERY_TOKEN)

        assert state == BitState(bit0=False, bit1=False)

    async def test_arm_four_a_json_object_carrying_both_bits_is_that_state(self, private_key):
        recorder = Recorder(_ok({"bit0": True, "bit1": False}))

        state = await _adapter(recorder, private_key).read_bits(QUERY_TOKEN)

        assert state == BitState(bit0=True, bit1=False)

    @pytest.mark.parametrize("response", [_text("something nobody documented"),
                                          _ok({"bit0": True}),
                                          _ok({"unrelated": 1})],
                             ids=["unparseable", "one bit only", "no bits"])
    async def test_arm_five_an_unrecognised_body_fails_closed_rather_than_defaulting(
            self, response, private_key):
        recorder = Recorder(*[response for _ in range(DEVICECHECK_ATTEMPTS)])

        with pytest.raises(Unavailable):
            await read_bits_with_retry(_adapter(recorder, private_key), QUERY_TOKEN)

    async def test_the_write_accepts_only_an_explicit_confirmation(self, private_key):
        recorder = Recorder(httpx.Response(400, text="Bad device token"))

        with pytest.raises(ProofRejected):
            await write_bits_with_retry(_adapter(recorder, private_key), UPDATE_TOKEN,
                                        bit0=True, bit1=False)

        assert len(recorder.requests) == 1


class TestAnAbsentCredentialFailsClosed:
    """No key, no request: an absent credential is a 503 and never a bypass of the gate."""

    @pytest.mark.parametrize("missing", ["key_id", "team_id", "key"])
    async def test_each_absent_value_raises_unavailable_and_issues_no_request(self, missing,
                                                                              private_key):
        recorder = Recorder()

        with pytest.raises(Unavailable):
            await _adapter(recorder, private_key, **{missing: None}).read_bits(QUERY_TOKEN)

        assert recorder.requests == []


class TestTheTransportIsReallyReached:
    """The control: an arm that silently measured nothing would pass every case above."""

    async def test_a_successful_query_actually_calls_the_transport(self, private_key):
        recorder = Recorder(_ok({"bit0": False, "bit1": True}))

        state = await read_bits_with_retry(_adapter(recorder, private_key), QUERY_TOKEN)

        assert len(recorder.requests) == 1
        assert state == BitState(bit0=False, bit1=True)
