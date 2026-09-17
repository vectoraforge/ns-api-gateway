# Phase 49: Delete the single-implementation auth Protocols - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-16
**Phase:** 49-delete-the-single-implementation-auth-protocols
**Areas discussed:** ChallengesDB shape, The challenge route, The fake stores, Unannotated adapter

---

## ChallengesDB shape

| Option | Description | Selected |
|--------|-------------|----------|
| ChallengesDB(db) | Same shape as `IdentitiesDB(db)` and `GrantsDB(db)`; the four methods lose their session parameter; tests that use one store across sessions build one per session | ✓ |
| Keep ChallengesDB() | No change to `crud/challenges.py`; `AuthService` holds one crud class that takes the session on each call | |

**User's choice:** `ChallengesDB(db)`.
**Notes:** The user first answered with a question: "Why are you changing ChallengesDB? What
requirement is that?" No requirement asks for it; the ROADMAP goal only moves where the class is
built. Claude read the question as a rejection, recorded "keep `ChallengesDB()`" and moved to the
next area. The user stopped that and said the question was not answered. Claude corrected the
checkpoint and asked again; the user chose `ChallengesDB(db)`.

| Option | Description | Selected |
|--------|-------------|----------|
| self.challenges_db | Matches `self.identities_db` and `self.grants_db` | ✓ |
| Keep self.challenge_store | The four read sites do not change | |

**User's choice:** `self.challenges_db`.

---

## The challenge route

| Option | Description | Selected |
|--------|-------------|----------|
| ChallengesDB(session).issue in the route | One line changes; the route already builds `IdentitiesDB(session)` | ✓ |
| A new AuthService method | The route declares `get_auth_service`; pulls the Firebase and DeviceCheck dependencies it does not use | |

**User's choice:** `ChallengesDB(session).issue` in the route.

---

## The fake stores

| Option | Description | Selected |
|--------|-------------|----------|
| One conftest fixture | `FakeChallengeStore` stays in conftest; one fixture patches `locate`, `claim`, `consume` and returns the fake | ✓ |
| Each suite patches its own | Four copies of the same three `setattr` lines | |

**User's choice:** One conftest fixture.

| Option | Description | Selected |
|--------|-------------|----------|
| Patch in each file | Each file keeps its `_RecordingChallengeStore` and patches `ChallengesDB.issue` | ✓ |
| Move to conftest | One recording fixture; the two recorders must first be made the same | |

**User's choice:** Patch in each file.

---

## Unannotated adapter

| Option | Description | Selected |
|--------|-------------|----------|
| Annotate with the concrete classes | `adapter: FirebaseAdminLookup`, `devicecheck: AppleDeviceCheck`; `ty` checks the calls | ✓ |
| Leave them unannotated | The phase touches only annotations that named a Protocol | |

**User's choice:** Annotate with the concrete classes.
**Notes:** Claude said before the question that no criterion asks for this. The lifespan always
builds both adapters, so no `| None`.

---

## Claude's Discretion

- The order of the five commits.
- Whether D-01 and the removal of `get_challenge_store` are one commit or two.
- Whether `tests/unit/test_adapter_interfaces.py` is deleted when it becomes empty.

## Deferred Ideas

None. The two matched todos were not folded, as in Phases 46 and 48; the user was not asked.
