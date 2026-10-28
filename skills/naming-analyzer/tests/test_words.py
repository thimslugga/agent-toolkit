"""Word splitting, style classification and conversion."""

from __future__ import annotations

from types import ModuleType

import pytest


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("getUser", ["get", "User"]),
        ("get_user", ["get", "user"]),
        ("HTTPServer", ["HTTP", "Server"]),
        ("parseHTTPResponse", ["parse", "HTTP", "Response"]),
        ("userID", ["user", "ID"]),
        ("MAX_RETRY_COUNT", ["MAX", "RETRY", "COUNT"]),
        ("__init__", ["init"]),
        ("_private_thing", ["private", "thing"]),
        ("sha256Sum", ["sha256", "Sum"]),
        ("user2", ["user2"]),
        ("my-func", ["my", "func"]),
    ],
)
def test_split_words(ns: ModuleType, name: str, words: list[str]) -> None:
    assert ns.split_words(name) == words


@pytest.mark.parametrize(
    ("name", "style"),
    [
        ("get_user", "snake"),
        ("getUser", "camel"),
        ("GetUser", "pascal"),
        ("MAX_RETRY", "upper_snake"),
        ("user", "lower"),
        ("URL", "upper"),
        ("Get_User", "mixed"),
        ("_private", "lower"),
        ("__dunder__", "lower"),
        ("x", "lower"),
        ("my-func", "kebab"),
    ],
)
def test_classify_style(ns: ModuleType, name: str, style: str) -> None:
    assert ns.classify_style(name) == style


@pytest.mark.parametrize(
    ("name", "style", "expected"),
    [
        ("getUserName", "snake", "get_user_name"),
        ("get_user_name", "camel", "getUserName"),
        ("get_user_name", "pascal", "GetUserName"),
        ("maxRetryCount", "upper_snake", "MAX_RETRY_COUNT"),
        ("HTTPServer", "snake", "http_server"),
        ("_privateValue", "snake", "_private_value"),
    ],
)
def test_convert(ns: ModuleType, name: str, style: str, expected: str) -> None:
    assert ns.convert(name, style) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("user_id", "userID"),
        ("UserId", "UserID"),
        ("parse_http_url", "parseHTTPURL"),
        ("MAX_RETRIES", "MaxRetries"),
        ("JsonApiClient", "JSONAPIClient"),
    ],
)
def test_go_mixed_caps(ns: ModuleType, name: str, expected: str) -> None:
    assert ns.go_name(name) == expected
