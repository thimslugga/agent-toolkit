# Naming Analyzer

An agent skill that reviews identifier names and proposes better ones. It
pairs a deterministic, dependency-free scanner with the agent's reading of
the code, so convention checks are exhaustive and cheap while the judgement
calls — "this `getUser` writes to the database" — are made by something that
actually read the function.

## What it checks

| Layer | Checks |
|---|---|
| **Scanner** (`scripts/naming-scan.py`) | Case style per language and kind · single letters · vague words · numbered suffixes · Hungarian notation · boolean form · negated booleans · Go initialisms and package stutter · Rust acronym casing · builtin shadowing · length · unclear abbreviations · exception suffixes · file names |
| **Agent** (SKILL.md workflow) | Misleading names (critical) · one concept with many verbs · missing units · wrong plurality · stale names after refactors · project conventions overriding defaults · safe rename plans |

Languages: Python (full `ast`), Go, Rust, JavaScript, TypeScript, Java,
POSIX sh / Bash. SQL, REST, GraphQL, env vars, CLI flags, IaC and file
naming are covered by a review reference.

## Install

**Claude Code**

```bash
cp -r skills/naming-analyzer ~/.claude/skills/
# or, from this marketplace
/plugin marketplace add thimslugga/agent-toolkit
/plugin install naming-analyzer@agent-toolkit
```

**claude.ai** — add the zipped skill folder as a custom skill, or add
`SKILL.md` and `references/` to project knowledge. No network access is needed.

## Use

Ask in plain language:

- "Review the naming in `src/billing/`"
- "What should I call this function?" (paste it)
- "Check Go naming conventions in `./internal`"
- "Rename the camelCase methods in `legacy/` to snake_case"

The agent runs the scanner, filters it through project rules and context,
reads the important code paths, and reports the few renames that matter
most, then offers to apply them with a semantic rename tool (gopls,
rust-analyzer, tsserver, rope).

## Run the scanner yourself

Python 3.9+, standard library only.

```bash
# JSON report (stdout); progress on stderr
python3 skills/naming-analyzer/scripts/naming-scan.py src/

# Compiler-style text, only minor and above
python3 skills/naming-analyzer/scripts/naming-scan.py src/ --format text --min-severity minor

# CI gate: exit 1 on any major finding, ignoring migrations
python3 skills/naming-analyzer/scripts/naming-scan.py . --fail-on major --exclude 'migrations/*'

# Stdin needs a language
git show HEAD:app/user.go | python3 skills/naming-analyzer/scripts/naming-scan.py - --lang go

# Rule table
python3 skills/naming-analyzer/scripts/naming-scan.py --list-rules
```

Example text output:

```text
app/user.py:1: minor N001 function 'getUser' Python function names use snake_case -> get_user (2 uses)
app/user.py:6: minor N003 variable 'data' 'data' says nothing about the domain; name what it holds or does (2 uses)
internal/user/service.go:3: minor N008 type 'UserId' Go initialisms keep a consistent case (ID, URL, HTTP, JSON) -> UserID (2 uses)
internal/user/service.go:3: minor N009 type 'UserId' Callers write user.UserId; drop the repeated package name -> ID (2 uses)
internal/user/service.go:5: minor N009 type 'UserService' Callers write user.UserService; drop the repeated package name -> Service (2 uses)
-- 2 files, 10 identifiers, 5 findings (minor=5)
```

Discovery honours `.gitignore` inside a git work tree and always skips
`node_modules`, `vendor`, `target`, virtualenvs, generated files
(`Code generated ... DO NOT EDIT.`, `@generated`), minified/bundled JS and
`.d.ts` files.

## Rules

| ID | Rule | Severity |
|---|---|---|
| N001 | case-style | minor |
| N002 | single-letter | major → info by scope and language |
| N003 | vague-name | major → info by kind |
| N004 | numbered-suffix | info |
| N005 | hungarian | minor |
| N006 | boolean-prefix | info |
| N007 | negated-boolean | minor |
| N008 | acronym-casing (Go, Rust) | minor |
| N009 | package-stutter (Go) | minor |
| N010 | shadows-builtin (Python, Go) | minor |
| N011 | too-long | info |
| N012 | unclear-abbreviation | minor |
| N013 | exception-suffix (Python) | info |
| N014 | file-name | minor (major for Java) |

`critical` is never emitted by the scanner; it is reserved for misleading
names the agent confirms. Full contract: [SPEC.md](SPEC.md).

## Calibration

Severities were tuned against idiomatic code: `net/http` and
`encoding/json` from the Go standard library and `json`, `http`,
`argparse` and `pathlib` from CPython. Each false positive found there is a
regression test. At `--min-severity minor` the scanner reports roughly one
finding per ~120 Go identifiers and one per ~20 Python identifiers in that
code, and what remains are real deviations (legacy stdlib names such as
`isReservedKey`) that the agent's context pass decides whether to keep.

## Layout

```text
naming-analyzer/
├── SKILL.md                 # agent workflow (loaded on demand)
├── SPEC.md                  # scanner contract
├── scripts/naming-scan.py   # the scanner (stdlib only)
├── references/              # loaded per language as needed
│   ├── python.md  go.md  rust.md  javascript-typescript.md  java.md  shell.md
│   ├── data-and-apis.md     # SQL, REST, GraphQL, env, CLI, IaC, files
│   ├── semantics.md         # judging and inventing names; misleading-name checklist
│   └── report-format.md
├── tests/                   # pytest suite, incl. stdlib regressions
└── pyproject.toml           # ruff / mypy / pytest config (dev only)
```

## Develop

Test-first: add a failing case to `tests/` (real-world false positives go in
`tests/test_regressions.py`), then change the scanner.

```bash
cd skills/naming-analyzer
uv run --with pytest --with pytest-cov pytest --cov=scripts
uvx ruff check . && uvx ruff format --check .
uvx mypy scripts/naming-scan.py
```
