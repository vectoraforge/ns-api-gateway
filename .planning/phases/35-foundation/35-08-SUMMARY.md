---
phase: 35-foundation
plan: 08
subsystem: hmac-keyring
tags: [hmac, hashlib, base64, pydantic, pydantic-settings, secretstr, structlog]

requires:
  - phase: 35-foundation
    plan: 05
    provides: "config/config.yaml with no apple or quotas block, and AppConfig(**yaml_data, ...) as the only construction site"
  - phase: 35-foundation
    plan: 06
    provides: "the lifespan's app.state.X construction order and the barrier this keyring sits beside"
provides:
  - "auth/keys.py -- ACTOR_SUBJECT_PREFIX / IDP_ACCOUNT_PREFIX pinned as bytes literals"
  - "HmacConfig -- the hmac: block model with the D-22 fail-closed active-key policy"
  - "HmacKeyring -- one derivation for §4.3 actor_subject_hash and §6.4 preauth_subject_hash"
  - "HmacKeyring.actor_subject_matches -- the compare_digest seam plans 09 and 10 call instead of =="
  - "config.AppConfig.hmac, required with no default"
  - "app.state.hmac_keyring, constructed in the lifespan with warn_missing_older called on it"
  - "hide_input_in_errors across the settings tree -- validation errors disclose no secret value"
affects: [35-09, 35-10, 35-11, 41-idp-account]

actuals:
  tokens: 9606
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Validating a secret's *encoding* at configuration load so the consumer constructor is total over valid config, rather than discovering a bad key at first use"
    - "hide_input_in_errors on the outer settings model, because pydantic renders a nested model's error under the outer model's config rather than the nested one's"
    - "Asserting a substring-run rather than whole-string containment when checking for a leak, because the renderer truncates"
    - "Pinning a timing-only property (compare_digest vs ==) by parsing the method's AST, since no input can distinguish the two"
    - "An injected logger parameter instead of a module-level one, so the warning path needs a plain recording object rather than any patching"

key-files:
  created:
    - src/nativespeaker/api/auth/keys.py
    - tests/unit/test_hmac_keys.py
  modified:
    - src/nativespeaker/api/config.py
    - config/config.yaml
    - src/nativespeaker/api/app/lifespan.py
    - tests/unit/test_config.py
  deleted: []

key-decisions:
  - "The checkpoint was answered `base64-yaml`: key material is base64 text in config/config.yaml, decoded to bytes exactly once at configuration load and stored thereafter only as bytes. The encoding is now pinned for the life of the product."
  - "idp_account_keys is a second key map, not a second prefix over the same key. The plan's <interfaces> sketch gave HmacConfig one `keys` map, but its own must_haves truth and §4.3 both say the idp-account derivation runs `under its own key` and is `never derived from the actor-subject key`. A shared key with two prefixes satisfies every acceptance criterion in the plan and still violates the truth those criteria exist to serve."
  - "hide_input_in_errors is set on BaseConfig as well as HmacConfig. SecretStr covers repr and str but not a validation error: pydantic renders the *pre-coercion* input in `input_value=...`, and a nested model's error is rendered under the outer model's config. Without the flag on the settings tree, an invalid hmac: block printed the raw base64 key -- observed directly, then mutation-confirmed."
  - "A *declared* key that does not decode is rejected at configuration load whatever its version, which keeps HmacKeyring.__init__ total over validated configuration. This is not in tension with D-22, which tolerates a version that is absent, not one that is present and unusable."
  - "actor_subject_matches ships now, with no caller. T-35-08-03 names hmac.compare_digest as a mitigation and the plan gave it no implementation site; shipping the comparison as part of the seam is what stops plans 09 and 10 each writing their own `==`."
  - "Task 3 ran no RED phase. It is a test-only task against code task 2 already shipped, so every case would have passed on first write and a green run would have proved nothing. Twelve mutations against the shipped module were run instead; three assertions were strengthened because mutants survived them."

requirements-completed: [FOUND-05]

coverage:
  - id: K1
    description: "actor_subject_hash is HMAC-SHA-256 over the pinned domain-separated message and is exactly 32 bytes"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_hmac_keys.py::TestTheDerivation::test_actor_subject_hash_is_exactly_32_bytes; ::test_the_prefixes_are_pinned_bytes_literals"
        status: pass
      - kind: other
        ref: "live boot probe: app.state.hmac_keyring.actor_subject_hash(...) -> 32 bytes"
        status: pass
    human_judgment: false
  - id: K2
    description: "The derivation is stable for a fixed (key, issuer, subject) and differs for the same input under a different key version"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "::test_the_same_inputs_yield_the_identical_digest; ::test_two_keyrings_from_the_same_configuration_agree; ::test_a_different_key_version_yields_a_different_digest"
        status: pass
    human_judgment: false
  - id: K3
    description: "One shared key derives both the audit actor_subject_hash and the challenge preauth_subject_hash, distinguished only by the pinned domain-separation prefix"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_hmac_keys.py::TestTheTwoFamiliesAreSeparate::test_identical_key_material_still_yields_different_digests -- both families handed byte-identical material, so only the prefix can separate them"
        status: pass
      - kind: other
        ref: "one method, `actor_subject_hash`, is the entire §4.3 + §6.4 surface; no second derivation exists to drift"
        status: pass
    human_judgment: false
  - id: K4
    description: "The idp-account derivation is a parallel prefix under its own key and is never derived from the actor-subject key"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "::test_the_idp_derivation_moves_with_its_own_key_and_not_the_actor_key; ::test_the_idp_digest_is_not_the_actor_key_under_the_idp_prefix; ::test_idp_account_hash_raises_when_no_idp_key_is_configured"
        status: pass
      - kind: other
        ref: "mutation M3 (idp_account_hash reads self._keys) -> 3 failed"
        status: pass
    human_judgment: false
  - id: K5
    description: "A missing or empty active key version aborts configuration load, so the process never starts without the key it needs to write"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_hmac_keys.py::TestTheActiveKeyPolicy (4 D-22 rejection cases: absent, empty, whitespace, short)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_config.py::TestHmacConfigSurface::test_a_config_file_with_no_hmac_block_fails_to_load"
        status: pass
      - kind: other
        ref: "live probe: config/config.yaml with a blanked active key -> EnvironmentConfig() raises, naming hmac"
        status: pass
      - kind: other
        ref: "mutation M5 (drop the absent-active-key check) -> 8 failed; M11 (drop the emptiness branch) -> 2 failed"
        status: pass
    human_judgment: false
  - id: K6
    description: "A missing older key version emits a warning and does not abort -- historical hashes become unrecomputable, which no request path needs"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "::TestTheHistoricalGapIsTolerated (3 cases: the gap loads, warn_missing_older names exactly the gap, a complete history warns about nothing)"
        status: pass
      - kind: other
        ref: "live probe through the real structlog logger, active 4 with keys 1 and 4 -> two hmac_key_version_missing lines, key_version 2 and 3, no raise"
        status: pass
    human_judgment: false
  - id: K7
    description: "active_version is bounded to the SMALLINT range so a bad configuration fails at load rather than at the first audit insert"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "::test_an_out_of_range_active_version_is_rejected (0, -1, 32768); ::test_the_range_bounds_themselves_are_accepted (1, 32767)"
        status: pass
      - kind: other
        ref: "mutation M9 (drop le=32767) -> 1 failed"
        status: pass
    human_judgment: false
  - id: K8
    description: "Key material is decoded from base64 to bytes exactly once, at configuration load, and hmac.new is never called on a str"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "::TestTheDerivation::test_the_derivation_runs_over_the_decoded_key_bytes_not_the_base64_text -- computes both candidate digests and requires the key-bytes one"
        status: pass
      - kind: unit
        ref: "::TestTheKeyringHoldsBytes (every stored key is bytes; three decodes at construction, zero across ten derivations)"
        status: pass
      - kind: other
        ref: "mutation M2 (derive over the base64 text) -> 2 failed; M10 (decode per call) -> 18 failed"
        status: pass
    human_judgment: false
  - id: K9
    description: "Key material never appears in a repr, a traceback, or a log line"
    requirement: FOUND-05
    verification:
      - kind: unit
        ref: "::TestNoLeakage (6 cases over repr(cfg), str(cfg), repr(keyring), three direct validation-error shapes, and the nested AppConfig path)"
        status: pass
      - kind: other
        ref: "mutation M8a (flag off on HmacConfig) -> 3 failed; M8b (flag off on the settings tree) -> 1 failed"
        status: pass
      - kind: other
        ref: "live boot: `HmacKeyring(active_version=1, versions=[1], idp_versions=[1])`; the lifespan `started` line carries no key field"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-08-21
status: complete
---

# Phase 35 Plan 08: The Shared HMAC Keyring Summary

**One derivation, two prefixes, two key families, and a startup policy that refuses to boot without
the key it needs to write — the seam plans 09 and 10 both hang off, built so they cannot drift
apart, and mutation-verified rather than trusted.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-08-21 07:21Z
- **Completed:** 2026-08-21 07:36Z
- **Tasks:** 3 of 3
- **Files:** 6 (2 created, 4 modified, 0 deleted) — 625 insertions, 2 deletions

## The checkpoint

Task 1 was `checkpoint:decision`, `gate="blocking"`: pin the on-disk encoding of HMAC key material.
It was presented to the developer by the orchestrator and answered before this executor ran.

| | |
|---|---|
| **Decision** | Pin the on-disk encoding of HMAC key material |
| **Selected** | **`base64-yaml`** — "Base64 text in config.yaml, decoded to bytes once at load (A5, recommended)" |
| **Reversibility** | one-way |

As implemented: key material is base64 text in `config/config.yaml`, decoded exactly once inside
`HmacConfig`'s validator and `HmacKeyring.__init__`, and stored thereafter only as `bytes`.
`hmac.new` is never called on a `str`. `TestTheDerivation::
test_the_derivation_runs_over_the_decoded_key_bytes_not_the_base64_text` computes *both* candidate
digests and requires the key-bytes one — because both are plausible 32-byte values, neither raises,
and only one matches whatever wrote the existing rows.

**D-20 is recorded, not re-litigated.** `config/config.yaml` is tracked in git, so the two keys
below are committed and rotating one leaves its predecessor readable in history for good. That was
raised and accepted; `.planning/todos/pending/secret-manager-integration.md` is the mitigation path
and exists for this reason. No key material moved to an environment variable, and the block above
it in the YAML records why an environment variable could not shadow it anyway.

## The active key version committed

**`active_version: 1`**, with version 1 present in both key maps:

```
$ python -c "...; k = EnvironmentConfig().app_config.hmac; print(k.active_version, sorted(k.keys))"
1 [1]

$ # live boot
app.state.hmac_keyring   : HmacKeyring(active_version=1, versions=[1], idp_versions=[1])
actor_subject_hash bytes : 32 bytes
matches recomputed       : True
idp differs from actor   : True
```

Both keys are `openssl rand -base64 32` development material, generated for this commit. They are
not production keys and the comment above the block says so.

## No key-version column was added to `core.auth_challenges`

Confirmed, as the plan asked. `git diff --name-only` over this plan's three commits touches
`migrations/` **not at all** — no migration was written, altered, or re-applied. The schema comment
at migration lines 588–595 stands unamended:

> This row records NO HMAC key version — verification uses the current active key alone, so a
> challenge outstanding across a key rotation simply fails. Do NOT add a key-version column here
> (unlike `audit.auth_events`, which has one).

The code side holds the same line. `actor_subject_hash(issuer, subject, *, version=None)` takes an
optional version so the **audit writer** (plan 09) can record and re-read `actor_subject_hash_
key_version`; the **challenge store** (plan 10) calls the same method with no `version` and gets
the active key, which is the only key §6.4 permits it. D-21's accepted consequence follows and is
asserted rather than asserted-about: `test_a_different_key_version_yields_a_different_digest` is
exactly the reason a rotation invalidates outstanding challenges — completion fails the binding
comparison, rejects `challenge_identity_mismatch`, and the client prepares a fresh one inside the
300-second TTL.

## What stops the two subsystems drifting

There is **one** method. `preauth_subject_hash` is not a parallel implementation of
`actor_subject_hash`; it is a call to it. The prefixes are module-level `bytes` literals, never
parameterized and never read from configuration, so there is no configuration surface through which
one caller could end up on a different message format from the other.

The prefix separation is proven in isolation rather than incidentally.
`test_identical_key_material_still_yields_different_digests` hands **byte-identical material** to
both families, so the only thing left that can separate the two digests is the prefix. The weaker
form — different keys *and* different prefixes — would have passed even if both prefixes were the
same string.

## Task Commits

| # | Task | Commit | Type |
|---|---|---|---|
| 1 | Task 1: checkpoint — resolved by the developer before dispatch | — | (no code) |
| 2 | Task 2 RED: failing tests for the shared keyring | `38cc8d4` | test |
| 3 | Task 2 GREEN: the keyring, the config field, the YAML block, the lifespan wiring | `9f06a13` | feat |
| 4 | Task 3: complete the key-management unit coverage | `b163e49` | test |

`38cc8d4` failed at collection against the absent `nativespeaker.api.auth.keys` — both
`test_hmac_keys.py` and `test_config.py` errored, so the RED was real and not a passing-test
mirage.

## Test Status

| Suite | Before | After | Δ |
|---|---|---|---|
| Unit (`pytest -q`) | 448 | **489** | +41 |
| E2E (`pytest -q -m e2e`) | 76 | **76** | untouched |
| Schema (`pytest -q -m schema`) | 77 | **77** | untouched |
| Combined (`pytest -q -m ""`) | 601 | **642 passed, 0 failed** | +41 |
| `ruff check src tests` | clean | **All checks passed!** | |
| `ty check src` | clean | **All checks passed!** | |

`489 + 76 + 77 = 642`. Zero `xfail`, zero `pytest.mark.skip` — `grep -rn "xfail\|pytest.mark.skip"
tests/` returns 0 lines.

The delta is `test_hmac_keys.py` (38, entirely new) and `test_config.py` 9 → 12 (+3).
`tests/e2e/test_startup_assertion.py` passes unchanged at 9, which is the plan's evidence that the
app still boots with a new **required** configuration field.

## Decisions Made

- **`idp_account_keys` is a second key map, not a second prefix over the same key.** The plan's
  `<interfaces>` sketch gave `HmacConfig` a single `keys` map, and every one of its acceptance
  criteria passes with one shared key — including `a != b` for the two families, which the prefixes
  alone satisfy. But the plan's own `must_haves` truth says the idp-account derivation runs "under
  its own key" and is "never derived from the actor-subject key", and `§4.3` and D-21 say the same.
  A shared key would have satisfied the criteria and violated the property they exist to check.
  `idp_account_keys` defaults to `{}` deliberately: making it required would move the failure for
  `HmacConfig(active_version=2, keys={1: 'AAAA'})` from the D-22 after-validator to a missing-field
  error, and the plan's acceptance criterion requires that error to name the active version.
- **`hide_input_in_errors` on the settings tree, not just on `HmacConfig`.** `SecretStr` covers
  `repr` and `str`; it does not cover a validation error, because pydantic renders the
  **pre-coercion** input in `input_value=...`. The first run of the plan's own acceptance probe
  printed `input_value={'active_version': 2, 'keys': {1: 'AAAA'}}` — the raw material, out of the
  one model whose entire job is to reject configurations. Setting the flag on `HmacConfig` fixes
  direct construction; a nested error is rendered under the **outer** model's config, so
  `BaseConfig` needed it too. The field path and message still identify what was wrong — only the
  offending value is withheld, and every secret this project loads (`db.password` included) travels
  through that tree.
- **A declared-but-undecodable key is rejected at load, whatever its version.** D-22 tolerates a
  version that is *absent*; it says nothing about one that is present and garbage. Validating all
  declared entries keeps `HmacKeyring.__init__` total over validated configuration, so a malformed
  historical key aborts with a message naming the version rather than surfacing as a `binascii`
  error part-way through lifespan construction.
- **`actor_subject_matches` ships with no caller.** T-35-08-03 lists `hmac.compare_digest` as a
  `mitigate` disposition, and the plan's interface gave it nowhere to live — which would have left
  two later plans each free to write `stored == recomputed`. The method is the seam; the AST case
  pins it, because no input can distinguish `compare_digest` from `==`.
- **`_decode` raises `from None`.** Chaining `binascii.Error` puts the original one frame away in a
  traceback that may well be logged, and nothing in its text helps an operator.
- **`test_a_stale_block_fails_loudly` now supplies a valid `hmac`.** With `hmac` required, the case
  would otherwise have raised on the missing field and passed without `extra='forbid'` ever being
  consulted — a green test asserting nothing it claims.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] The idp-account family had no key of its own**

- **Found during:** Task 2, writing `HmacConfig`.
- **Issue:** the plan's `<interfaces>` block declares `keys: dict[int, SecretStr]` and nothing else,
  and its `<action>` describes `idp_account_hash` only as "the parallel derivation under
  `IDP_ACCOUNT_PREFIX`". Implemented literally, `idp_account_hash` would run under the
  actor-subject key — contradicting the plan's own `must_haves` truth ("under its own key and is
  never derived from the actor-subject key"), `§4.3` ("under its own key"), and D-21 ("gets its own
  key"). Every acceptance criterion in the plan would still have passed.
- **Fix:** added `idp_account_keys: dict[int, SecretStr]`, defaulted to `{}` so the D-22
  acceptance criterion still surfaces the active-version error; a configured family without an
  entry for `active_version` is rejected; `idp_account_hash` raises rather than falling back to the
  actor key when none is configured. `config/config.yaml` carries a second generated key.
- **Committed in:** `9f06a13`, with coverage in `b163e49`.

**2. [Rule 2 - Missing critical functionality] Validation errors printed the raw key material**

- **Found during:** Task 2, running the plan's own acceptance probe for the D-22 rejection.
- **Issue:** `HmacConfig(active_version=2, keys={1:'AAAA'})` printed
  `input_value={'active_version': 2, 'keys': {1: 'AAAA'}}`. T-35-08-02's stated mitigation is that
  "the base64 text appears in no `repr`, `str`, or validation-error message"; `SecretStr` delivers
  the first two and not the third, because the rendered input is the pre-coercion value.
- **Fix:** `ConfigDict(hide_input_in_errors=True)` on `HmacConfig`, and the same flag on
  `BaseConfig` because a nested model's error is rendered under the outer model's config. Verified
  across all three paths — direct, through `AppConfig`, and through `EnvironmentConfig` loading a
  real YAML file.
- **Committed in:** `9f06a13`, with coverage in `b163e49`.

**3. [Rule 2 - Missing critical functionality] T-35-08-03 had no implementation site**

- **Found during:** Task 2, reading the threat register against the interface.
- **Issue:** the register disposes T-35-08-03 as `mitigate` — "`hmac.compare_digest` for every
  stored-hash comparison, never `==`" — but the plan's `<interfaces>` block declares only the two
  derivation methods. The comparison would have been written independently in plan 09 and plan 10.
- **Fix:** `HmacKeyring.actor_subject_matches(stored, issuer, subject)`, the exact operation §6.4's
  binding verification needs, pinned to `compare_digest` by an AST assertion.
- **Committed in:** `9f06a13`, with coverage in `b163e49`.

**4. [Rule 3 - Process] Task 3 ran mutation verification in place of a RED phase**

- **Found during:** Task 3, choosing where the TDD RED commit goes.
- **Issue:** the plan marks task 3 `tdd="true"`, but it is a test-only task whose subject —
  `auth/keys.py` — task 2 already shipped. Every case would have passed on first write. Committing
  that as a RED gate would have been a false one, and the fail-fast rule says a test passing before
  implementation is a stop signal, not a green light.
- **Fix:** wrote the module, then mutated the shipped source twelve times and read which cases
  noticed. Three assertions were strengthened as a direct result (see Issues Encountered). The
  driving RED that TDD actually calls for is task 2's `38cc8d4`, which failed at collection.

**5. [Rule 3 - Blocking] `tests/unit/test_config.py` needed four edits, not one**

- **Found during:** Task 2 RED.
- **Issue:** the plan says "Update `tests/unit/test_config.py` for the new field". Making `hmac`
  required breaks more than one case: `test_main_config_loads_yaml_and_content` writes its own YAML
  with no `hmac:` block, and `test_a_stale_block_fails_loudly` constructs `AppConfig` directly.
- **Fix:** added an `hmac:` block to the inline YAML; supplied a valid `hmac` to the stale-block
  case so it still asserts what it claims; added `TestHmacConfigSurface` with three cases — the
  field is declared, a config file with no `hmac:` block aborts load, and the *committed*
  development key decodes and derives a real 32-byte digest. That last one is the only place in the
  suite that asserts against the tracked key, and it belongs there rather than in
  `test_hmac_keys.py`.
- **Committed in:** `38cc8d4`.

---

**Total deviations:** 5 — three Rule 2 gaps where a stated `mitigate` disposition or a stated
`must_haves` truth had no implementation site in the plan's interface, and two Rule 3 process/scope
corrections. No Rule 1 bug was found in code this plan wrote, and no Rule 4 architectural question
arose. All three Rule 2 items share one shape: the plan's acceptance criteria would have passed
without them.

## Issues Encountered

- **Twelve mutations; three survivors, two of which were real holes.** The module was verified by
  mutating the shipped source rather than inferred from a green run:

  | Mutation | Result |
  |---|---|
  | M1 — `actor-subject:v1:` → `:v2:` | 1 failed |
  | M2 — derive over the base64 text, not key bytes | 2 failed |
  | M3 — `idp_account_hash` reads `self._keys` | 3 failed |
  | M4 — `MIN_KEY_BYTES` 32 → 1 | 2 failed |
  | M5 — drop the D-22 absent-active-key check | **passed 50** → strengthened, then **8 failed** |
  | M6 — `warn_missing_older` spans the active version | **passed 50** — equivalent mutant, see below |
  | M7 — `compare_digest` → `==` | 1 failed |
  | M8a — `hide_input_in_errors` off (`HmacConfig`) | 3 failed |
  | M8b — `hide_input_in_errors` off (settings tree) | **passed 50** → strengthened, then **1 failed** |
  | M9 — drop the `le=32767` bound | 1 failed |
  | M10 — decode per call instead of once | 18 failed |
  | M11 — drop the emptiness branch | **passed 50** → strengthened, then **2 failed** |
  | M12 — drop the idp active-version cross-check | 1 failed |

  Each mutation's anchor was confirmed present before its result was read, and
  `git diff --exit-code -- src/` reported the tree byte-identical after every restore.

  **The three survivors are worth reading, because two of them were the tests' fault:**

  - **M5** survived because `test_an_absent_active_key_is_rejected` used
    `pytest.raises(ValidationError, match="2")`. A single digit matches almost any pydantic message,
    so the case passed while the configuration was being rejected for an entirely different reason.
    Now `match="no entry for active_version 2"`.
  - **M8b** survived because the leakage cases asserted `text not in str(error)`. Pydantic
    **truncates** long values in error output, so a leaked 44-character key renders as its head and
    its tail with an ellipsis between them — whole-string containment passes while most of the key
    is on screen. Replaced with a `discloses()` helper that fails on any 8-character run of the key
    text, and applied to every leakage case.
  - **M11** survived because the emptiness branch is subsumed by the length check: an empty key
    still fails, as "decodes to 0 bytes". Kept the branch and pinned its message — a blanked-out or
    not-yet-filled key is the case an operator most needs a readable answer for.

  **M6 is an equivalent mutant, not a hole.** `HmacConfig`'s validator guarantees
  `active_version in keys`, so version `active_version` can never be missing, so
  `range(1, active + 1)` can never emit a warning `range(1, active)` would not. No input
  distinguishes them, and no test should pretend to.

- **Two acceptance-criterion probes needed the environment loaded.** The plan's
  `python -c "...EnvironmentConfig()..."` commands fail in a bare shell with five missing
  `DatabaseConfig` fields. That is pre-existing and unrelated to this plan — `BaseConfig` declares
  no `env_file`, so `DB_*`/`JWT_*` reach it from `os.environ`, which `pytest-dotenv` populates under
  pytest and a shell does not. Re-run with `set -a; . ./.env` they print `1 [1]`, `32`, and `True`
  as specified.

- **Two self-referential test failures, both mine.** The first version of the `compare_digest` check
  scanned `inspect.getsource` for the literal `==`, and found it inside the method's own docstring.
  The first version of the "reads no file from `config/`" check searched the module's string
  literals for `"config/"` — which is itself a string literal in that check. Both were rewritten
  against the AST: the first asserts no `ast.Compare` with `Eq`/`NotEq` and a call to
  `hmac.compare_digest`; the second asserts that every `open`/`read_text` call in the module names
  `__file__`, with a positive control so it cannot pass vacuously.

- **No out-of-scope discoveries.** The two warnings in a combined run (`langchain_core` pydantic-v1
  on 3.14, PyJWT's `InsecureKeyLengthWarning` from `test_jwt_security.py`'s deliberate HS256 case)
  reproduce exactly as measured at baseline. Nothing was added to `deferred-items.md`.

## Known Stubs

None. Every symbol this plan declares is implemented, wired into the running application, and
exercised — `app.state.hmac_keyring` is constructed by the real lifespan and `warn_missing_older`
is called on it at every boot.

Two things are deliberately unbuilt or unconsumed and are **not** stubs, because a stub is an
unfinished implementation and these are complete ones awaiting their caller:

| Item | State | Owner |
|---|---|---|
| `idp_account_hash` and the `idp_account_keys` entry | complete, keyed, unit-covered; the committed key derives a real digest today | Phase 41 (`§4.3`'s parallel derivation) |
| `actor_subject_matches` | complete and pinned to `compare_digest`; no stored hash exists to compare against yet | plan 35-10 (challenge binding verification) |

Both are the point of the plan rather than an oversight: this is the seam plans 09, 10, and 41 build
on, and shipping the derivation without the comparison would have handed each of them the chance to
write `==` instead.

## Threat Flags

None. This plan registers no route, opens no network path, writes no query, and adds no dependency
(`hmac`, `hashlib`, `base64`, and `binascii` are stdlib, so T-35-08-SC stays vacuous). Every file it
created or modified is covered by the plan's own `<threat_model>`. All five `mitigate` dispositions
are implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-08-01 | **Accepted, as planned.** The keys are committed and the comment above them says so, names the git-history consequence, and points at the Secret Manager todo. Generated development material, not production keys. |
| T-35-08-02 | `SecretStr` for every configured key, decoded to bytes once and never re-exposed; an explicit `HmacKeyring.__repr__` so no later refactor to a dataclass turns it into a key dump; `hide_input_in_errors` on both `HmacConfig` and the settings tree, which `SecretStr` alone did **not** cover. Six unit cases assert against repr, str, three validation-error shapes and the nested `AppConfig` path, on an 8-character-run basis so truncation cannot hide a leak. |
| T-35-08-03 | `HmacKeyring.actor_subject_matches` is the comparison, and `test_the_comparison_is_compare_digest_and_not_an_equality_operator` parses its AST — the only way to distinguish it, since `==` returns identical answers. `grep -rn "compare_digest" src/` is the single site. |
| T-35-08-04 | Decoded exactly once at load, `bytes` only thereafter, asserted three ways: the digest matches the key-bytes derivation and not the base64-text one, every stored value is `bytes`, and three decodes happen at construction with zero across ten derivations. The checkpoint pinned the encoding before any row exists. |
| T-35-08-05 | An absent, empty, whitespace, short, or undecodable active key raises out of `EnvironmentConfig()` — before the lifespan runs, so the process fails to start rather than starting and failing every audit insert. Confirmed live against a blanked key in a copy of the real `config/config.yaml`. |
| T-35-08-06 | **Accepted, as planned.** A gap below the active version warns and continues; confirmed live through the real structlog logger. |
| T-35-08-07 | **Accepted, as planned.** `test_a_different_key_version_yields_a_different_digest` is the rotation consequence stated as an assertion. |

`tests/unit/test_adapter_interfaces.py::test_foundation_calls_no_adapter_method_anywhere_in_src`
still passes: `keys.py` names none of the ten adapter methods, imports no provider SDK, and touches
only `base64`, `binascii`, `hashlib`, `hmac`, `typing`, and `pydantic`.

## Next Phase Readiness

Ready. The shared derivation exists, is wired onto `app.state`, and cannot be reimplemented by
accident — there is one method and it is the whole of `§4.3` plus `§6.4`.

- **Plan 09** (audit writer) reads `app.state.hmac_keyring` per request and calls
  `actor_subject_hash(issuer, subject)` for `actor_subject_hash`, recording
  `keyring.active_version` in `actor_subject_hash_key_version` (SMALLINT — the bound is already
  enforced at config load, so no insert can fail on it). RESEARCH Pitfall 10 still applies: an
  `internal_error` or `preauth_identity_not_allowed` row must populate all three actor fields from
  the already-verified `(issuer, subject)`, with `actor_provider` NULL.
- **Plan 10** (challenge store) calls the **same** method with no `version` argument for
  `preauth_subject_hash`, and stores no key version — the column does not exist and must not be
  added. For binding verification at completion, call `actor_subject_matches`, not `==`.
- **Plan 11** writes the `auth/__init__.py` barrel. `keys.py` is deliberately not exported from it
  yet, per this plan's barrel note; the four symbols to add are `ACTOR_SUBJECT_PREFIX`,
  `IDP_ACCOUNT_PREFIX`, `HmacConfig`, `HmacKeyring`.
- **Phase 41** inherits `idp_account_hash` and a configured `idp_account_keys` entry. It is a
  separate key on purpose — do not consolidate the two maps.
- **The Secret Manager follow-up** must **remove** the `hmac:` entries from `config/config.yaml`,
  not shadow them. `AppConfig(**yaml_data, ...)` ranks `init_settings` above `env_settings`, so an
  environment variable cannot override a key the YAML declares; a hybrid would silently keep using
  the committed one.

## Self-Check: PASSED

- Both claimed created files exist on disk (`src/nativespeaker/api/auth/keys.py`,
  `tests/unit/test_hmac_keys.py`), and all four claimed modified files carry the claimed content.
- All 3 claimed commits are in `git log`: `38cc8d4`, `9f06a13`, `b163e49`.
- `pytest -q -m ""` exits 0 at **642 passed, 0 failed**; `ruff check src tests` and `ty check src`
  both print `All checks passed!`.
- Every acceptance criterion in the plan verified by direct execution: `1 [1]`, `32`, `True`,
  `True True True`, the non-zero exit naming `active_version 2`, `pytest -q tests/unit/
  test_hmac_keys.py tests/unit/test_config.py` at 50 passed, and
  `pytest -q -m e2e tests/e2e/test_startup_assertion.py` at 9 passed.
- `git diff --diff-filter=D --name-only` over this plan's commits is empty — nothing was deleted.
- `migrations/` is untouched, so no key-version column was added to `core.auth_challenges`.
- `.planning/STATE.md`, `.planning/ROADMAP.md` and `uv.lock` are untouched, as instructed.
- Working tree carries no change outside this plan's file list: `docker-compose.yml`, `.gsd/` and
  `.planning/research/.cache/` were pre-existing, are untouched, and remain uncommitted.

---
*Phase: 35-foundation*
*Completed: 2026-08-21*
