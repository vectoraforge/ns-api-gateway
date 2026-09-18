# Description

The product is an AI chat that fixes grammar issues in sentences, sold
as a subscription for under $5/month. The product's value is not great
enough to make stealing it attractive — don't over-engineer for that
threat model. But don't skip normal security measures just because
there are no users yet.

## Requirements

- Use the latest modern patterns and libraries versions
- Always use Context7 MCP when I need library/API documentation, code generation, setup or configuration steps without me having to explicitly ask.
- Use shorter names for branch names
- Don't use string-based module references in Python tests

## Coding style

- Docstrings — three lines maximum. State what the function, class, or module does. Nothing else. Use plain English.
- Comments - 1 line maximum only when they are absolutely necessary to avoid confusion. Prefer inline style. Use plain English.
- A router may call `crud/` directly. Introduce a `services/` class when the
  router body would otherwise become too big or complicated: a service is earned
  by complexity, not assumed by category. One awaited read is neither, so it
  stays in the handler — § "Function shape" says to inline a function that is
  only a step.
- Do not write functions that are only one step. The check:** inline it, then read the call site. If the call site now needs a
  comment to explain what the code does, the name was carrying meaning and the function stays.
- Use this alignment style for multiline argument lists (func defs one per line, func calls collapse into 1+ line):
    async def create(self,
                     chat_id: UUID,
                     comment: str,
                     lang: str) -> None:
        return send_chat_message(chat_id=chat_id, user_id=user_id, content=body.content)
    """"""
    func code goes here
