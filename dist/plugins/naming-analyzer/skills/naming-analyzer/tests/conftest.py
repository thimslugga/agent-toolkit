"""Shared fixtures: load the hyphenated script as a module and scan helpers."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "naming-scan.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("naming_scan", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["naming_scan"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def ns() -> ModuleType:
    return _load()


ScanFn = Callable[..., list[Any]]


@pytest.fixture
def scan(ns: ModuleType) -> ScanFn:
    """scan(code, lang, path=...) -> list of findings (dedented source)."""

    def _scan(code: str, lang: str, path: str | None = None) -> list[Any]:
        default = {
            "python": "mod.py",
            "go": "user.go",
            "rust": "lib.rs",
            "javascript": "app.js",
            "typescript": "app.ts",
            "java": "Thing.java",
            "shell": "run.sh",
        }[lang]
        result = ns.scan_source(textwrap.dedent(code), lang, path or default)
        return list(result.findings)

    return _scan


def hits(findings: list[Any], name: str, rule: str | None = None) -> list[Any]:
    return [f for f in findings if f.name == name and (rule is None or f.rule == rule)]


def rules(findings: list[Any], name: str) -> set[str]:
    return {f.rule for f in findings if f.name == name}
