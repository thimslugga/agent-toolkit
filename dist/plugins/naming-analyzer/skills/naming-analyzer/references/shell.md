# Shell Naming (POSIX sh and Bash)

Source of truth: the Google Shell Style Guide ("Naming Conventions") and
POSIX (XCU 2.9.5 function definitions, XBD 8.1 environment variables).
ShellCheck does not lint naming; this scanner and review do.

## Conventions

| Kind | Style | Example |
|---|---|---|
| Function | `lower_snake_case`; `::` separates library namespaces | `log_info`, `mylib::fetch_url` |
| Local variable | `lower_snake_case`, declared with `local` | `local retry_count=3` |
| Script-internal global | `lower_snake_case` | `config_dir=/etc/app` |
| Constant, exported or environment variable | `UPPER_SNAKE_CASE`, declared near the top with `readonly` / `export` | `readonly CONFIG_DIR=/etc/app` |
| Loop variable | like other variables | `for file in "${files[@]}"` |
| Script file | lowercase with `_` or `-`; no extension for executables on `PATH` | `deploy_app`, `lib_utils.sh` |

## Why lowercase for internal variables

POSIX reserves uppercase names in practice: the standard utilities use
uppercase environment variables (`PATH`, `HOME`, `IFS`, `PWD`, `USER`,
`TMPDIR`), and XBD 8.1 notes that lowercase names are left to applications.
A script that writes `PATH=...` or `USER=...` by accident breaks things.

```sh
# Bad: clobbers the environment
USER=$(whoami); PATH=/opt/app

# Good
current_user=$(whoami); app_path=/opt/app
```

Uppercase locals (`local PACKAGE=$1`) are common in Debian tooling; the
scanner reports them at `info`, not `minor`.

## Portability: function names

POSIX function names must be valid *names*: `[A-Za-z_][A-Za-z0-9_]*`. Bash
accepts hyphens and dots (`my-func`, `lib.fn`) outside POSIX mode; `dash`,
`busybox sh` and `bash --posix` reject them.

```sh
my-helper() { :; }     # bash only
my_helper() { :; }     # POSIX ✓
```

`::` (Google style namespaces) is also a bash extension; use it only in
`#!/bin/bash` scripts.

## Common fixes

```bash
fetchData() { ... }               → fetch_data() { ... }
local RetryCount=1                → local retry_count=1
readonly config_dir=/etc          → readonly CONFIG_DIR=/etc
export apiKey=x                   → export API_KEY=x
tmp=$(mktemp)                     → work_dir=$(mktemp -d)        # name the role
```

## Renaming safely

There is no semantic rename tool for shell. Variables appear as `$name`,
`${name}`, `${name:-x}`, in `local`/`declare`, in `unset`, and inside
strings — so search before editing:

```bash
rg -n -w 'retryCount' scripts/
sed -i -E 's/\bretryCount\b/retry_count/g' scripts/deploy.sh   # only after reviewing the matches
shellcheck scripts/deploy.sh && git diff scripts/deploy.sh
```
