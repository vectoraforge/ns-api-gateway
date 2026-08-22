"""§02 step 9's closed providerData classifier and step 10's email-copy predicate.

Two pure read-rules over a `getUser` response, expressed over foundation's dataclasses. No provider
import, no I/O, no session -- which is what lets both be unit-tested in wave 2, driven by a
substituted adapter in tests, and reused unchanged by phases 40/41/42.

**The three §02 step 9 prohibitions, in the negative, because each one names a way a best-effort
reading would link an account the caller may not own (T-37-15):**

* **Never take the first recognized entry.** The length check below runs *before* any per-entry
  inspection, so this is structural rather than a comment someone can drift away from. A
  providerData carrying both a `google.com` and an `apple.com` entry rejects in either order.
* **Never classify non-empty providerData as anonymous.** `anonymous` is the answer to an *empty*
  providerData and to nothing else.
* **Never read `firebase.sign_in_provider`.** The account's type comes from the linked provider
  entries, not from how the caller happened to sign in this time.

**What this module does not do, per D-12.** RESEARCH described it as owning the classification
*plus* the client-declaration match *plus* the `required_flow` derivation. D-12 deletes the client
flow declaration outright, so there is **no declaration match** here and **no `required_flow`**
derived anywhere -- neither concept exists to be evaluated. The closed classifier itself is
unchanged by that deletion.

**What a rejection means.** A rejecting shape is an unclassifiable *account*, not a declaration
mismatch. It audits as internal `provider_not_linked` with the bounded cause `empty` or
`invalid-shape` -- the third cause, `supported-provider-mismatch`, went with the declaration -- and
surfaces to the client as `operation_not_allowed`, with no flow named.
"""
from nativespeaker.api.auth.adapters import ProviderDataEntry, ProviderDataOutcome, ProviderDataResult
from nativespeaker.api.models.identities import IdentityProvider

# Exactly two recognized provider ids, verbatim from §02 step 9. A third is a spec change, not a
# refactor: it needs a `core.identity_provider` enum value, a migration, and an entitlement story.
_RECOGNIZED: dict[str, IdentityProvider] = {
    "google.com": IdentityProvider.google,
    "apple.com": IdentityProvider.apple,
}


def classify_provider_data(entries: tuple[ProviderDataEntry, ...]) -> tuple[IdentityProvider, str | None] | None:
    """Classify a successful `getUser` providerData read. `None` means reject.

    Returns `(provider, provider_uid)`. `provider_uid` is `None` **exactly** for `anonymous`: the
    `core.external_identities` CHECK requires NULL there and forbids a sentinel, and the row falls
    outside the provider-account reservation on purpose. For google and apple it is the matching
    entry's `uid`, which §02 makes the **sole** source of `provider_uid` -- never a token claim,
    never client input, never an email or display name.

    The empty-uid guard stays even though the SDK's `ProviderUserInfo.__init__` raises first on that
    shape (Pitfall 3, mapped to `retryable_failure` in `auth/firebase.py`). This function is also
    driven by substituted adapters in tests and by phases 40/41/42, and a correctness rule of its
    own must not depend on an upstream raise.
    """
    if not entries:
        return IdentityProvider.anonymous, None
    if len(entries) != 1:
        # Before any per-entry inspection: both providers, or two of one, or a recognized entry
        # beside an unrecognized one. There is no first entry to take.
        return None
    provider = _RECOGNIZED.get(entries[0].provider_id)
    if provider is None:
        # An unrecognized provider id -- `password` (the e2e credential's shape), `facebook.com`,
        # anything else Firebase may link.
        return None
    if not entries[0].uid:
        # Missing/empty uid = malformed or indeterminate lookup -> reject, no persistence.
        return None
    return provider, entries[0].uid


def email_to_persist(result: ProviderDataResult) -> str | None:
    """§02 step 10's email-copy rule, evaluated here and in **no** other module.

    "Copy `email` only when the same successful `getUser` response has a non-empty address AND
    `emailVerified = true`, else NULL." The two conditions are independent and both are checked;
    the outcome gate is checked too, so a failure arm can never yield an address even if a caller
    somehow populated the fields.

    The address is returned **exactly as the provider gave it** -- not lowercased, trimmed, or
    otherwise normalized. The `.strip()` below is a non-empty *test*, not a transform: a
    whitespace-only value is not an address.

    It lives beside the classifier rather than in `auth/firebase.py` (a persistence rule does not
    belong in the provider module, and the adapter reports rather than judges) and rather than in
    `auth/creation.py` (which keeps it a pure function, unit-testable without a session).
    `auth/creation.py` receives an already-resolved `email` argument and re-derives nothing, so
    there are never two sites that can disagree (T-37-34).
    """
    if result.outcome is not ProviderDataOutcome.ok:
        return None
    if result.email is None or not result.email.strip():
        return None
    if not result.email_verified:
        return None
    return result.email
