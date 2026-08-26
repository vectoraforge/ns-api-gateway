"""The closed providerData classifier and the email-copy predicate, both written table-driven."""
import pytest

from nativespeaker.api.auth.adapters import (
    ProviderDataEntry,
    ProviderDataOutcome,
    ProviderDataResult,
)
from nativespeaker.api.auth.firebase import classify_provider_data, email_to_persist
from nativespeaker.api.models.identities import IdentityProvider

GOOGLE = ProviderDataEntry(provider_id="google.com", uid="google-uid-1")
APPLE = ProviderDataEntry(provider_id="apple.com", uid="apple-uid-1")
PASSWORD = ProviderDataEntry(provider_id="password", uid="user@example.test")
FACEBOOK = ProviderDataEntry(provider_id="facebook.com", uid="facebook-uid-1")
GOOGLE_NO_UID = ProviderDataEntry(provider_id="google.com", uid="")
APPLE_NO_UID = ProviderDataEntry(provider_id="apple.com", uid="")
GOOGLE_OTHER = ProviderDataEntry(provider_id="google.com", uid="google-uid-2")

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
    def test_a_recognized_shape_classifies(self, entries, expected, why):
        assert classify_provider_data(entries) == expected, why

    def test_anonymous_carries_no_provider_uid(self):
        """`core.external_identities`' CHECK requires NULL for anonymous and forbids a sentinel."""
        provider, provider_uid = classify_provider_data(())
        assert provider is IdentityProvider.anonymous
        assert provider_uid is None

    @pytest.mark.parametrize("entry,provider", [(GOOGLE, IdentityProvider.google),
                                                (APPLE, IdentityProvider.apple)])
    def test_the_matching_entrys_uid_is_the_sole_source_of_provider_uid(self, entry, provider):
        """The matching entry's non-empty uid is the only source of `provider_uid`."""
        assert classify_provider_data((entry,)) == (provider, entry.uid)

    def test_the_recognized_provider_map_has_exactly_two_keys(self):
        """A third recognized provider is a spec change, not a refactor."""
        from nativespeaker.api.auth import firebase
        assert set(firebase._RECOGNIZED) == {"google.com", "apple.com"}


class TestTheRejectSet:
    """Shapes that must never be linked to a provider account the caller may not own."""

    @pytest.mark.parametrize("entries,why", REJECTED, ids=[case[1] for case in REJECTED])
    def test_an_unrecognized_shape_rejects(self, entries, why):
        assert classify_provider_data(entries) is None, why

    @pytest.mark.parametrize("pair", [(GOOGLE, APPLE), (GOOGLE, FACEBOOK), (GOOGLE, GOOGLE_OTHER)])
    def test_rejection_is_order_independent(self, pair):
        """Both orderings, because a classifier taking the first entry it recognizes passes only one of them."""
        first, second = pair
        assert classify_provider_data((first, second)) is None
        assert classify_provider_data((second, first)) is None

    def test_a_two_entry_shape_rejects_even_when_both_entries_are_the_same_provider(self):
        assert classify_provider_data((GOOGLE, GOOGLE)) is None


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


class TestEmailToPersist:
    """The two-condition copy rule, evaluated in exactly one place."""

    @staticmethod
    def _ok(email, email_verified):
        return ProviderDataResult(outcome=ProviderDataOutcome.ok,
                                  entries=(GOOGLE,),
                                  email=email,
                                  email_verified=email_verified)

    def test_a_non_empty_verified_address_is_copied(self):
        assert email_to_persist(self._ok("a@b.test", True)) == "a@b.test"

    @pytest.mark.parametrize("email,email_verified,why", [
        ("a@b.test", False, "unverified -- the second condition fails"),
        (None, True, "absent -- the first condition fails"),
        ("", True, "empty -- the first condition fails"),
        ("   ", True, "whitespace only is not an address"),
        (None, False, "neither condition holds"),
    ], ids=["unverified", "absent", "empty", "whitespace-only", "neither"])
    def test_every_other_combination_yields_none(self, email, email_verified, why):
        assert email_to_persist(self._ok(email, email_verified)) is None, why

    @pytest.mark.parametrize("outcome", [ProviderDataOutcome.user_not_found,
                                         ProviderDataOutcome.retryable_failure,
                                         ProviderDataOutcome.selection_failure])
    def test_a_non_ok_outcome_never_yields_an_address(self, outcome):
        """The defaults make `None` the only reachable answer on a failure arm."""
        assert email_to_persist(ProviderDataResult(outcome)) is None

    def test_a_non_ok_outcome_yields_none_even_if_the_fields_were_somehow_populated(self):
        """The outcome gate is checked, not merely implied by the defaults."""
        result = ProviderDataResult(outcome=ProviderDataOutcome.retryable_failure,
                                    email="a@b.test",
                                    email_verified=True)
        assert email_to_persist(result) is None

    def test_the_address_is_returned_verbatim_and_never_normalized(self):
        """The `.strip()` inside the predicate is a non-empty test, not a normalization step."""
        assert email_to_persist(self._ok("  Mixed.Case@B.TEST  ", True)) == "  Mixed.Case@B.TEST  "


class TestTheProviderDataResultAmendment:
    """The Phase 35 foundation amendment: two fields, both defaulted, no caller changed."""

    def test_the_result_declares_exactly_four_fields(self):
        from dataclasses import fields
        assert [f.name for f in fields(ProviderDataResult)] == [
            "outcome", "entries", "email", "email_verified",
        ]

    def test_a_pre_existing_construction_site_still_takes_one_positional_argument(self):
        """`ProviderDataResult(ProviderDataOutcome.selection_failure)` -- unchanged by the amendment."""
        result = ProviderDataResult(ProviderDataOutcome.selection_failure)
        assert result.outcome is ProviderDataOutcome.selection_failure
        assert result.entries == ()
        assert result.email is None
        assert result.email_verified is False
