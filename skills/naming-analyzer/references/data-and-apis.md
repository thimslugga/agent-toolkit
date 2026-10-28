# Names Outside Code: Data, APIs, Files and Config

The scanner does not parse these; review them by reading. Consistency within
one system matters more than any table below, and external contracts (a
published API, a shared schema) are expensive to rename — propose additive
changes and deprecations.

## SQL schemas

| Element | Convention | Example |
|---|---|---|
| Table | `snake_case`; pick singular *or* plural and keep it | `order_item` / `order_items` |
| Column | `snake_case` | `created_at` |
| Primary key | `id` | `id` |
| Foreign key | `<referenced_table_singular>_id` | `customer_id` |
| Boolean | `is_` / `has_` | `is_active` |
| Timestamp | `_at` for instants (UTC), `_on` / `_date` for dates | `deleted_at`, `due_on` |
| Index | `idx_<table>_<columns>` | `idx_orders_customer_id` |
| Unique / FK / check constraint | `uq_` / `fk_` / `ck_` prefixes | `fk_orders_customer_id` |
| Money | integer minor units + currency column | `amount_cents`, `currency` |

PostgreSQL folds unquoted identifiers to lowercase, so `CustomerID` becomes
`customerid` unless quoted everywhere. Use `snake_case` and never quote.
Avoid reserved words (`user`, `order`, `group`) as table names.

## REST and HTTP

| Element | Convention | Example |
|---|---|---|
| Path segment | plural nouns, `kebab-case` | `/v1/payment-methods/{id}` |
| Action that is not CRUD | sub-resource or verb suffix, used sparingly | `POST /v1/orders/{id}/cancel` |
| Query parameter | match the body field style | `?page_size=50` or `?pageSize=50` |
| JSON field | `camelCase` (Google JSON style) or `snake_case` (GitHub, Stripe) — one per API | `createdAt` |
| Header | `Title-Case`, no `X-` prefix for new headers (RFC 6648) | `Idempotency-Key` |

## GraphQL

Types, interfaces, unions, inputs: `PascalCase`. Fields, arguments:
`camelCase`. Enum values: `SCREAMING_SNAKE_CASE`. Inputs end in `Input`
(`CreateUserInput`); mutations are verb-first (`createUser`).

## Environment variables and config keys

- `UPPER_SNAKE_CASE`, prefixed with the application: `MYAPP_DATABASE_URL`.
- Units in the name: `MYAPP_HTTP_TIMEOUT_SECONDS`, `MYAPP_MAX_BODY_BYTES`.
- Booleans as positive switches: `MYAPP_ENABLE_METRICS=true`, not `MYAPP_NO_METRICS`.
- Config file keys follow the file format's ecosystem: YAML/TOML usually
  `snake_case` or `kebab-case` (one style per file); Kubernetes manifests `camelCase`.

## CLI flags

GNU style: long options in `kebab-case` (`--dry-run`, `--output-dir`),
negation as `--no-<flag>`, short options single letters for the common
ones only (`-v`, `-o`). Subcommands are verbs (`app deploy`, `app logs`).

## Infrastructure as code

| Tool | Convention | Example |
|---|---|---|
| Terraform resource / variable / output | `snake_case`; no resource type in the name | `aws_s3_bucket.logs`, not `.logs_bucket` |
| Ansible variable | `snake_case`, prefixed with the role name (`ansible-lint` `var-naming`) | `nginx_worker_processes` |
| Kubernetes object | DNS-1123: lowercase alphanumerics and `-`, max 63 for labels / 253 for most names | `payment-api` |
| Kubernetes label key | `prefix/name`, reverse-DNS prefix for your own | `app.kubernetes.io/name` |
| Container image | lowercase, `-` / `_` / `.` separators | `ghcr.io/acme/payment-api` |
| AWS tags | `PascalCase` keys are common (`CostCenter`); be consistent | `Environment=prod` |

## Files and directories

| Ecosystem | Convention |
|---|---|
| Python | modules `snake_case.py`; executable scripts may use `-` (they are not imported) |
| Go | lowercase, `_` allowed; `_test`, `_<os>`, `_<arch>` suffixes are build constraints |
| Rust | `snake_case.rs`; `mod.rs` or `<module>.rs` |
| Java | file = public type name: `UserService.java` |
| JS/TS | project choice: `kebab-case.ts` or `PascalCase.tsx` for components |
| Shell | lowercase; `.sh` for libraries, no extension for commands on `PATH` |
| Docs and config | lowercase `kebab-case` (`getting-started.md`), except conventional upper-case files (`README.md`, `LICENSE`, `CHANGELOG.md`, `Makefile`, `Dockerfile`) |

Directory names follow the language's package rules where they become
import paths (Go, Python, Java); elsewhere `kebab-case` is the safe default
because it survives case-insensitive filesystems and URLs.
