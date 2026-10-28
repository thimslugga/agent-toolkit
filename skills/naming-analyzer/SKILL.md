---
name: naming-analyzer
description: Review and improve identifier names (variables, functions, types, constants, files, packages) in Python, Go, Rust, JavaScript/TypeScript, Java and shell by running a deterministic convention scanner, then judging misleading, vague and inconsistent names in context and proposing safe renames. Use when asked to "review naming", "suggest better names", "check naming conventions in src/", "what should I call this", "is this a good name", or to rename identifiers across a codebase.
---

# Naming Analyzer

Finds names that break language conventions, carry no meaning, or lie about
what the code does, and proposes better ones with a safe path to rename.

The work splits in two, and the split matters:

| Half | Who | Catches |
|---|---|---|
| Mechanical | `scripts/naming-scan.py` | Case style, single letters, vague words, numbered suffixes, Hungarian notation, boolean form, Go initialisms and stutter, Rust acronyms, builtin shadowing, length, abbreviations, exception suffixes, file names |
| Semantic | You, by reading code | Names that mislead (critical), inconsistent vocabulary, missing units, wrong plurality, stale names after refactors |

The scanner never reports `critical`. Only you can, after reading the body.

## Modes

Pick from the request; ask only if it is genuinely unclear.

| Request | Mode |
|---|---|
| "review naming in X", a path, "check conventions" | **Review** (default) |
| "what should I call this?", one identifier or snippet | **Name one thing**: skip the scanner, use [references/semantics.md](references/semantics.md) |
| "what are the conventions for Go?" | **Reference**: answer from the language reference below |
| "rename these", "fix all" | **Rename**: Review first, then the rename workflow |

## Review workflow

1. **Scope.** Resolve the target path. Note the languages present and read
   the matching reference(s) — only those:
   [python](references/python.md) · [go](references/go.md) ·
   [rust](references/rust.md) · [javascript/typescript](references/javascript-typescript.md) ·
   [java](references/java.md) · [shell](references/shell.md) ·
   [data, APIs, files, config](references/data-and-apis.md).

2. **Find project rules first.** They override language defaults. Look for:
   `pyproject.toml`/`ruff.toml` (`N` = pep8-naming), `.golangci.yml`
   (`revive` var-naming, `stylecheck` ST1003), `clippy.toml` / `#![warn(clippy::...)]`,
   `.eslintrc*` / `eslint.config.*` (`camelcase`, `@typescript-eslint/naming-convention`),
   `checkstyle.xml`, a glossary, `CONTRIBUTING.md`, or ADRs about naming.

3. **Run the scanner** from the project root. Python 3.9+, stdlib only, no
   install. Set `SKILL_DIR` to this skill's directory (the base directory
   shown when the skill loads, e.g. `~/.claude/skills/naming-analyzer`):

   ```bash
   SCAN="python3 $SKILL_DIR/scripts/naming-scan.py"
   $SCAN src/ --min-severity minor > /tmp/naming.json        # full report
   $SCAN src/ --min-severity minor --format text | head -50  # skim
   $SCAN --list-rules                                       # rule table
   ```

   Read the JSON in pieces rather than dumping it (it can hold up to
   `--max-findings`, default 1000):

   ```bash
   python3 -c 'import json; r=json.load(open("/tmp/naming.json")); print(json.dumps(r["summary"], indent=1)); [print(f["severity"], f["rule"], f["path"], f["line"], f["name"], "->", f["suggestion"], f["occurrences"]) for f in r["findings"][:40]]'
   ```

   Useful flags: `--exclude 'migrations/*'` (repeatable), `--lang` (force for
   stdin `-` or explicit files), `--fail-on major` (CI gate, exit 1),
   `--max-findings N`. A missing path exits 2. Inside a git repo it honours
   `.gitignore`; it always skips `node_modules`, `vendor`, generated,
   minified and `.d.ts` files. Start at `--min-severity minor` on large
   codebases; drop to `info` for a single file.

   **Unsupported languages** (C, C++, C#, Kotlin, Ruby, PHP, Swift...) are
   skipped silently: `summary.languages` shows what was scanned. Say so in
   the report and review those files by reading, using
   [references/semantics.md](references/semantics.md) and the language's own
   style guide.

4. **Read `summary.style_profile` before the findings.** It counts styles per
   language and kind. If the project is consistently off-convention (say 95%
   `snake_case` functions in a JS codebase), consistency wins: treat that as
   the standard, drop the matching N001 findings, and mention it once.

5. **Verify every finding you report.** The scanner is lexical. Open the line
   for anything `major`, anything with many `occurrences`, and anything
   public. Drop or downgrade when the name is:
   - required by a framework or protocol (`setUp`, `ServeHTTP`, `do_GET`,
     React `useX` hooks, Django `Meta`, ORM columns mirroring a schema,
     JSON/GraphQL fields that mirror an external contract);
   - public API where a rename breaks users (keep it; propose a deprecation alias);
   - conventional in that domain (`i`, `j` loops; `x`, `y` coordinates;
     `df` in pandas; `ctx`, `err`, `req`, `res`; `T` for a type parameter);
   - a deliberate project choice found in step 2.

6. **Semantic pass.** Read the public surface and the most-used names (high
   `occurrences`), plus any function longer than ~40 lines. Check each against
   the misleading-name checklist in [references/semantics.md](references/semantics.md):
   `get*` that mutates, `is*` that returns a non-boolean or has side effects,
   singular names for collections, durations and sizes without units, one
   concept with several verbs (`fetch`/`get`/`load`), one name with two
   meanings, names left behind by a refactor.

7. **Report** with [references/report-format.md](references/report-format.md).
   Lead with the handful of renames that matter most, not the full list.

## Severity model

| Severity | Meaning | Source |
|---|---|---|
| `critical` | Misleading: the name promises something the code does not do | Agent only |
| `major` | Opaque at a public or wide scope: vague function/type names, single-letter functions or types | Scanner + agent |
| `minor` | Convention violation or unclear local name; fix when touching the code | Scanner |
| `info` | Taste, or idiomatic in context (Go short locals, numbered pairs, test files) | Scanner |

## Rename workflow

Never rename without the user's go-ahead, and never with blind text
replacement: identifiers collide with strings, comments, other scopes and
other modules.

1. **Size it.** `occurrences` in the JSON counts whole-word uses of the
   name across *all* scanned files and languages, so it overstates common
   names (`data`, `id`). Treat it as an upper bound and confirm scope with
   `rg -w --count-matches '<name>' <path>` or the LSP "find references".
2. **Use the language's semantic rename** (scope-aware):

   | Language | Tool |
   |---|---|
   | Python | LSP rename (pyright/basedpyright, pylsp + rope); scripted: `rope` |
   | Go | `gopls rename -w path/file.go:#<byte-offset> NewName` |
   | Rust | rust-analyzer rename (LSP); check with `cargo check` |
   | JS/TS | tsserver rename (LSP); scripted: `ts-morph` or `jscodeshift` |
   | Java | IDE refactor, or OpenRewrite `ChangeMethodName` / `ChangeType` recipes |
   | Shell | No semantic tool: `rg -w` the name, edit by hand, review `git diff` |

3. **Protect public API.** Keep the old name as a deprecated alias for a
   release: Python `old = new` plus `warnings.warn(..., DeprecationWarning)`;
   Go a wrapper with a `// Deprecated: use New.` comment; Rust
   `#[deprecated(note = "use new")]` plus `pub use`; TS a re-export with a
   `/** @deprecated */` JSDoc tag.
4. **Prove it.** Run the build, linter and tests; show `git diff --stat`.
   Go: also check file renames against build-constraint suffixes
   (`_linux.go`, `_test.go`, `_amd64.go` change what compiles).

## Present results to the user

```markdown
## Naming review: <path> — <N> files, <M> identifiers

**Top renames** (highest impact first)
1. `getUser` → `fetchAndTouchUser` — critical: also writes `lastLogin` (services/user.ts:45, 12 uses)
2. `process` → `applyRefund` — major: says nothing (billing/refund.py:88, public)

**Conventions**: 14 minor findings, mostly `snake_case` methods in `legacy/` — fix opportunistically.
**Kept on purpose**: `ServeHTTP`, `setUp` (framework); `x, y` (coordinates).

Want me to apply renames 1–2 with the TypeScript and Python language-server rename and run the tests?
```

Keep the full list in a file or collapsible section when there are more than
~15 findings; the user needs the decision, not the dump.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `files_scanned: 0` | Extensions not recognised, or ignored by `.gitignore`; pass files explicitly with `--lang` |
| Entries in `errors` with `SyntaxError` | File is not valid for the parser's Python version (3.9+ grammar on the running interpreter); review that file by hand |
| Thousands of findings | `--min-severity minor`, `--exclude` generated or legacy dirs, then work package by package |
| Finding is wrong | Lexical scanners miss context; drop it and, if it recurs, note the pattern in the report |
| `python3` missing | Any Python 3.9+ works: `uv run --python 3.12 "$SKILL_DIR/scripts/naming-scan.py" <path>` |
| `No such file or directory` for the script | `SKILL_DIR` is unset or wrong; use the absolute path of this skill's folder |

## Files

- `scripts/naming-scan.py` — the scanner (see `SPEC.md` for the contract).
- `references/<language>.md` — conventions, idioms and linter rules per language.
- `references/semantics.md` — how to judge and invent names; misleading-name checklist.
- `references/report-format.md` — full report template.
- `tests/` — scanner test suite (`uv run --with pytest pytest`).
