"""The closed providerData classifier and the email-copy rule, both written table-driven.

Both now live inside `_read` rather than beside it, so this file drives the two module-private
helpers directly. The same cases against the whole adapter -- which is where they belong once the
classification is adapter-internal -- are the subject of the next task.
"""
import pytest

from nativespeaker.api.auth.exceptions import NotLinked
from nativespeaker.api.auth.firebase import _resolve_provider, _verified_email
from nativespeaker.api.models.identities import IdentityProvider

GOOGLE = ("google.com", "google-uid-1")
APPLE = ("apple.com", "apple-uid-1")
PASSWORD = ("password", "user@example.test")
FACEBOOK = ("facebook.com", "facebook-uid-1")
GOOGLE_NO_UID = ("google.com", "")
APPLE_NO_UID = ("apple.com", "")
GOOGLE_OTHER = ("google.com", "google-uid-2")

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
        assert _resolve_provider(entries) == expected, why

    def test_anonymous_carries_no_provider_uid(self):
        """`core.external_identities`' CHECK requires NULL for anonymous and forbids a sentinel."""
        provider, provider_uid = _resolve_provider(())
        assert provider is IdentityProvider.anonymous
        assert provider_uid is None

    @pytest.mark.parametrize("entry,provider", [(GOOGLE, IdentityProvider.google),
                                                (APPLE, IdentityProvider.apple)])
    def test_the_matching_entrys_uid_is_the_sole_source_of_provider_uid(self, entry, provider):
        """The matching entry's non-empty uid is the only source of `provider_uid`."""
        assert _resolve_provider((entry,)) == (provider, entry[1])

    def test_the_recognized_provider_map_has_exactly_two_keys(self):
        """A third recognized provider is a spec change, not a refactor."""
        from nativespeaker.api.auth import firebase
        assert set(firebase._RECOGNIZED) == {"google.com", "apple.com"}


class TestTheRejectSet:
    """Shapes that must never be linked to a provider account the caller may not own."""

    @pytest.mark.parametrize("entries,why", REJECTED, ids=[case[1] for case in REJECTED])
    def test_an_unrecognized_shape_rejects(self, entries, why):
        with pytest.raises(NotLinked) as raised:
            _resolve_provider(entries)
        assert raised.value.stage == "provider_classification", why

    def test_the_rejection_carries_the_one_bounded_cause(self):
        """The bounded string is ours; the shape that produced it never reaches a client."""
        with pytest.raises(NotLinked) as raised:
            _resolve_provider((PASSWORD,))
        assert raised.value.cause == "invalid-shape"

    @pytest.mark.parametrize("pair", [(GOOGLE, APPLE), (GOOGLE, FACEBOOK), (GOOGLE, GOOGLE_OTHER)])
    def test_rejection_is_order_independent(self, pair):
        """Both orderings, because a classifier taking the first entry it recognizes passes only one of them."""
        first, second = pair
        with pytest.raises(NotLinked):
            _resolve_provider((first, second))
        with pytest.raises(NotLinked):
            _resolve_provider((second, first))

    def test_a_two_entry_shape_rejects_even_when_both_entries_are_the_same_provider(self):
        with pytest.raises(NotLinked):
            _resolve_provider((GOOGLE, GOOGLE))


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


class TestTheVerifiedEmailRule:
    """The two-condition copy rule, evaluated in exactly one place."""

    def test_a_non_empty_verified_address_is_copied(self):
        assert _verified_email("a@b.test", True) == "a@b.test"

    @pytest.mark.parametrize("email,email_verified,why", [
        ("a@b.test", False, "unverified -- the second condition fails"),
        (None, True, "absent -- the first condition fails"),
        ("", True, "empty -- the first condition fails"),
        ("   ", True, "whitespace only is not an address"),
        (None, False, "neither condition holds"),
    ], ids=["unverified", "absent", "empty", "whitespace-only", "neither"])
    def test_every_other_combination_yields_none(self, email, email_verified, why):
        assert _verified_email(email, email_verified) is None, why

    def test_the_address_is_returned_verbatim_and_never_normalized(self):
        """The `.strip()` inside the rule is a non-empty test, not a normalization step."""
        assert _verified_email("  Mixed.Case@B.TEST  ", True) == "  Mixed.Case@B.TEST  "
