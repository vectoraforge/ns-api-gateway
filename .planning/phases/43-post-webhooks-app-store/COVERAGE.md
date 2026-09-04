# API Coverage — Apple App Store Server Notifications V2 (`app-store-server-library` 3.0.0)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

The deterministic detector returned `detected: false` for this phase's scope. The matrix is written
anyway, because the phase does integrate an external provider's callback API and a decided matrix is
cheaper than a rediscovered hole.

The capability surface below is the surface this phase can reach: the notification the store posts,
the parts of the library that verify it, and the library's neighbouring capabilities that a reader
would reasonably expect a store integration to use.

## Notification verification — the library's `SignedDataVerifier`

| capability | decision | reason |
|---|---|---|
| `verify_and_decode_notification` (the envelope) | INTEGRATE | |
| `verify_and_decode_signed_transaction` (the nested transaction) | INTEGRATE | |
| `verify_and_decode_renewal_info` (the nested renewal info) | INTEGRATE | |
| `x5c` chain verification to a pinned root | INTEGRATE | |
| bundle id, app apple id and environment binding | INTEGRATE | |
| `verify_and_decode_app_transaction` | OPT-OUT | not needed — this route ingests server notifications, not an app receipt; Phase 45's restore is the phase that verifies a client-submitted artifact |
| `enable_online_checks` (OCSP revocation) | OPT-OUT | explicitly out of scope — D-09 turns it off, because a per-request network call on the admission path is forbidden by the Phase 35 barrier rule; the cost is recorded under APPLEHOOK-01 |
| `Environment.XCODE` and `Environment.LOCAL_TESTING` | OPT-OUT | explicitly out of scope — both make the library skip signature verification entirely; the configuration is typed so neither can be expressed |

## Notification handling — the store's own callback contract

| capability | decision | reason |
|---|---|---|
| accept and apply a notification carrying a transaction | INTEGRATE | |
| accept a notification carrying no transaction (TEST and summary types) | INTEGRATE | |
| replay suppression by `notificationUUID` | INTEGRATE | |
| answer 5xx so the store's retry schedule applies | INTEGRATE | |
| record the notification type as received, unknown types included | INTEGRATE | |
| branch on the notification type or its subtype | OPT-OUT | not needed — D-13 derives the subscription's status from the dates alone, so a new Apple type costs nothing; the type is recorded and never read as a decision |
| the version 1 notification format | OPT-OUT | explicitly out of scope — the brief names version 2, and version 1 is superseded |
| consumption requests and refund decisions | OPT-OUT | not needed yet — this product sells one subscription under $5 and answers no consumption request; the notification is recorded like any other |
| external purchase tokens | OPT-OUT | not needed — the product has no external purchase channel |

## The App Store Server API (outbound calls to Apple)

| capability | decision | reason |
|---|---|---|
| every outbound endpoint — transaction history, subscription status, refund lookup, notification test, order lookup | OPT-OUT | explicitly out of scope — this phase makes no outbound call to Apple at all. Verification is local computation, and the brief forbids a network call on the admission path. Phase 45 owns direct artifact verification against Apple |

## Google Play

| capability | decision | reason |
|---|---|---|
| Real-Time Developer Notifications over Cloud Pub/Sub | OPT-OUT | explicitly out of scope — Phase 44 owns it, and PLAYHOOK-02 binds it to the service this phase builds rather than to a forked copy |
