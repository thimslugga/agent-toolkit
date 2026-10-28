# Go Naming

Source of truth: Effective Go ("Names"), Go Code Review Comments
("Initialisms", "Receiver Names", "Package Names", "Variable Names"), and
the Go blog post "Package names". Enforced by `revive` (`var-naming`,
`receiver-naming`, `exported`) and `staticcheck` (`ST1003`, `ST1016` — both
off by default; enable them explicitly).

## Conventions

| Kind | Style | Example |
|---|---|---|
| Package | short, lowercase, one word, no `_` or mixedCaps | `package httputil` |
| Exported identifier | `MixedCaps` | `ParseDuration`, `MaxRetries` |
| Unexported identifier | `mixedCaps` | `parseHeader`, `maxRetries` |
| Constant | `MixedCaps` — **not** `UPPER_SNAKE` | `const DefaultPort = 8080` |
| Initialism | consistent case for the whole initialism | `userID`, `ServeHTTP`, `parseURL`, `xmlHTTPRequest` |
| Interface (one method) | method name + `-er` | `Reader`, `Stringer`, `Closer` |
| Error variable | `Err` prefix | `var ErrNotFound = errors.New("not found")` |
| Error type | `Error` suffix | `type ParseError struct{...}` |
| Receiver | 1–2 letters, consistent, never `this`/`self` | `func (c *Client) Do(...)` |
| Getter / setter | `Owner()` / `SetOwner()` — no `Get` | `u.Name()` |
| Test function | `TestXxx`, `BenchmarkXxx`, `ExampleXxx`, `FuzzXxx`; `_` allowed | `TestParse_emptyInput` |
| External test package | `<pkg>_test` | `package http_test` |
| File | lowercase, `_` allowed | `server_conn.go` |

**File-name suffixes are build constraints.** `_test.go`, `_linux.go`,
`_windows_amd64.go` decide what compiles. Never propose renaming a file
into or out of such a suffix by accident.

## Avoid stutter

Callers always write the package name, so do not repeat it:

```go
// package user
type UserService struct{}     // callers write user.UserService
type Service struct{}         // callers write user.Service      ✓

// package bufio
func NewBufReader() {}        // bufio.NewBufReader
func NewReader() {}           // bufio.NewReader                 ✓
```

## Short names in short scopes

Go style prefers `c` over `lineCount` *when the scope is a few lines*, and
descriptive names as distance from the declaration grows. That is why the
scanner reports Go single-letter locals at `info`. Judge by scope length:

```go
for i, v := range values { sum += v * weights[i] }   // fine

func (s *Server) handle(w http.ResponseWriter, r *http.Request) {
    // 80 lines later, `u` is unreadable: name it `currentUser`.
}
```

Idiomatic single letters the scanner allows: `i j k n x y z`, `t *testing.T`,
`b *testing.B`, `w http.ResponseWriter`, `r *http.Request`, `f *os.File`.

## Common initialisms

`ACL API ASCII CPU CSS DNS EOF GUID HTML HTTP HTTPS ID IP JSON QPS RAM RPC SLA
SMTP SQL SSH TCP TLS TTL UDP UI UID UUID URI URL UTF8 VM XML XMPP XSRF XSS`

```go
userId   → userID          // N008
parseUrl → parseURL
HttpPort → HTTPPort
Json     → JSON            // exported
json     → json            // unexported leading word stays lowercase
```

## Common fixes

```go
func get_user_name() {}          → func getUserName() {}
const MAX_RETRIES = 3            → const MaxRetries = 3
type UserId string               → type UserID string
func (this *Server) Start()      → func (s *Server) Start()
func (s *Store) GetUser(id) {}   → func (s *Store) User(id) {}   // when it is a cheap accessor
len := 3                         → n := 3                         // N010: shadows the builtin
```

## Linter setup

```yaml
# .golangci.yml (golangci-lint v2 format; v1 used a top-level `linters-settings:`)
version: "2"
linters:
  enable: [revive, staticcheck]
  settings:
    revive:
      rules:
        - name: var-naming
        - name: receiver-naming
        - name: exported
    staticcheck:
      checks: ["all", "-ST1000"]   # ST1003/ST1016 naming checks are not in the default set
```

```bash
golangci-lint run ./...
gopls rename -w internal/user/service.go:#123 Service   # semantic rename at byte offset
```
