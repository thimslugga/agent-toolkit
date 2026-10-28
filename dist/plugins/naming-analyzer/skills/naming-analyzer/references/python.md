# Python Naming

Source of truth: PEP 8 "Naming Conventions"; typing conventions from PEP 484
and the typing docs. Enforced by `ruff` rule group `N` (pep8-naming).

## Conventions

| Kind | Style | Example |
|---|---|---|
| Module | short `snake_case` (underscores discouraged but allowed) | `http_client.py` |
| Package | short lowercase, avoid underscores | `mypkg/` |
| Class | `CapWords` | `HttpClient`, `UserRepository` |
| Exception | `CapWords` + `Error` suffix if it is an error | `ConfigError` |
| Function, method, variable, parameter | `snake_case` | `load_config`, `retry_count` |
| Module-level constant | `UPPER_SNAKE_CASE` | `MAX_RETRIES = 3` |
| Type variable | short `CapWords`; `_co` / `_contra` for variance | `T`, `KT`, `T_co` |
| Type alias | `CapWords` | `UserId = NewType("UserId", int)` |
| Internal | one leading underscore | `_parse_header` |
| Name-mangled attribute | two leading underscores (rarely needed) | `self.__token` |
| Keyword clash | one trailing underscore | `class_`, `type_` |
| Dunder | reserved for the language | `__init__`, `__all__` |

Acronyms: PEP 8 capitalises all letters of an acronym in `CapWords`
(`HTTPServerError`), and the stdlib mixes both. Prefer whatever the project
already does.

## Idioms the scanner accepts

- `self`, `cls`, `mcs`; `_` for throwaways.
- `i`, `j`, `k`, `n`, `x`, `y`, `z`; `f` for a file handle (`with open(p) as f`),
  `m` for a regex match, `e` for a caught exception.
- unittest hooks `setUp`/`tearDown`, `ast.NodeVisitor.visit_ClassName`,
  `http.server` handlers `do_GET`.
- Module-level `CapWords` assignments are treated as type aliases.
- `UPPER_SNAKE` inside a function (local constant) and class attributes in
  `CapWords` (nested aliases) are allowed.

## Common fixes

```python
# Bad                                     # Good
def GetUser(userId): ...                  def get_user(user_id): ...
class user_repo: ...                      class UserRepo: ...
class Oops(Exception): ...                class OopsError(Exception): ...
default_timeout = 30   # module level     DEFAULT_TIMEOUT_SECONDS = 30
def go(list, id, type): ...               def go(items, user_id, kind): ...   # no builtin shadowing
str_name = ""                             name = ""                           # no Hungarian
is_not_valid = check()                    is_valid = check()
```

Properties are nouns or adjectives, not verbs: `@property def total(self)`,
not `def get_total(self)`. Predicates are `is_`/`has_` methods or properties.

## Linter mapping

| Scanner rule | ruff rule |
|---|---|
| N001 function / method | `N802` |
| N001 argument | `N803` |
| N001 class | `N801` |
| N001 variable in function | `N806` |
| N001 mixedCase in class / global scope | `N815`, `N816` |
| N013 exception suffix | `N818` |
| N010 builtin shadowing | `A001`–`A006` (flake8-builtins) |

Enable in `pyproject.toml`:

```toml
[tool.ruff.lint]
extend-select = ["N", "A"]

[tool.ruff.lint.pep8-naming]
ignore-names = ["setUp", "tearDown", "visit_*"]
```

```bash
uvx ruff check --select N,A src/
```
