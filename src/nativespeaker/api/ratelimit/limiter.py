"""The backend `limits` layer.

Endpoint-specific rate limits are enforced with the Python `limits` library, through the
configured strategy and the configured storage backend. Nothing here holds a limit of its own:
every decision reads a named entry out of the application configuration file.
"""

import math
import time
from dataclasses import dataclass, field

from limits import RateLimitItem
from limits.storage import Storage, storage_from_string
from limits.strategies import STRATEGIES
from limits.strategies import RateLimiter as LimitsStrategy

from nativespeaker.api.ratelimit.config import (
    FailureMode,
    RateLimitConfigError,
    RateLimitEntry,
    RateLimitsConfig,
)
from nativespeaker.api.ratelimit.keys import GatewayResolvedAddress, canonical_client_ip_key


class UnconfiguredLimitError(RateLimitConfigError):
    """A call site asked for a limit the configuration file does not declare. No endpoint may
    hard-code its own limit string, key function, cost, strategy, enabled state or failure
    behaviour, so an unconfigured name is a configuration error and never a built-in fallback."""


@dataclass(frozen=True, slots=True)
class LimitDecision:
    """One limiter's verdict."""
    allowed: bool
    limiter: str
    retry_after_seconds: int | None = None
    storage_failed: bool = False
    charged: bool = False
    exhausted: tuple[str, ...] = field(default_factory=tuple)


class RateLimiter:
    """Evaluates the configured entries against the configured `limits` storage."""

    def __init__(self, config: RateLimitsConfig, storage: Storage | None = None):
        # Counters live in the configured `limits` storage backend, not in the auth refactor
        # PostgreSQL schema: the storage is built from the configured URI and this object holds
        # no database session of any kind.
        # [impl->req~ratelimit-limits-library-and-storage-separation~1]
        # [impl->req~ratelimit-shared-storage-in-production~1]
        # [impl->req~ratelimit-config-key-storage-uri~1]
        self._config = config
        self._storage = storage if storage is not None else storage_from_string(config.storage_uri)
        # [impl->req~ratelimit-config-key-strategy~1]
        self._strategy: LimitsStrategy = STRATEGIES[str(config.strategy)](self._storage)

    @property
    def strategy(self) -> LimitsStrategy:
        return self._strategy

    def entry(self, name: str) -> RateLimitEntry:
        """The named entry, read from configuration and nowhere else."""
        # [impl->req~ratelimit-all-limits-in-config-no-hardcoding~1]
        found = self._config.entries.get(name)
        if found is None:
            raise UnconfiguredLimitError(f"{name!r} is not a configured rate-limit entry")
        return found

    def windows(self, name: str) -> list[RateLimitItem]:
        """The entry's configured windows. A multi-window string such as
        `2/minute; 6/hour; 20/day` is parsed with `limits.parse_many()` and enforced as a set:
        every window must admit the request."""
        # [impl->req~ratelimit-parse-many-multi-window-strings~1]
        return self.entry(name).parsed

    def test(self, name: str, key: str) -> LimitDecision:
        """Evaluate the entry non-destructively: no counter is incremented."""
        # [impl->req~ratelimit-parse-many-multi-window-strings~1]
        return self._evaluate(name, key, charge=False, cost=None)

    def hit(self, name: str, key: str, *, cost: int | None = None) -> LimitDecision:
        """Evaluate the entry and charge it."""
        # [impl->req~ratelimit-entry-cost~1]
        return self._evaluate(name, key, charge=True, cost=cost)

    def consume(self, name: str, key: str, *, cost: int | None = None) -> LimitDecision:
        """Atomically check and consume one unit of the entry.

        For a single-window entry the check and the consumption are one operation against the
        configured storage — the `limits` strategy's own `hit` — so the unit is taken atomically
        across every backend replica and no second replica can dispatch between a separate check
        and charge. This is what a global provider-call budget meters an outbound attempt with.
        """
        # [impl->req~ratelimit-global-provider-call-budgets~1]
        entry = self.entry(name)
        # [impl->req~ratelimit-config-key-enabled~1]
        if not self._config.enabled or not entry.enabled:
            return LimitDecision(allowed=True, limiter=name)
        charged_cost = entry.cost if cost is None else cost
        windows = entry.parsed
        try:
            # Every configured window must admit the dispatch, and a refusal charges none of
            # them: no unit is consumed unless an outbound call actually follows. A single
            # window — the shape a budget is normally configured in — takes the atomic
            # check-and-consume; a window set is tested in full before any counter moves.
            # [impl->req~ratelimit-parse-many-multi-window-strings~1]
            if len(windows) == 1:
                allowed = self._strategy.hit(windows[0], key, cost=charged_cost)
            else:
                allowed = all(self._strategy.test(window, key, cost=charged_cost)
                              for window in windows)
                if allowed:
                    for window in windows:
                        self._strategy.hit(window, key, cost=charged_cost)
        except Exception:
            # [impl->req~ratelimit-entry-failure-behavior~1]
            # [impl->req~ratelimit-default-fail-closed-unless-configured~1]
            open_ = entry.failure_mode is FailureMode.fail_open
            return LimitDecision(allowed=open_, limiter=name, storage_failed=True)
        if allowed:
            return LimitDecision(allowed=True, limiter=name, charged=True)
        # A refused dispatch charges nothing: `charged` reports whether a counter actually moved.
        return LimitDecision(allowed=False, limiter=name,
                             retry_after_seconds=self._retry_after(entry, key),
                             charged=False, exhausted=(name,))

    def _evaluate(self, name: str, key: str, *, charge: bool, cost: int | None) -> LimitDecision:
        entry = self.entry(name)
        # [impl->req~ratelimit-config-key-enabled~1]
        # [impl->req~ratelimit-entry-enabled~1]
        if not self._config.enabled or not entry.enabled:
            return LimitDecision(allowed=True, limiter=name)
        # The configured cost, defaulting to 1, is what a hit deducts.
        # [impl->req~ratelimit-entry-cost~1]
        charged_cost = entry.cost if cost is None else cost
        try:
            windows = entry.parsed
            # Every configured window must admit the request, and a rejection charges none of
            # them: the whole set is tested before any counter moves.
            # [impl->req~ratelimit-parse-many-multi-window-strings~1]
            allowed = all(self._strategy.test(window, key, cost=charged_cost)
                          for window in windows)
            if allowed and charge:
                for window in windows:
                    self._strategy.hit(window, key, cost=charged_cost)
        except Exception:
            # The failure behaviour when the `limits` backend is unavailable is the entry's own,
            # and it is fail-closed unless the configuration file chose fail-open for it.
            # [impl->req~ratelimit-entry-failure-behavior~1]
            # [impl->req~ratelimit-default-fail-closed-unless-configured~1]
            open_ = entry.failure_mode is FailureMode.fail_open
            return LimitDecision(allowed=open_, limiter=name, storage_failed=True)
        if allowed:
            return LimitDecision(allowed=True, limiter=name, charged=charge)
        return LimitDecision(allowed=False, limiter=name,
                             retry_after_seconds=self._retry_after(entry, key),
                             charged=charge, exhausted=(name,))

    def client_ip_key(self, resolved: GatewayResolvedAddress | None) -> str:
        """The canonical client-IP key, aggregated at the configured IPv6 prefix."""
        # [impl->req~ratelimit-canonical-client-ip-resolution~2]
        return canonical_client_ip_key(resolved,
                                       ipv6_prefix=self._config.client_address.ipv6_prefix)

    def unresolved_address_ceiling(self) -> RateLimitEntry:
        """The configured single-address ceiling the one shared unresolved-address bucket runs
        at. The route is never left unlimited."""
        # [impl->req~ratelimit-canonical-client-ip-resolution~2]
        return RateLimitEntry(limit=self._config.client_address.unresolved_limit, key="ip")

    def _retry_after(self, entry: RateLimitEntry, key: str) -> int | None:
        """The limiting bucket's true wait — the longest known wait when more than one window
        applies — or `None` when the backend cannot compute a reset time."""
        now = time.time()
        waits: list[int] = []
        for window in entry.parsed:
            try:
                stats = self._strategy.get_window_stats(window, key)
            except Exception:
                continue
            if stats.remaining <= 0:
                waits.append(max(1, math.ceil(stats.reset_time - now)))
        return max(waits) if waits else None

