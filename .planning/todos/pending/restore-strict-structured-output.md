---
title: Restore strict structured output on the LLM chain
area: llm
created: 2026-08-21
source: Phase 36 D-13
status: open
---

# Restore strict structured output on the LLM chain

Bind the three response models in `src/nativespeaker/api/models/llm.py` — `AnalyzeResponse`,
`FollowUpResponse`, `RejectResponse` — as a strict schema on the chat model call, so the provider
is constrained to emit them, instead of parsing unconstrained JSON and validating it after the fact.

**Why now (context):** `PROJECT.md` listed `with_structured_output(strict=True, method='json_schema')`
as both a validated capability and a good decision, but `git log -S"with_structured_output" -- src/`
returns nothing — it was never in the source. `services/llm.py:30` has always been
`prompt_template | self.llm | JsonOutputParser()`: unconstrained JSON, validated afterwards by the
Pydantic response models in `services/chats.py`. Phase 36 D-13 corrected the two documentation
claims; this item is the actual fix they described.

The gap has already cost a defect. D-35-11-A (`.planning/phases/35-foundation/deferred-items.md`):
a grammatically correct phrase made `POST /chats` return **500**, because the model returned only
`{resolved_mode, response}` and `AnalyzeResponse` required `issues` and `suggestions`. Phase 36 D-12
shipped the narrow instance fix — both list fields now default to `[]`, so a correct phrase returns
200 with empty arrays. This item is the general fix: with a strict schema bound to the call, the
provider cannot omit a declared key at all, and the response models stop needing per-field
concessions to work around an unconstrained chain.

**Note for whoever picks this up — the prompt is not the fix.** `config/prompt.txt:124` already
instructs "if nearly perfect → provide 1 to 2 suggestions", and the model ignores it. Prompt
instruction alone is demonstrably not holding; strengthening the wording will not close this.

**Scope when picked up:**
- One seam: `LLMService.create_chain` in `src/nativespeaker/api/services/llm.py`. The three modes
  are dispatched on `resolved_mode`, so binding needs a union/discriminated schema rather than one
  model, and `ChatService.ask_llm` currently re-validates the parsed dict — decide whether that
  validation stays as defence in depth or is removed once the schema is enforced at the call.
- Requires **real-provider e2e coverage**: strict schema support is provider- and model-specific,
  and a mocked chain proves nothing about whether the provider honoured the constraint. This is why
  it is out of scope for Phase 36, a route-rebinding phase with no LLM-chain remit.
- Revisit the D-12 defaults afterwards. They are a knowing, narrow exception to
  `01-foundation.md §8.3`; once the schema is enforced, decide deliberately whether the empty-list
  defaults stay (they are also the client-facing contract now) or revert to required fields.
