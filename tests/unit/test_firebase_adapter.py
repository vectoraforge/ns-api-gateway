"""§7.1's concrete issuer-selected Firebase Admin adapter -- no network, no credential, no app.

Everything here runs against a monkeypatched `firebase_admin.auth.get_user` and a monkeypatched
`initialize_app`, so the suite needs neither a service account nor an outbound call. What it pins
is the four things that cannot be checked by reading the code once:

* **Selection fails closed.** An issuer with no configured app returns `selection_failure` and
  makes **no call at all** (T-37-19). A fallback to "the app we do have" would be reading another
  project's users.
* **No `[DEFAULT]` app is ever created** (T-37-14). Not creating one is what makes a call site that
  forgets `app=` fail loudly instead of silently picking up Application Default Credentials -- in
  local dev, the developer's own gcloud identity.
* **`provider_data` is materialized inside the threadpool call.** It is a *lazy* property that
  constructs `ProviderUserInfo`, which raises `ValueError` on an empty `rawId`. Touched after the
  call returns, that exception escapes the retry policy entirely and becomes an unhandled 500
  (T-37-17). The `raising_provider_data` case below drives exactly that shape.
* **The two email fields are read from the same `UserRecord`, on the `ok` arm only** -- §02 step 10
  pins the copy to "the same successful `getUser` response", and every failure arm leaves both at
  their defaults (T-37-34). The adapter *reports*; `classifier.email_to_persist` is what judges.
"""
import dataclasses
import json

import firebase_admin
import google.auth
import google.auth.exceptions
import pytest
from firebase_admin import auth, credentials, exceptions

from nativespeaker.api.auth.adapters import ProviderDataOutcome
from nativespeaker.api.auth.firebase import (
    FIREBASE_HTTP_TIMEOUT_SECONDS,
    FirebaseAdminLookup,
    build_admin_apps,
)
from nativespeaker.api.auth.retry import FIREBASE_LOOKUP_ATTEMPTS, lookup_with_retry
from nativespeaker.api.config import FirebaseConfig, JWTConfig

PROJECT_ID = "ns-test-project"
ISSUER = f"https://securetoken.google.com/{PROJECT_ID}"
OTHER_ISSUER = "https://securetoken.google.com/some-other-project"
SUBJECT = "firebase-uid-1"

# Shaped like a service account, but never used as one: `credentials.Certificate` is monkeypatched
# in the one test that reaches it, so no key material -- real or fake-but-valid -- exists here.
CREDENTIAL = {"type": "service_account", "project_id": PROJECT_ID,
              "client_email": f"admin@{PROJECT_ID}.iam.gserviceaccount.com", "private_key": "unused"}

PROVIDER_TEXT = "USER_NOT_FOUND: no user record for that uid in project ns-test-project"


class StubConfig:
    """The two blocks `build_admin_apps` reads, with the real `FirebaseConfig` parse behind them."""

    def __init__(self, service_account_json: str | None) -> None:
        self.jwt = JWTConfig(project_id=PROJECT_ID, api_key="unused-api-key")
        self.firebase = FirebaseConfig(service_account_json=service_account_json)


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
    """Force the environment to offer no Application Default Credentials.

    `build_admin_apps` falls back to ADC when no key is configured, so a developer machine with a
    gcloud login -- or a `GOOGLE_APPLICATION_CREDENTIALS` in `.env` -- makes the genuinely-absent
    state unreachable. Any case asserting the absent state must take this fixture, or it quietly
    starts asserting something else.
    """
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

    def test_a_configured_credential_yields_one_app_keyed_on_the_issuer(self, monkeypatch):
        seen = {}

        def fake_certificate(parsed):
            seen["credential"] = parsed
            return "certificate-object"

        def fake_initialize_app(credential, options=None, name=None):
            seen["args"] = (credential, options, name)
            return RecordingApp(name)

        monkeypatch.setattr("nativespeaker.api.auth.firebase.credentials.Certificate",
                            fake_certificate)
        monkeypatch.setattr(firebase_admin, "initialize_app", fake_initialize_app)

        apps = build_admin_apps(StubConfig(json.dumps(CREDENTIAL)))

        assert list(apps) == [ISSUER]
        assert seen["credential"] == CREDENTIAL
        credential, options, name = seen["args"]
        assert credential == "certificate-object"
        assert name == f"issuer:{ISSUER}"
        assert options == {"projectId": PROJECT_ID,
                           "httpTimeout": FIREBASE_HTTP_TIMEOUT_SECONDS}

    def test_an_absent_credential_yields_an_empty_mapping_and_no_default_app(self, no_adc):
        """Absent is a supported state (37-03): the service boots and completion fails closed.

        `no_adc` is mandatory here. Since ADC became the second credential source, "absent" means
        *both* sources absent -- and a developer machine with a gcloud login supplies the second
        one, so without the fixture this case silently stops testing the state it names.
        """
        assert build_admin_apps(StubConfig(None)) == {}
        assert firebase_admin._DEFAULT_APP_NAME not in firebase_admin._apps

    def test_an_absent_credential_does_not_raise_and_does_not_initialize_anything(self, monkeypatch,
                                                                                 no_adc):
        def explode(*args, **kwargs):
            raise AssertionError("initialize_app must not be called with no credential")

        monkeypatch.setattr(firebase_admin, "initialize_app", explode)
        assert build_admin_apps(StubConfig(None)) == {}

    def test_adc_supplies_the_credential_when_no_key_is_configured(self, monkeypatch):
        """The second source: no key file, but the environment offers ADC.

        This is the arm the organization policy forces -- `iam.disableServiceAccountKeyCreation`
        means no key can be minted, so ADC is the only route to a real Admin call here.
        """
        monkeypatch.setattr(google.auth, "default", lambda *a, **k: (object(), PROJECT_ID))
        passed = {}

        def capture(credential, options, name):
            passed.update(credential=credential, options=options, name=name)
            return "app-sentinel"

        monkeypatch.setattr(firebase_admin, "initialize_app", capture)
        apps = build_admin_apps(StubConfig(None))

        assert apps == {ISSUER: "app-sentinel"}
        assert isinstance(passed["credential"], credentials.ApplicationDefault)
        # Never inferred from the credential: user-scoped ADC carries no project, and an Admin
        # client bound to the wrong one reads another project's users.
        assert passed["options"]["projectId"] == PROJECT_ID

    def test_an_explicit_key_wins_over_adc(self, monkeypatch):
        """Source order: a configured key is used even where ADC is also available."""
        monkeypatch.setattr(google.auth, "default", lambda *a, **k: (object(), PROJECT_ID))
        passed = {}

        def capture(credential, options, name):
            passed.update(credential=credential)
            return "app-sentinel"

        monkeypatch.setattr(firebase_admin, "initialize_app", capture)
        monkeypatch.setattr(credentials, "Certificate", lambda d: "certificate-sentinel")
        build_admin_apps(StubConfig(json.dumps(CREDENTIAL)))

        assert passed["credential"] == "certificate-sentinel"

    def test_the_per_attempt_timeout_sits_inside_the_mandated_band(self):
        """`adapters.py:16-17`: a fixed configured per-attempt timeout on the order of 5-10 s."""
        assert 5 <= FIREBASE_HTTP_TIMEOUT_SECONDS <= 10


class TestSelection:
    """§7.1: one client selected by issuer match, and no fallback expressible."""

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
    """§02 step 10's carrier: read from the same record, on the `ok` arm, judged nowhere here."""

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
        """CR-01. Credential acquisition happens before the request is sent, outside every arm.

        `AuthorizedSession.request` calls `credentials.before_request()` first, and firebase-admin
        converts only `requests.exceptions.RequestException` into a `FirebaseError`. `RefreshError`
        is none of the three types the other arms catch, so without its own arm it escapes the
        adapter: `retry_if_result` never sees a result, no retry is spent, and the caller gets 500
        with the claim left unconsumed instead of 503.

        This is the steady state under ADC, not an edge case -- the org policy blocks key creation,
        so every deployment renews a short-lived token and every renewal can fail.
        """
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
        """Pitfall 3 / T-37-17 -- the empty-`rawId` shape, materialized inside the threadpool."""
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
    """One method, not three -- and recorded as a decision rather than left as an omission."""

    @pytest.mark.parametrize("method", ["verify_id_token", "revoke_refresh_tokens"])
    def test_the_other_two_protocol_methods_are_not_implemented(self, method):
        """`verify_id_token` would be unreachable (the barrier verifies); revocation is Phase 46."""
        assert not hasattr(FirebaseAdminLookup, method)

    def test_the_class_is_not_annotated_as_the_full_protocol(self):
        """It does not satisfy `FirebaseAdminAdapter`, so it must not claim to."""
        from nativespeaker.api.auth.adapters import FirebaseAdminAdapter
        assert FirebaseAdminAdapter not in FirebaseAdminLookup.__mro__


class TestTheLazyReExport:
    """D-23's one import root still reaches this module -- just not eagerly.

    `TestNoProviderDependency.test_importing_the_module_does_not_import_firebase_admin` pins the
    other half in a subprocess: importing the adapters seam leaves `firebase_admin` out of
    `sys.modules`. What is pinned here is that the lazy path is a genuine **re-export** and not a
    copy, so a caller reaching a name through the root and a caller reaching it directly are
    holding the same object.
    """

    @pytest.mark.parametrize("name", ["build_admin_apps", "FirebaseAdminLookup",
                                      "FIREBASE_HTTP_TIMEOUT_SECONDS"])
    def test_the_root_yields_the_same_object_as_the_direct_import(self, name):
        import nativespeaker.api.auth as auth_root
        from nativespeaker.api.auth import firebase as firebase_module
        assert getattr(auth_root, name) is getattr(firebase_module, name)

    @pytest.mark.parametrize("name", ["build_admin_apps", "FirebaseAdminLookup",
                                      "FIREBASE_HTTP_TIMEOUT_SECONDS"])
    def test_every_lazy_name_is_declared_in_all(self, name):
        import nativespeaker.api.auth as auth_root
        assert name in auth_root.__all__

    def test_an_unknown_name_still_raises_attribute_error(self):
        """`__getattr__` resolves the mapping and nothing else -- it is not a catch-all."""
        import nativespeaker.api.auth as auth_root
        with pytest.raises(AttributeError):
            auth_root.no_such_name

    def test_dir_still_shows_the_whole_root(self):
        import nativespeaker.api.auth as auth_root
        assert dir(auth_root) == sorted(auth_root.__all__)
