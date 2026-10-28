"""Go extraction and rules."""

from __future__ import annotations

from conftest import ScanFn, hits, rules

CLEAN = """
package user

import "net/http"

// MaxRetries is fine: Go constants are MixedCaps.
const MaxRetries = 3

type Service struct {
    BaseURL    string
    httpClient *http.Client
    IsEnabled  bool
}

func (s *Service) FetchByID(ctx context.Context, userID string) (*Profile, error) {
    for i := 0; i < MaxRetries; i++ {
        _ = i
    }
    for _, v := range s.items {
        _ = v
    }
    resp, err := s.httpClient.Get(s.BaseURL)
    return nil, err
}

func TestFetch_notFound(t *testing.T) {}

func handle(w http.ResponseWriter, r *http.Request) {}
"""


def test_clean_go_has_no_findings(scan: ScanFn) -> None:
    assert scan(CLEAN, "go") == []


def test_snake_case_function_flagged(scan: ScanFn) -> None:
    f = hits(scan("package user\n\nfunc get_user_name() {}\n", "go"), "get_user_name", "N001")
    assert f and f[0].suggestion == "getUserName"


def test_upper_snake_constant_flagged(scan: ScanFn) -> None:
    f = hits(scan("package user\n\nconst MAX_RETRIES = 3\n", "go"), "MAX_RETRIES", "N001")
    assert f and f[0].suggestion == "MaxRetries"


def test_const_block_entries(scan: ScanFn) -> None:
    code = "package user\n\nconst (\n    DEFAULT_TTL = 5\n    okValue = 1\n)\n"
    found = scan(code, "go")
    assert hits(found, "DEFAULT_TTL", "N001")
    assert not hits(found, "okValue")


def test_initialisms(scan: ScanFn) -> None:
    code = "package user\n\ntype UserId string\n\nfunc parseUrl(rawJson string) {}\n"
    found = scan(code, "go")
    assert hits(found, "UserId", "N008")[0].suggestion == "UserID"
    assert hits(found, "parseUrl", "N008")[0].suggestion == "parseURL"
    assert hits(found, "rawJson", "N008")[0].suggestion == "rawJSON"


def test_package_stutter(scan: ScanFn) -> None:
    f = hits(scan("package user\n\ntype UserService struct{}\n", "go"), "UserService", "N009")
    assert f and f[0].suggestion == "Service"


def test_unexported_stutter_not_flagged(scan: ScanFn) -> None:
    assert not hits(scan("package user\n\ntype userCache struct{}\n", "go"), "userCache", "N009")


def test_package_name_rules(scan: ScanFn) -> None:
    found = scan("package user_store\n", "go", "store.go")
    assert "N001" in rules(found, "user_store")


def test_struct_fields_and_bool(scan: ScanFn) -> None:
    code = "package user\n\ntype T struct {\n    user_name string\n    Active, Deleted bool\n    Login bool\n}\n"
    found = scan(code, "go")
    assert hits(found, "user_name", "N001")[0].kind == "field"
    assert hits(found, "Login", "N006")
    assert not hits(found, "Active") and not hits(found, "Deleted")


def test_short_var_decl_and_params(scan: ScanFn) -> None:
    code = "package user\n\nfunc run(user_id string, count int) {\n    tmp_val := 1\n    d := 2\n}\n"
    found = scan(code, "go")
    assert hits(found, "user_id", "N001")[0].kind == "parameter"
    assert hits(found, "tmp_val", "N001")
    assert hits(found, "d", "N002")


def test_predeclared_shadowing(scan: ScanFn) -> None:
    code = "package user\n\nfunc run() {\n    len := 3\n    copy := 1\n}\n"
    found = scan(code, "go")
    assert "N010" in rules(found, "len") and "N010" in rules(found, "copy")


def test_strings_and_comments_ignored(scan: ScanFn) -> None:
    code = 'package user\n\n// func bad_name() {}\nvar okName = "func also_bad() {}"\nvar raw = `type bad_type int`\n'
    assert scan(code, "go") == []


def test_go_file_name(scan: ScanFn) -> None:
    assert "N014" in rules(scan("package user\n", "go", "UserStore.go"), "UserStore")
