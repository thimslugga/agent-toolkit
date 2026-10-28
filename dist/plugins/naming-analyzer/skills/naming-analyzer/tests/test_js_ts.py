"""JavaScript and TypeScript extraction and rules."""

from __future__ import annotations

from conftest import ScanFn, hits

CLEAN_JS = """
const API_URL = 'https://example.com';
const defaultTimeout = 30;

export class UserService {
  #cache = new Map();

  constructor(httpClient) {
    this.httpClient = httpClient;
  }

  async fetchUser(userId) {
    if (userId) {
      return this.httpClient.get(`${API_URL}/users/${userId}`);
    }
    for (let i = 0; i < 3; i++) {}
    for (const entry of this.#cache) {}
  }
}

function formatName(firstName, lastName) {
  const isEmpty = !firstName;
  return isEmpty ? lastName : `${firstName} ${lastName}`;
}

const toUpper = (value) => value.toUpperCase();
const $root = document.body;
"""


def test_clean_js(scan: ScanFn) -> None:
    assert scan(CLEAN_JS, "javascript") == []


def test_snake_function_and_variable(scan: ScanFn) -> None:
    code = "function get_user(user_id) {\n  let retry_count = 0;\n}\n"
    found = scan(code, "javascript")
    assert hits(found, "get_user", "N001")[0].suggestion == "getUser"
    assert hits(found, "user_id", "N001")[0].kind == "parameter"
    assert hits(found, "retry_count", "N001")


def test_arrow_function_kind(scan: ScanFn) -> None:
    f = hits(scan("const fetch_all = async (x) => x;\n", "javascript"), "fetch_all", "N001")
    assert f and f[0].kind == "function"


def test_lowercase_class(scan: ScanFn) -> None:
    f = hits(scan("class userStore {}\n", "javascript"), "userStore", "N001")
    assert f and f[0].suggestion == "UserStore"


def test_pascal_components_allowed_in_jsx(scan: ScanFn) -> None:
    code = "function UserCard(props) {\n  return null;\n}\nconst NavBar = () => null;\n"
    assert scan(code, "javascript", "Card.jsx") == []
    assert hits(scan(code, "javascript", "card.js"), "UserCard", "N001")


def test_control_flow_not_mistaken_for_methods(scan: ScanFn) -> None:
    code = "class Runner {\n  run() {\n    if (x) {}\n    while (y) {}\n    switch (z) {}\n  }\n}\n"
    assert scan(code, "javascript") == []


def test_js_boolean_literal(scan: ScanFn) -> None:
    found = scan("let loading = true;\nlet isOpen = false;\n", "javascript")
    assert not hits(found, "loading")  # -ing adjective-ish states are accepted
    assert not hits(found, "isOpen")
    assert hits(scan("let status = false;\n", "javascript"), "status", "N006")


def test_ts_interfaces_types_enums(scan: ScanFn) -> None:
    code = (
        "interface IUser { name: string }\n"
        "type user_id = string;\n"
        "enum color { Red }\n"
        "function check(login: boolean): void {}\n"
    )
    found = scan(code, "typescript")
    assert hits(found, "IUser", "N005")[0].severity == "info"
    assert hits(found, "user_id", "N001")[0].suggestion == "UserId"
    assert hits(found, "color", "N001")
    assert hits(found, "login", "N006")


def test_ts_typed_params_and_methods(scan: ScanFn) -> None:
    code = (
        "class Repo {\n  private async find_by_id<T>(record_id: string): Promise<T> {\n    return null as T;\n  }\n}\n"
    )
    found = scan(code, "typescript")
    assert hits(found, "find_by_id", "N001")[0].kind == "method"
    assert hits(found, "record_id", "N001")


def test_template_literals_and_regex_ignored(scan: ScanFn) -> None:
    code = "const msg = `function bad_one() {}`;\n// const bad_two = 1;\n"
    assert scan(code, "javascript") == []
