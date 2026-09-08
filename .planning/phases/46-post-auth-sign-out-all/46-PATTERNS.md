# Phase 46: POST /auth/sign-out-all - Pattern Map

**Mapped:** 2026-09-08
**Files analyzed:** 12 (4 source, 8 test)
**Analogs found:** 12 / 12

Every file this phase touches has an in-tree analog. Nothing here is new shape; each edit is a twin
of a line that already exists. All paths below are git-tracked source.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/nativespeaker/api/auth/adapters.py` | seam Protocol | request-response | its own `get_user_provider_data` (`:24-26`) | exact |
| `src/nativespeaker/api/auth/firebase.py` | adapter (external SDK) | request-response | `get_user_provider_data` + `_read` + `lookup_with_retry` in the same file | exact |
| `src/nativespeaker/api/errors.py` | error leaf | — | `Unavailable` (`:407-410`) | exact |
| `src/nativespeaker/api/routers/auth.py` | route handler | request-response | `sync` (`:181-192`) for the narrowing; `delete_chat` (`routers/chats.py:78-86`) for 204 | exact (split) |
| `tests/unit/conftest.py` | test fake | — | `FakeDeviceCheckAdapter` (`tests/e2e/conftest.py:238-266`) two-method model | exact |
| `tests/unit/test_firebase_adapter.py` | unit test | — | `TestSelection` + `get_user_calls` fixture in the same file | exact |
| `tests/unit/test_firebase_retry.py` | unit test | — | `TestTheExhaustionConversion` in the same file | exact |
| `tests/unit/test_adapter_interfaces.py` | unit test (literal) | — | `:110-111` — rewrite | exact |
| `tests/unit/test_auth_package_shape.py` | unit test (literal) | — | `:13 CURRENT` — re-measure | exact |
| `tests/unit/test_rejection_vocabulary.py` | unit test (literal) | — | the `Unavailable` entries | exact |
| `tests/unit/test_app_wiring.py` | unit test (literal) | — | `:70-73` and `:80-83` | exact |
| `tests/e2e/test_sign_out_all.py` | e2e test (new) | request-response | `tests/e2e/test_sync.py` + spy from `tests/e2e/test_app_store_webhook.py:60-101` | role-match |

## Pattern Assignments

### `auth/adapters.py` — one Protocol method (D-01)

Copy the shape at `:24-26`, with `-> None` instead of a value type (no new import, so the
allowlist at `tests/unit/test_adapter_interfaces.py:24` stays satisfied):

```python
    def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """The providerData read: the verified identity, or a raise."""
        ...
```

### `auth/firebase.py` — the seam method (`firebase.py:64-72`)

Mirror arm for arm; only the leaf and the SDK call change:

```python
    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """Read `subject`'s providerData through the app `issuer` selects: the identity, or a raise."""
        app = self._apps.get(issuer)
        if app is None:
            # Fails closed with no call made: there is no ambient app to fall back to, by design.
            raise Unavailable(stage="issuer_selection")
        # `firebase-admin` is built on `requests` and has no async client, so it runs off the loop.
        return await run_in_threadpool(self._read, app, subject)
```

### `auth/firebase.py` — the synchronous body (`firebase.py:73-95`)

Copy the arm **order** (`UserNotFoundError` before `FirebaseError`) and the log-field style
(`code=`, `detail=`), but **not** the `ValueError` classification — see RESEARCH.md Pitfall 1:

```python
        except auth.UserNotFoundError:
            # Definitive, spends no retry budget, and listed before the FirebaseError it subclasses.
            logger.info("firebase_get_user_not_found")
            raise UserNotFound(stage="provider_lookup") from None
        except ValueError as error:
            logger.warning("firebase_provider_data_malformed", detail=str(error))
            raise RetryableLookupError(str(error)) from error       # <- revocation: NOT retryable
        except google.auth.exceptions.GoogleAuthError as error:
            # Not a FirebaseError and raised before the request is sent, so it needs its own arm.
            logger.warning("firebase_credential_unavailable", detail=str(error))
            raise RetryableLookupError(str(error)) from error
        except exceptions.FirebaseError as error:
            # Outage or integration-auth failure; the provider's text is for the log, never a body.
            logger.warning("firebase_get_user_failed", code=error.code, detail=str(error))
            raise RetryableLookupError(str(error)) from error
```

### `auth/firebase.py` — the retry tier (`firebase.py:130-147`)

Two functions, the twin of each (RESEARCH.md Open Question 1 recommends two wrappers, not one
generic). The new callback raises `RevocationUnconfirmed`, never `_exhausted`'s `Unavailable`:

```python
def _exhausted(retry_state) -> NoReturn:
    """Convert an exhausted retry budget into the `Unavailable` rejection the client is owed."""
    raise Unavailable(stage="provider_lookup") from retry_state.outcome.exception()


async def lookup_with_retry(adapter, issuer: str, subject: str) -> VerifiedProviderIdentity:
    """Call the adapter up to `FIREBASE_LOOKUP_ATTEMPTS` times; return the identity or raise."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        # Only the internal marker retries, so `UserNotFound` and `NotLinked` propagate after one attempt.
        retry=retry_if_exception_type(RetryableLookupError),
        retry_error_callback=_exhausted,
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
```

### `errors.py` — the new leaf (`errors.py:407-410`)

Placed under `# --- Lookup arms ---`, beside `Unavailable`, declaring both `status` and `code`:

```python
class Unavailable(ProviderLookupError):
    """The read could not be completed: an exhausted retry budget, or no app configured."""
    status = 503
    code = "verification_temporarily_unavailable"
```

### `routers/auth.py` — the eighth route

Two analogs, combined. The narrowing comment and decorator style from `sync`
(`routers/auth.py:180-186`):

```python
# The route-level dependency narrows this one route to linked callers; the router-level one cannot.
@router.post("/auth/sync",
             response_model=SyncResponse,
             summary="Report the caller's entitlement and registration state",
             description="Reads the caller's effective grant, the current period's usage and the "
                         "stored registration state. Nothing is written.")
async def sync(identity: Identity = Depends(get_linked_identity),
               service: SyncService = Depends(get_sync_service)) -> SyncResponse:
```

The 204 shape from `routers/chats.py:78-86` — `status_code=204`, no `response_model`, return
annotation `Response`:

```python
@router.delete("/chats/{chat_id}",
               status_code=204, ...)
async def delete_chat(...) -> Response:
    await service.delete_chat(chat_id, identity.user.id)
    return Response(status_code=204)
```

The seam is taken by `Depends(get_firebase_adapter)` (`app/dependencies.py:115-118`), never
constructed. `identity.identity.id` is the D-07 `identity_row_id`
(`schemas/auth.py:97-102`); the module-level `logger` at `routers/auth.py:39` writes it. The field
name and the "not admissible" rule come from `UpgradeRefused.log_fields` (`errors.py:437-441`):

```python
        # Enough to find the row and name the disagreement; the provider account uid is not admissible.
        return {"identity_row_id": str(self.identity_row_id), ...}
```

Module docstring at `:1-3` says "The seven auth routes" and enumerates them — rewrite to three
lines or fewer including the eighth (Pitfall 5).

### `tests/unit/conftest.py` — the fake gains a method

`FakeFirebaseAdapter` (`:189-207`) has one `answer`/`calls` pair. Add a second pair on the
`FakeDeviceCheckAdapter` model (`tests/e2e/conftest.py:238-266`), whose write method is the exact
raise-or-confirm shape a revocation needs:

```python
    def script_write(self, answer: BaseException | None) -> None:
        """Raise-or-confirm: a scripted exception is raised, `None` confirms the write."""
        self.write_answer = answer

    async def write_bits(self, device_token: str, *, bit0: bool, bit1: bool) -> None:
        self.write_calls.append((device_token, bit0, bit1))
        if isinstance(self.write_answer, BaseException):
            raise self.write_answer
```

`tests/e2e/conftest.py:226-235` (`scripted_firebase_adapter`) swaps the same class onto
`app.state.firebase_adapter` — no edit.

### `tests/unit/test_firebase_adapter.py` — scripting the SDK

The fixture at `:101-115` monkeypatches the SDK function; the twin patches
`auth.revoke_refresh_tokens` and its scripted success answer is `None`:

```python
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
```

`RecordingApp` (`:75-79`), `app` (`:96-98`) and `adapter` (`:100-102`) are reusable unchanged.
`TestSelection` (`:159-188`) is the four-case model; its
`test_a_configured_issuer_passes_its_own_app_explicitly` asserts
`calls == [{"uid": SUBJECT, "app": app}]` — the proof no `[DEFAULT]` app is reachable.

### `tests/unit/test_firebase_retry.py` — counting attempts

`CountingAdapter`/`AsyncCountingAdapter` (`:33-56`) raise `AssertionError` on script overrun;
the `DEFINITIVE` table (`:25-30`) is the per-outcome list. The exhaustion cases assert the
**class**, not the status (Pitfall 3) — `:134-145`:

```python
    async def test_neither_the_retry_error_nor_the_internal_marker_escapes(self):
        adapter = CountingAdapter(*[_retryable() for _ in range(FIREBASE_LOOKUP_ATTEMPTS)])

        with pytest.raises(BaseException) as raised:  # noqa: B017 -- the class is the assertion
            await lookup_with_retry(adapter, ISSUER, SUBJECT)

        assert not isinstance(raised.value, tenacity.RetryError)
        assert not isinstance(raised.value, RetryableLookupError)
        assert isinstance(raised.value, Unavailable)
```

### `tests/e2e/test_sign_out_all.py` (new)

Module and client shape from `tests/e2e/test_sync.py:1-30` and
`tests/e2e/test_restore_subscription.py:85-94`:

```python
pytestmark = pytest.mark.e2e


@pytest_asyncio.fixture(loop_scope="module")
async def restore_client(_app_lifespan, stub_verifier):
    """A client over the real started app whose tokens the stub verifier accepts."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _auth(subject: str = SUBJECT) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=subject)}"}
```

Rows come from `seed_identity` (`tests/e2e/conftest.py:523-543`); tokens from
`tests/unit/conftest.py:46-56` (`make_token`).

The D-07 INFO assertion must use the spy, never `capture_logs`
(`tests/e2e/test_app_store_webhook.py:63-101`), targeting `routers/auth.py`'s module logger:

```python
_LOGGERS = ("nativespeaker.api.app.error_handlers.logger",
            "nativespeaker.api.services.subscriptions.logger")


class _LogSpy:
    """A recording spy on a module's own logger, so "which record, once" stays observable."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, event: str, **fields) -> None:
        self.entries.append((event, fields))


def _spy_on(monkeypatch, targets: tuple[str, ...], levels: tuple[str, ...]) -> _LogSpy:
    """A spy, not `capture_logs`: the module-level logger caches its binding, so capture sees nothing."""
    spy = _LogSpy()
    for target in targets:
        for level in levels:
            monkeypatch.setattr(f"{target}.{level}", spy.record)
    return spy
```

## Shared Patterns

### Failing closed on issuer selection
**Source:** `auth/firebase.py:66-69` — `raise <leaf>(stage="issuer_selection")` with no call made.
**Apply to:** the new seam method, its unit selection cases, and the e2e "no app" 503 case.

### One leaf per outcome, status and code declared once
**Source:** `errors.py:397-410`. The class name is the log event
(`app/error_handlers.py:33-44` writes `camel_to_snake(type(exc).__name__)`).
**Apply to:** `RevocationUnconfirmed`, its `test_rejection_vocabulary` `EVENT_NAMES` entry, and a
`CONSTRUCTOR_ARGUMENTS` entry on the `Unavailable` model (`test_rejection_vocabulary.py:179`):

```python
    errors_module.Unavailable: ((), {"stage": "issuer_selection"}),
```

### Route-level narrowing, asserted twice
**Source:** the comment line above every narrowed route in `routers/auth.py` plus the two
parametrize literals at `tests/unit/test_app_wiring.py:70-73` and `:80-83`:

```python
    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant",
                                      "/auth/restore-subscription", "/users/me"))
```
**Apply to:** `/auth/sign-out-all` joins both. `_declared(route)` at `:36-44` is also the one-line
way to assert `get_db not in _declared(route)` (D-04, RESEARCH.md Open Question 3).

### Hand-written literals that break by construction
| File | Line | Edit |
|---|---|---|
| `tests/unit/test_adapter_interfaces.py` | `:110-111` | method set, case name and class docstring all say "one method" |
| `tests/unit/test_auth_package_shape.py` | `:13` | `CURRENT = (8, 24, 59)` — re-measure, do not guess |
| `tests/unit/test_rejection_vocabulary.py` | `EVENT_NAMES`, `CONSTRUCTOR_ARGUMENTS` | add `revocation_unconfirmed` and its sample |
| `tests/unit/test_app_wiring.py` | `:70-73`, `:80-83` | add the path to both |

### Comments and docstrings
**Source:** every excerpt above. Docstrings are three lines maximum
(`tests/unit/test_docstring_bar.py:42-48`, baseline `0`); comments are one line, inline, ASD-STE100
(D-11).

## No Analog Found

None. Every file has a match in the tree.

## Metadata

**Analog search scope:** `src/nativespeaker/api/{auth,routers,app}`, `src/nativespeaker/api/errors.py`,
`tests/unit`, `tests/e2e`
**Files read:** 16, all git-tracked
**Pattern extraction date:** 2026-09-08
