---
title: Message ordering is unspecified on read and on the LLM history
area: chats
created: 2026-08-31
source: Phase 37.5 code review (CR-03, CR-04), 37.5-REVIEW.md
status: open
---

# Message ordering is unspecified on read and on the LLM history

Two related defects, both pre-existing but surfaced by Phase 37.5's review.

**CR-03 — the API documents an order it does not provide.** `routers/chats.py:32`
publishes "ordered chronologically" into the OpenAPI description, while
`ChatsDB.get_messages` orders by `col(Message.id).desc()`. The key is a `uuid7`, so
`id` is time-ordered — but descending. Clients following the published contract get
the transcript backwards. One of the two is wrong; decide which and change it.

**CR-04 — the model receives history in no guaranteed order.** `ask_llm` iterates
`chat.messages`, loaded by `selectinload` against a `Relationship` with no
`order_by`. SQLAlchemy makes no ordering promise there, so the conversation handed
to the provider can be shuffled. A follow-up can answer the wrong turn, silently,
*after* the quota charge has already committed — the user pays for the wrong answer.

**Scope when picked up:**
- Add `order_by` to the `messages` relationship (ascending `id`), which fixes CR-04
  at the source and makes the ordering a property of the model rather than of each
  caller.
- Reconcile `get_messages`'s `desc()` with the OpenAPI text.
- A regression test for CR-04 needs to assert on the order of what reaches the
  provider double, not just on the response body — the existing `RecordingLLM` in
  `tests/unit/conftest.py` is the seam for it.
