# Deferred Items

- `.planning/WINDOWS.md` frontmatter counts disagree with its entries
  status: open
  **What:** `gsd-tools windows append` refuses to write, reporting
  `frontmatter open/waived/fixed/total=20/1/11/32 but entries yield 19/1/12/32`.
  One entry was fixed without its frontmatter counter being moved.
  **Found during:** plan 48-01, appending a deviation entry.
  **Why deferred:** pre-existing and unrelated to this plan's changes; the
  executor scope boundary forbids auto-fixing it here. Correcting the counters
  is a one-line edit whoever owns the ledger should make.
  **Cost of leaving it:** every `windows append` in phases 48 to 50 fails the
  same way, so defects that should reach the ship gate are recorded only in
  their own SUMMARY.
