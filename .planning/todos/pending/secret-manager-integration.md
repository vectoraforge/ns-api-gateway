---
title: Retrieve all secrets via google.cloud.secretmanager
area: config
created: 2026-08-20
source: Phase 35 discussion
status: open
---

# Retrieve all secrets via Google Secret Manager

Replace file- and environment-sourced secret material with `google.cloud.secretmanager`
lookups behind the existing `pydantic-settings` loader.

**Why now (context):** Phase 35 puts the versioned HMAC key material
(`k_actor_subject_vN`, shared by the audit writer §4.3 and the challenge store §6.4)
in `config/config.yaml`, which is tracked in git. Existing secrets (`DB_*`,
`JWT_*`, `OPENAI_API_KEY`) stay in the gitignored `.env`. That means HMAC key
material lands in git history, and rotating a key is a commit whose predecessor
stays readable forever.

**Scope when picked up:**
- One loader seam in `src/nativespeaker/api/config.py` — the split between
  YAML structure and secret values already exists, so this replaces the value
  source, not the config models.
- Covers the HMAC key map, DB password, OpenAI key, and Firebase credentials.
- Fail closed at startup when a required secret cannot be resolved.
