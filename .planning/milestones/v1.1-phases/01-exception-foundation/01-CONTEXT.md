# Phase 1: Exception Foundation - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a typed exception hierarchy covering all known error cases, with registered HTTP handlers that return structured error responses. This is an API contract concern — what callers receive when things go wrong. No new capabilities, no new endpoints.

</domain>

<decisions>
## Implementation Decisions

### Error response shape
- All error responses must follow: `{"status": <http_code>, "error": "<human message>"}`
- This shape applies universally — typed exceptions, FastAPI 422 validation errors, Starlette defaults, and any 3rd-party library errors
- Goal: hide the FastAPI signature; no framework internals should be detectable from responses

### Error codes
- No machine-readable code field — HTTP status code is sufficient for clients to branch on
- VALIDATION_ERROR is acceptable as a conceptual label internally but does not appear in the response body

### 500 coverage
- Unhandled/bare exceptions return `{"status": 500, "error": "Internal server error"}` — same shape, generic message
- Full exception detail (message + stack trace) must be logged server-side
- Nothing about the internal failure is exposed to the client

### Claude's Discretion
- Exception class naming and hierarchy depth
- How to hook into FastAPI/Starlette to intercept all error paths (exception_handler, middleware, etc.)
- Log format and log level for 500s

</decisions>

<specifics>
## Specific Ideas

- The overriding of default responses is intentional security hardening — the service should not reveal which framework it uses

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-exception-foundation*
*Context gathered: 2026-02-25*
