---
phase: 23-envoy-gateway-rate-limiting
plan: 03
subsystem: infra
tags: [helm, envoy-gateway, kubernetes, rate-limiting, jwt, httproute, security-policy]

requires:
  - phase: 22-apple-subscription-integration
    provides: Subscription tiers (free/silver/gold/platinum) and Firebase JWT plan claim
provides:
  - Helm chart (k8s/) with Deployment, Service, HTTPRoutes, SecurityPolicy, BackendTrafficPolicy
  - Envoy Gateway JWT validation with plan claim extraction to x-user-plan header
  - Per-tier local rate limiting on POST /chats only (5/50/100/1000 per minute)
  - Separate HTTPRoutes for app (JWT), LLM (JWT + rate-limit), webhooks (public), health (public)
  - Custom 429 response body with {"code":"rate_limited"}
affects: [deployment, envoy-gateway, infrastructure]

tech-stack:
  added: [helm, envoy-gateway-v1.7.1, kubernetes-gateway-api-v1]
  patterns: [helm-chart-with-envoy-policies, separate-httproutes-per-auth-level, local-rate-limiting-per-plan-tier]

key-files:
  created:
    - k8s/Chart.yaml
    - k8s/values.yaml
    - k8s/templates/_helpers.tpl
    - k8s/templates/NOTES.txt
    - k8s/templates/deployment.yaml
    - k8s/templates/service.yaml
    - k8s/templates/httproute-app.yaml
    - k8s/templates/httproute-llm.yaml
    - k8s/templates/httproute-webhooks.yaml
    - k8s/templates/httproute-health.yaml
    - k8s/templates/security-policy.yaml
    - k8s/templates/backend-traffic-policy.yaml
  modified: []

key-decisions:
  - "SecurityPolicy targets both app-routes and llm-routes for JWT coverage on all authenticated endpoints"
  - "BackendTrafficPolicy targets llm-routes only -- read endpoints unrestricted per user decision"
  - "No default rate limit rule to avoid stacking with tier-specific rules -- unknown headers bypass Envoy rate limiting, backend quota is authoritative"
  - "Separate HTTPRoutes per auth level: app (JWT), llm (JWT + rate-limit), webhooks (public), health (public)"

patterns-established:
  - "Separate HTTPRoutes per auth/rate-limit level rather than one catch-all route"
  - "SecurityPolicy with claimToHeaders for JWT claim extraction to request headers"
  - "BackendTrafficPolicy with per-header clientSelectors for tier-based local rate limiting"
  - "responseOverride for custom JSON error body on 429"

requirements-completed: [ENVOY-01, ENVOY-02, ENVOY-03, ENVOY-04]

duration: 2min
completed: 2026-03-22
---

# Phase 23 Plan 03: Helm Chart Summary

**Helm chart with Envoy Gateway SecurityPolicy for JWT plan claim extraction and BackendTrafficPolicy for per-tier local rate limiting on POST /chats only**

## Performance

- **Duration:** 2min
- **Started:** 2026-03-22T01:25:40Z
- **Completed:** 2026-03-22T01:27:59Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- Complete Helm chart in k8s/ rendering 8 valid Kubernetes manifests (Deployment, Service, 4 HTTPRoutes, SecurityPolicy, BackendTrafficPolicy)
- SecurityPolicy extracts JWT plan claim to x-user-plan header on both app-routes and llm-routes
- BackendTrafficPolicy enforces per-tier rate limits (free:5, silver:50, gold:100, platinum:1000/min) only on llm-routes (POST /chats)
- Read endpoints (GET /users/me, GET /chats, etc.) are unrestricted -- no BackendTrafficPolicy targeting
- Webhook and health endpoints bypass JWT and rate limiting via separate HTTPRoutes

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Helm chart structure** - `2b15e5e` (feat)
2. **Task 2: Create Deployment, Service, HTTPRoutes, SecurityPolicy, BackendTrafficPolicy** - `19e3a3b` (feat)

## Files Created/Modified
- `k8s/Chart.yaml` - Helm chart metadata (ns-api-gateway, appVersion 1.5.0)
- `k8s/values.yaml` - Configurable defaults: replicas, image, rate limits, quotas, JWT, probes
- `k8s/templates/_helpers.tpl` - Helm helpers: name, fullname, labels, selectorLabels
- `k8s/templates/NOTES.txt` - Post-install deployment summary
- `k8s/templates/deployment.yaml` - App Deployment with probes and resource limits
- `k8s/templates/service.yaml` - ClusterIP Service on port 8000
- `k8s/templates/httproute-app.yaml` - Authenticated routes (/chats, /users, /examples)
- `k8s/templates/httproute-llm.yaml` - LLM routes (POST /chats only, rate-limited)
- `k8s/templates/httproute-webhooks.yaml` - Webhook route (POST /webhooks/apple, public)
- `k8s/templates/httproute-health.yaml` - Health route (/health, public)
- `k8s/templates/security-policy.yaml` - JWT validation + plan claim extraction (targets app-routes + llm-routes)
- `k8s/templates/backend-traffic-policy.yaml` - Per-tier local rate limiting (targets llm-routes only)

## Decisions Made
- SecurityPolicy targets both app-routes and llm-routes: app-routes needs JWT for authentication on all endpoints; llm-routes needs JWT so x-user-plan header is present for BackendTrafficPolicy
- No default rate limit rule: avoids rule stacking where a default (5/min) would also limit platinum users to 5/min. Unknown/missing headers bypass Envoy rate limiting -- acceptable since backend PostgreSQL quota is authoritative
- BackendTrafficPolicy targets llm-routes only (not app-routes): per user decision, only POST /chats endpoints are rate-limited
- responseOverride returns `{"code":"rate_limited"}` on 429 to match the app-level error contract

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all values are configurable via values.yaml. Empty strings for `image.repository`, `image.tag`, and `jwt.issuer` are intentional deployment-time configuration.

## Next Phase Readiness
- Helm chart is complete and renders valid YAML via `helm template` and `helm lint`
- Ready for deployment to Kubernetes cluster with Envoy Gateway v1.7.1 installed
- Backend quota enforcement (plans 01-02) provides the authoritative monthly limit

## Self-Check: PASSED

- All 12 created files verified present on disk
- Both task commits (2b15e5e, 19e3a3b) verified in git log

---
*Phase: 23-envoy-gateway-rate-limiting*
*Completed: 2026-03-22*
