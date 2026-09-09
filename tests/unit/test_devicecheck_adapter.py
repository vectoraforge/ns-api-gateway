"""The Apple wire contract: the signing, both request bodies, the bit1 carry-forward and every parse arm.
The shapes are [ASSUMED] from secondary sources -- see 41-RESEARCH.md § Assumptions Log, so a real 400
from Apple is evidence about these literals rather than a regression."""
import inspect
import json
import typing

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from nativespeaker.api.auth.devicecheck import (
    DEVICECHECK_ATTEMPTS,
    DEVICECHECK_HOST,
    QUERY_PATH,
    UPDATE_PATH,
    AppleDeviceCheck,
    BitState,
    DeviceCheckAdapter,
    read_bits_with_retry,
    read_private_key,
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

# The pair the two wrong mounts are cut from: the public half, and the passphrase-wrapped private half.
MISMOUNTED = ec.generate_private_key(ec.SECP256R1())


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
                                          _ok({"unrelated": 1}),
                                          _ok({"bit0": None, "bit1": None}),
                                          _ok({"bit0": 1, "bit1": 0})],
                             ids=["unparseable", "one bit only", "no bits",
                                  "both bits null", "both bits numeric"])
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

    @pytest.mark.parametrize("contents", [
        b"not a pem at all",
        b"",
        b"-----BEGIN PRIVATE KEY-----\n-----END PRIVATE KEY-----\n",
        b"\x80\x81\x82",
        MISMOUNTED.public_key().public_bytes(encoding=serialization.Encoding.PEM,
                                             format=serialization.PublicFormat.SubjectPublicKeyInfo),
        MISMOUNTED.private_bytes(encoding=serialization.Encoding.PEM,
                                 format=serialization.PrivateFormat.PKCS8,
                                 encryption_algorithm=serialization.BestAvailableEncryption(b"secret")),
    ], ids=["garbage", "empty", "framing-only", "not-text", "public-half", "passphrase-wrapped"])
    async def test_a_present_but_unusable_key_is_that_same_absent_state(self, contents, tmp_path):
        """WR-22: nothing parsed the PEM, so a truncated or corrupt file reached `jwt.encode` and
        raised past the retry frame onto the generic 500 on every claim, with the pod healthy.
        CR-09: the last two parse and then fail with `AttributeError` and `TypeError`, which the
        original except tuple did not name, so they raised out of `lifespan` and crashlooped."""
        pem = tmp_path / "AuthKey_ABCDE12345.p8"
        pem.write_bytes(contents)
        recorder = Recorder()

        assert read_private_key(str(pem)) is None

        with pytest.raises(Unavailable):
            await _adapter(recorder, "", key=read_private_key(str(pem))).read_bits(QUERY_TOKEN)
        assert recorder.requests == []

    async def test_a_key_of_the_wrong_type_is_refused_the_same_way(self, tmp_path):
        """An RSA key mounted at the DeviceCheck path parses as a PEM and then fails ES256."""
        pem = tmp_path / "AuthKey_ABCDE12345.p8"
        pem.write_bytes(rsa.generate_private_key(public_exponent=65537, key_size=2048)
                        .private_bytes(encoding=serialization.Encoding.PEM,
                                       format=serialization.PrivateFormat.PKCS8,
                                       encryption_algorithm=serialization.NoEncryption()))

        assert read_private_key(str(pem)) is None

    def test_a_real_key_is_still_read_back_control(self, private_key, tmp_path):
        """The control: a reader that answered `None` for everything would pass every case above."""
        pem = tmp_path / "AuthKey_ABCDE12345.p8"
        pem.write_text(private_key)

        assert read_private_key(str(pem)) == private_key
        assert read_private_key(str(tmp_path / "no-such-file.p8")) is None
        assert read_private_key(None) is None


class TestTheSeamIsTheAnnotation:
    """WR-23: a Protocol nothing is typed against catches nothing -- the e2e double and every
    renamed method passed unchecked. Both consumers of the seam name it, which is why it exists."""

    @pytest.mark.parametrize("helper", [read_bits_with_retry, write_bits_with_retry],
                             ids=["read", "write"])
    def test_both_retry_helpers_take_the_declared_seam(self, helper):
        assert inspect.get_annotations(helper, eval_str=True)["adapter"] is DeviceCheckAdapter

    def test_the_production_class_carries_every_member_it_declares_control(self):
        """The control: an annotation naming a shape the production class lacks would be worse."""
        assert typing.get_protocol_members(DeviceCheckAdapter) <= set(dir(AppleDeviceCheck))


class TestTheTransportIsReallyReached:
    """The control: an arm that silently measured nothing would pass every case above."""

    async def test_a_successful_query_actually_calls_the_transport(self, private_key):
        recorder = Recorder(_ok({"bit0": False, "bit1": True}))

        state = await read_bits_with_retry(_adapter(recorder, private_key), QUERY_TOKEN)

        assert len(recorder.requests) == 1
        assert state == BitState(bit0=False, bit1=True)
