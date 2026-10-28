"""Shell and Java extraction and rules."""

from __future__ import annotations

from conftest import ScanFn, hits, rules

CLEAN_SH = """
#!/usr/bin/env bash
set -euo pipefail

readonly CONFIG_DIR="/etc/app"
export LOG_LEVEL=info
retry_count=3

log_info() {
  local message="$1"
  echo "${message}" >&2
}

function mylib::fetch_url {
  local url="$1"
  cat <<EOF
badName() { echo no; }
EOF
}

for i in 1 2 3; do echo "$i"; done
"""


def test_clean_shell(scan: ScanFn) -> None:
    assert scan(CLEAN_SH, "shell") == []


def test_shell_function_styles(scan: ScanFn) -> None:
    code = "fetchData() {\n  :\n}\nfunction my-helper {\n  :\n}\n"
    found = scan(code, "shell")
    assert hits(found, "fetchData", "N001")[0].suggestion == "fetch_data"
    f = hits(found, "my-helper", "N001")
    assert f and "POSIX" in f[0].message and f[0].suggestion == "my_helper"


def test_shell_local_and_readonly(scan: ScanFn) -> None:
    code = "go() {\n  local RetryCount=1\n}\nreadonly config_dir=/etc\nexport apiKey=x\n"
    found = scan(code, "shell")
    assert hits(found, "RetryCount", "N001")[0].suggestion == "retry_count"
    assert hits(found, "config_dir", "N001")[0].suggestion == "CONFIG_DIR"
    assert hits(found, "apiKey", "N001")[0].suggestion == "API_KEY"


def test_shell_camel_global(scan: ScanFn) -> None:
    assert "N001" in rules(scan("retryCount=3\n", "shell"), "retryCount")


CLEAN_JAVA = """
package com.example.users;

public class UserService {
    private static final int MAX_RETRIES = 3;
    private final HttpClient httpClient;
    private boolean isActive;

    public UserService(HttpClient httpClient) {
        this.httpClient = httpClient;
    }

    public Optional<User> findById(String userId) {
        for (int i = 0; i < MAX_RETRIES; i++) {
            if (userId == null) {
                return Optional.empty();
            }
        }
        return Optional.empty();
    }
}
"""


def test_clean_java(scan: ScanFn) -> None:
    assert scan(CLEAN_JAVA, "java", "UserService.java") == []


def test_java_rules(scan: ScanFn) -> None:
    code = (
        "package com.Example;\n"
        "class user_store {\n"
        "    static final int maxSize = 3;\n"
        "    private String user_name;\n"
        "    public void Save_All(String record_id) {}\n"
        "}\n"
    )
    found = scan(code, "java", "user_store.java")
    assert hits(found, "com.Example", "N001")
    assert hits(found, "user_store", "N001")[0].suggestion == "UserStore"
    assert hits(found, "maxSize", "N001")[0].suggestion == "MAX_SIZE"
    assert hits(found, "user_name", "N001")[0].kind == "field"
    assert hits(found, "Save_All", "N001")[0].kind == "method"
    assert hits(found, "record_id", "N001")[0].kind == "parameter"


def test_java_file_must_match_public_class(scan: ScanFn) -> None:
    code = "public class UserService {}\n"
    assert "N014" in rules(scan(code, "java", "Users.java"), "Users")
