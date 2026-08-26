"""The issuer-selected Firebase Admin adapter against a monkeypatched SDK: no network, no credential, no app."""
import dataclasses

import firebase_admin
import google.auth
import google.auth.exceptions
import pytest
from firebase_admin import auth, credentials, exceptions

from nativespeaker.api.auth.adapters import ProviderDataOutcome
from nativespeaker.api.auth.firebase import (
    FIREBASE_HTTP_TIMEOUT_SECONDS,
    FIREBASE_LOOKUP_ATTEMPTS,
    FirebaseAdminLookup,
    build_admin_apps,
    lookup_with_retry,
)
from nativespeaker.api.config import JWTConfig

PROJECT_ID = "ns-test-project"
ISSUER = f"https://securetoken.google.com/{PROJECT_ID}"
OTHER_ISSUER = "https://securetoken.google.com/some-other-project"
SUBJECT = "firebase-uid-1"

PROVIDER_TEXT = "USER_NOT_FOUND: no user record for that uid in project ns-test-project"


class StubConfig:
    """The one block `build_admin_apps` reads: the credential comes from the environment, not from here."""

    def __init__(self) -> None:
        self.jwt = JWTConfig(project_id=PROJECT_ID, api_key="unused-api-key")


class StubUserRecord:
    """A `UserRecord` stand-in whose `provider_data` is lazy, exactly as the SDK's is."""

    def __init__(self, provider_data=(), email=None, email_verified=False, raises=None) -> None:
        self._provider_data = list(provider_data)
        self._raises = raises
        self.email = email
        self.email_verified = email_verified

    @property
    def provider_data(self):
        if self._raises is not None:
            raise self._raises
        return self._provider_data


class StubProviderUserInfo:
    def __init__(self, provider_id: str, uid: str) -> None:
        self.provider_id = provider_id
        self.uid = uid


class RecordingApp:
    """Stands in for a `firebase_admin.App`; identity is all the adapter needs from it."""

    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def no_adc(monkeypatch):
    """Force the environment to offer no Application Default Credentials; any absent-state case must take this."""
    def no_credentials(*args, **kwargs):
        raise google.auth.exceptions.DefaultCredentialsError("no ADC in this test")

    monkeypatch.setattr(google.auth, "default", no_credentials)


@pytest.fixture
def app() -> RecordingApp:
    return RecordingApp(f"issuer:{ISSUER}")


@pytest.fixture
def adapter(app) -> FirebaseAdminLookup:
    return FirebaseAdminLookup({ISSUER: app})


@pytest.fixture
def get_user_calls(monkeypatch):
    """Monkeypatches `auth.get_user` to record its calls; the test scripts the answer."""
    calls: list[dict] = []

    def script(answer):
        def fake_get_user(uid, app=None):
            calls.append({"uid": uid, "app": app})
            if isinstance(answer, BaseException):
                raise answer
            return answer
        monkeypatch.setattr(auth, "get_user", fake_get_user)
        return calls

    return script


class TestBuildAdminApps:
    """One named app per configured issuer, and never a `[DEFAULT]` one."""

    def test_adc_yields_one_app_keyed_on_the_issuer(self, monkeypatch):
        """The only arm there is: org policy forbids minting a key, so ADC is the sole route to a real call."""
        monkeypatch.setattr(google.auth, "default", lambda *a, **k: (object(), PROJECT_ID))
        passed = {}

        def capture(credential, options, name):
            passed.update(credential=credential, options=options, name=name)
            return "app-sentinel"

        monkeypatch.setattr(firebase_admin, "initialize_app", capture)
        apps = build_admin_apps(StubConfig())

        assert apps == {ISSUER: "app-sentinel"}
        assert isinstance(passed["credential"], credentials.ApplicationDefault)
        assert passed["name"] == f"issuer:{ISSUER}"
        # Never inferred from the credential: a client bound to the wrong project reads other users.
        assert passed["options"] == {"projectId": PROJECT_ID,
                                     "httpTimeout": FIREBASE_HTTP_TIMEOUT_SECONDS}

    def test_an_absent_credential_yields_an_empty_mapping_and_no_default_app(self, no_adc):
        """ADC is the only source, so `no_adc` is what makes absent mean absent here."""
        assert build_admin_apps(StubConfig()) == {}
        assert firebase_admin._DEFAULT_APP_NAME not in firebase_admin._apps

    def test_an_absent_credential_does_not_raise_and_does_not_initialize_anything(self, monkeypatch,
                                                                                 no_adc):
        def explode(*args, **kwargs):
            raise AssertionError("initialize_app must not be called with no credential")

        monkeypatch.setattr(firebase_admin, "initialize_app", explode)
        assert build_admin_apps(StubConfig()) == {}

    def test_the_per_attempt_timeout_sits_inside_the_mandated_band(self):
        """`adapters.py:16-17`: a fixed configured per-attempt timeout on the order of 5-10 s."""
        assert 5 <= FIREBASE_HTTP_TIMEOUT_SECONDS <= 10


class TestSelection:
    """One client selected by issuer match, with no fallback expressible."""

    async def test_an_unconfigured_issuer_fails_closed_and_calls_nothing(self, adapter,
                                                                        get_user_calls):
        calls = get_user_calls(StubUserRecord())
        result = await adapter.get_user_provider_data(OTHER_ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.selection_failure
        assert calls == []

    async def test_an_empty_mapping_fails_closed_for_every_issuer(self, get_user_calls):
        calls = get_user_calls(StubUserRecord())
        result = await FirebaseAdminLookup({}).get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.selection_failure
        assert calls == []

    async def test_a_configured_issuer_passes_its_own_app_explicitly(self, adapter, app,
                                                                    get_user_calls):
        """A forgotten `app=` would reach the `[DEFAULT]` app -- which is why none is created."""
        calls = get_user_calls(StubUserRecord())
        await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert calls == [{"uid": SUBJECT, "app": app}]


class TestSuccessfulReads:
    """`ok` carries foundation's own frozen entries, never the SDK's objects."""

    async def test_empty_provider_data_is_an_ok_with_no_entries(self, adapter, get_user_calls):
        get_user_calls(StubUserRecord(provider_data=()))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.ok
        assert result.entries == ()

    async def test_entries_are_foundation_dataclasses_carrying_provider_id_and_uid(self, adapter,
                                                                                  get_user_calls):
        get_user_calls(StubUserRecord(
            provider_data=[StubProviderUserInfo("google.com", "google-uid-1")]))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.ok
        assert [(e.provider_id, e.uid) for e in result.entries] == [("google.com", "google-uid-1")]
        assert all(dataclasses.is_dataclass(entry) for entry in result.entries)


class TestTheEmailFields:
    """Read from the same record on the `ok` arm; the adapter reports and judges nothing."""

    async def test_a_verified_address_rides_out_on_the_result(self, adapter, get_user_calls):
        get_user_calls(StubUserRecord(email="a@b.test", email_verified=True))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.ok
        assert result.email == "a@b.test"
        assert result.email_verified is True

    async def test_an_unverified_address_is_reported_verbatim_not_suppressed(self, adapter,
                                                                            get_user_calls):
        """The adapter reports; `email_to_persist` is what turns this pair into `None`."""
        get_user_calls(StubUserRecord(email="a@b.test", email_verified=False))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.ok
        assert result.email == "a@b.test"
        assert result.email_verified is False

    async def test_an_absent_address_is_none(self, adapter, get_user_calls):
        get_user_calls(StubUserRecord(email=None, email_verified=False))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.ok
        assert result.email is None
        assert result.email_verified is False

    @pytest.mark.parametrize("answer,expected", [
        (auth.UserNotFoundError(PROVIDER_TEXT), ProviderDataOutcome.user_not_found),
        (exceptions.FirebaseError("unavailable", PROVIDER_TEXT), ProviderDataOutcome.retryable_failure),
        (StubUserRecord(raises=ValueError("User ID must not be None or empty.")),
         ProviderDataOutcome.retryable_failure),
    ], ids=["user_not_found", "firebase_error", "malformed_provider_data"])
    async def test_every_non_ok_result_carries_the_defaults(self, adapter, get_user_calls,
                                                            answer, expected):
        get_user_calls(answer)
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is expected
        assert result.email is None
        assert result.email_verified is False
        assert result.entries == ()

    async def test_a_selection_failure_carries_the_defaults_too(self, adapter):
        result = await adapter.get_user_provider_data(OTHER_ISSUER, SUBJECT)
        assert result.email is None
        assert result.email_verified is False


class TestFailureMapping:
    """Every SDK failure mode lands in the closed four-value outcome set. Nothing escapes."""

    async def test_user_not_found_is_definitive(self, adapter, get_user_calls):
        """Non-retryable: it spends no retry budget (`adapters.py:52-54`)."""
        get_user_calls(auth.UserNotFoundError(PROVIDER_TEXT))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.user_not_found

    async def test_a_firebase_error_is_retryable(self, adapter, get_user_calls):
        get_user_calls(exceptions.FirebaseError("unavailable", PROVIDER_TEXT))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.retryable_failure

    async def test_a_credential_refresh_failure_is_retryable_and_never_escapes(self, adapter,
                                                                              get_user_calls):
        """A refresh error is none of the types the other arms catch, so without this arm it escapes as a 500."""
        assert not issubclass(google.auth.exceptions.RefreshError, exceptions.FirebaseError)
        assert not issubclass(google.auth.exceptions.RefreshError, ValueError)
        get_user_calls(google.auth.exceptions.RefreshError("token refresh failed"))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.retryable_failure

    async def test_a_credential_failure_spends_the_full_retry_budget(self, adapter, monkeypatch):
        """The point of returning a result rather than raising: the policy can actually retry it."""
        calls = []

        def failing_get_user(uid, app=None):
            calls.append(uid)
            raise google.auth.exceptions.RefreshError("token refresh failed")

        monkeypatch.setattr(auth, "get_user", failing_get_user)
        result = await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert result.outcome is ProviderDataOutcome.retryable_failure
        assert len(calls) == FIREBASE_LOOKUP_ATTEMPTS

    async def test_a_lazy_provider_data_value_error_is_retryable_and_never_escapes(self, adapter,
                                                                                  get_user_calls):
        """The empty-`rawId` shape, materialized inside the threadpool call rather than after it returns."""
        get_user_calls(StubUserRecord(raises=ValueError("User ID must not be None or empty.")))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is ProviderDataOutcome.retryable_failure

    async def test_user_not_found_is_not_swallowed_by_the_firebase_error_arm(self, adapter,
                                                                            get_user_calls):
        """`UserNotFoundError` subclasses `FirebaseError`; a reordered `except` would misclassify."""
        assert issubclass(auth.UserNotFoundError, exceptions.FirebaseError)
        get_user_calls(auth.UserNotFoundError(PROVIDER_TEXT))
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert result.outcome is not ProviderDataOutcome.retryable_failure


class TestNoProviderTextLeaks:
    """`adapters.py:19-20`: provider diagnostics are log material, never response material."""

    @pytest.mark.parametrize("answer", [
        auth.UserNotFoundError(PROVIDER_TEXT),
        exceptions.FirebaseError("unavailable", PROVIDER_TEXT),
        StubUserRecord(raises=ValueError(PROVIDER_TEXT)),
    ], ids=["user_not_found", "firebase_error", "malformed_provider_data"])
    async def test_no_field_of_a_failure_result_carries_the_providers_message(self, adapter,
                                                                             get_user_calls,
                                                                             answer):
        get_user_calls(answer)
        result = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        rendered = repr(dataclasses.asdict(result))
        assert PROVIDER_TEXT not in rendered
        assert "ns-test-project" not in rendered


class TestTheDeliberateNonImplementations:
    """The concrete lookup is not the seam: it implements the one method and claims nothing more."""

    def test_the_class_is_not_annotated_as_the_full_protocol(self):
        """It does not satisfy `FirebaseAdminAdapter`, so it must not claim to."""
        from nativespeaker.api.auth.adapters import FirebaseAdminAdapter
        assert FirebaseAdminAdapter not in FirebaseAdminLookup.__mro__
