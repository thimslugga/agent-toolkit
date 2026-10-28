"""Rust extraction and rules."""

from __future__ import annotations

from conftest import ScanFn, hits, rules

CLEAN = """
use std::collections::HashMap;

pub const MAX_RETRIES: u32 = 3;
static DEFAULT_NAME: &str = "x";

mod http_client {}

pub struct HttpServer {
    pub bind_address: String,
    is_running: bool,
}

pub enum Shape {
    Circle { radius: f64 },
    Square(f64),
    Empty,
}

pub trait Render<'a> {
    fn render(&self, out: &mut String);
}

impl HttpServer {
    pub fn start(&mut self, worker_count: usize) -> Result<(), String> {
        let mut seen = HashMap::new();
        for i in 0..worker_count {
            seen.insert(i, 'c');
        }
        let label = "fn bad_Name() {}";
        Ok(())
    }
}
"""


def test_clean_rust_has_no_findings(scan: ScanFn) -> None:
    assert scan(CLEAN, "rust") == []


def test_camel_fn_and_let(scan: ScanFn) -> None:
    code = "fn getUser(userId: u32) {\n    let mut retryCount = 0;\n}\n"
    found = scan(code, "rust")
    assert hits(found, "getUser", "N001")[0].suggestion == "get_user"
    assert hits(found, "userId", "N001")[0].kind == "parameter"
    assert hits(found, "retryCount", "N001")[0].suggestion == "retry_count"


def test_types_and_variants_pascal(scan: ScanFn) -> None:
    code = "struct user_repo;\nenum Color {\n    dark_red,\n    Blue,\n}\n"
    found = scan(code, "rust")
    assert hits(found, "user_repo", "N001")[0].suggestion == "UserRepo"
    v = hits(found, "dark_red", "N001")
    assert v and v[0].kind == "variant" and v[0].suggestion == "DarkRed"
    assert not hits(found, "Blue")


def test_const_must_be_screaming(scan: ScanFn) -> None:
    f = hits(scan("const maxRetries: u32 = 3;\n", "rust"), "maxRetries", "N001")
    assert f and f[0].suggestion == "MAX_RETRIES"


def test_rust_acronyms_are_words(scan: ScanFn) -> None:
    f = hits(scan("struct HTTPServer;\n", "rust"), "HTTPServer", "N008")
    assert f and f[0].suggestion == "HttpServer"


def test_struct_field_and_bool(scan: ScanFn) -> None:
    code = "struct Conn {\n    pub userName: String,\n    login: bool,\n}\n"
    found = scan(code, "rust")
    assert hits(found, "userName", "N001")[0].kind == "field"
    assert hits(found, "login", "N006")


def test_lifetimes_and_char_literals_do_not_break_lexing(scan: ScanFn) -> None:
    code = "fn first<'a>(s: &'a str) -> char {\n    let c = 'x';\n    let badName = 1;\n    c\n}\n"
    found = scan(code, "rust")
    assert "N001" in rules(found, "badName")
    assert not hits(found, "a")


def test_rust_file_name(scan: ScanFn) -> None:
    assert "N014" in rules(scan("fn ok() {}\n", "rust", "src/HttpServer.rs"), "HttpServer")
