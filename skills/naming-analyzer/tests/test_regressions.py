"""False positives found by dogfooding on the Go and Python standard libraries.

Each case is idiomatic code from a real, well-reviewed codebase. If one of
these starts failing, the scanner has regressed toward noise.
"""

from __future__ import annotations

from conftest import ScanFn, hits

# -- Go ----------------------------------------------------------------------


def test_go_external_test_package_is_idiomatic(scan: ScanFn) -> None:
    assert not hits(scan("package http_test\n", "go", "client_test.go"), "http_test")


def test_go_test_files_allow_underscored_helpers(scan: ScanFn) -> None:
    code = "package http\n\nfunc testClientTimeout_Headers(t *testing.T) {}\nvar Export_writeStatusLine = writeStatusLine\n"
    assert scan(code, "go", "client_test.go") == []


def test_go_initialism_with_digits(ns) -> None:  # type: ignore[no-untyped-def]
    assert ns.go_name("setup_http2_conn") == "setupHTTP2Conn"


def test_go_acronym_rule_leaves_unknown_caps_alone(scan: ScanFn) -> None:
    code = "package json\n\nfunc scan(firstNonWS int, wantCT string, hasCE bool) {}\n"
    assert not [f for f in scan(code, "go") if f.rule == "N008"]


def test_go_acronym_rule_fixes_only_initialism_words(scan: ScanFn) -> None:
    f = hits(scan("package fcgi\n\nfunc read(reqId uint16) {}\n", "go"), "reqId", "N008")
    assert f and f[0].suggestion == "reqID"


def test_go_single_letters_are_info(scan: ScanFn) -> None:
    code = "package json\n\nfunc addrMarshalerEncoder(e *encodeState, v reflect.Value) {\n    c := 1\n}\n"
    found = scan(code, "go")
    assert {f.severity for f in found if f.rule == "N002"} == {"info"}


def test_go_n_prefix_counts_are_not_hungarian(scan: ScanFn) -> None:
    code = "package http\n\nfunc run() {\n    nBytes := 0\n    nRuns := 1\n}\n"
    assert not [f for f in scan(code, "go") if f.rule == "N005"]


def test_not_prefixed_non_booleans_are_not_negated_booleans(scan: ScanFn) -> None:
    code = "package http\n\nfunc NotFound(w ResponseWriter, r *Request) {}\n"
    assert not hits(scan(code, "go"), "NotFound", "N007")


def test_methods_named_do_or_run_get_meaning_from_receiver(scan: ScanFn) -> None:
    code = "package http\n\nfunc (c *Client) Do(req *Request) (*Response, error) {}\n"
    assert not hits(scan(code, "go"), "Do")


def test_test_file_names_are_not_too_long(scan: ScanFn) -> None:
    code = "package http\n\nfunc testTransportDoesNotLimitDelivered1xxResponses(t *testing.T) {}\n"
    assert not hits(scan(code, "go", "transport_test.go"), "testTransportDoesNotLimitDelivered1xxResponses")


def test_numbered_pairs_are_info(scan: ScanFn) -> None:
    code = "package http\n\nfunc run() {\n    body1 := 1\n    body2 := 2\n}\n"
    assert {f.severity for f in scan(code, "go") if f.rule == "N004"} == {"info"}


def test_unicode_identifiers_skip_case_rule(scan: ScanFn) -> None:
    assert not scan("package json\n\ntype T2 struct {\n    Aβ int\n    À int\n}\n", "go")


def test_past_tense_and_option_flags_are_booleans(scan: ScanFn) -> None:
    code = "package http\n\ntype response struct {\n    wroteHeader bool\n    escapeHTML bool\n}\n"
    assert not [f for f in scan(code, "go") if f.rule == "N006"]


# -- Python ------------------------------------------------------------------


def test_or_expression_is_not_boolean(scan: ScanFn) -> None:
    assert not hits(scan("def go(a, b):\n    name = a or b\n    return name\n", "python"), "name", "N006")


def test_imperative_keyword_flags(scan: ScanFn) -> None:
    code = (
        "def dump(obj, skipkeys=False, ensure_ascii=True, check_circular=True, sort_keys=False,"
        " follow_symlinks=True, branch_matches=False, in_class=False):\n    pass\n"
    )
    assert not [f for f in scan(code, "python") if f.rule == "N006"]


def test_enum_members_starting_with_not(scan: ScanFn) -> None:
    code = "class HTTPStatus(IntEnum):\n    NOT_FOUND = 404\n    NOT_MODIFIED = 304\n"
    assert not scan(code, "python")


def test_exception_class_not_flagged_as_negated(scan: ScanFn) -> None:
    found = scan("class NotConnected(HTTPException):\n    pass\n", "python")
    assert not hits(found, "NotConnected", "N007")


def test_single_uppercase_math_names_only_get_single_letter_rule(scan: ScanFn) -> None:
    found = scan("def lca(A, B):\n    M = len(A)\n    return M\n", "python")
    assert not [f for f in found if f.rule == "N001"]


def test_python_idiomatic_single_letters(scan: ScanFn) -> None:
    code = "def go(path):\n    with open(path) as f:\n        m = PATTERN.match(f.read())\n    return m\n"
    assert not [f for f in scan(code, "python") if f.rule == "N002"]


def test_function_local_upper_constants_and_class_pascal_aliases(scan: ScanFn) -> None:
    code = (
        "def parse():\n    TYPE_KEYVALUE = 1\n    return TYPE_KEYVALUE\n\n"
        "class Policy:\n    DomainStrict = 1\n    visit_FunctionDef = staticmethod(print)\n"
    )
    assert not [f for f in scan(code, "python") if f.rule == "N001"]


def test_vague_parameters_are_info(scan: ScanFn) -> None:
    found = scan("def unmarshal(data):\n    return data\n", "python")
    assert hits(found, "data", "N003")[0].severity == "info"


def test_ambiguous_abbreviations_not_expanded(scan: ScanFn) -> None:
    code = (
        "def go():\n    rec = 1\n    proc = 2\n    robots_txt = 3\n    col = 4\n    return rec, proc, robots_txt, col\n"
    )
    assert not [f for f in scan(code, "python") if f.rule == "N012"]


def test_single_letter_fields_in_tests_and_coordinates(scan: ScanFn) -> None:
    code = "package json\n\ntype point struct {\n    X, Y int\n    q int\n}\n"
    found = scan(code, "go", "bench_test.go")
    assert not hits(found, "X") and not hits(found, "Y")
    assert hits(found, "q", "N002")[0].severity == "info"
    assert hits(scan(code, "go", "point.go"), "q", "N002")[0].severity == "minor"


# -- JavaScript / shell -------------------------------------------------------


def test_commonjs_class_imports_may_be_pascal(scan: ScanFn) -> None:
    code = "var Parser = require('./parser');\nlet Lexer = require('./lexer');\n"
    assert scan(code, "javascript") == []


def test_shell_uppercase_locals_are_info(scan: ScanFn) -> None:
    found = scan('finish() {\n  local PACKAGE="$1"\n}\n', "shell")
    assert hits(found, "PACKAGE", "N001")[0].severity == "info"


def test_java_mutable_static_finals_are_not_constants(scan: ScanFn) -> None:
    code = (
        "public class Svc {\n"
        "    private static final Logger logger = Logger.getLogger(Svc.class.getName());\n"
        "    private static final Set<String> mutableNames = new HashSet<>();\n"
        '    private static final Logger LOG = Logger.getLogger("x");\n'
        "    private static final int maxSize = 3;\n"
        "}\n"
    )
    found = scan(code, "java", "Svc.java")
    assert not hits(found, "logger") and not hits(found, "mutableNames") and not hits(found, "LOG")
    assert hits(found, "maxSize", "N001")


def test_stutter_suggestion_applies_initialisms(scan: ScanFn) -> None:
    f = hits(scan("package user\n\ntype UserId string\n", "go"), "UserId", "N009")
    assert f and f[0].suggestion == "ID"
