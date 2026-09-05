# Phase 44: User Setup Required

**Generated:** 2026-09-05
**Phase:** 44-post-webhooks-google-play-rtdn
**Status:** Incomplete

`POST /webhooks/google-play/rtdn` reads authoritative subscription state from
`purchases.subscriptionsv2.get`. The route is registered in every environment. It answers 503
`verification_temporarily_unavailable` until the items below are complete, and it logs one
`google_play_configuration_absent` warning at boot.

Everything that this repository can do is done. The items below need a human in a browser, with
access to accounts this project holds no credentials for.

## Environment Variables

None of these three is a secret. Set all three, or set none: the route needs all of them.

| Status | Variable | Source | Add to |
|--------|----------|--------|--------|
| [ ] | `GOOGLE_PLAY_PACKAGE_NAME` | Play Console → the app → the package name, e.g. `com.example.yourapp` | `.env` |
| [ ] | `GOOGLE_PLAY_PUSH_AUDIENCE` | Google Cloud console → Pub/Sub → the push subscription → Authentication → Audience | `.env` |
| [ ] | `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL` | Google Cloud console → Pub/Sub → the push subscription → Authentication → Service account | `.env` |

`.env.example` carries the same three lines, commented out, with values that parse.

**The audience must be the exact `aud` string that the push token carries.** A value that only
looks equivalent is still wrong, and a wrong value is not a visible failure. See the warning at
the end of this file.

## Account Setup

No new account. The route uses Application Default Credentials, which is the identity Firebase
Admin already uses, so this phase adds no key file and no new secret.

- [ ] **Confirm ADC is available to the pod**
  - The same credential the Firebase Admin path already needs.
  - Skip if: the Firebase completion path already works in this environment.

## Dashboard Configuration

- [ ] **Grant the ADC identity access to the Play Developer API**
  - Location: Play Console → Users and permissions
  - Scope: `https://www.googleapis.com/auth/androidpublisher`
  - Notes: The grant is made in Play Console. It is **not** made in GCP IAM. A GCP IAM role does
    not give access to the Play Developer API.

- [ ] **Create the Pub/Sub topic and the push subscription**
  - Location: Google Cloud console → Pub/Sub
  - Endpoint: `POST https://<your-domain>/webhooks/google-play/rtdn`
  - Authentication: enable an OIDC token, and record its audience and its service account. Those
    two values are the second and third environment variables above.

- [ ] **Point Play at the topic**
  - Location: Play Console → Monetisation setup → Real-time developer notifications
  - Set the topic created in the previous step.
  - Notes: The first message that Play sends is a `testNotification`. The route answers 200 to it
    and writes nothing, which is correct.

- [ ] **Open egress to two hosts**
  - `https://www.googleapis.com` — the JWKS document. Firebase already needs this host.
  - `https://androidpublisher.googleapis.com` — the subscription read. This application has never
    called this host before, so an existing allow-list will not contain it.

- [ ] **Make the Android client send the attribution id**
  - Location: the Android application, outside this repository.
  - The client must pass this project's server-minted `store_purchase_tokens.identity_value` as
    `BillingFlowParams` `obfuscatedAccountId` at purchase time.
  - Google does not mint that value. Without it, every Google subscription is ingested
    unattributed and grants nobody anything. Nothing raises an error, so no alert reports it.

## Verification

After the three variables are set:

```bash
# The three variables are present in the environment
grep GOOGLE_PLAY .env

# The boot warning is gone: this prints nothing when the configuration is complete
uv run python -c "
from nativespeaker.api.config import EnvironmentConfig
g = EnvironmentConfig().app_config.google_play
print('package_name  :', g.package_name)
print('push_audience :', g.push_audience)
print('push_sa_email :', g.push_service_account_email)
"
```

Expected: the three values print, and the boot log carries no
`google_play_configuration_absent` warning.

Then, from Play Console → Monetisation setup → Real-time developer notifications, use
**Send test notification** and confirm the route answers 200.

## The failure mode that looks like nothing

Cloud Pub/Sub accepts only the statuses 102, 200, 201, 202 and 204 as an acknowledgement. It
resends the message on every other status, and 401 is one of them.

So a mistyped `GOOGLE_PLAY_PUSH_AUDIENCE`, or a wrong
`GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL`, refuses **every genuine notification**, and Pub/Sub
retries each refused message until message retention expires. The deployment looks correct from
the outside. No subscription is written.

The `stage` field on the refusal log line is the only signal that separates "this deployment is
misconfigured" from "this token is not Google's". Read it before you conclude that no
notifications are arriving.

---

**Once all items complete:** Mark status as "Complete" at top of file.
