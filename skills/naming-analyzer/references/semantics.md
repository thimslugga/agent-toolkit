# Judging and Inventing Names

Read this for the semantic pass of a review and whenever you must propose a
name. Conventions (case, prefixes) live in the per-language references.

## Contents

1. A method for naming one thing
2. Scope decides length
3. Vocabulary: verbs, nouns, booleans, units
4. Misleading-name checklist (critical findings)
5. Consistency across a codebase
6. Worked examples

## 1. A method for naming one thing

1. **Say what it is in one sentence**, from the caller's point of view.
   "Returns the invoices for this customer that are past due."
2. **Take the head noun or verb** from that sentence: `overdue_invoices`,
   `find_overdue_invoices`.
3. **Delete words the context already supplies.** In `class Invoice`, a
   method is `is_overdue`, not `is_invoice_overdue`. In Go package `invoice`,
   the type is `invoice.Store`, not `invoice.InvoiceStore`.
4. **Add what the type cannot say**: units (`timeout_ms`), state
   (`unpaid_invoices`), source (`raw_body` vs `parsed_body`).
5. **Read it at the call site.** `if invoice.is_overdue(today):` reads as a
   sentence; `if check(inv, d):` does not.
6. **Search the codebase for the concept** and reuse its existing word.

If step 1 needs "and", the unit does two things. Say so instead of naming it
`validate_and_save_and_notify`; splitting it is the real fix.

## 2. Scope decides length

The further a name travels from its declaration, the more it must say.

| Scope | Good | Bad |
|---|---|---|
| 3-line loop or lambda | `i`, `x`, `k, v` | `currentIndexIntoUserArray` |
| Function body | `retries`, `deadline` | `r`, `d` |
| Module or package public API | `parse_duration`, `MaxRetries` | `pd`, `MR` |
| Process-wide (env var, config key, DB column) | `MYAPP_CACHE_TTL_SECONDS` | `TTL` |

Go makes this explicit: short names for short scopes are idiomatic, which is
why the scanner reports Go single-letter locals at `info`.

## 3. Vocabulary

### Verbs that promise different things

| Verb | Promise | Example |
|---|---|---|
| `get` | Cheap, local, no I/O, no mutation | `get_header(name)` |
| `fetch` / `load` | I/O (network / disk); may fail or be slow | `fetch_profile(user_id)` |
| `find` / `lookup` / `search` | May return nothing; signal it in the type | `find_user(...) -> User \| None` |
| `compute` / `calculate` | Pure but non-trivial work | `compute_checksum(data)` |
| `build` / `make` / `new` / `create` | Constructs; `create` usually persists | `create_order(...)` writes a row |
| `ensure` | Idempotent: makes it true if it is not | `ensure_dir(path)` |
| `parse` | Text/bytes to structure; may fail | `parse_config(text)` |
| `to_` / `as_` / `into_` | Conversion (Rust: `as_` free, `to_` costs, `into_` consumes) | `to_json()` |
| `validate` | Checks; raises or returns errors | `validate(order) -> list[Error]` |
| `is_valid` | Checks; returns bool, no side effects | `is_valid(order) -> bool` |
| `handle` / `process` / `manage` | Almost nothing; replace with the actual action | `process(order)` → `charge_order(order)` |

Language overrides: Go and Rust drop `get` on getters (`user.Name()`,
`user.name()`); Java keeps `getName()` by JavaBeans convention.

### Nouns

- **Collections are plural**: `users`, `user_ids`. Maps say both sides:
  `price_by_sku`, `usersByID`.
- **Counts say so**: `user_count` / `num_users`, never a bare `users` holding an int.
- **Avoid empty nouns**: `data`, `info`, `item`, `object`, `value`, `result`,
  `manager`, `helper`, `util`. They are fine only when the scope is tiny or
  the type says everything (`data []byte` in a decoder).
- **Classes and types are nouns**; interfaces with one method may be agent
  nouns (`Reader`, `Formatter`).

### Booleans

Make the true state obvious and positive.

```python
# Bad: noun, ambiguous, negated
login = user.authenticated
not_ready = queue.size() == 0
disable_cache = False

# Good
is_logged_in = user.authenticated
is_ready = queue.size() > 0
use_cache = True
```

`is_` state, `has_` possession, `can_` capability, `should_` decision,
`was_`/`did_` past events. Adjectives (`enabled`, `visible`, `dirty`) and
option flags (`verbose`, `dry_run`, `follow_symlinks`) are idiomatic too.
Negated names (`is_not_valid`, `no_retry`) force double negatives at call
sites: `if not is_not_valid`.

### Units and kinds

Put the unit in the name whenever the type does not carry it.

```go
// Bad
const Timeout = 30
func Retry(delay int)

// Good: or use time.Duration, which makes the unit part of the type
const TimeoutSeconds = 30
func Retry(delay time.Duration)
```

Same for sizes (`max_body_bytes`), money (`amount_cents`), rates
(`requests_per_second`), angles (`angle_rad`) and timestamps
(`created_at` UTC instant vs `created_on` date).

## 4. Misleading-name checklist (critical)

Report as `critical` only after reading the body. Each item names the
mismatch to look for.

| Name says | Code does | Fix direction |
|---|---|---|
| `get_x`, `x()` getter | Writes state, does I/O, or is expensive | `fetch_x`, `load_x`, `compute_x`; or remove the side effect |
| `is_x`, `has_x`, `can_x` | Returns a non-boolean, raises, or mutates | Return a bool; move the side effect out |
| Singular (`user`) | Holds a list, or a count | `users`, `user_count` |
| Plural (`items`) | Holds one element or a page cursor | `item`, `next_page_token` |
| `validate_x` | Also normalises or saves | Split, or `normalize_and_validate` |
| `x_id` | Holds the whole object | `x` |
| `sorted_x`, `unique_x` | Not sorted / not deduplicated | Fix the name or the code |
| `async`/`await`-free `fetch_x` | Reads a cache only | `cached_x` |
| `temp`, `old`, `new`, `v2` | Long-lived production state | Name the role |
| A name that matches a removed feature | Code after a refactor | Rename to current behaviour |

Example from the original version of this skill:

```javascript
// Critical: "get" promises a read; this writes.
function getUser(id) {
  const user = fetchUser(id);
  user.lastLogin = Date.now();
  saveUser(user);
  return user;
}

// Better: make the write visible, or separate it.
function fetchUserAndRecordLogin(id) { /* ... */ }
// or
const user = await fetchUser(id);
await recordLogin(user);
```

## 5. Consistency across a codebase

- **One concept, one word.** If the code says `fetch_user`, `get_account`,
  `load_invoice` and `retrieve_order` for the same kind of operation, pick
  one and report the rest as a group, not as four findings.
- **One word, one concept.** `session` meaning an HTTP session in one module
  and a DB session in another invites bugs; qualify both (`http_session`,
  `db_session`).
- **Mirror the domain.** Use the words the business uses (`policy`,
  `premium`, `claim`), not developer synonyms (`record`, `amount`, `request`).
- **Pairs are symmetric**: `open`/`close`, `start`/`stop`, `begin`/`end`,
  `acquire`/`release`, `source`/`destination` (or `src`/`dst`, never `src`/`target`).

Group consistency problems in the report under one heading with the chosen
word and the list of places to change.

## 6. Worked examples

```python
# Before
def calc(lst, f=False):
    tmp = 0
    for x in lst:
        tmp += x.amt
    return tmp * 1.2 if f else tmp


# After
VAT_RATE = 0.2


def order_total(line_items: list[LineItem], include_vat: bool = False) -> Decimal:
    subtotal = sum(item.amount for item in line_items)
    return subtotal * (1 + VAT_RATE) if include_vat else subtotal
```

```go
// Before (package user)
type UserService struct{ db *sql.DB }
func (s *UserService) GetUserById(id string) (*User, error)

// After: callers write user.Service and svc.ByID(id)
type Service struct{ db *sql.DB }
func (s *Service) ByID(id string) (*User, error)
```

```rust
// Before
struct HTTPClient { timeout: u64 }
fn get_body(self) -> Vec<u8> { /* consumes self */ }

// After: acronym as a word; unit in the name; into_ for consumption
struct HttpClient { timeout_ms: u64 }
fn into_body(self) -> Vec<u8> { /* ... */ }
```

```bash
# Before
proc() { local F=$1; tmp=$(wc -l < "$F"); echo $tmp; }

# After
count_lines() {
  local file="$1"
  local line_count
  line_count=$(wc -l < "${file}")
  echo "${line_count}"
}
```
