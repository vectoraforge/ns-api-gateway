"""Introductory entitlement: exactly the free-credit grant the two claim operations create."""

from enum import StrEnum

from nativespeaker.api.auth.operations import AuthOperation


class AccessGrantSource(StrEnum):
    """`core.access_grant_source`. There is no introductory source, type, counter or flag."""
    subscription = "subscription"
    anonymous_device_grant = "anonymous_device_grant"
    registered_account_grant = "registered_account_grant"
    manual = "manual"


# Introductory entitlement is exactly what `claim_anonymous_grant` and `claim_registered_grant`
# create, through those two free-credit grant sources and nothing else.
# [impl->req~shared-introductory-entitlement-definition~1]
INTRODUCTORY_GRANT_SOURCES: dict[AccessGrantSource, AuthOperation] = {
    AccessGrantSource.anonymous_device_grant: AuthOperation.claim_anonymous_grant,
    AccessGrantSource.registered_account_grant: AuthOperation.claim_registered_grant,
}

# Authentication, identity resolution and the in-place anonymous-to-registered upgrade
# allocate nothing implicitly.
NON_ALLOCATING_OPERATIONS: frozenset[AuthOperation] = frozenset({
    AuthOperation.create_user,
    AuthOperation.upgrade_anonymous_to_registered,
    AuthOperation.sign_out_all,
    AuthOperation.sync,
})


class GrantMutation(StrEnum):
    """What the prohibition forbids of a non-allocating operation."""
    access_grant_write = "access_grant_write"
    claim_path_invocation = "claim_path_invocation"
    usage_counter_as_entitlement = "usage_counter_as_entitlement"


class IntroductoryEntitlementError(RuntimeError):
    """An operation attempted an allocation this specification forbids it."""


def allocates_introductory_entitlement(operation: AuthOperation) -> bool:
    """Introductory entitlement does not exist before a successful claim, and no other
    operation allocates or implies it."""
    return operation in set(INTRODUCTORY_GRANT_SOURCES.values())


def guard_grant_mutation(operation: AuthOperation,
                         mutation: GrantMutation,
                         *,
                         source: AccessGrantSource | None = None) -> None:
    """Fail closed on the prohibition: a non-allocating operation may not create or modify a
    `core.access_grants` row, may not invoke either claim path, and no operation may treat a
    `core.user_monthly_usage` counter as an entitlement."""
    # [impl->req~shared-introductory-entitlement-prohibition~1]
    if mutation is GrantMutation.usage_counter_as_entitlement:
        raise IntroductoryEntitlementError(
            "a monthly usage counter is never an entitlement")
    if operation in NON_ALLOCATING_OPERATIONS:
        raise IntroductoryEntitlementError(f"{operation} must not allocate entitlement")
    if source in INTRODUCTORY_GRANT_SOURCES and INTRODUCTORY_GRANT_SOURCES[source] is not operation:
        raise IntroductoryEntitlementError(f"{operation} may not create a {source} grant")
