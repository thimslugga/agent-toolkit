"""Defects found by independent review; each was reproduced before being pinned here."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import SCRIPT, ScanFn, hits

# -- severity contract --------------------------------------------------------


def test_vague_rule_skips_variants_and_constants(scan: ScanFn) -> None:
    assert not scan("enum Level {\n    Info,\n    Object,\n}\n", "rust")
    assert not [f for f in scan("INFO = 20\n", "python") if f.rule == "N003"]


def test_vague_methods_and_properties_only_empty_words(scan: ScanFn) -> None:
    code = "class Resp:\n    @property\n    def data(self):\n        return 1\n\n    def foo(self):\n        pass\n"
    found = scan(code, "python")
    assert not hits(found, "data")
    assert hits(found, "foo", "N003")[0].severity == "minor"


def test_inferred_single_letter_module_constant_is_minor(scan: ScanFn) -> None:
    assert hits(scan("x = 5\n", "python"), "x", "N002")[0].severity == "minor"


def test_no_op_is_not_a_negation(scan: ScanFn) -> None:
    assert not hits(scan("def go():\n    is_no_op = True\n    return is_no_op\n", "python"), "is_no_op", "N007")


# -- lexing / extraction ------------------------------------------------------


def test_shell_arithmetic_shift_is_not_heredoc(scan: ScanFn) -> None:
    assert hits(scan("x=$(( 1 << n ))\nbadName() { :; }\n", "shell"), "badName", "N001")


def test_go_generic_type_params(scan: ScanFn) -> None:
    found = scan("package p\n\nfunc Bad_name[S ~[]E, E any](s S, user_id int) {}\n", "go")
    assert hits(found, "Bad_name", "N001") and hits(found, "user_id", "N001")


def test_go_var_block_composite_literal_keys_are_not_vars(ns) -> None:  # type: ignore[no-untyped-def]
    code = 'package p\n\nvar (\n    cfg = Config{\n        Name_x: "x",\n    }\n)\n'
    names = {i.name for i in ns.scan_source(code, "go", "p.go").identifiers}
    assert "cfg" in names and "Name_x" not in names


def test_go_channel_direction_params(scan: ScanFn) -> None:
    found = scan("package p\n\nfunc run(jobs <-chan int, results chan<- int, bad_name int) {}\n", "go")
    assert hits(found, "bad_name", "N001")


def test_rust_fn_trait_bound_arrow(scan: ScanFn) -> None:
    assert hits(scan("fn apply<F: Fn(i32) -> i32>(f: F, badName: i32) {}\n", "rust"), "badName", "N001")


def test_java_text_block_is_a_string(scan: ScanFn) -> None:
    code = 'class Box {\n    String text = """\n        int bad_name = 1;\n        """;\n}\n'
    assert not hits(scan(code, "java", "Box.java"), "bad_name")


def test_java_allman_braces(scan: ScanFn) -> None:
    code = "class Box\n{\n    static final int MAX_SIZE = 3;\n    private int user_id;\n}\n"
    found = scan(code, "java", "Box.java")
    assert not hits(found, "MAX_SIZE")
    assert hits(found, "user_id", "N001")[0].kind == "field"


def test_bom_is_ignored(scan: ScanFn) -> None:
    assert hits(scan("﻿def getX():\n    pass\n", "python"), "getX", "N001")
    assert hits(scan("﻿package user\n\ntype UserService struct{}\n", "go"), "UserService", "N009")


def test_js_regex_literal_with_quotes(scan: ScanFn) -> None:
    code = "const re = /`/g;\nconst quote = /'/;\nfunction bad_name() {}\nconst ratio = a / b / c;\n"
    assert hits(scan(code, "javascript"), "bad_name", "N001")


def test_js_multiple_declarators(scan: ScanFn) -> None:
    found = scan("let a_b, c_d;\nconst e_f = 1, g_h = 2;\n", "javascript")
    assert {f.name for f in found if f.rule == "N001"} == {"a_b", "c_d", "e_f", "g_h"}


def test_shell_multiple_exports(scan: ScanFn) -> None:
    found = scan("export A_B=1 c_d=2\nlocal_fn() {\n  local x_y z_w\n}\n", "shell")
    assert hits(found, "c_d", "N001")


# -- CLI ----------------------------------------------------------------------


def _run(*args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, input=stdin, check=False)


def test_missing_path_is_a_usage_error() -> None:
    assert _run("/definitely/not/here", "--fail-on", "major").returncode == 2


def test_invalid_utf8_stdin_does_not_crash() -> None:
    proc = _run("-", "--lang", "python", stdin=b'x = "\xff"\ndef getX():\n    pass\n')
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["findings"]


def test_summary_counts_are_pre_truncation(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("".join(f"def badName{i}():\n    pass\n" for i in range(10)))
    report = json.loads(_run(str(tmp_path), "--max-findings", "3", "--min-severity", "minor").stdout)
    assert report["summary"]["findings"] == 10 and len(report["findings"]) == 3


def test_test_detection_ignores_ancestors_of_the_scan_root(tmp_path: Path) -> None:
    root = tmp_path / "tests" / "project"
    root.mkdir(parents=True)
    (root / "app.py").write_text("def foo():\n    pass\n")
    report = json.loads(_run(str(root)).stdout)
    assert report["findings"][0]["severity"] == "major"  # not downgraded as a test file


def test_git_mode_keeps_tracked_build_packages(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "plan.go").write_text("package build\n\nfunc bad_name() {}\n")
    report = json.loads(_run(str(tmp_path)).stdout)
    assert any(f["name"] == "bad_name" for f in report["findings"])


# -- performance --------------------------------------------------------------

LONG_LINES = {
    "go": "package p\nvar x = []int{" + ", ".join(["a"] * 40000) + "}\n",
    "rust": "fn f() { let r = 1; }\n" * 20000,
    "javascript": "const x = [" + ", ".join(["a"] * 40000) + "];\n",
    "typescript": "const x: number[] = [" + ", ".join(["a"] * 40000) + "];\n",
    "java": "class Big {\n int[] x = {" + ", ".join(["1"] * 40000) + "};\n}\n",
    "shell": "arr=(" + " ".join(["a"] * 40000) + ")\n",
    "python": "x = [" + ", ".join(["a"] * 40000) + "]\n",
}


@pytest.mark.parametrize("lang", sorted(LONG_LINES))
def test_long_lines_are_linear(ns, lang: str) -> None:  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    ns.scan_source(LONG_LINES[lang], lang, "big")
    assert time.perf_counter() - start < 5.0
