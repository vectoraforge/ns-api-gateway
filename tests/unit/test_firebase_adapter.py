"""The issuer-selected Firebase Admin adapter against a monkeypatched SDK: no network, no credential, no app."""
import firebase_admin
import google.auth
import google.auth.exceptions
import pytest
from firebase_admin import auth, credentials, exceptions

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.auth.firebase import (
    FIREBASE_HTTP_TIMEOUT_SECONDS,
    FIREBASE_LOOKUP_ATTEMPTS,
    FirebaseAdminLookup,
    RetryableLookupError,
    _application_default_credential,
    build_admin_apps,
    lookup_with_retry,
)
from nativespeaker.api.config import JWTConfig
from nativespeaker.api.errors import (
    AppError,
    NotLinked,
    RevocationUnconfirmed,
    Unavailable,
    UserNotFound,
)
from nativespeaker.api.tables.identities import IdentityProvider

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


# The providerData shapes the accept and reject tables below are built from.
GOOGLE = ("google.com", "google-uid-1")
APPLE = ("apple.com", "apple-uid-1")
PASSWORD = ("password", "user@example.test")
FACEBOOK = ("facebook.com", "facebook-uid-1")
GOOGLE_NO_UID = ("google.com", "")
APPLE_NO_UID = ("apple.com", "")
GOOGLE_OTHER = ("google.com", "google-uid-2")

def _record(entries, email=None, email_verified=False) -> StubUserRecord:
    """A `UserRecord` stand-in whose providerData is the given `(provider_id, uid)` shape."""
    return StubUserRecord(provider_data=[StubProviderUserInfo(provider_id, uid)
                                         for provider_id, uid in entries],
                          email=email,
                          email_verified=email_verified)


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
def firebase_logs(monkeypatch) -> list[tuple[str, dict]]:
    """A spy, not `capture_logs`: the module-level logger caches its binding at import."""
    records: list[tuple[str, dict]] = []
    for level in ("info", "warning", "error"):
        monkeypatch.setattr(f"nativespeaker.api.auth.firebase.logger.{level}",
                            lambda event, **fields: records.append((event, fields)))
    return records


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


@pytest.fixture
def revoke_calls(monkeypatch):
    """Monkeypatches `auth.revoke_refresh_tokens` to record its calls; the test scripts the answer."""
    calls: list[dict] = []

    def script(answer):
        def fake_revoke(uid, app=None):
            calls.append({"uid": uid, "app": app})
            if isinstance(answer, BaseException):
                raise answer
            # The SDK returns nothing on a confirmed revocation, so neither does the stand-in.
            return None
        monkeypatch.setattr(auth, "revoke_refresh_tokens", fake_revoke)
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

    @pytest.mark.parametrize("failure", ["DefaultCredentialsError", "RefreshError",
                                         "TransportError", "MutualTLSChannelError"])
    def test_every_adc_failure_is_that_absent_state_and_never_a_dead_pod(self, monkeypatch,
                                                                        failure):
        """WR-08b, the twin of WR-08: a metadata server that answers badly raises a different
        `GoogleAuthError` subclass, and caught narrowly it escaped `lifespan` and crashlooped the
        pod -- under a docstring that promises this reader never raises."""
        def raising(*_args, **_kwargs):
            raise getattr(google.auth.exceptions, failure)(f"{failure} in this test")

        def explode(*_args, **_kwargs):
            raise AssertionError("initialize_app must not be called with no credential")

        monkeypatch.setattr(google.auth, "default", raising)
        monkeypatch.setattr(firebase_admin, "initialize_app", explode)

        assert _application_default_credential() is None
        assert build_admin_apps(StubConfig()) == {}

    def test_a_supplied_credential_is_still_read_control(self, monkeypatch):
        """The control: a reader that answered `None` unconditionally would pass every case above."""
        monkeypatch.setattr(google.auth, "default", lambda *a, **k: (object(), PROJECT_ID))

        assert isinstance(_application_default_credential(), credentials.ApplicationDefault)

    def test_the_per_attempt_timeout_sits_inside_the_mandated_band(self):
        """`adapters.py`'s preamble: a fixed configured per-attempt timeout on the order of 5-10 s."""
        assert 5 <= FIREBASE_HTTP_TIMEOUT_SECONDS <= 10


class TestSelection:
    """One client selected by issuer match, with no fallback expressible."""

    async def test_an_unconfigured_issuer_fails_closed_and_calls_nothing(self, adapter,
                                                                        get_user_calls):
        calls = get_user_calls(StubUserRecord())
        with pytest.raises(Unavailable) as raised:
            await adapter.get_user_provider_data(OTHER_ISSUER, SUBJECT)
        assert raised.value.stage == "issuer_selection"
        assert calls == []

    async def test_an_empty_mapping_fails_closed_for_every_issuer(self, get_user_calls):
        calls = get_user_calls(StubUserRecord())
        with pytest.raises(Unavailable) as raised:
            await FirebaseAdminLookup({}).get_user_provider_data(ISSUER, SUBJECT)
        assert raised.value.stage == "issuer_selection"
        assert calls == []

    async def test_the_issuer_arm_answers_the_retryable_class_not_a_hard_failure(self, adapter):
        """503, not 500: a misconfigured issuer is ours to fix, and the caller may usefully come back."""
        with pytest.raises(Unavailable) as raised:
            await adapter.get_user_provider_data(OTHER_ISSUER, SUBJECT)
        assert raised.value.status == 503
        assert raised.value.code == "verification_temporarily_unavailable"

    async def test_a_configured_issuer_passes_its_own_app_explicitly(self, adapter, app,
                                                                    get_user_calls):
        """A forgotten `app=` would reach the `[DEFAULT]` app -- which is why none is created."""
        calls = get_user_calls(StubUserRecord())
        await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert calls == [{"uid": SUBJECT, "app": app}]


class TestTheRevocation:
    """The second seam method: its app selection, its confirmed answer, and its four raising arms."""

    async def test_a_configured_issuer_passes_its_own_app_explicitly(self, adapter, app,
                                                                     revoke_calls):
        """A forgotten `app=` would reach the `[DEFAULT]` app -- which is why none is created."""
        calls = revoke_calls(None)
        await adapter.revoke_refresh_tokens(ISSUER, SUBJECT)
        assert calls == [{"uid": SUBJECT, "app": app}]

    async def test_a_confirmed_revocation_returns_none(self, adapter, revoke_calls):
        """The call returning without a raise is the whole confirmation; there is no value to read."""
        revoke_calls(None)
        assert await adapter.revoke_refresh_tokens(ISSUER, SUBJECT) is None

    async def test_an_unconfigured_issuer_fails_closed_and_calls_nothing(self, adapter,
                                                                        revoke_calls):
        calls = revoke_calls(None)
        with pytest.raises(RevocationUnconfirmed) as raised:
            await adapter.revoke_refresh_tokens(OTHER_ISSUER, SUBJECT)
        assert raised.value.stage == "issuer_selection"
        assert calls == []

    async def test_an_empty_mapping_fails_closed_for_every_issuer(self, revoke_calls):
        calls = revoke_calls(None)
        with pytest.raises(RevocationUnconfirmed) as raised:
            await FirebaseAdminLookup({}).revoke_refresh_tokens(ISSUER, SUBJECT)
        assert raised.value.stage == "issuer_selection"
        assert calls == []

    async def test_the_issuer_arm_answers_the_retryable_class_not_a_hard_failure(self, adapter):
        """503, not 500: a misconfigured issuer is ours to fix, and the caller may usefully come back."""
        with pytest.raises(RevocationUnconfirmed) as raised:
            await adapter.revoke_refresh_tokens(OTHER_ISSUER, SUBJECT)
        assert raised.value.status == 503
        assert raised.value.code == "verification_temporarily_unavailable"

    async def test_a_vanished_account_is_unconfirmed_and_never_the_firebase_error_arm(
            self, adapter, revoke_calls):
        """WR-29. `UserNotFoundError` subclasses `FirebaseError`; a reordered `except` would
        misclassify it as retryable, and spec 11 admits no `auth_required` past the barrier."""
        assert issubclass(auth.UserNotFoundError, exceptions.FirebaseError)
        revoke_calls(auth.UserNotFoundError(PROVIDER_TEXT))
        with pytest.raises(RevocationUnconfirmed) as raised:
            await adapter.revoke_refresh_tokens(ISSUER, SUBJECT)
        assert raised.value.stage == "subject_absent"
        # Never a 401: telling a client with a verified token to re-authenticate is a loop.
        assert (raised.value.status, raised.value.code) == (503,
                                                            "verification_temporarily_unavailable")
        assert not isinstance(raised.value, UserNotFound)
        # Definitive, so it must not be the retry marker either: another call answers the same.
        assert not isinstance(raised.value, RetryableLookupError)

    async def test_the_provider_lookup_still_answers_the_401_arm_control(self, adapter):
        """The control: WR-29 narrows the revocation alone, and spec 11 does map the read to 401."""
        assert UserNotFound.status == 401
        assert "provider_lookup" == UserNotFound(stage="provider_lookup").stage

    async def test_a_malformed_subject_is_definitive_and_never_the_retry_marker(self, adapter,
                                                                               revoke_calls):
        """The SDK checks the uid before it sends the request, so another attempt answers the same."""
        revoke_calls(ValueError("Invalid uid: the uid must be a non-empty string"))
        with pytest.raises(RevocationUnconfirmed) as raised:
            await adapter.revoke_refresh_tokens(ISSUER, SUBJECT)
        assert raised.value.stage == "subject_rejected"
        # The read classes this arm as retryable; here it must not be, or a settled uid burns the budget.
        assert not isinstance(raised.value, RetryableLookupError)

    async def test_a_firebase_error_is_retryable(self, adapter, revoke_calls):
        revoke_calls(exceptions.FirebaseError("unavailable", PROVIDER_TEXT))
        with pytest.raises(RetryableLookupError):
            await adapter.revoke_refresh_tokens(ISSUER, SUBJECT)

    async def test_a_credential_refresh_failure_is_retryable_and_never_escapes(self, adapter,
                                                                               revoke_calls):
        """A refresh error is none of the types the other arms catch, so without this arm it escapes as a 500."""
        assert not issubclass(google.auth.exceptions.RefreshError, exceptions.FirebaseError)
        revoke_calls(google.auth.exceptions.RefreshError("token refresh failed"))
        with pytest.raises(RetryableLookupError):
            await adapter.revoke_refresh_tokens(ISSUER, SUBJECT)


class TestSuccessfulReads:
    """A completed read produces the seam's one value type, never the SDK's own objects."""

    async def test_empty_provider_data_is_the_anonymous_identity(self, adapter, get_user_calls):
        get_user_calls(StubUserRecord(provider_data=()))
        identity = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert isinstance(identity, VerifiedProviderIdentity)
        assert identity.provider is IdentityProvider.anonymous
        assert identity.provider_uid is None


class TestTheEmailRuleIsAppliedInsideTheRead:
    """The two-condition copy rule: absent, empty after stripping, or unverified each withholds the address."""

    async def test_a_non_empty_verified_address_is_copied(self, adapter, get_user_calls):
        get_user_calls(StubUserRecord(email="a@b.test", email_verified=True))
        identity = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert identity.email == "a@b.test"

    @pytest.mark.parametrize("email,email_verified,why", [
        ("a@b.test", False, "unverified -- the second condition fails"),
        (None, True, "absent -- the first condition fails"),
        ("", True, "empty -- the first condition fails"),
        ("   ", True, "whitespace only is not an address"),
        (None, False, "neither condition holds"),
    ], ids=["unverified", "absent", "empty", "whitespace-only", "neither"])
    async def test_every_other_combination_yields_none(self, adapter, get_user_calls,
                                                       email, email_verified, why):
        """The read judges now; no downstream predicate is left to turn any of these into `None`."""
        get_user_calls(StubUserRecord(email=email, email_verified=email_verified))
        identity = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert identity.email is None, why

    async def test_the_address_is_returned_verbatim_and_never_normalized(self, adapter,
                                                                        get_user_calls):
        """The `.strip()` inside the rule is a non-empty test, not a normalization step."""
        get_user_calls(StubUserRecord(email="  Mixed.Case@B.TEST  ", email_verified=True))
        identity = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert identity.email == "  Mixed.Case@B.TEST  "

    async def test_the_address_rides_out_on_a_classified_identity_too(self, adapter,
                                                                     get_user_calls):
        """Both rules are applied to the same read, so neither can quietly suppress the other."""
        get_user_calls(_record((GOOGLE,), email="a@b.test", email_verified=True))
        identity = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert (identity.provider, identity.provider_uid, identity.email) == (
            IdentityProvider.google, "google-uid-1", "a@b.test")


class TestFailureMapping:
    """Every SDK failure mode becomes either the internal retry marker or a family rejection."""

    async def test_user_not_found_is_definitive(self, adapter, get_user_calls):
        """Non-retryable, so it is deliberately not the marker the retry predicate catches."""
        get_user_calls(auth.UserNotFoundError(PROVIDER_TEXT))
        with pytest.raises(UserNotFound) as raised:
            await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert raised.value.stage == "provider_lookup"
        assert raised.value.status == 401

    async def test_a_firebase_error_is_retryable(self, adapter, get_user_calls):
        get_user_calls(exceptions.FirebaseError("unavailable", PROVIDER_TEXT))
        with pytest.raises(RetryableLookupError):
            await adapter.get_user_provider_data(ISSUER, SUBJECT)

    async def test_a_credential_refresh_failure_is_retryable_and_never_escapes(self, adapter,
                                                                              get_user_calls):
        """A refresh error is none of the types the other arms catch, so without this arm it escapes as a 500."""
        assert not issubclass(google.auth.exceptions.RefreshError, exceptions.FirebaseError)
        assert not issubclass(google.auth.exceptions.RefreshError, ValueError)
        get_user_calls(google.auth.exceptions.RefreshError("token refresh failed"))
        with pytest.raises(RetryableLookupError):
            await adapter.get_user_provider_data(ISSUER, SUBJECT)

    async def test_a_credential_failure_spends_the_full_retry_budget(self, adapter, monkeypatch):
        """The point of a separate internal marker: the policy can actually retry this one."""
        calls = []

        def failing_get_user(uid, app=None):
            calls.append(uid)
            raise google.auth.exceptions.RefreshError("token refresh failed")

        monkeypatch.setattr(auth, "get_user", failing_get_user)
        with pytest.raises(Unavailable) as raised:
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert raised.value.stage == "provider_lookup"
        assert len(calls) == FIREBASE_LOOKUP_ATTEMPTS

    async def test_a_lazy_provider_data_value_error_is_definitive_and_spends_no_budget(
            self, adapter, get_user_calls):
        """WR-01: the empty-`rawId` shape is materialized off a response already in hand, so a
        second attempt re-derives it. Definitive, exactly as `_revoke` classifies the same type."""
        calls = get_user_calls(StubUserRecord(raises=ValueError("User ID must not be None or empty.")))

        with pytest.raises(Unavailable) as raised:
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert raised.value.stage == "provider_lookup"
        # The point of the change: one call, never the three a retryable classification would spend.
        assert len(calls) == 1

    async def test_user_not_found_is_not_swallowed_by_the_firebase_error_arm(self, adapter,
                                                                            get_user_calls):
        """`UserNotFoundError` subclasses `FirebaseError`; a reordered `except` would misclassify."""
        assert issubclass(auth.UserNotFoundError, exceptions.FirebaseError)
        get_user_calls(auth.UserNotFoundError(PROVIDER_TEXT))
        with pytest.raises(UserNotFound):
            await adapter.get_user_provider_data(ISSUER, SUBJECT)

    def test_the_internal_marker_is_not_a_member_of_the_rejection_family(self):
        """It declares no status or code, so an escape is a loud 500 rather than a wrong body."""
        assert not issubclass(RetryableLookupError, AppError)
        assert not hasattr(RetryableLookupError, "code")


class TestNoProviderTextLeaks:
    """The seam's preamble: provider diagnostics are log material, never response material."""

    @pytest.mark.parametrize("answer", [
        auth.UserNotFoundError(PROVIDER_TEXT),
        exceptions.FirebaseError("unavailable", PROVIDER_TEXT),
        StubUserRecord(raises=ValueError(PROVIDER_TEXT)),
    ], ids=["user_not_found", "firebase_error", "malformed_provider_data"])
    async def test_the_client_facing_rejection_carries_none_of_the_providers_message(
            self, adapter, get_user_calls, answer):
        """Driven through the retry frame, so the internal marker is already converted to what a client sees."""
        get_user_calls(answer)
        with pytest.raises(AppError) as raised:
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        rendered = repr(raised.value.log_fields()) + repr(raised.value.args)
        assert PROVIDER_TEXT not in rendered
        assert "ns-test-project" not in rendered

    async def test_the_provider_lookups_own_log_line_carries_no_sdk_message(
            self, adapter, get_user_calls, firebase_logs):
        """WR-02: the SDK's `ValueError` text embeds the uid and the raw Identity Toolkit record,
        so the event name stands alone -- the rule `_revoke` states for the same exception type."""
        get_user_calls(StubUserRecord(raises=ValueError(PROVIDER_TEXT)))

        with pytest.raises(Unavailable):
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        # Equality over the whole list, so the record really fired and it carries no field at all:
        # an emptied `detail=` would leave the key behind, and a `str` filter would not see it.
        assert firebase_logs == [("firebase_provider_data_malformed", {})]

    async def test_the_internal_marker_does_carry_it_for_the_log(self, adapter, get_user_calls):
        """The control: the text is not merely absent everywhere, it is kept where the log needs it."""
        get_user_calls(exceptions.FirebaseError("unavailable", PROVIDER_TEXT))
        with pytest.raises(RetryableLookupError) as raised:
            await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert PROVIDER_TEXT in str(raised.value)



# The whole accept set. Three shapes, no fourth.
ACCEPTED = [
    ((), (IdentityProvider.anonymous, None), "empty providerData is anonymous"),
    ((GOOGLE,), (IdentityProvider.google, "google-uid-1"), "exactly one google.com entry"),
    ((APPLE,), (IdentityProvider.apple, "apple-uid-1"), "exactly one apple.com entry"),
]

# Everything else; each case names the prohibition it would violate if it were accepted.
REJECTED = [
    ((GOOGLE, APPLE), "both providers, google first -- never take the first recognized entry"),
    ((APPLE, GOOGLE), "both providers, apple first -- rejection is order-independent"),
    ((GOOGLE, GOOGLE_OTHER), "two google.com entries -- multiple entries never classify"),
    ((PASSWORD,), "the e2e credential's shape -- `password` is not a recognized provider"),
    ((FACEBOOK,), "an unrecognized provider id"),
    ((GOOGLE_NO_UID,), "an empty uid is malformed/indeterminate, never persisted"),
    ((APPLE_NO_UID,), "an empty uid is malformed/indeterminate, never persisted"),
    ((GOOGLE, FACEBOOK), "recognized first, unrecognized second -- the recognized one is not taken"),
    ((FACEBOOK, GOOGLE), "unrecognized first, recognized second -- same answer, either way"),
]


class TestTheAcceptSet:
    """Exactly three shapes classify. `provider_uid` is NULL for anonymous and the uid otherwise."""

    @pytest.mark.parametrize("entries,expected,why", ACCEPTED, ids=[case[2] for case in ACCEPTED])
    async def test_a_recognized_shape_classifies(self, adapter, get_user_calls,
                                                 entries, expected, why):
        get_user_calls(_record(entries))
        identity = await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert (identity.provider, identity.provider_uid) == expected, why

    def test_the_recognized_provider_map_has_exactly_two_keys(self):
        """A third recognized provider is a spec change, not a refactor."""
        from nativespeaker.api.auth import firebase
        assert set(firebase._RECOGNIZED) == {"google.com", "apple.com"}


class TestTheRejectSet:
    """Shapes that must never be linked to a provider account the caller may not own."""

    @pytest.mark.parametrize("entries,why", REJECTED, ids=[case[1] for case in REJECTED])
    async def test_an_unrecognized_shape_rejects(self, adapter, get_user_calls, entries, why):
        get_user_calls(_record(entries))
        with pytest.raises(NotLinked) as raised:
            await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert raised.value.stage == "provider_classification", why

    async def test_the_rejection_carries_the_one_bounded_cause(self, adapter, get_user_calls):
        """The bounded string is ours; the shape that produced it never reaches a client."""
        get_user_calls(_record((PASSWORD,)))
        with pytest.raises(NotLinked) as raised:
            await adapter.get_user_provider_data(ISSUER, SUBJECT)
        assert raised.value.cause == "invalid-shape"
        assert raised.value.status == 403

    async def test_a_rejecting_shape_spends_exactly_one_attempt(self, adapter, monkeypatch):
        """Classification is definitive, so the budget is for outages and not for a settled verdict."""
        calls = []

        def counting_get_user(uid, app=None):
            calls.append(uid)
            return _record((PASSWORD,))

        monkeypatch.setattr(auth, "get_user", counting_get_user)
        with pytest.raises(NotLinked):
            await lookup_with_retry(adapter, ISSUER, SUBJECT)
        assert len(calls) == 1

    async def test_a_not_found_read_is_answered_before_any_shape_is_classified(
            self, adapter, get_user_calls):
        """Classifying first would answer a terminal 403 to a caller whose token merely no longer
        identifies a user, so the not-found arm answers even for a shape that would reject."""
        get_user_calls(auth.UserNotFoundError(PROVIDER_TEXT))
        with pytest.raises(UserNotFound):
            await adapter.get_user_provider_data(ISSUER, SUBJECT)


class TestTheClassifierRecordsItsProhibitions:
    """The prohibitions recorded where the next reader is."""

    @pytest.mark.parametrize("phrase", [
        "never take the first recognized entry",
        "never classify non-empty providerdata as anonymous",
        "never read `firebase.sign_in_provider`",
        "no declaration match",
        "no `required_flow`",
    ])
    def test_the_module_docstring_records_the_prohibitions(self, phrase):
        from nativespeaker.api.auth import firebase
        assert phrase in firebase.__doc__.lower()

    @pytest.mark.parametrize("name", ["sign_in_provider", "required_flow"])
    def test_neither_deleted_concept_appears_outside_the_docstring(self, name):
        """Checks the code rather than the file: strip the docstrings and neither identifier survives."""
        import ast
        from pathlib import Path

        from nativespeaker.api.auth import firebase
        source = Path(firebase.__file__).read_text()
        code = source.replace(ast.get_docstring(ast.parse(source), clean=False), "", 1)
        assert name not in code


class TestTheDeliberateNonImplementations:
    """The concrete lookup is not the seam: it conforms structurally and claims nothing more."""

    def test_the_class_is_not_annotated_as_the_full_protocol(self):
        """A Protocol is satisfied structurally, so conforming to it is never a reason to inherit it."""
        from nativespeaker.api.auth.adapters import FirebaseAdminAdapter
        assert FirebaseAdminAdapter not in FirebaseAdminLookup.__mro__
