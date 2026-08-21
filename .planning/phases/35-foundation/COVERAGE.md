# Phase 35 — Foundation: API Coverage

No external API integration: this phase defines adapter interfaces only — no Firebase Admin,
store, or device-check implementation ships (FOUND-08).

`auth/adapters.py` declares three Protocols — `FirebaseAdminAdapter`, `StoreAdapter`,
`VendorProofAdapter` — with their closed outcome enums and frozen result types, and nothing behind
them. `tests/unit/test_adapter_interfaces.py::test_foundation_calls_no_adapter_method_anywhere_in_src`
scans every module under `src/` for the ten adapter method names and requires zero hits, so the
absence is asserted rather than assumed. No provider SDK is imported, no credential is read at
startup, and no network call to a provider is reachable from any registered route.

There is deliberately no capability matrix and no endpoint table below. Building one would describe
call sites that do not exist.

## Accepted gaps carried into v2.0

Recorded here so a later reviewer reads them as decisions rather than rediscovering them as
defects. The first six are decided and closed; the last three are **open and unowned**, and are
marked as such.

**1. The Envoy gateway contract (FOUND-09 / §9) is deferred to v2.1 per D-08.** Nothing in `k8s/`
was touched this phase. Four accepted consequences: only the v1.6 chart's rate limiting ships,
unverified against §9; Envoy's 429s keep their empty body, which does not satisfy the client error
contract; `xff_num_trusted_hops` stays unpinned, so the client address is trusted rather than
proven — which is why only the IP *bucket kind* is recorded in the request context and never a
derived address; and no backend correctness depends on the gateway, §9 being explicit that the
backend is the sole authoritative verifier.

**2. Backend traffic limiting is removed from the product per D-05, not deferred.** No `limits`
dependency, no Redis/Valkey, no `rate_limits` config block, no named entries, no canonical-IP key
derivation. Envoy Gateway is the sole request-rate enforcement point. `rate_limited` (429) stays in
the error registry regardless per D-07, as the class Envoy's body must name once §9 lands.

**3. `k8s/templates/backend-traffic-policy.yaml:53` emits `'{"code":"quota_exceeded"}'` on a 429**
where §3.2 wants `rate_limited`. D-08 forbids touching `k8s/` this phase, so this is a known,
accepted inconsistency rather than a defect. It is fixed with the gateway contract in v2.1.

**4. Anti-oracle enforcement is structural only per D-13.** Guaranteed and asserted: identical
status, body and copy per class, and both `account_unavailable` branches reached through the same
code path and the same single identity query. Timing normalization is deliberately **not**
implemented, and no test asserts timing parity — `test_no_timing_normalisation_is_present` pins the
absence so it stays a decision. A timing oracle separating "retired" from "blocked" on a sub-$5
subscription buys an attacker nothing worth per-rejection latency.

**5. Chat and quota routes have no allowance to enforce until Phase 36 rewires them onto the grant
model per D-15**, and `core.access_tiers` is empty — verified live, count **0**, and the v2.0
migration contains no `INSERT INTO core.access_tiers`. REBIND-05 resolves a grant's allowance by
joining through `core.access_tiers.tier_id`, so it has nothing to resolve against until tiers are
configured. No test in the suite asserts a quota outcome on a chat route, because there is none to
assert.

**6. REBIND-01 was satisfied early by Phase 35's route declarations** — all eight routes declared,
set equality against the live router in both directions at real startup. REBIND-02, REBIND-03,
REBIND-05 and REBIND-06 remain Phase 36. REBIND-04 is **void**: the named `quota_checked_request`
admission entry it required no longer exists, deleted with §5 by D-05.

**7. No metrics exporter ships — the §1.2 alert cannot fire. Unowned (D-35-06-A).** The bounded
rejection counter §1.2 and §8.2 require exists, carries the right labels (result × bounded reason ×
route), and is proven to increment on every rejection. Nothing reads it: this deployment has no
Prometheus client, no scrape endpoint and no exporter. This matters more than its size suggests —
§1.2 makes a systemic verification break client-indistinguishable from ordinary session expiry *by
design*, so this counter is the **only** detection path for one, and it is currently dark. The
counter is also per-process and in-memory, so each replica holds its own view and a restart
discards it. Needs an exporter scheduled or an explicit acceptance.

**8. `actor_provider` is NULL on every audit row this phase can write — including
`historical_identity` and `blocked_user`, where a stored provider does exist. Unowned for now;
Phase 37 owns the widening.** §4.2's rule is what holds — the value is never fabricated and never
taken from claims, headers or client input — but `Reject` does not carry the resolved identity row,
so the writer receives `None` even where the column could be populated. The writer parameter and
the guard already exist; only the plumbing through `auth/identity.py` is missing. Phase 35 writes
**zero** production audit rows (§8.2 puts every route it registers off the audited path; live count
0), so nothing is lost yet — but the first phase to register an audited route inherits rows less
attributable than the schema allows.

**9. A grammatically correct phrase makes `POST /chats` return 500. Unowned (D-35-11-A).** Found
while restoring `test_create_chat_autodetect_lang`, whose original input was correct English.
`config/prompt.txt` asks for `issues` and `suggestions` conditionally while
`models/llm.py::AnalyzeResponse` requires them, so a phrase with nothing to correct fails
validation after the model returns. Reproduced four ways; phrase correctness is the variable and
`lang` is not. Not fixed here: both files are outside this phase, §8.3 requires existing non-auth
contracts unchanged, and the fix is a product choice (default the fields to `[]`, changing the
client contract, or change the prompt). It is the primary route of a grammar-fixing product failing
for exactly the input a user gets when their sentence is already right, so it should not wait long.

---

*Phase: 35-foundation*
*Written: 2026-08-21*
