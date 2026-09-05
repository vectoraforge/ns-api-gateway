# API Coverage — Google Play Billing RTDN + Play Developer API v3 (`androidpublisher`)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
>
> Apple (Phase 43) was the first integration against the same need. This matrix was re-decided
> from a full-coverage baseline for Google rather than inherited from Apple's opt-outs, so a
> first-class/fallback asymmetry cannot accumulate silently. Where an asymmetry survives it is
> named in the reason column.

## Cloud Pub/Sub push transport

| capability | decision | reason |
|---|---|---|
| `push.oidc_token_verification` | INTEGRATE | |
| `push.ack_by_status_code` | INTEGRATE | Only 102/200/201/202/204 acknowledge; every other status redelivers (F-11) |
| `push.ordering_keys` | OPT-OUT | Google Play does not publish RTDN with an ordering key; the `store_signed_at` guard on `eventTimeMillis` is the ordering control (D-12) |
| `push.dead_letter_topic` | OPT-OUT | Provisioning the topic and the push subscription is infrastructure, explicitly out of this repository (§ Deferred) |

## RTDN notification bodies (`DeveloperNotification`)

| capability | decision | reason |
|---|---|---|
| `rtdn.subscriptionNotification` | INTEGRATE | |
| `rtdn.testNotification` | OPT-OUT | No purchase state exists to record; acknowledged with 200 and no write so Pub/Sub stops (D-05) |
| `rtdn.oneTimeProductNotification` | OPT-OUT | This product sells only subscriptions; acknowledged with 200 and no write (D-05) |
| `rtdn.voidedPurchaseNotification` | OPT-OUT | A subscription refund reaches us separately as a `subscriptionNotification` of type 12; acknowledged with 200 and no write (D-05) |
| `rtdn.pendingRefundReviewNotification` | OPT-OUT | Not named by D-05 and covered by the same present-or-absent rule; acknowledged with 200 and no write (F-10) |

## `purchases.subscriptionsv2`

| capability | decision | reason |
|---|---|---|
| `purchases.subscriptionsv2.get` | INTEGRATE | |
| `subscriptionsv2.subscriptionState` | INTEGRATE | All nine values mapped (F-08) |
| `subscriptionsv2.lineItems[].productId` | INTEGRATE | |
| `subscriptionsv2.lineItems[].expiryTime` | INTEGRATE | |
| `subscriptionsv2.startTime` | INTEGRATE | |
| `subscriptionsv2.latestOrderId` | INTEGRATE | |
| `subscriptionsv2.externalAccountIdentifiers` | INTEGRATE | |
| `subscriptionsv2.linkedPurchaseToken` | OPT-OUT | Read into the response model but not acted on (OQ-3); acting on it means a subscription write outside the notification's own lifecycle key. Google sends `SUBSCRIPTION_EXPIRED` for the old token on its own schedule |
| `subscriptionsv2.canceledStateContext` | OPT-OUT | No revocation signal exists there (OQ-1); the cancellation reason is not a column this schema holds |
| `subscriptionsv2.pausedStateContext.autoResumeTime` | OPT-OUT | `core.subscription_status` carries no paused word; `expired` stands in (D-11) and a `paused` status is a recorded deferred idea |
| `subscriptionsv2.acknowledgementState` | OPT-OUT | Acknowledgement is the Android client's obligation, not this backend's |
| `purchases.subscriptionsv2.revoke` | OPT-OUT | This backend never revokes a buyer's subscription; revocation is initiated in Play Console or by Google, and reaches us as an RTDN |

## Other `androidpublisher` resources

| capability | decision | reason |
|---|---|---|
| `purchases.subscriptions.*` (v1) | OPT-OUT | v1 is deprecated and superseded by `subscriptionsv2` (§ State of the Art) |
| `purchases.products.get` / `.acknowledge` / `.consume` | OPT-OUT | No one-time products are sold |
| `orders.get` / `.batchGet` / `.refund` | OPT-OUT | Order administration is not this service's job; refunds are initiated in Play Console |
| `monetization.subscriptions.*` | OPT-OUT | The subscription catalogue is authored in Play Console; this backend only reads purchases and resolves `productId` through a tracked map (D-16) |
| `inappproducts.*` | OPT-OUT | Catalogue publishing; out of the phase boundary |
| `edits.*` | OPT-OUT | App publishing; out of the phase boundary |
| `applications.deviceTierConfigs.*` | OPT-OUT | Play delivery configuration; unrelated to entitlement |

## Provider asymmetries this matrix records

- `SubscriptionStatus.revoked` is reachable on the Apple path only. `subscriptionsv2` exposes no
  citable revocation signal (OQ-1), so a Google revocation is recorded as `expired` with
  `event_type` 12 preserving the reason.
- Apple carries `gracePeriodExpiresDate` as its own field; Google does not, and the line item's own
  `expiryTime` is the grace-window end (P-01).
