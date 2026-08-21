"""The §7.1 provider-call budget seam, as plain in-process counters (D-06).

**This is per-request provider-call metering. It is not traffic limiting.** A `BudgetGate` counts
outbound calls issued while serving *one* request; it does not count requests, and it cannot be
made to. D-05 deleted §5 -- the backend rate-limit engine -- from the product outright: Envoy
Gateway is the sole request-rate enforcement point. So there is deliberately no IP key, no user
key, no route key, no request key, no shared, persistent, or cross-request counter store, and no
`limits`, `redis`, or `valkey` dependency. That override of `SHARED-INVARIANTS.md` § Rate limits
and `01-foundation.md` §5 is recorded in `35-CONTEXT.md` as the required conflict flag rather than
resolved silently. `tests/unit/test_budgets.py::TestNotTrafficLimiting` fails if any of it returns.

`rate_limited` (429) still lives in the error registry regardless, per D-07 -- it is the class
Envoy's 429 body must name once the gateway contract lands. Exhaustion of a *budget* is not a
rate-limit rejection: it maps to internal `firebase_lookup_unavailable` -> client
`verification_temporarily_unavailable`, and `BudgetExhausted` carries that mapping as data.

The contract, from §7.1, and the reason the ordering is load-bearing:

    names = [ADAPTER_FIREBASE_LOOKUP, ...endpoint_layer_entries]   # broadest to narrowest
    if (blocked := gate.check_all(names)) is not None:             # reads, mutates nothing
        ...reject, recording gate.exhausted(names) in metrics
    gate.charge_all(names)                                         # all together, or not at all
    ...issue the outbound call

`check_all` never moves a counter, so a caller may call it as often as it likes. `charge_all` is
the only mutator, it re-checks before it touches anything, and it charges every name together or
raises -- no counter is incremented unless every applicable budget has capacity. Once charged they
stay charged however the call resolves, because budgets meter calls *actually issued*: callers
charge immediately before the outbound call and again before each permitted retry.

Foundation ships exactly one name. Every endpoint-layer name belongs to a later phase.
A `user_not_found` outcome is definitive, non-retryable, and spends no retry budget -- that is the
caller's concern in phase 37; this module only meters.

**Concurrency:** none is claimed. A gate is created per request and lives on that request's
context, so no counter is shared across requests, tasks, or processes. There is no lock, because
there is nothing to serialize -- unlike `resilience.CircuitBreaker`, which is process-wide.
"""
from collections.abc import Mapping, Sequence

from nativespeaker.api.errors import VERIFICATION_TEMPORARILY_UNAVAILABLE, ErrorClass
from nativespeaker.api.models.auth import AuthEventResult

# The one budget name foundation ships: the global provider-call budget guarding the Firebase
# Admin `getUser` lookup. It is the broadest budget, so callers name it first and it is the primary
# reported result when more than one is exhausted.
ADAPTER_FIREBASE_LOOKUP = "adapter_firebase_lookup"

# §7.1: 3 attempts total -- the initial call plus up to two additional -- for retryable causes only.
FIREBASE_LOOKUP_ATTEMPTS = 3


class BudgetExhausted(Exception):
    """`charge_all` refused because at least one named budget had no capacity. Nothing was charged.

    The §7.1 mapping travels on the class as data rather than as behaviour. Deliberately **not** a
    `ServiceError`: one that auto-converted to a 503 would let an unhandled exhaustion produce a
    perfectly plausible client response while silently skipping the `audit.auth_events` row the
    audited attempt path requires. The call site (phases 37/40/41/42) writes that row and builds
    the response; this module writes neither, and an unhandled `BudgetExhausted` is a loud 500.

    `primary` is the broadest exhausted name -- the first in the caller's broadest-to-narrowest
    order -- and `exhausted` is every one of them, for the metric §7.1 requires.
    """
    audit_result: AuthEventResult = AuthEventResult.firebase_lookup_unavailable
    error_class: ErrorClass = VERIFICATION_TEMPORARILY_UNAVAILABLE

    def __init__(self, primary: str, exhausted: Sequence[str]):
        self.primary = primary
        self.exhausted: tuple[str, ...] = tuple(exhausted)
        # Never client-visible: §3.1 pins the body to the class code alone, and plan 02 proves
        # `str(exc)` cannot reach it.
        super().__init__(f"provider-call budget {primary!r} exhausted (all: {', '.join(self.exhausted)})")


def _ordered_unique(names: Sequence[str]) -> list[str]:
    """First-occurrence order, duplicates dropped.

    One budget named twice is one budget. Deduplicating here is what makes `check_all` and
    `charge_all` structurally incapable of disagreeing: without it, `check_all([N, N])` against a
    remaining count of 1 would report capacity that `charge_all([N, N])` would then overspend.
    """
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


class BudgetGate:
    """Per-request provider-call metering. NOT traffic limiting (D-05).

    Construct one per request from a mapping of budget name to permitted call count, e.g.
    `BudgetGate({ADAPTER_FIREBASE_LOOKUP: FIREBASE_LOOKUP_ATTEMPTS})`.
    """

    def __init__(self, limits: Mapping[str, int]) -> None:
        remaining: dict[str, int] = {}
        for name, limit in limits.items():
            if not isinstance(limit, int) or isinstance(limit, bool):
                # No rounding path exists, so a float limit is rejected rather than truncated --
                # truncation would silently hand out a different number of provider calls than the
                # one written down. Python ints are arbitrary precision, so there is no overflow
                # path either.
                raise TypeError(f"budget {name!r} limit must be an int, got {type(limit).__name__}")
            # A negative limit is representable honestly as "no capacity", and clamping fails
            # closed. Raising instead would turn a constant-declaration bug into a 500 on every
            # request rather than a 503 on the one path that meters.
            remaining[name] = max(0, limit)
        self._remaining = remaining

    def remaining(self, name: str) -> int:
        """Calls still permitted under `name`. Never negative, and zero for an unknown name.

        An undeclared budget fails closed rather than reading as unlimited: a caller naming a
        budget this gate was not built with is a bug, and the safe reading of that bug is that the
        provider call is not permitted.
        """
        return self._remaining.get(name, 0)

    def check_all(self, names: Sequence[str]) -> str | None:
        """Return the first exhausted name in `names`, or `None` when every one has capacity.

        Non-destructive: it reads counters and mutates nothing, so it may be called any number of
        times. `names` is the caller's order, broadest to narrowest -- §7.1 makes the global
        `adapter_firebase_lookup` the primary reported result, and that holds because the caller
        names it first, not because this method sorts anything.
        """
        for name in _ordered_unique(names):
            if self._remaining.get(name, 0) <= 0:
                return name
        return None

    def exhausted(self, names: Sequence[str]) -> list[str]:
        """Every exhausted name, in the caller's order -- the metric companion to `check_all`.

        §7.1 records *all* exhausted limiters alongside the primary. Non-destructive.
        """
        return [name for name in _ordered_unique(names) if self._remaining.get(name, 0) <= 0]

    def charge_all(self, names: Sequence[str]) -> None:
        """Spend one call against every name, together, or raise `BudgetExhausted` and spend none.

        The re-check is not redundant with `check_all`: it is what makes the all-or-nothing
        property hold at this method rather than at its call sites. Counters move only after every
        name has been proven to have capacity, so no partial charge is observable -- not on an
        exception path, not by ordering, not ever.
        """
        unique = _ordered_unique(names)
        blocked = [name for name in unique if self._remaining.get(name, 0) <= 0]
        if blocked:
            raise BudgetExhausted(blocked[0], blocked)
        for name in unique:
            self._remaining[name] -= 1
