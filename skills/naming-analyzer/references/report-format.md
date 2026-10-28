# Naming Review Report Template

Use for reviews with more than a handful of findings, or when the user asks
for a written report. For a quick answer, the short template in SKILL.md is
enough. Leave out empty sections.

```markdown
# Naming Review: <path>

**Scope:** <N> files, <M> identifiers (<languages>) · scanner `--min-severity <level>`
**Project conventions applied:** <e.g. ruff N rules; snake_case JSON fields mirror the public API>

## Summary

| Severity | Count | What it means |
|---|---|---|
| Critical | 2 | Names that mislead about behaviour (agent-verified) |
| Major | 5 | Vague or opaque names on public or wide scopes |
| Minor | 23 | Convention violations, unclear locals |
| Info | 41 | Taste; listed in the appendix only |

## Top renames

Ranked by impact: severity, then public exposure, then `occurrences`.

| # | Current | Proposed | Why | Where | Uses |
|---|---|---|---|---|---|
| 1 | `getUser` | `fetchUserAndRecordLogin` | Critical: also writes `lastLogin` | `src/services/user.ts:45` | 12 |
| 2 | `process` | `applyRefund` | Major: says nothing; public | `billing/refund.py:88` | 7 |
| 3 | `UserId` | `UserID` | Go initialism (N008) | `internal/user/types.go:12` | 31 |

## Critical: misleading names

### `getUser` — src/services/user.ts:45
**Says:** a read. **Does:** reads, sets `lastLogin`, saves.
**Risk:** callers use it in read-only paths (`reports/export.ts:19`) and silently update login times.
**Options:** rename to `fetchUserAndRecordLogin`, or split into `fetchUser` + `recordLogin` (preferred).

## Consistency

### One concept, four verbs
`fetchUser` (api/), `getAccount` (billing/), `loadInvoice` (invoices/), `retrieveOrder` (orders/)
all perform a network read. **Proposal:** standardise on `fetch*` (14 sites).

## Conventions by area

| Area | Rule | Count | Example | Note |
|---|---|---|---|---|
| `src/legacy/` | N001 camelCase methods in Python | 18 | `getRows` → `get_rows` | Fix when touched |
| `cmd/` | N009 package stutter | 3 | `config.ConfigLoader` → `config.Loader` | Breaking for importers |

## Kept on purpose

- `ServeHTTP`, `setUp`, `do_GET` — framework-mandated.
- `x`, `y` in `geometry/` — coordinates.
- JSON fields in `api/schema.py` — mirror the public API contract.

## Rename plan

1. Add deprecated aliases for public names (#1, #3).
2. Run semantic renames: `gopls rename`, LSP rename for TS/Python.
3. `make lint test`; review `git diff --stat`.
4. Remove aliases after one release.

## Appendix: info findings

<collapsed list or path to the JSON file>
```
