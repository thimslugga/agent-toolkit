# Rust Naming

Source of truth: Rust API Guidelines — C-CASE (casing), C-CONV (conversion
names), C-GETTER, C-ITER, C-FEATURE — and RFC 430. `rustc` warns via
`non_snake_case`, `non_camel_case_types`, `non_upper_case_globals`; Clippy
adds style and pedantic naming lints.

## Conventions

| Kind | Style | Example |
|---|---|---|
| Crate | `snake_case` (Cargo may use `kebab-case`; it maps to `_`) | `serde_json` |
| Module, function, method, local, field, macro | `snake_case` | `fn parse_header`, `mod http_client` |
| Type, trait, enum, enum variant | `UpperCamelCase` | `HttpServer`, `Shape::Circle` |
| `const` / `static` | `SCREAMING_SNAKE_CASE` | `const MAX_RETRIES: u32 = 3;` |
| Type parameter | concise `UpperCamelCase`, usually one letter | `T`, `K`, `V`, `E` |
| Lifetime | short lowercase | `'a`, `'de`, `'src` |
| Feature flag | plain name, no `use-` / `with-` prefix | `std`, `serde` |

**Acronyms are one word** in `UpperCamelCase` (`Uuid`, `Usize`, `Stdin`,
`HttpServer`) and lowercase in `snake_case` (`is_xid_start`). This is the
opposite of Go. Clippy `upper_case_acronyms` enforces it, but by default only
for fully capitalised names (`HTTP`); set `upper-case-acronyms-aggressive = true`
in `clippy.toml` to also catch `HTTPServer`.

## Method name conventions

| Prefix | Cost | Ownership | Example |
|---|---|---|---|
| `as_` | free | borrowed → borrowed | `str::as_bytes` |
| `to_` | expensive | borrowed → owned (or copy) | `str::to_lowercase` |
| `into_` | variable | owned → owned (consumes `self`) | `String::into_bytes` |
| (none) | getter | `&self` → field | `fn name(&self) -> &str`, not `get_name` |
| `iter`, `iter_mut`, `into_iter` | — | iterators over `&T`, `&mut T`, `T` | `vec.iter()` |
| `try_` | fallible variant | — | `try_from`, `try_reserve` |
| `with_` | constructor variant | — | `Vec::with_capacity` |
| `is_`, `has_` | predicate | — | `is_empty` |

`get` without a suffix is reserved for indexed or keyed access
(`HashMap::get`, `slice::get`).

## Common fixes

```rust
fn getUser(userId: u32)           → fn user(user_id: u32)
struct user_repo;                 → struct UserRepo;
enum Color { dark_red }           → enum Color { DarkRed }
const maxRetries: u32 = 3;        → const MAX_RETRIES: u32 = 3;
struct HTTPServer;                → struct HttpServer;            // N008
fn to_body(self) -> Vec<u8>       → fn into_body(self) -> Vec<u8> // consumes self
mod my_mod { pub struct MyModConfig; } → pub struct Config;       // module_name_repetitions
```

## Clippy lints worth enabling

| Lint | Group | Catches |
|---|---|---|
| `upper_case_acronyms` | style | `HTTP`; `HTTPServer` with `upper-case-acronyms-aggressive` |
| `wrong_self_convention` | style | `to_*` taking `self`, `into_*` taking `&self` |
| `enum_variant_names` | style | variants repeating the enum name |
| `module_name_repetitions` | pedantic | `config::ConfigLoader` |
| `many_single_char_names` | pedantic | functions full of `a, b, c, d` |
| `similar_names` | pedantic | `lhs` vs `rhs`-style near-collisions |

```bash
cargo clippy -- -W clippy::pedantic -A clippy::must_use_candidate
```

Rename with rust-analyzer (LSP "Rename Symbol"), then `cargo check && cargo test`.
