# ns-api-gateway

## Comments and docstrings

These rules bind all code in this repository. They supersede the dense prose
register introduced by Phase 37.1 (D-16).

**Docstrings — three lines maximum.** State what the function, class, or module
does. Nothing else.

Do not describe what lives somewhere else, what the entity is not, or how the
application works in general. A docstring like `"The getUser providerData read,
and nothing else: token verification and revocation live elsewhere."` fails on
every count: it is not a sentence, and it defines the subject by naming code
that is not in it.

**Comments — only where they are necessary**, to resolve a genuine ambiguity or
prevent a misreading. Default to none.

**One line each.** A comment explains the specific line or lines below it. It
never explains the design, the request lifecycle, a rule enforced in another
module, or a decision that was made elsewhere.
