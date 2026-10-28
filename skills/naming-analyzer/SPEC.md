# naming-scan Specification

Contract for `scripts/naming-scan.py`, the deterministic half of the
naming-analyzer skill. The tests in `tests/` are the executable form of this
document; when they disagree, fix one of them in the same change.

## Division of labour

| Concern | Owner | Why |
|---|---|---|
| Case style per language and kind | scanner | Mechanical, exhaustive, cheap |
| Single letters, numbered suffixes, Hungarian, length | scanner | Pattern-shaped |
| Vague words, unclear abbreviations | scanner (flags) + agent (confirms) | Lists catch candidates; context decides |
| Boolean prefixes, negated booleans | scanner (when type is known) | Needs a type signal |
| Go initialisms and package stutter; Rust acronym casing | scanner | Rule-shaped and language-specific |
| Python builtin / Go predeclared shadowing | scanner | Fixed lists |
| **Misleading names** (name and behaviour disagree) | agent only | Needs reading the body |
| Domain vocabulary, consistency with project glossary | agent only | Needs project context |
| Rename execution | agent, with language-aware tooling | Text replacement is unsafe |

The scanner never emits `critical`. Critical is reserved for misleading names
the agent confirms by reading code.

## Interface

```
naming-scan.py [PATH ...] [--format json|text] [--lang LANG]
               [--exclude GLOB]... [--min-severity LEVEL] [--fail-on LEVEL]
               [--max-findings N] [--list-rules]
```

- `PATH` is a file or directory; `-` reads stdin and requires `--lang`.
  No paths means `.`.
- Directories inside a git work tree use `git ls-files -co --exclude-standard`
  and prune only `node_modules` and `vendor` (tracked `build/` or `dist/`
  packages are real code); otherwise a walk that skips `.git node_modules
  vendor target dist build .venv venv __pycache__ .tox .mypy_cache
  .ruff_cache .pytest_cache .next`.
- Skipped: files over 1 MiB, `*.min.js`, files marked generated
  (`Code generated ... DO NOT EDIT.` or `@generated` in the first 5 lines).
- Language by extension, then shebang for extensionless files.
- JSON goes to stdout; progress and warnings go to stderr.
- Exit codes: `0` ok, `1` a finding at or above `--fail-on`, `2` usage error
  (including a path that does not exist).
- Input is decoded as UTF-8 with an optional BOM; undecodable stdin bytes are
  replaced, undecodable files are skipped with a warning.
- Test-file detection (`tests/`, `test_*.py`, `*_test.go`, `*.spec.ts`...)
  looks only at the path *below* the scan root.

### JSON shape

```json
{
  "version": 1,
  "summary": {
    "files_scanned": 3, "identifiers": 120, "findings": 9,
    "by_severity": {"major": 2, "minor": 5, "info": 2},
    "by_rule": {"N001": 4},
    "languages": {"python": 2, "go": 1},
    "style_profile": {"python": {"function": {"snake": 40, "camel": 2}}},
    "truncated": false, "reported": 9
  },
  "findings": [{
    "path": "app/user.py", "line": 12, "language": "python",
    "kind": "function", "name": "getUser", "rule": "N001",
    "severity": "minor", "message": "...", "suggestion": "get_user",
    "occurrences": 7
  }],
  "errors": [{"path": "bad.py", "message": "SyntaxError: ..."}]
}
```

Summary counts cover every finding at or above `--min-severity`;
`reported` is how many are in `findings` after `--max-findings`.
`occurrences` counts whole-word uses of the name across every scanned file
and language — an upper bound on the rename size.

## Severities

`info` < `minor` < `major` < `critical` (agent only).

## Rules

| ID | Name | Severity | Notes |
|---|---|---|---|
| N001 | case-style | minor; info for inferred Python constants and shell UPPER locals | Suggestion is the converted name; single letters and non-ASCII names skipped |
| N002 | single-letter | major (functions, types, constants); minor (locals, fields); info (Go locals, test files) | Loop/lambda vars and per-language idioms exempt (`i j k n x y z`; Python `f m e`; Go `t b w r f`) |
| N003 | vague-name | major (functions, types); minor (locals, fields); info (params, test placeholders) | Methods take meaning from the receiver: only empty words (`foo`, `stuff`) apply |
| N004 | numbered-suffix | info | `user2`; technical tokens (`sha256`, `ec2`, `ipv6`) exempt; skipped when N003 fires |
| N005 | hungarian | minor; info for TS/Java `IUser` | Type prefixes (`str`, `arr`, `obj`, `sz`, `b`) and scope prefixes (`m_`, `g_`); `n`-for-count is not Hungarian |
| N006 | boolean-prefix | info | Only when the type is known bool; predicates, adjectives, past tense, option-flag verbs accepted |
| N007 | negated-boolean | minor | `isNotValid`, `has_no_items`; bare `not…` only for known booleans |
| N008 | acronym-casing | minor | Go: re-cases only real initialisms (`UserId`→`UserID`); Rust: `HTTPServer`→`HttpServer` |
| N009 | package-stutter | minor | Go: `package user; type UserService` → `Service` |
| N010 | shadows-builtin | minor | Python builtins, Go predeclared identifiers |
| N011 | too-long | info | > 40 chars or > 6 words; test functions and test files exempt |
| N012 | unclear-abbreviation | minor | Conservative dictionary; ambiguous forms (`rec`, `proc`, `col`, `txt`) excluded |
| N013 | exception-suffix | info | Python exception classes end in Error/Exception/Warning/Exit/Interrupt |
| N014 | file-name | minor; major for Java (compile error) | Python modules (non-scripts), Go (uppercase), Rust: snake; Java: matches public type |

Also skipped entirely: `.d.ts` declaration files and bundled JS/TS (any of
the first 20 lines longer than 1000 characters).

Every false positive found while calibrating against the Go and Python
standard libraries is pinned in `tests/test_regressions.py`.

## Per-language conventions (N001)

| Language | function / method | variable / param / field | type / class | constant | other |
|---|---|---|---|---|---|
| Python | snake | snake | Pascal | UPPER_SNAKE | class attrs: snake or UPPER; module Pascal assign = type alias |
| Go | MixedCaps | MixedCaps | MixedCaps | MixedCaps (not UPPER_SNAKE) | package: lower, no `_`; `TestX_y` funcs exempt |
| Rust | snake | snake | Pascal (variants too) | SCREAMING_SNAKE (`const`, `static`) | module: snake |
| JS / TS | camel (Pascal in .jsx/.tsx) | camel; `const` may be UPPER_SNAKE | Pascal | — | leading `_`, `#`, `$` allowed |
| Java | camel | camel | Pascal | UPPER_SNAKE (`static final` *immutable* types only) | package: lower; other `static final`: camel or UPPER |
| Shell | lower_snake (`::` allowed) | lower_snake or UPPER_SNAKE; `local` lower | — | `readonly`/`export`/`declare -r`/`-x`: UPPER_SNAKE | hyphenated function names are not POSIX |

Leading/trailing underscores are stripped before classification. Python
dunders, `self`, `cls`, `_`, unittest hooks (`setUp`...), `visit_*` and
`do_GET`-style handlers are exempt.
