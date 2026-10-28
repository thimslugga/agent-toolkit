"""Python extraction (ast) and rules."""

from __future__ import annotations

from conftest import ScanFn, hits, rules


def test_camel_function_flagged_with_snake_suggestion(scan: ScanFn) -> None:
    f = hits(scan("def getUserName(uid):\n    return uid\n", "python"), "getUserName", "N001")
    assert len(f) == 1
    assert f[0].kind == "function"
    assert f[0].suggestion == "get_user_name"
    assert f[0].line == 1


def test_clean_module_has_no_findings(scan: ScanFn) -> None:
    code = """
    MAX_RETRIES = 3

    class UserRepository:
        default_limit = 50

        def __init__(self, session):
            self.session = session

        def find_by_email(self, email_address: str) -> list[str]:
            return [row for row in self.session if row == email_address]

    def load_config(path):
        with open(path) as handle:
            return handle.read()
    """
    assert scan(code, "python") == []


def test_lowercase_class_flagged(scan: ScanFn) -> None:
    f = hits(scan("class user_repo:\n    pass\n", "python"), "user_repo", "N001")
    assert f and f[0].suggestion == "UserRepo" and f[0].kind == "class"


def test_dunder_self_cls_and_underscore_exempt(scan: ScanFn) -> None:
    code = """
    class Thing:
        def __repr__(self):
            return ""

        @classmethod
        def build(cls):
            _ = 1
            return cls()
    """
    assert scan(code, "python") == []


def test_unittest_hooks_and_visitors_exempt(scan: ScanFn) -> None:
    code = """
    class TestThing:
        def setUp(self):
            pass

        def tearDown(self):
            pass

    class Walker:
        def visit_FunctionDef(self, node):
            return node

        def do_GET(self):
            pass
    """
    assert scan(code, "python") == []


def test_module_pascal_assignment_is_type_alias(scan: ScanFn) -> None:
    code = "UserId = int\nPayload = dict[str, object]\nT = TypeVar('T')\n"
    assert scan(code, "python") == []


def test_inferred_module_constant_is_info(scan: ScanFn) -> None:
    f = hits(scan("default_timeout = 30\n", "python"), "default_timeout", "N001")
    assert f and f[0].severity == "info" and f[0].suggestion == "DEFAULT_TIMEOUT"


def test_single_letter_variable_flagged_but_loop_var_exempt(scan: ScanFn) -> None:
    code = """
    def total(items):
        t = 0
        for i in items:
            t += i
        return [x * 2 for x in items], (lambda y: y)
    """
    found = scan(code, "python")
    assert rules(found, "t") == {"N002"}
    assert not hits(found, "i") and not hits(found, "x") and not hits(found, "y")


def test_single_letter_function_is_major(scan: ScanFn) -> None:
    f = hits(scan("def f(items):\n    return items\n", "python"), "f", "N002")
    assert f and f[0].severity == "major"


def test_vague_names(scan: ScanFn) -> None:
    code = """
    def process(data):
        info = data
        return info
    """
    found = scan(code, "python")
    assert hits(found, "process", "N003")[0].severity == "major"
    assert hits(found, "data", "N003")[0].severity == "info"  # params carry a type
    assert hits(found, "info", "N003")[0].severity == "minor"  # locals: minor; functions/types: major


def test_vague_with_digits_reports_vague_not_numbered(scan: ScanFn) -> None:
    found = scan("def go():\n    tmp2 = 1\n    return tmp2\n", "python")
    assert rules(found, "tmp2") == {"N003"}


def test_numbered_suffix_and_technical_exemptions(scan: ScanFn) -> None:
    code = """
    def go():
        user2 = 1
        sha256 = 2
        ipv6 = 3
        return user2, sha256, ipv6
    """
    found = scan(code, "python")
    assert rules(found, "user2") == {"N004"}
    assert not hits(found, "sha256") and not hits(found, "ipv6")


def test_hungarian(scan: ScanFn) -> None:
    code = "def go():\n    str_name = ''\n    m_count = 0\n    return str_name, m_count\n"
    found = scan(code, "python")
    assert "N005" in rules(found, "str_name")
    assert "N005" in rules(found, "m_count")


def test_boolean_prefix_from_annotation_and_literal(scan: ScanFn) -> None:
    code = """
    def go(login: bool, verbose: bool = False, enable_cache=True):
        status = True
        is_ready = False
        user_authenticated = a > b
        return login, status
    """
    found = scan(code, "python")
    assert hits(found, "login", "N006")[0].severity == "info"
    assert hits(found, "status", "N006")
    assert not hits(found, "verbose") and not hits(found, "enable_cache")
    assert not hits(found, "is_ready") and not hits(found, "user_authenticated")


def test_negated_boolean(scan: ScanFn) -> None:
    found = scan("def go():\n    is_not_valid = False\n    return is_not_valid\n", "python")
    f = hits(found, "is_not_valid", "N007")
    assert f and f[0].severity == "minor"


def test_shadowing_builtins(scan: ScanFn) -> None:
    found = scan("def go(list, id):\n    type = 1\n    return type\n", "python")
    assert "N010" in rules(found, "list")
    assert "N010" in rules(found, "id")
    assert "N010" in rules(found, "type")


def test_too_long_but_test_functions_exempt(scan: ScanFn) -> None:
    long_name = "fetch_the_current_user_profile_from_remote_cache_now"
    code = f"def {long_name}():\n    pass\n\ndef test_{long_name}():\n    pass\n"
    found = scan(code, "python", "mod.py")
    assert rules(found, long_name) == {"N011"}
    assert not hits(found, f"test_{long_name}")
    assert not hits(scan(code, "python", "test_mod.py"), long_name)  # test files are exempt


def test_unclear_abbreviation_with_expansion(scan: ScanFn) -> None:
    f = hits(scan("def go():\n    usr_mgr = 1\n    return usr_mgr\n", "python"), "usr_mgr", "N012")
    assert f and f[0].suggestion == "user_manager"


def test_well_known_abbreviations_ok(scan: ScanFn) -> None:
    code = "def go(ctx, req, url, db_conn, html):\n    return ctx, req, url, db_conn, html\n"
    assert not [f for f in scan(code, "python") if f.rule == "N012"]


def test_exception_suffix(scan: ScanFn) -> None:
    code = "class Oops(Exception):\n    pass\n\nclass BadInputError(ValueError):\n    pass\n"
    found = scan(code, "python")
    assert hits(found, "Oops", "N013")[0].severity == "info"
    assert not hits(found, "BadInputError")


def test_self_attributes_are_fields_reported_once(scan: ScanFn) -> None:
    code = """
    class A:
        def __init__(self):
            self.userName = 1

        def reset(self):
            self.userName = 2
    """
    f = hits(scan(code, "python"), "userName", "N001")
    assert len(f) == 1 and f[0].kind == "field"


def test_python_module_file_name(scan: ScanFn) -> None:
    found = scan("x_value = None\n", "python", "src/UserRepo.py")
    assert "N014" in rules(found, "UserRepo")


def test_python_script_with_shebang_may_be_hyphenated(scan: ScanFn) -> None:
    assert not scan("#!/usr/bin/env python3\n", "python", "scripts/naming-scan.py")


def test_syntax_error_reported_not_raised(ns) -> None:  # type: ignore[no-untyped-def]
    result = ns.scan_source("def broken(:\n", "python", "bad.py")
    assert result.findings == []
    assert result.errors and "SyntaxError" in result.errors[0]
