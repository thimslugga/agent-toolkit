#!/usr/bin/env python3
"""naming-scan: deterministic identifier-naming checks for the naming-analyzer skill.

Extracts declared identifiers from Python (via ``ast``), Go, Rust,
JavaScript/TypeScript, Java and shell (via comment/string-aware lexical
scanning) and reports mechanical naming problems: case style, single letters,
vague words, numbered suffixes, Hungarian notation, boolean prefixes, acronym
casing, package stutter, builtin shadowing, length, abbreviations, exception
suffixes and file names.

Semantic problems (a name that lies about what the code does) are out of
scope: the agent judges those by reading the code. See SPEC.md.

Standard library only, Python 3.9+. JSON to stdout, diagnostics to stderr.

Usage:
    naming-scan.py [PATH ...] [--format json|text] [--lang LANG]
                   [--exclude GLOB] [--min-severity LEVEL] [--fail-on LEVEL]
                   [--max-findings N] [--list-rules]
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VERSION = 1

SEVERITIES = ("info", "minor", "major", "critical")
SEV_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}

RULES: dict[str, tuple[str, str]] = {
    "N001": ("case-style", "Identifier does not follow the language convention for its kind"),
    "N002": ("single-letter", "Single-letter name outside a loop, lambda or idiomatic slot"),
    "N003": ("vague-name", "Name carries no domain meaning (data, info, tmp, process, Manager...)"),
    "N004": ("numbered-suffix", "Trailing digits distinguish names instead of meaning (user2)"),
    "N005": ("hungarian", "Type or scope encoded in the name (strName, m_count, IUser)"),
    "N006": ("boolean-prefix", "Boolean without a predicate form (is/has/can/should...)"),
    "N007": ("negated-boolean", "Negated boolean invites double negatives (isNotValid)"),
    "N008": ("acronym-casing", "Acronym casing against language convention (Go: UserID; Rust: HttpServer)"),
    "N009": ("package-stutter", "Exported Go name repeats its package (user.UserService)"),
    "N010": ("shadows-builtin", "Shadows a builtin or predeclared identifier"),
    "N011": ("too-long", "Longer than 40 characters or 6 words"),
    "N012": ("unclear-abbreviation", "Abbreviation that obscures the word (usr, mgr, cnt)"),
    "N013": ("exception-suffix", "Exception class name should end in Error/Exception/Warning"),
    "N014": ("file-name", "File name breaks the language convention"),
}

LANGUAGES = ("python", "go", "rust", "javascript", "typescript", "java", "shell")
LANG_ALIASES = {
    "py": "python",
    "golang": "go",
    "rs": "rust",
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "sh": "shell",
    "bash": "shell",
}
EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".go": "go",
    ".rs": "rust",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".sh": "shell",
    ".bash": "shell",
    ".ksh": "shell",
}
SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "target",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".next",
    }
)
MAX_FILE_BYTES = 1 << 20

# --------------------------------------------------------------------------- #
# Word handling
# --------------------------------------------------------------------------- #

_WORD_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+[0-9]*|[A-Z]+[0-9]*|[0-9]+")
_LEADING = re.compile(r"^[_$#]+")


def _core(name: str) -> str:
    return _LEADING.sub("", name).rstrip("_")


def split_words(name: str) -> list[str]:
    """Split an identifier into words across case, underscores, hyphens, ``::`` and dots."""
    words: list[str] = []
    for part in re.split(r"[_\-.]+|::", name):
        if part:
            words.extend(_WORD_RE.findall(part))
    return words


def classify_style(name: str) -> str:
    """Return one of lower, upper, snake, upper_snake, camel, pascal, kebab, mixed."""
    core = _core(name)
    if not core:
        return "lower"
    if "-" in core:
        return "kebab"
    patterns = (
        ("lower", r"[a-z][a-z0-9]*"),
        ("upper", r"[A-Z][A-Z0-9]*"),
        ("snake", r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+"),
        ("upper_snake", r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+"),
        ("camel", r"[a-z][a-zA-Z0-9]*"),
        ("pascal", r"[A-Z][a-zA-Z0-9]*"),
    )
    for style, pattern in patterns:
        if re.fullmatch(pattern, core):
            return style
    return "mixed"


ACCEPT = {
    "snake": frozenset({"snake", "lower"}),
    "camel": frozenset({"camel", "lower"}),
    "pascal": frozenset({"pascal", "upper"}),
    "upper_snake": frozenset({"upper_snake", "upper"}),
}


def _cap(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


def render(words: Sequence[str], style: str, prefix: str = "") -> str:
    if not words:
        return prefix
    if style in ("snake", "lower", "mixed"):
        body = "_".join(w.lower() for w in words)
    elif style in ("upper_snake", "upper"):
        body = "_".join(w.upper() for w in words)
    elif style == "camel":
        body = words[0].lower() + "".join(_cap(w) for w in words[1:])
    elif style == "pascal":
        body = "".join(_cap(w) for w in words)
    elif style == "kebab":
        body = "-".join(w.lower() for w in words)
    else:
        raise ValueError(f"unknown style {style!r}")
    return prefix + body


def convert(name: str, style: str) -> str:
    """Convert ``name`` to ``style`` keeping leading underscores."""
    prefix = re.match(r"^_*", name)
    return render(split_words(name), style, prefix.group(0) if prefix else "")


GO_INITIALISMS = frozenset(
    """ACL API ASCII CPU CSS DNS EOF GUID HTML HTTP HTTPS ID IP JSON LHS QPS RAM RHS RPC SLA SMTP SQL
    SSH TCP TLS TTL UDP UI GID UID UUID URI URL UTF8 VM XML XMPP XSRF XSS""".split()
)


def _is_initialism(word: str) -> bool:
    upper = word.upper()
    return upper in GO_INITIALISMS or re.sub(r"\d+$", "", upper) in GO_INITIALISMS


def go_fix_initialisms(name: str) -> str:
    """Upper-case only the words that are Go initialisms (``UserId`` -> ``UserID``); leave the rest."""
    core = _core(name)
    exported = core[:1].isupper()
    return "".join(
        w.upper() if _is_initialism(w) and w != w.upper() and (i > 0 or exported) else w
        for i, w in enumerate(split_words(core))
    )


def go_name(name: str) -> str:
    """Render ``name`` as Go MixedCaps with initialisms upper-cased; keeps exportedness."""
    core = _core(name)
    exported = bool(core) and core[0].isupper()
    out: list[str] = []
    for index, word in enumerate(split_words(name)):
        if index == 0 and not exported:
            out.append(word.lower())
        elif _is_initialism(word):
            out.append(word.upper())
        else:
            out.append(_cap(word))
    return "".join(out)


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


@dataclass
class Identifier:
    name: str
    kind: str
    line: int
    is_bool: bool = False
    is_loop: bool = False
    inferred: bool = False
    top_level: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    path: str
    line: int
    language: str
    kind: str
    name: str
    rule: str
    severity: str
    message: str
    suggestion: str | None = None
    occurrences: int = 0


@dataclass
class ScanResult:
    path: str
    language: str
    identifiers: list[Identifier] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tokens: Counter[str] = field(default_factory=Counter)


@dataclass
class Context:
    language: str
    path: str
    text: str
    is_test_file: bool
    jsx: bool
    package: str | None = None


# --------------------------------------------------------------------------- #
# Lexical stripping (comments and string bodies -> spaces, newlines preserved)
# --------------------------------------------------------------------------- #


def _blank(chunk: str) -> str:
    return "".join("\n" if ch == "\n" else " " for ch in chunk)


_RUST_RAW = re.compile(r'(?:br|r)(#*)"')
_CHAR_LIT = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F]+\}|x[0-9a-fA-F]{2}|.)|[^\\'\n])'")
_JS_REGEX_PREV = frozenset("(,=:[!&|?{};+-*%<>~^")
_JS_REGEX_KEYWORDS = ("return", "typeof", "case", "in", "of", "delete", "void", "throw", "new", "yield", "await")


def _js_regex_allowed(text: str, i: int) -> bool:
    """A '/' starts a regex literal when it cannot be division (after an operator, keyword or line start)."""
    j = i - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] == "\n":
        return True
    if text[j] in _JS_REGEX_PREV:
        return True
    k = j
    while k >= 0 and (text[k].isalnum() or text[k] in "_$"):
        k -= 1
    return text[k + 1 : j + 1] in _JS_REGEX_KEYWORDS


def _js_regex_end(text: str, i: int) -> int:
    """Index just past a regex literal starting at ``text[i] == '/'``, or -1 if it is not one."""
    j, n, in_class = i + 1, len(text), False
    while j < n:
        ch = text[j]
        if ch == "\n":
            return -1
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            j += 1
            while j < n and text[j].isalpha():
                j += 1
            return j
        j += 1
    return -1


def strip_c_like(text: str, language: str) -> str:
    """Blank comments and string contents for Go, Rust, JS/TS and Java (newlines preserved)."""
    out: list[str] = []
    i, n = 0, len(text)
    backtick = language in ("go", "javascript", "typescript")
    js = language in ("javascript", "typescript")
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            end = text.find("\n", i)
            end = n if end == -1 else end
            out.append(_blank(text[i:end]))
            i = end
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            out.append(_blank(text[i:end]))
            i = end
        elif ch == "/" and js and _js_regex_allowed(text, i) and (end := _js_regex_end(text, i)) != -1:
            out.append("/" + " " * (end - i - 1))
            i = end
        elif language == "java" and text.startswith('"""', i):
            end = text.find('"""', i + 3)
            end = n if end == -1 else end + 3
            out.append('"' + _blank(text[i + 1 : end - 1]) + '"')
            i = end
        elif (
            language == "rust"
            and ch in "rb"
            and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_"))
            and (raw := _RUST_RAW.match(text, i)) is not None
        ):
            closer = '"' + raw.group(1)
            end = text.find(closer, raw.end())
            end = n if end == -1 else end + len(closer)
            out.append(_blank(text[i:end]))
            i = end
        elif ch == '"' or (ch == "`" and backtick):
            j = i + 1
            while j < n and text[j] != ch:
                if text[j] == "\\" and (ch == '"' or language != "go"):
                    j += 1
                elif text[j] == "\n" and ch == '"' and language != "rust":
                    break
                j += 1
            closed = j < n and text[j] == ch
            out.append(ch + _blank(text[i + 1 : j]) + (ch if closed else ""))
            i = j + 1 if closed else j
        elif ch == "'":
            if js:
                j = i + 1
                while j < n and text[j] not in "'\n":
                    j += 2 if text[j] == "\\" else 1
                closed = j < n and text[j] == "'"
                out.append("'" + _blank(text[i + 1 : j]) + ("'" if closed else ""))
                i = j + 1 if closed else j
            else:
                m = _CHAR_LIT.match(text, i)
                if m:
                    out.append("'" + " " * (m.end() - i - 2) + "'")
                    i = m.end()
                else:  # Rust lifetime / label
                    out.append(ch)
                    i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


_HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][\w]*)\2")


def strip_shell(text: str) -> str:
    """Blank heredoc bodies, comments and quoted strings in shell source."""
    lines = text.split("\n")
    pending: list[tuple[str, bool]] = []
    for idx, line in enumerate(lines):
        if pending:
            delim, dash = pending[0]
            candidate = line.lstrip("\t") if dash else line
            lines[idx] = ""
            if candidate == delim:
                pending.pop(0)
            continue
        for m in _HEREDOC.finditer(line):
            before = line[: m.start()]
            in_arith = before.count("((") > before.count("))") or bool(re.search(r"\blet\b|\[\[", before))
            if not before.endswith("<") and not in_arith:
                pending.append((m.group(3), m.group(1) == "-"))
    out: list[str] = []
    joined = "\n".join(lines)
    i, n = 0, len(joined)
    while i < n:
        ch = joined[i]
        prev = joined[i - 1] if i else "\n"
        if ch == "#" and prev in " \t\n;":
            end = joined.find("\n", i)
            end = n if end == -1 else end
            out.append(_blank(joined[i:end]))
            i = end
        elif ch == "'":
            end = joined.find("'", i + 1)
            end = n if end == -1 else end
            out.append("'" + _blank(joined[i + 1 : end]) + "'")
            i = end + 1
        elif ch == '"':
            j = i + 1
            while j < n and joined[j] != '"':
                j += 2 if joined[j] == "\\" else 1
            out.append('"' + _blank(joined[i + 1 : j]) + '"')
            i = j + 1
        elif ch == "\\" and i + 1 < n:
            out.append("  " if joined[i + 1] != "\n" else " \n")
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _line_of(text: str) -> Any:
    starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line_of(offset: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    return line_of


def _is_arrow(text: str, j: int) -> bool:
    return text[j] == ">" and j > 0 and text[j - 1] in "-="


def _balanced(text: str, start: int, opener: str = "(", closer: str = ")") -> tuple[str, int]:
    """Return (inner, end_index_after_closer) for a group starting at ``text[start] == opener``."""
    depth = 0
    for j in range(start, len(text)):
        if text[j] == opener:
            depth += 1
        elif text[j] == closer and not _is_arrow(text, j):
            depth -= 1
            if depth == 0:
                return text[start + 1 : j], j + 1
    return text[start + 1 :], len(text)


def _split_top(text: str, sep: str = ",", angles: bool = True) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    openers, closers = ("([{<", ")]}>") if angles else ("([{", ")]}")
    for j, ch in enumerate(text):
        if ch in openers and not (ch == "<" and text[j + 1 : j + 2] == "-"):
            depth += 1
        elif ch in closers and not _is_arrow(text, j):
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _depths(stripped: str) -> list[int]:
    """Brace depth at the start of each line (1-indexed list; index 0 unused)."""
    depths = [0]
    depth = 0
    for line in stripped.split("\n"):
        depths.append(depth)
        depth += line.count("{") - line.count("}")
        depth = max(depth, 0)
    return depths


# --------------------------------------------------------------------------- #
# Extractors
# --------------------------------------------------------------------------- #

PY_HOOKS = frozenset(
    """setUp tearDown setUpClass tearDownClass setUpModule tearDownModule asyncSetUp asyncTearDown
    generic_visit""".split()
)
PY_TYPE_FACTORIES = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple", "NewType"})
PY_BOOL_CALLS = frozenset({"isinstance", "issubclass", "callable", "hasattr", "bool", "any", "all"})


class _PyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.out: list[Identifier] = []
        self.scopes: list[str] = ["module"]
        self.classes: list[str] = []
        self.seen_fields: set[tuple[str, str]] = set()

    def add(self, name: str, kind: str, node: ast.AST, **kw: Any) -> None:
        self.out.append(Identifier(name, kind, getattr(node, "lineno", 1), **kw))

    # -- helpers --
    @staticmethod
    def _is_bool_annotation(node: ast.AST | None) -> bool:
        return (isinstance(node, ast.Name) and node.id == "bool") or (
            isinstance(node, ast.Constant) and node.value == "bool"
        )

    @staticmethod
    def _is_bool_value(node: ast.AST | None) -> bool:
        if isinstance(node, ast.Constant):
            return isinstance(node.value, bool)
        if isinstance(node, ast.Compare):
            return True
        if isinstance(node, ast.UnaryOp):
            return isinstance(node.op, ast.Not)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in PY_BOOL_CALLS
        return False

    @staticmethod
    def _is_literal(node: ast.AST | None) -> bool:
        if isinstance(node, ast.Constant):
            return node.value is not None and node.value is not Ellipsis
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)) and node.elts:
            return all(isinstance(e, ast.Constant) and e.value is not None for e in node.elts)
        return False

    def _names(self, target: ast.AST) -> Iterator[ast.Name]:
        if isinstance(target, ast.Name):
            yield target
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                yield from self._names(elt)
        elif isinstance(target, ast.Starred):
            yield from self._names(target.value)

    # -- definitions --
    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        in_class = self.scopes[-1] == "class"
        name = node.name
        decorators = {
            d.id if isinstance(d, ast.Name) else d.attr if isinstance(d, ast.Attribute) else ""
            for d in node.decorator_list
        }
        exempt = (
            (name.startswith("__") and name.endswith("__"))
            or name in PY_HOOKS
            or name.startswith(("visit_", "depart_"))
            or bool(re.fullmatch(r"do_[A-Z]+", name))
        )
        if not exempt:
            kind = "property" if "property" in decorators else "method" if in_class else "function"
            self.add(
                name,
                kind,
                node,
                is_bool=kind == "property" and self._is_bool_annotation(node.returns),
                top_level=self.scopes[-1] == "module",
            )
        args = node.args
        positional = [*args.posonlyargs, *args.args]
        defaults: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults))
        defaults += list(args.defaults)
        pairs: list[tuple[ast.arg, ast.expr | None]] = list(zip(positional, defaults))
        pairs += list(zip(args.kwonlyargs, args.kw_defaults))
        pairs += [(a, None) for a in (args.vararg, args.kwarg) if a is not None]
        skip_first = in_class and "staticmethod" not in decorators
        for index, (arg, default) in enumerate(pairs):
            if (index == 0 and skip_first and arg in positional) or arg.arg in ("self", "cls", "mcs"):
                continue
            self.add(
                arg.arg,
                "parameter",
                arg,
                is_bool=self._is_bool_annotation(arg.annotation) or self._is_bool_value(default),
            )
        self.scopes.append("function")
        for stmt in node.body:
            self.visit(stmt)
        self.scopes.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            self.add(arg.arg, "parameter", arg, is_loop=True)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [
            b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else "" for b in node.bases
        ]
        is_exc = any(b in ("Exception", "BaseException") or b.endswith(("Error", "Exception")) for b in bases)
        self.add(node.name, "class", node, top_level=self.scopes[-1] == "module", meta={"exception": is_exc})
        self.scopes.append("class")
        self.classes.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self.classes.pop()
        self.scopes.pop()

    def _assign(
        self, targets: Iterable[ast.AST], value: ast.AST | None, annotation: ast.AST | None, node: ast.AST
    ) -> None:
        scope = self.scopes[-1]
        is_bool = self._is_bool_annotation(annotation) or self._is_bool_value(value)
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in ("self", "cls")
                and self.classes
            ):
                key = (self.classes[-1], target.attr)
                if key not in self.seen_fields:
                    self.seen_fields.add(key)
                    self.add(target.attr, "field", target, is_bool=is_bool)
                continue
            for name_node in self._names(target):
                name = name_node.id
                if name == "_" or (name.startswith("__") and name.endswith("__")):
                    continue
                style = classify_style(name)
                if scope == "module":
                    if (
                        isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and value.func.id in PY_TYPE_FACTORIES
                    ):
                        kind = "class" if value.func.id == "NewType" else "typevar"
                        self.add(name, kind, name_node, top_level=True)
                    elif style == "pascal":
                        self.add(name, "type", name_node, top_level=True)
                    elif style in ("upper", "upper_snake"):
                        self.add(name, "constant", name_node, top_level=True)
                    elif self._is_literal(value) and not is_bool:
                        self.add(name, "constant", name_node, inferred=True, top_level=True)
                    else:
                        self.add(name, "variable", name_node, is_bool=is_bool, top_level=True)
                elif scope == "class":
                    self.add(name, "field", name_node, is_bool=is_bool, meta={"class_attr": True})
                else:
                    self.add(name, "variable", name_node, is_bool=is_bool)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._assign(node.targets, node.value, None, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._assign([node.target], node.value, node.annotation, node)
        if node.value is not None:
            self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.add(node.target.id, "variable", node.target, is_bool=self._is_bool_value(node.value))
        self.visit(node.value)

    def _loop_target(self, target: ast.AST) -> None:
        for name_node in self._names(target):
            if name_node.id != "_":
                self.add(name_node.id, "variable", name_node, is_loop=True)

    def visit_For(self, node: ast.For | ast.AsyncFor) -> None:
        self._loop_target(node.target)
        self.generic_visit(node)

    visit_AsyncFor = visit_For

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._loop_target(node.target)
        self.generic_visit(node)

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                for name_node in self._names(item.optional_vars):
                    self.add(name_node.id, "variable", name_node)
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_TypeAlias(self, node: Any) -> None:  # Python 3.12+
        if isinstance(node.name, ast.Name):
            self.add(node.name.id, "type", node, top_level=True)


def extract_python(ctx: Context) -> tuple[list[Identifier], list[str]]:
    try:
        tree = ast.parse(ctx.text, filename=ctx.path)
    except SyntaxError as exc:
        return [], [f"SyntaxError: {exc.msg} (line {exc.lineno})"]
    visitor = _PyVisitor()
    visitor.visit(tree)
    return visitor.out, []


# -- Go --

_GO_FUNC = re.compile(r"^func\s*(\([^)]*\)\s*)?(\w+)\s*", re.MULTILINE)


def _go_short_decl_names(text: str, colon: int) -> tuple[list[str], int] | None:
    """Names on the left of the ':=' at ``colon``, scanning backwards in linear time."""
    names: list[str] = []
    j = colon
    while True:
        while j > 0 and text[j - 1] in " \t":
            j -= 1
        end = j
        while j > 0 and (text[j - 1].isalnum() or text[j - 1] == "_"):
            j -= 1
        if j == end:
            return None
        names.append(text[j:end])
        k = j
        while k > 0 and text[k - 1] in " \t":
            k -= 1
        if k > 0 and text[k - 1] == ",":
            j = k - 1
            continue
        if k > 0 and text[k - 1] == ".":
            return None
        return names[::-1], j


def _go_params(inner: str) -> list[tuple[str, str]]:
    parts = [p.split(None, 1) for p in _split_top(inner, angles=False)]
    if not any(len(p) == 2 for p in parts):
        return []
    result: list[tuple[str, str]] = []
    pending: list[str] = []
    for part in parts:
        if len(part) == 2:
            for name in [*pending, part[0]]:
                result.append((name, part[1].strip()))
            pending = []
        else:
            pending.append(part[0])
    return [(n, t) for n, t in result if re.fullmatch(r"\w+", n)]


def extract_go(ctx: Context) -> tuple[list[Identifier], list[str]]:
    text = strip_c_like(ctx.text, "go")
    line_of = _line_of(text)
    out: list[Identifier] = []

    m = re.search(r"^package\s+(\w+)", text, re.MULTILINE)
    if m:
        ctx.package = m.group(1)
        out.append(Identifier(m.group(1), "package", line_of(m.start(1)), top_level=True))

    for m in _GO_FUNC.finditer(text):
        pos = m.end()
        if text[pos : pos + 1] == "[":  # type parameters
            _, pos = _balanced(text, pos, "[", "]")
            while pos < len(text) and text[pos] in " \t":
                pos += 1
        if text[pos : pos + 1] != "(":
            continue
        kind = "method" if m.group(1) else "function"
        line = line_of(m.start(2))
        out.append(Identifier(m.group(2), kind, line, top_level=True))
        inner, _ = _balanced(text, pos)
        for name, typ in _go_params(inner):
            if name != "_":
                out.append(Identifier(name, "parameter", line, is_bool=typ == "bool"))

    colon = text.find(":=")
    while colon != -1:
        found = _go_short_decl_names(text, colon)
        rhs = text[colon + 2 : colon + 14].lstrip()
        next_colon = text.find(":=", colon + 2)
        if found is None:
            colon = next_colon
            continue
        decl_names, start = found
        line_start = text.rfind("\n", 0, start) + 1
        is_loop = bool(re.fullmatch(r"\s*for\s+", text[line_start:start]))
        line_no = line_of(start)
        colon = next_colon
        for name in decl_names:
            if name != "_":
                out.append(
                    Identifier(
                        name,
                        "variable",
                        line_no,
                        is_loop=is_loop,
                        is_bool=bool(re.match(r"(true|false)\b", rhs)),
                    )
                )

    lines = text.split("\n")
    block: str | None = None
    block_depth = 0
    body_depth: int | None = None
    body_kind = ""
    depth = 0
    for lineno, line in enumerate(lines, 1):
        s = line.strip()
        top = line[:1] not in (" ", "\t") and bool(s)
        if body_depth is not None and depth == body_depth and s and not s.startswith("}"):
            if body_kind == "struct":
                fm = re.match(r"^(\w+(?:\s*,\s*\w+)*)\s+(\S.*)$", s)
                if fm:
                    for name in re.split(r"\s*,\s*", fm.group(1)):
                        out.append(Identifier(name, "field", lineno, is_bool=fm.group(2).startswith("bool")))
            else:
                fm = re.match(r"^(\w+)\s*\(", s)
                if fm:
                    out.append(Identifier(fm.group(1), "method", lineno))
        elif block is not None:
            if s.startswith(")") and depth == block_depth:
                block = None
            elif s and depth == block_depth:
                if block == "type":
                    bm = re.match(r"^(\w+)\s", s)
                    if bm:
                        out.append(Identifier(bm.group(1), "type", lineno, top_level=True))
                else:
                    bm = re.match(r"^(\w+(?:\s*,\s*\w+)*)(.*)$", s)
                    if bm:
                        rest = bm.group(2)
                        is_bool = bool(re.match(r"\s*bool\b", rest) or re.search(r"=\s*(true|false)\b", rest))
                        for name in re.split(r"\s*,\s*", bm.group(1)):
                            if name != "_":
                                out.append(
                                    Identifier(
                                        name,
                                        "constant" if block == "const" else "variable",
                                        lineno,
                                        is_bool=is_bool,
                                        top_level=True,
                                    )
                                )
        else:
            dm = re.match(r"^(var|const|type)\s*\(\s*$", s)
            if dm and top:
                block = dm.group(1)
                block_depth = depth
            else:
                vm = re.match(r"^(var|const)\s+((?:\w+\s*,\s*)*\w+)(.*)$", s)
                if vm:
                    rest = vm.group(3)
                    is_bool = bool(re.match(r"\s*bool\b", rest) or re.search(r"=\s*(true|false)\b", rest))
                    for name in re.split(r"\s*,\s*", vm.group(2)):
                        if name != "_":
                            out.append(
                                Identifier(
                                    name,
                                    "constant" if vm.group(1) == "const" else "variable",
                                    lineno,
                                    is_bool=is_bool,
                                    top_level=top,
                                )
                            )
                tm = re.match(r"^type\s+(\w+)\b", s)
                if tm:
                    out.append(Identifier(tm.group(1), "type", lineno, top_level=top))
        sm = re.search(r"\b(struct|interface)\s*\{", line)
        if sm and body_depth is None and "}" not in line[sm.end() :]:
            body_depth = depth + line[: sm.end()].count("{") - line[: sm.end()].count("}")
            body_kind = sm.group(1)
        depth += line.count("{") - line.count("}")
        if body_depth is not None and depth < body_depth:
            body_depth = None
    return out, []


# -- Rust --


def _rust_params(inner: str) -> list[tuple[str, str]]:
    result = []
    for part in _split_top(inner):
        part = re.sub(r"^mut\s+", "", part)
        m = re.match(r"^(\w+)\s*:(?!:)\s*(.*)$", part, re.DOTALL)
        if m and m.group(1) not in ("self", "_"):
            result.append((m.group(1), m.group(2).strip()))
    return result


def extract_rust(ctx: Context) -> tuple[list[Identifier], list[str]]:
    text = strip_c_like(ctx.text, "rust")
    line_of = _line_of(text)
    out: list[Identifier] = []

    for m in re.finditer(r"\bfn\s+(\w+)", text):
        pos = m.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == "<":
            _, pos = _balanced(text, pos, "<", ">")
            while pos < len(text) and text[pos].isspace():
                pos += 1
        line = line_of(m.start(1))
        out.append(Identifier(m.group(1), "function", line))
        if pos < len(text) and text[pos] == "(":
            inner, _ = _balanced(text, pos)
            for name, typ in _rust_params(inner):
                out.append(Identifier(name, "parameter", line, is_bool=typ == "bool"))

    for m in re.finditer(
        r"\blet\s+(?:mut\s+)?([A-Za-z_]\w*)\b(?!\s*(?:\(|\{|::))(\s*:\s*([^=;]+))?(\s*=\s*(\w+))?", text
    ):
        typ, rhs = (m.group(3) or "").strip(), m.group(5) or ""
        out.append(
            Identifier(m.group(1), "variable", line_of(m.start(1)), is_bool=typ == "bool" or rhs in ("true", "false"))
        )
    for m in re.finditer(r"\bfor\s+(?:mut\s+)?([A-Za-z_]\w*)\s+in\b", text):
        out.append(Identifier(m.group(1), "variable", line_of(m.start(1)), is_loop=True))
    for m in re.finditer(r"\b(struct|enum|trait|type|union)\s+([A-Za-z_]\w*)", text):
        out.append(
            Identifier(m.group(2), "trait" if m.group(1) == "trait" else "type", line_of(m.start(2)), top_level=True)
        )
    for m in re.finditer(r"\bmod\s+([A-Za-z_]\w*)", text):
        out.append(Identifier(m.group(1), "module", line_of(m.start(1))))
    for m in re.finditer(r"\b(?:const|static(?:\s+mut)?)\s+([A-Za-z_]\w*)\s*:", text):
        out.append(Identifier(m.group(1), "constant", line_of(m.start(1)), top_level=True))
    for m in re.finditer(r"\bmacro_rules!\s*([A-Za-z_]\w*)", text):
        out.append(Identifier(m.group(1), "macro", line_of(m.start(1))))

    depth = 0
    body: tuple[str, int] | None = None
    for lineno, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if body is not None and depth == body[1] and s and not s.startswith(("}", "#")):
            if body[0] == "struct":
                fm = re.match(r"^(?:pub(?:\([^)]*\))?\s+)?([A-Za-z_]\w*)\s*:(?!:)\s*(.+?),?$", s)
                if fm:
                    out.append(Identifier(fm.group(1), "field", lineno, is_bool=fm.group(2).strip() == "bool"))
            else:
                vm = re.match(r"^([A-Za-z_]\w*)\b", s)
                if vm:
                    out.append(Identifier(vm.group(1), "variant", lineno))
        dm = re.search(r"\b(struct|enum)\s+\w+[^;{]*\{", line)
        if dm and body is None and line[dm.end() :].count("}") < line[dm.end() - 1 :].count("{"):
            body = (dm.group(1), depth + line[: dm.end()].count("{") - line[: dm.end()].count("}"))
        depth = max(0, depth + line.count("{") - line.count("}"))
        if body is not None and depth < body[1]:
            body = None
    return out, []


# -- JavaScript / TypeScript --

_JS_ID = r"[A-Za-z_$#][\w$]*"
JS_KEYWORDS = frozenset(
    """if for while switch catch function return with do else try new typeof await yield super delete
    void in of instanceof throw case default import export from class extends""".split()
)
_JS_ARROW = re.compile(r"^(?:async\s+)?(?:\(([^()]*)\)|([A-Za-z_$][\w$]*))\s*(?::\s*[^=]+?)?\s*=>")


_JS_DECLARATOR = re.compile(
    r"^([A-Za-z_$][\w$]*)\s*!?\s*(?::\s*([^=]+?))?\s*(?:=(?!=)\s*(.*))?(?:\s+(?:of|in)\b.*)?$", re.DOTALL
)


def _js_statement(text: str, pos: int) -> str:
    """Text of a declaration list from ``pos`` to its ';' (or newline) at bracket depth 0."""
    depth = 0
    for j in range(pos, len(text)):
        ch = text[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return text[pos:j]
            depth -= 1
        elif ch in ";\n" and depth == 0:
            return text[pos:j]
    return text[pos:]


def _js_params(inner: str) -> list[tuple[str, bool]]:
    result = []
    for part in _split_top(inner):
        part = re.sub(r"^(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|private|protected|readonly|override)\s+)*", "", part)
        if part.startswith(("{", "[")):
            continue
        part = part.lstrip(".")
        m = re.match(r"^([A-Za-z_$][\w$]*)\??\s*(?::\s*([^=]+))?(?:=\s*(.*))?$", part, re.DOTALL)
        if m and m.group(1) != "this":
            typ, default = (m.group(2) or "").strip(), (m.group(3) or "").strip()
            result.append((m.group(1), typ == "boolean" or default in ("true", "false")))
    return result


def extract_js(ctx: Context) -> tuple[list[Identifier], list[str]]:
    text = strip_c_like(ctx.text, ctx.language)
    line_of = _line_of(text)
    out: list[Identifier] = []

    def add_params(inner: str, line: int, loop: bool = False) -> None:
        for name, is_bool in _js_params(inner):
            out.append(Identifier(name, "parameter", line, is_bool=is_bool, is_loop=loop))

    def after_generics(pos: int) -> int:
        while pos < len(text) and text[pos] in " \t":
            pos += 1
        if pos < len(text) and text[pos] == "<":
            _, pos = _balanced(text, pos, "<", ">")
        while pos < len(text) and text[pos].isspace():
            pos += 1
        return pos

    for m in re.finditer(r"\bfunction\b\s*\*?\s*([A-Za-z_$][\w$]*)", text):
        pos = after_generics(m.end())
        if pos < len(text) and text[pos] == "(":
            line = line_of(m.start(1))
            out.append(Identifier(m.group(1), "function", line))
            add_params(_balanced(text, pos)[0], line)

    for m in re.finditer(r"\b(class|interface|enum)\s+([A-Za-z_$][\w$]*)", text):
        if text[max(0, m.start() - 1)] != ".":
            out.append(Identifier(m.group(2), m.group(1) if m.group(1) != "class" else "class", line_of(m.start(2))))
    if ctx.language == "typescript":
        for m in re.finditer(r"(?<![\w.$])type\s+([A-Za-z_$][\w$]*)\s*(?:<[^=]*>)?\s*=", text):
            out.append(Identifier(m.group(1), "type", line_of(m.start(1))))

    for m in re.finditer(r"\b(const|let|var)\s+", text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        is_loop = bool(re.search(r"\bfor\s*\(\s*$", text[line_start : m.start()]))
        statement = _js_statement(text, m.end())
        offset = m.end()
        for part in _split_top(statement):
            dm = _JS_DECLARATOR.match(part)
            if dm is None:
                continue
            name, typ, rhs = dm.group(1), (dm.group(2) or "").strip(), (dm.group(3) or "").strip()
            found_at = text.find(name, offset)
            line = line_of(found_at if found_at != -1 else m.end())
            offset = found_at + len(name) if found_at != -1 else offset
            arrow = _JS_ARROW.match(rhs)
            if arrow or re.match(r"(?:async\s+)?function\b", rhs):
                out.append(Identifier(name, "function", line))
                if arrow:
                    add_params(arrow.group(1) if arrow.group(1) is not None else arrow.group(2) or "", line, loop=True)
                continue
            is_bool = typ == "boolean" or bool(re.match(r"(true|false)\b|!", rhs))
            out.append(
                Identifier(
                    name,
                    "variable",
                    line,
                    is_bool=is_bool,
                    is_loop=is_loop,
                    meta={
                        "const": m.group(1) == "const",
                        "import": bool(re.match(r"(?:await\s+)?(?:require|import)\s*\(", rhs)),
                    },
                )
            )

    method = re.compile(
        r"^[ \t]*(?:(?:public|private|protected|static|async|readonly|override|abstract|get|set)\s+)*\*?\s*"
        r"(#?[A-Za-z_$][\w$]*)\s*(?:<[^<>()]*>)?\s*\(([^()]*)\)\s*(?::\s*[^{};=]+?)?\s*\{",
        re.MULTILINE,
    )
    for m in method.finditer(text):
        if m.group(1) in JS_KEYWORDS:
            continue
        line = line_of(m.start(1))
        if m.group(1) != "constructor":
            out.append(Identifier(m.group(1), "method", line))
        add_params(m.group(2), line)

    seen: set[str] = set()
    for m in re.finditer(r"\bthis\.(#?[A-Za-z_$][\w$]*)\s*=(?!=)\s*(\w*)", text):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(Identifier(m.group(1), "field", line_of(m.start(1)), is_bool=m.group(2) in ("true", "false")))
    return out, []


# -- Java --

JAVA_IMMUTABLE_TYPES = frozenset(
    """byte short int long float double char boolean String Byte Short Integer Long Float Double
    Character Boolean BigInteger BigDecimal Pattern Duration Instant""".split()
)
JAVA_TYPE_KEYWORDS = frozenset(
    """return throw new else package import case break continue assert yield if for while switch do try
    catch""".split()
)


def extract_java(ctx: Context) -> tuple[list[Identifier], list[str]]:
    text = strip_c_like(ctx.text, "java")
    depths = _depths(text)
    out: list[Identifier] = []
    type_stack: list[tuple[str, int]] = []
    pending_type: str | None = None
    method = re.compile(
        r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|private|protected|static|final|abstract|synchronized|native|default|strictfp)\s+)*"
        r"(?:<[^>]+>\s+)?(?:([\w<>\[\],.?]+(?:\s*<[^()]*>)?)\s+)?(\w+)\s*\(([^()]*)\)\s*(?:throws\s+[\w.,\s]+)?[{;]"
    )
    decl = re.compile(
        r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*((?:(?:public|private|protected|static|final|transient|volatile)\s+)*)"
        r"([\w\[\].?]+(?:\s*<[^;=()]*>)?(?:\[\])*)\s+(\w+)\s*(=|;)"
    )
    for lineno, line in enumerate(text.split("\n"), 1):
        depth = depths[lineno]
        while type_stack and depth < type_stack[-1][1]:
            type_stack.pop()
        if pending_type is not None and line.strip().startswith("{"):
            type_stack.append((pending_type, depth + 1))
            pending_type = None
            continue
        pm = re.match(r"^\s*package\s+([\w.]+)\s*;", line)
        if pm:
            out.append(Identifier(pm.group(1), "package", lineno, top_level=True))
            continue
        tm = re.search(r"\b(class|interface|enum|record)\s+(\w+)", line)
        if tm and not re.search(r"\.\s*class\b", line):
            kind = "interface" if tm.group(1) == "interface" else "class"
            public = bool(re.search(r"\bpublic\b", line[: tm.start()]))
            out.append(Identifier(tm.group(2), kind, lineno, top_level=depth == 0, meta={"public": public}))
            if "{" in line[tm.end() :]:
                type_stack.append((tm.group(2), depth + 1))
            else:
                pending_type = tm.group(2)  # Allman style: brace on a later line
            continue
        for fm in re.finditer(r"\bfor\s*\(\s*(?:final\s+)?[\w<>\[\],.?]+\s+(\w+)\s*[:=]", line):
            out.append(Identifier(fm.group(1), "variable", lineno, is_loop=True))
        mm = method.match(line)
        if mm and mm.group(2) not in JAVA_TYPE_KEYWORDS and (mm.group(1) or "") not in JAVA_TYPE_KEYWORDS:
            if mm.group(1) is not None:  # no return type means a constructor (or a bare call)
                out.append(Identifier(mm.group(2), "method", lineno))
            for part in _split_top(mm.group(3)):
                tokens = [t for t in re.sub(r"@\w+|\bfinal\b", "", part).split() if t]
                if len(tokens) >= 2:
                    out.append(
                        Identifier(
                            tokens[-1].lstrip("."),
                            "parameter",
                            lineno,
                            is_bool=tokens[-2].replace("...", "") in ("boolean", "Boolean"),
                        )
                    )
            continue
        dm = decl.match(line)
        if dm and dm.group(2) not in JAVA_TYPE_KEYWORDS:
            modifiers = dm.group(1).split()
            in_body = bool(type_stack) and depth == type_stack[-1][1]
            is_bool = dm.group(2) in ("boolean", "Boolean")
            meta: dict[str, Any] = {}
            if in_body and "static" in modifiers and "final" in modifiers:
                # Google Java Style: only deeply immutable static finals are constants.
                immutable = dm.group(2) in JAVA_IMMUTABLE_TYPES or dm.group(2).startswith("Immutable")
                kind = "constant" if immutable else "field"
                meta = {} if immutable else {"static_final": True}
            elif in_body:
                kind = "field"
            else:
                kind = "variable"
            out.append(Identifier(dm.group(3), kind, lineno, is_bool=is_bool, meta=meta))
    return out, []


# -- Shell --


def _shell_decl_names(rest: str) -> list[str]:
    """Names in ``a=1 b c="x y" d=$(cmd arg)``; stops at a command separator."""
    names: list[str] = []
    i, n = 0, len(rest)
    while i < n:
        while i < n and rest[i] in " \t":
            i += 1
        if i >= n or rest[i] in ";&|#":
            break
        m = re.match(r"[A-Za-z_]\w*", rest[i:])
        if m is None:
            break
        names.append(m.group(0))
        i += m.end()
        if i < n and rest[i] == "[":
            i = rest.find("]", i) + 1 or n
        if i < n and rest[i] == "=":
            i += 1
            while i < n and rest[i] not in " \t;&|":
                if rest[i] in "\"'":
                    close = rest.find(rest[i], i + 1)
                    i = n if close == -1 else close + 1
                elif rest.startswith("$(", i):
                    _, i = _balanced(rest, i + 1)
                else:
                    i += 1
        elif i < n and rest[i] not in " \t;&|":
            break
    return names


def extract_shell(ctx: Context) -> tuple[list[Identifier], list[str]]:
    text = strip_shell(ctx.text)
    out: list[Identifier] = []
    depth = 0
    fn_depths: list[int] = []
    func = re.compile(r"^\s*(?:function\s+([\w:.\-]+)\s*(?:\(\s*\))?|([\w:.\-]+)\s*\(\s*\))\s*(?:\{|$)")
    declare = re.compile(
        r"^\s*(local|declare|typeset|readonly|export)\s+((?:-\w+\s+)*)([A-Za-z_]\w*)(?:\[[^\]]*\])?(=|\s|;|$)"
    )
    assign = re.compile(r"^\s*([A-Za-z_]\w*)(?:\[[^\]]*\])?\+?=(?!=)")
    for lineno, line in enumerate(text.split("\n"), 1):
        while fn_depths and depth < fn_depths[-1]:
            fn_depths.pop()
        in_function = bool(fn_depths)
        fm = func.match(line)
        if fm:
            name = fm.group(1) or fm.group(2)
            out.append(Identifier(name, "function", lineno))
            fn_depths.append(depth + 1)
        for lm in re.finditer(r"(?:^|[;&|]\s*|\bdo\s+)for\s+([A-Za-z_]\w*)\s+in\b", line):
            out.append(Identifier(lm.group(1), "variable", lineno, is_loop=True))
        dm = declare.match(line)
        if dm:
            keyword, flags = dm.group(1), dm.group(2)
            if "-f" in flags or "-F" in flags:
                pass
            else:
                names = _shell_decl_names(line[dm.start(3) :])
                for name in names:
                    if keyword == "local" or (
                        keyword in ("declare", "typeset") and in_function and not re.search(r"-\w*[rx]", flags)
                    ):
                        out.append(Identifier(name, "variable", lineno, meta={"local": True}))
                    elif keyword in ("readonly", "export") or re.search(r"-\w*[rx]", flags):
                        out.append(Identifier(name, "constant", lineno, meta={"keyword": keyword}))
                    else:
                        out.append(Identifier(name, "variable", lineno))
        else:
            am = assign.match(line)
            if am:
                out.append(Identifier(am.group(1), "variable", lineno, meta={"global": not in_function}))
        depth = max(0, depth + len(re.findall(r"(?:^|\s|;)\{(?=\s|$)", line)) - len(re.findall(r"(?:^|\s|;)\}", line)))
    return out, []


EXTRACTORS = {
    "python": extract_python,
    "go": extract_go,
    "rust": extract_rust,
    "javascript": extract_js,
    "typescript": extract_js,
    "java": extract_java,
    "shell": extract_shell,
}

# --------------------------------------------------------------------------- #
# Word lists
# --------------------------------------------------------------------------- #

VAGUE_COMMON = frozenset(
    """data info temp tmp obj thing things stuff val foo bar baz qux misc junk blah whatever mydata
    myvar variable dummy""".split()
)
VAGUE_FUNCTIONS = VAGUE_COMMON | frozenset(
    """process do doit dostuff dothings dowork dosomething perform func function method helper runit""".split()
)
VAGUE_TYPES = frozenset(
    ["manager", "helper", "helpers", "util", "utils", "utility", "utilities", "misc", "stuff", "data", "info", "object"]
)
TEST_PLACEHOLDERS = frozenset(["foo", "bar", "baz", "qux", "dummy"])

TECH_TOKENS = frozenset(
    """sha1 sha224 sha256 sha384 sha512 sha3 md4 md5 crc16 crc32 crc64 utf8 utf16 utf32 base16 base32
    base58 base64 b64 int8 int16 int32 int64 uint8 uint16 uint32 uint64 float16 float32 float64 ipv4
    ipv6 http1 http2 http3 oauth1 oauth2 log2 log10 log1p exp2 atan2 vec2 vec3 vec4 mat2 mat3 mat4
    x509 h264 h265 mp3 mp4 blake2 blake3 argon2 pbkdf2 aes128 aes256 rsa2048 rsa4096 ed25519 x25519
    p256 p384 p521 tls12 tls13 ssl3 python2 python3 py2 py3 es5 es6 es2015 web3 k8s i18n l10n a11y
    win32 win64 x64 x86 arm64 amd64 aarch64 i386 i686 wasm32 riscv64 rfc3339 rfc822 rfc1123 rfc2822
    iso8601 bz2 lz4 gen2 gen3 ucs2 ucs4 dns1123 cp1252 latin1 fnv1 fnv1a murmur3 xxh64 xxh3 s3 ec2""".split()
)

ABBREVIATIONS = {
    "usr": "user",
    "usrs": "users",
    "mgr": "manager",
    "mngr": "manager",
    "cnt": "count",
    "amt": "amount",
    "qty": "quantity",
    "acct": "account",
    "accnt": "account",
    "cust": "customer",
    "emp": "employee",
    "txn": "transaction",
    "trx": "transaction",
    "calc": "calculate",
    "svc": "service",
    "prd": "product",
    "prdct": "product",
    "dsc": "description",
    "lst": "list",
    "dct": "dict",
    "curr": "current",
    "pkt": "packet",
    "nbr": "number",
    "evt": "event",
    "rcv": "receive",
    "snd": "send",
    "rqst": "request",
    "rsp": "response",
    "hdr": "header",
    "hndl": "handle",
    "pmt": "payment",
    "pymt": "payment",
    "mthd": "method",
    "lbl": "label",
    "wrk": "work",
    "wrkr": "worker",
    "svr": "server",
    "clnt": "client",
    "cxn": "connection",
    "frst": "first",
    "smpl": "sample",
    "dflt": "default",
    "tbl": "table",
}

BOOL_PREFIXES = frozenset(
    """is are has have had can could should must may might will would was were did does do needs need
    allow allows allowed enable enables disable disables use uses include includes support supports
    show hide skip keep want wants require requires contains exists ignore ignores force with
    without no dry auto expect expects accept accepts prefer prefers in on at within inside under
    over only wrote saw seen sent got called follow sort ensure check recurse discard strip escape
    indent disallow validate verify raise overwrite preserve create delete remove add append reuse
    retry flush compress emit log print exclude parse normalize quote unquote trim wrap fail track
    watch wait block merge sign encrypt render capture collect dedupe expand return reset""".split()
)
BOOL_WORDS = frozenset(
    """verbose debug quiet silent force recursive enabled disabled active inactive visible hidden valid
    invalid ready done ok found success dirty empty required optional readonly strict interactive
    overwrite append all online offline open closed locked pending busy idle on off async sync
    dryrun trace pretty raw checked selected expanded collapsed loaded initialized running paused
    primary default deleted archived public private internal experimental beta exclusive unique
    nullable mandatory verified admin excluded included healthy ephemeral persistent cached first
    last secure close closing once exempt explicit implicit clear complete set matches equals exists
    contains includes supports needs allows requires wants expects succeeds fails passes applies
    overlaps conflicts true false yes""".split()
)

PY_BUILTINS = frozenset(
    """list dict set tuple str int float bool bytes type id input filter map sum min max len hash
    format iter next open range vars dir all any object compile eval exec help zip sorted reversed
    round abs pow print property super bin hex oct ord chr slice frozenset bytearray memoryview
    complex callable globals locals delattr getattr setattr hasattr isinstance issubclass divmod
    enumerate breakpoint classmethod staticmethod ascii repr""".split()
)
GO_PREDECLARED = frozenset(
    """append cap clear close complex copy delete imag len make max min new panic print println real
    recover bool byte comparable complex64 complex128 error float32 float64 int int8 int16 int32
    int64 rune string uint uint8 uint16 uint32 uint64 uintptr any true false iota nil""".split()
)

SINGLE_LETTER_OK = {
    "python": frozenset("ijknxyzfme"),
    "go": frozenset("ijknxyztbwrf"),
    "rust": frozenset("ijknxyz"),
    "javascript": frozenset("ijknxyze"),
    "typescript": frozenset("ijknxyze"),
    "java": frozenset("ijknxyze"),
    "shell": frozenset("ijkn"),
}

# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #

_SNAKE_KINDS = {"function", "method", "variable", "parameter", "field", "property", "module", "macro"}
_PASCAL_KINDS = {"class", "type", "trait", "interface", "enum", "variant"}


def expected_style(ident: Identifier, ctx: Context) -> tuple[frozenset[str], str] | None:
    """Return (accepted styles, suggestion style) for N001, or None to skip."""
    lang, kind = ctx.language, ident.kind
    if kind == "typevar":
        return None
    if lang in ("python", "rust"):
        if kind == "constant":
            return ACCEPT["upper_snake"], "upper_snake"
        if kind in _PASCAL_KINDS:
            return ACCEPT["pascal"], "pascal"
        if lang == "python" and kind == "field" and ident.meta.get("class_attr"):
            if re.match(r"(visit|depart)_", ident.name):
                return None
            return ACCEPT["snake"] | ACCEPT["upper_snake"] | ACCEPT["pascal"], "snake"
        if lang == "python" and kind == "variable" and not ident.top_level:
            return ACCEPT["snake"] | ACCEPT["upper_snake"], "snake"
        return ACCEPT["snake"], "snake"
    if lang in ("javascript", "typescript"):
        if kind in _PASCAL_KINDS:
            return ACCEPT["pascal"], "pascal"
        if kind == "function" and ctx.jsx:
            return ACCEPT["camel"] | ACCEPT["pascal"], "camel"
        if kind == "variable" and (ident.meta.get("const") or ident.meta.get("import")):
            return ACCEPT["camel"] | ACCEPT["upper_snake"] | ACCEPT["pascal"], "camel"
        return ACCEPT["camel"], "camel"
    if lang == "java":
        if kind in _PASCAL_KINDS:
            return ACCEPT["pascal"], "pascal"
        if kind == "constant":
            return ACCEPT["upper_snake"], "upper_snake"
        if ident.meta.get("static_final"):
            return ACCEPT["camel"] | ACCEPT["upper_snake"], "camel"
        return ACCEPT["camel"], "camel"
    if lang == "shell":
        if kind == "function":
            return ACCEPT["snake"], "snake"
        if kind == "constant":
            return ACCEPT["upper_snake"], "upper_snake"
        if ident.meta.get("local"):
            return ACCEPT["snake"], "snake"
        return ACCEPT["snake"] | ACCEPT["upper_snake"], "snake"
    return None


def _is_test_function(ident: Identifier, ctx: Context) -> bool:
    if ident.kind not in ("function", "method"):
        return False
    if ctx.language == "go":
        return bool(re.match(r"(Test|Benchmark|Example|Fuzz)", ident.name)) or (
            ctx.is_test_file and ident.name.startswith("test")
        )
    if ident.name.lower().startswith("test"):
        return True
    return ctx.is_test_file and ctx.language in ("java", "rust")


def _finding(
    ident: Identifier, ctx: Context, rule: str, severity: str, message: str, suggestion: str | None = None
) -> Finding:
    return Finding(ctx.path, ident.line, ctx.language, ident.kind, ident.name, rule, severity, message, suggestion)


def _rule_case(ident: Identifier, ctx: Context) -> list[Finding]:
    name, style = ident.name, classify_style(ident.name)
    if len(_core(name)) == 1:
        return []
    if ctx.language == "go":
        if ident.kind == "package":
            if style != "lower" and not (ctx.is_test_file and re.fullmatch(r"[a-z][a-z0-9]*_test", name)):
                return [
                    _finding(
                        ident,
                        ctx,
                        "N001",
                        "minor",
                        "Go package names are short, lower case, without underscores or mixedCaps",
                        re.sub(r"[^a-z0-9]", "", name.lower()),
                    )
                ]
            return []
        if _is_test_function(ident, ctx) or (ctx.is_test_file and "_" in _core(name)):
            return []
        if style in ("snake", "upper_snake", "mixed", "kebab"):
            what = "constants" if ident.kind == "constant" else "names"
            return [
                _finding(
                    ident,
                    ctx,
                    "N001",
                    "minor",
                    f"Go {what} use MixedCaps (exported) or mixedCaps (unexported), not underscores",
                    go_name(name),
                )
            ]
        return []
    if ctx.language == "java" and ident.kind == "package":
        if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", name):
            return [_finding(ident, ctx, "N001", "minor", "Java package names are all lower case", name.lower())]
        return []
    if ctx.language == "java" and name == "serialVersionUID":
        return []
    if ctx.language == "shell" and ident.kind == "function":
        segments = name.split("::")
        if all(classify_style(seg) in ACCEPT["snake"] for seg in segments):
            return []
        fixed = "::".join(convert(seg, "snake") for seg in segments)
        message = "Shell function names are lower_snake_case (Google style; '::' separates libraries)"
        if "-" in name or "." in name:
            message = "Hyphens/dots in function names are a bash extension; POSIX sh allows only [A-Za-z0-9_]"
        return [_finding(ident, ctx, "N001", "minor", message, fixed)]
    expected = expected_style(ident, ctx)
    if expected is None:
        return []
    accepted, target = expected
    if style in accepted:
        return []
    shell_upper_local = ctx.language == "shell" and ident.meta.get("local") and style in ACCEPT["upper_snake"]
    severity = "info" if ident.inferred or shell_upper_local else "minor"
    label = {"snake": "snake_case", "camel": "camelCase", "pascal": "PascalCase", "upper_snake": "UPPER_SNAKE_CASE"}[
        target
    ]
    note = " (module-level literal looks like a constant)" if ident.inferred else ""
    return [
        _finding(
            ident,
            ctx,
            "N001",
            severity,
            f"{ctx.language.capitalize()} {ident.kind} names use {label}{note}",
            convert(name, target),
        )
    ]


def _rule_single(ident: Identifier, ctx: Context) -> list[Finding]:
    core = _core(ident.name)
    if len(core) != 1 or ident.is_loop or ident.kind in ("typevar", "package"):
        return []
    if ident.inferred:  # module-level literal: a global, so the loop/coordinate idioms do not apply
        return [_finding(ident, ctx, "N002", "minor", "Single-letter module-level name; say what it holds")]
    local = ident.kind in ("parameter", "variable")
    allowed = core.lower() in SINGLE_LETTER_OK.get(ctx.language, frozenset())
    if allowed and (local or (ident.kind == "field" and core.lower() in "xyz")):
        return []
    if ctx.is_test_file or (local and ctx.language == "go"):
        return [_finding(ident, ctx, "N002", "info", "Single-letter name; fine in a few-line scope, opaque beyond")]
    if local or ident.kind == "field":
        return [_finding(ident, ctx, "N002", "minor", "Single-letter name; say what it holds")]
    return [_finding(ident, ctx, "N002", "major", f"Single-letter {ident.kind} name is unsearchable and opaque")]


EMPTY_WORDS = frozenset("foo bar baz qux stuff thing things junk blah whatever dummy misc".split())
_VAGUE_MAJOR_KINDS = {"function", "class", "type", "trait", "interface", "enum"}


def _rule_vague(ident: Identifier, ctx: Context) -> list[Finding]:
    """N003. Kinds whose context supplies meaning (variants, constants, modules) are skipped."""
    base = re.sub(r"\d+$", "", _core(ident.name)).lower().replace("_", "").replace("-", "")
    kind = ident.kind
    if not base or kind in ("variant", "constant", "module", "macro", "package", "typevar"):
        return []
    if kind in _PASCAL_KINDS:
        vocabulary = VAGUE_TYPES
    elif kind == "function":
        vocabulary = VAGUE_FUNCTIONS
    elif kind in ("method", "property"):
        vocabulary = EMPTY_WORDS  # a receiver or owning type supplies the meaning
    else:
        vocabulary = VAGUE_COMMON
    if base not in vocabulary:
        return []
    if (ctx.is_test_file and base in TEST_PLACEHOLDERS) or kind == "parameter":
        severity = "info"
    elif kind in _VAGUE_MAJOR_KINDS:
        severity = "major"
    else:
        severity = "minor"
    return [
        _finding(
            ident, ctx, "N003", severity, f"'{ident.name}' says nothing about the domain; name what it holds or does"
        )
    ]


def _rule_numbered(ident: Identifier, ctx: Context) -> list[Finding]:
    words = split_words(ident.name)
    if not words or not re.search(r"[A-Za-z]\d{1,2}$", _core(ident.name)):
        return []
    last = words[-1].lower()
    stem = re.sub(r"\d+$", "", last)
    if len(stem) < 3 or last in TECH_TOKENS or _core(ident.name).lower() in TECH_TOKENS:
        return []
    return [
        _finding(
            ident,
            ctx,
            "N004",
            "info",
            "Numbered suffix; name the difference (primary_user, retry_user) instead of counting",
        )
    ]


_HUNGARIAN = (
    re.compile(r"^(?:str|sz|lst|arr|dict|obj|bool|flt|dbl)_[a-z]"),
    re.compile(r"^[mg]_[A-Za-z]"),
    re.compile(r"^(?:str|sz|lst|arr|dict|obj|bool|dbl|flt)[A-Z]"),
    re.compile(r"^(?:b|sz)[A-Z][a-z]"),
)


def _rule_hungarian(ident: Identifier, ctx: Context) -> list[Finding]:
    if ident.kind == "interface" and ctx.language in ("typescript", "java") and re.match(r"^I[A-Z][a-z]", ident.name):
        return [
            _finding(
                ident,
                ctx,
                "N005",
                "info",
                "The I-prefix on interfaces is discouraged; name the concept",
                ident.name[1:],
            )
        ]
    if ident.kind not in ("variable", "parameter", "field"):
        return []
    core = _LEADING.sub("", ident.name)
    if any(p.match(core) for p in _HUNGARIAN):
        return [
            _finding(
                ident,
                ctx,
                "N005",
                "minor",
                "Hungarian notation encodes type or scope the compiler and editor already know",
            )
        ]
    return []


def _rule_bool(ident: Identifier, ctx: Context) -> list[Finding]:
    if not ident.is_bool or ident.is_loop or ident.kind not in ("variable", "parameter", "field", "property"):
        return []
    words = [w.lower() for w in split_words(ident.name)]
    if not words:
        return []
    joined = "".join(words)
    last = words[-1]
    if (
        words[0] in BOOL_PREFIXES
        or any(joined.startswith(v) and len(joined) > len(v) + 2 for v in ("skip", "allow", "use", "show", "keep"))
        or joined in BOOL_WORDS
        or last in BOOL_WORDS
        or last.endswith(("ed", "ing", "able", "ible"))
    ):
        return []
    return [
        _finding(
            ident,
            ctx,
            "N006",
            "info",
            "Boolean reads as a noun; use a predicate (is_/has_/can_/should_ or an adjective)",
        )
    ]


def _rule_negated(ident: Identifier, ctx: Context) -> list[Finding]:
    words = split_words(ident.name)
    lower = [w.lower() for w in words]
    if len(lower) < 2:
        return []
    if lower[0] == "not":
        if not ident.is_bool:
            return []
        positive = ["is", *words[1:]]
    elif lower[1:3] == ["no", "op"]:
        return []
    elif lower[0] in ("is", "has", "can", "should", "was", "were", "does", "did", "will") and lower[1] in (
        "not",
        "no",
        "non",
    ):
        positive = [words[0], *words[2:]]
    else:
        return []
    if len(positive) < 2:
        return []
    style = classify_style(ident.name)
    prefix = re.match(r"^_*", ident.name)
    suggestion = render(positive, style if style != "lower" else "snake", prefix.group(0) if prefix else "")
    return [
        _finding(
            ident,
            ctx,
            "N007",
            "minor",
            "Negated boolean; invert it (and its call sites) to avoid double negatives",
            suggestion,
        )
    ]


def _rule_acronym(ident: Identifier, ctx: Context, case_fired: bool) -> list[Finding]:
    if ctx.language == "go" and not case_fired and ident.kind != "package" and not _is_test_function(ident, ctx):
        words = "".join(split_words(_core(ident.name)))
        fixed = go_fix_initialisms(ident.name)
        if fixed != words:
            return [
                _finding(
                    ident, ctx, "N008", "minor", "Go initialisms keep a consistent case (ID, URL, HTTP, JSON)", fixed
                )
            ]
    if ctx.language == "rust" and ident.kind in ("type", "trait", "variant") and re.search(r"[A-Z]{2,}", ident.name):
        fixed = convert(ident.name, "pascal")
        if fixed != ident.name:
            return [
                _finding(
                    ident,
                    ctx,
                    "N008",
                    "minor",
                    "Rust UpperCamelCase treats acronyms as one word (Uuid, HttpServer)",
                    fixed,
                )
            ]
    return []


def _rule_stutter(ident: Identifier, ctx: Context) -> list[Finding]:
    pkg = ctx.package
    if ctx.language != "go" or not pkg or not ident.top_level or ident.kind in ("package", "method"):
        return []
    name = ident.name
    if not name[:1].isupper() or not name.lower().startswith(pkg.lower()) or len(name) <= len(pkg):
        return []
    rest = name[len(pkg) :]
    if not rest[:1].isupper():
        return []
    rest = go_fix_initialisms(rest)
    return [_finding(ident, ctx, "N009", "minor", f"Callers write {pkg}.{name}; drop the repeated package name", rest)]


def _rule_builtin(ident: Identifier, ctx: Context) -> list[Finding]:
    if ctx.language == "python":
        table = PY_BUILTINS
        kinds = {"variable", "parameter"} | ({"function"} if ident.top_level else set())
    elif ctx.language == "go":
        table = GO_PREDECLARED
        kinds = {"variable", "parameter", "function", "type", "constant"}
    else:
        return []
    if ident.name in table and ident.kind in kinds:
        return [_finding(ident, ctx, "N010", "minor", f"Shadows the builtin '{ident.name}' in this scope")]
    return []


def _rule_long(ident: Identifier, ctx: Context) -> list[Finding]:
    if _is_test_function(ident, ctx) or ctx.is_test_file or ident.kind == "package":
        return []
    core = _core(ident.name)
    words = split_words(core)
    if len(core) > 40 or len(words) > 6:
        return [
            _finding(
                ident,
                ctx,
                "N011",
                "info",
                f"{len(core)} chars / {len(words)} words; usually a sign the unit does too much "
                "or the context already supplies some words",
            )
        ]
    return []


def _rule_abbrev(ident: Identifier, ctx: Context) -> list[Finding]:
    words = split_words(ident.name)
    lower = [re.sub(r"\d+$", "", w.lower()) for w in words]
    if not any(w in ABBREVIATIONS for w in lower):
        return []
    if len(words) == 1 and lower[0] in VAGUE_COMMON:
        return []
    expanded = [ABBREVIATIONS.get(lw, w) for w, lw in zip(words, lower)]
    style = classify_style(ident.name)
    style = {"lower": "snake", "upper": "upper_snake", "mixed": "snake"}.get(style, style)
    if ctx.language in ("javascript", "typescript", "java", "go") and classify_style(ident.name) == "lower":
        style = "camel"
    prefix = re.match(r"^_*", ident.name)
    suggestion = render(expanded, style, prefix.group(0) if prefix else "")
    if ctx.language == "go":
        suggestion = go_name(suggestion)
    found = ", ".join(sorted({w for w in lower if w in ABBREVIATIONS}))
    return [_finding(ident, ctx, "N012", "minor", f"Unclear abbreviation ({found}); spell the word out", suggestion)]


def _rule_exception(ident: Identifier, ctx: Context) -> list[Finding]:
    if ctx.language != "python" or ident.kind != "class" or not ident.meta.get("exception"):
        return []
    if ident.name.endswith(("Error", "Exception", "Warning", "Exit", "Interrupt")):
        return []
    return [
        _finding(
            ident, ctx, "N013", "info", "PEP 8: exception classes that are errors end in 'Error'", ident.name + "Error"
        )
    ]


RULE_FUNCS = (
    _rule_single,
    _rule_vague,
    _rule_hungarian,
    _rule_bool,
    _rule_negated,
    _rule_stutter,
    _rule_builtin,
    _rule_long,
    _rule_abbrev,
    _rule_exception,
)


def check_identifier(ident: Identifier, ctx: Context) -> list[Finding]:
    if not _core(ident.name) or ident.name == "_" or not ident.name.isascii():
        return []  # word-structure rules assume ASCII; leave non-ASCII names to the agent
    case = _rule_case(ident, ctx)
    findings = list(case)
    findings += _rule_acronym(ident, ctx, bool(case))
    for rule in RULE_FUNCS:
        findings += rule(ident, ctx)
    if any(f.rule == "N003" for f in findings):
        findings = [f for f in findings if f.rule != "N004"]
    else:
        findings += _rule_numbered(ident, ctx)
    return findings


def check_file_name(ctx: Context, identifiers: Sequence[Identifier]) -> list[Finding]:
    path = Path(ctx.path)
    stem = path.stem
    if ctx.path in ("<stdin>", "-"):
        return []

    def finding(message: str, suggestion: str, severity: str = "minor") -> Finding:
        return Finding(ctx.path, 1, ctx.language, "module", stem, "N014", severity, message, suggestion)

    if ctx.language == "python":
        if ctx.text.startswith("#!") or stem in ("__init__", "__main__", "conftest"):
            return []
        if classify_style(stem) not in ACCEPT["snake"]:
            return [
                finding("Python modules are short snake_case names so they can be imported", convert(stem, "snake"))
            ]
    elif ctx.language == "go":
        base = re.sub(r"_test$", "", stem)
        if re.search(r"[A-Z\-]", base):
            return [finding("Go file names are lower case (underscores allowed)", convert(base, "snake"))]
    elif ctx.language == "rust":
        if stem not in ("main", "lib", "mod", "build") and classify_style(stem) not in ACCEPT["snake"]:
            return [finding("Rust module files are snake_case", convert(stem, "snake"))]
    elif ctx.language == "java":
        public = [i for i in identifiers if i.kind in ("class", "interface") and i.top_level and i.meta.get("public")]
        if public and public[0].name != stem:
            return [
                finding(f"Public type {public[0].name} must live in {public[0].name}.java", public[0].name, "major")
            ]
    return []


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

_TOKEN = re.compile(r"[A-Za-z_$][\w$]*")


def _is_test_path(path: str, language: str) -> bool:
    p = Path(path)
    parts = set(p.parts)
    name = p.name
    if parts & {"tests", "test", "__tests__", "spec"}:
        return True
    if language == "python":
        return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
    if language == "go":
        return name.endswith("_test.go")
    if language in ("javascript", "typescript"):
        return bool(re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", name))
    if language == "java":
        return name.endswith(("Test.java", "Tests.java", "IT.java"))
    return False


def scan_source(text: str, language: str, path: str = "<stdin>", rel: str | None = None) -> ScanResult:
    """Extract identifiers from ``text`` and check them. Never raises on bad input."""
    language = LANG_ALIASES.get(language, language)
    text = text.removeprefix("\ufeff")
    if language not in EXTRACTORS:
        raise ValueError(f"unsupported language {language!r}")
    ctx = Context(
        language=language,
        path=path,
        text=text,
        is_test_file=_is_test_path(rel if rel is not None else path, language),
        jsx=path.endswith((".jsx", ".tsx")),
    )
    result = ScanResult(path=path, language=language)
    try:
        identifiers, errors = EXTRACTORS[language](ctx)
    except (RecursionError, ValueError) as exc:  # pragma: no cover - defensive
        identifiers, errors = [], [f"{type(exc).__name__}: {exc}"]
    result.identifiers, result.errors = identifiers, errors
    seen: set[tuple[int, str, str, str]] = set()
    findings: list[Finding] = []
    for ident in identifiers:
        for f in check_identifier(ident, ctx):
            key = (f.line, f.name, f.rule, f.kind)
            if key not in seen:
                seen.add(key)
                findings.append(f)
    if not errors:
        findings += check_file_name(ctx, identifiers)
    result.tokens = Counter(_TOKEN.findall(text))
    for f in findings:
        f.occurrences = result.tokens.get(f.name, 0) or text.count(f.name)
    findings.sort(key=lambda f: (f.line, f.name, f.rule))
    result.findings = findings
    return result


def detect_language(path: Path) -> str | None:
    lang = EXTENSIONS.get(path.suffix.lower())
    if lang or path.suffix:
        return lang
    try:
        with path.open("rb") as handle:
            first = handle.readline(200).decode("utf-8", "replace")
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    if re.search(r"\bpython[0-9.]*\b", first):
        return "python"
    if re.search(r"\b(?:ba|da|k|z)?sh\b", first):
        return "shell"
    if re.search(r"\bnode\b", first):
        return "javascript"
    return None


def _is_generated(text: str) -> bool:
    head = "\n".join(text.split("\n", 5)[:5])
    return "@generated" in head or ("Code generated" in head and "DO NOT EDIT" in head)


def _is_bundled(text: str) -> bool:
    """Minified or bundled JS: very long lines near the top."""
    return any(len(line) > 1000 for line in text.split("\n", 20)[:20])


def _git_files(directory: Path) -> list[str] | None:
    try:
        inside = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        listed = subprocess.run(
            ["git", "-C", str(directory), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if listed.returncode != 0:
        return None
    return [p for p in listed.stdout.split("\0") if p]


def _walk(directory: Path) -> list[str]:
    files: list[str] = []
    for root, dirs, names in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            files.append(str((Path(root) / name).relative_to(directory)))
    return files


GIT_SKIP_DIRS = frozenset({"node_modules", "vendor"})


def discover(paths: Sequence[str], excludes: Sequence[str]) -> Iterator[tuple[Path, str, str]]:
    """Yield (filesystem path, display path, path relative to the scan root) for candidate files."""

    def excluded(rel: str, display: str) -> bool:
        return any(
            fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(display, pat) or fnmatch.fnmatch(Path(rel).name, pat)
            for pat in excludes
        )

    for arg in paths:
        base = Path(arg)
        if base.is_file():
            if not excluded(base.name, arg):
                yield base, arg, base.name
            continue
        if not base.is_dir():
            print(f"naming-scan: no such file or directory: {arg}", file=sys.stderr)
            continue
        rels = _git_files(base)
        skip = GIT_SKIP_DIRS
        if rels is None:
            rels, skip = _walk(base), SKIP_DIRS
        for rel in sorted(rels):
            if set(Path(rel).parts[:-1]) & skip:
                continue
            display = str(base / rel) if arg not in (".", "./") else rel
            if not excluded(rel, display):
                yield base / rel, display, rel


def _summary(results: Sequence[ScanResult], findings: Sequence[Finding], truncated: bool) -> dict[str, Any]:
    profile: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for res in results:
        for ident in res.identifiers:
            if _core(ident.name):
                profile[res.language][ident.kind][classify_style(ident.name)] += 1
    return {
        "files_scanned": len(results),
        "identifiers": sum(len(r.identifiers) for r in results),
        "findings": len(findings),
        "by_severity": dict(Counter(f.severity for f in findings)),
        "by_rule": dict(sorted(Counter(f.rule for f in findings).items())),
        "languages": dict(Counter(r.language for r in results)),
        "style_profile": {lang: {kind: dict(c) for kind, c in kinds.items()} for lang, kinds in profile.items()},
        "truncated": truncated,
    }


def _format_text(report: dict[str, Any]) -> str:
    lines = []
    for f in report["findings"]:
        tail = f" -> {f['suggestion']}" if f["suggestion"] else ""
        uses = f" ({f['occurrences']} uses)" if f["occurrences"] > 1 else ""
        lines.append(
            f"{f['path']}:{f['line']}: {f['severity']:<5} {f['rule']} {f['kind']} "
            f"'{f['name']}' {f['message']}{tail}{uses}"
        )
    for err in report["errors"]:
        lines.append(f"{err['path']}: error: {err['message']}")
    s = report["summary"]
    sev = ", ".join(f"{k}={v}" for k, v in sorted(s["by_severity"].items(), key=lambda kv: -SEV_RANK[kv[0]]))
    severity_note = f" ({sev})" if sev else ""
    shown = f" [showing {s['reported']}]" if s["truncated"] else ""
    lines.append(
        f"-- {s['files_scanned']} files, {s['identifiers']} identifiers, {s['findings']} findings{severity_note}{shown}"
    )
    return "\n".join(lines)


def _rules_table() -> str:
    rows = ["ID    name                  default   description"]
    defaults = {
        "N001": "minor",
        "N002": "info-major",
        "N003": "info-major",
        "N004": "info",
        "N005": "minor",
        "N006": "info",
        "N007": "minor",
        "N008": "minor",
        "N009": "minor",
        "N010": "minor",
        "N011": "info",
        "N012": "minor",
        "N013": "info",
        "N014": "minor",
    }
    for rule, (name, desc) in RULES.items():
        rows.append(f"{rule}  {name:<21} {defaults[rule]:<9} {desc}")
    rows.append("critical is never emitted by the scanner: it is reserved for misleading names the agent confirms.")
    return "\n".join(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="naming-scan",
        description="Report mechanical identifier-naming problems (see SPEC.md).",
    )
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories; '-' reads stdin")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--lang", help=f"force language ({', '.join(LANGUAGES)}); required for stdin")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    parser.add_argument("--min-severity", choices=SEVERITIES[:3], default="info")
    parser.add_argument("--fail-on", choices=SEVERITIES[:3], default=None)
    parser.add_argument("--max-findings", type=int, default=1000)
    parser.add_argument("--list-rules", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_rules:
        print(_rules_table())
        return 0
    forced = LANG_ALIASES.get(args.lang, args.lang) if args.lang else None
    if forced and forced not in LANGUAGES:
        parser.error(f"unsupported --lang {args.lang!r}")

    results: list[ScanResult] = []
    if args.paths == ["-"]:
        if not forced:
            print("naming-scan: --lang is required when reading stdin", file=sys.stderr)
            return 2
        results.append(scan_source(sys.stdin.buffer.read().decode("utf-8-sig", "replace"), forced, "<stdin>"))
    else:
        missing = [p for p in args.paths if p != "-" and not Path(p).exists()]
        if missing:
            print(f"naming-scan: no such file or directory: {', '.join(missing)}", file=sys.stderr)
            return 2
        for fs_path, display, rel in discover(args.paths, args.exclude):
            explicit = display in args.paths
            language = forced if (forced and explicit) else detect_language(fs_path)
            if language is None or fs_path.name.endswith((".min.js", ".d.ts", ".d.mts", ".d.cts")):
                continue
            try:
                if fs_path.stat().st_size > MAX_FILE_BYTES:
                    print(f"naming-scan: skipping large file {display}", file=sys.stderr)
                    continue
                text = fs_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"naming-scan: skipping {display}: {exc}", file=sys.stderr)
                continue
            if _is_generated(text) or (language in ("javascript", "typescript") and _is_bundled(text)):
                continue
            results.append(scan_source(text, language, display, rel))

    totals: Counter[str] = Counter()
    for res in results:
        totals.update(res.tokens)
    findings = [f for res in results for f in res.findings]
    for f in findings:
        f.occurrences = totals.get(f.name, f.occurrences)
    fail = args.fail_on is not None and any(SEV_RANK[f.severity] >= SEV_RANK[args.fail_on] for f in findings)
    findings = [f for f in findings if SEV_RANK[f.severity] >= SEV_RANK[args.min_severity]]
    findings.sort(key=lambda f: (-SEV_RANK[f.severity], f.path, f.line, f.rule))
    summary = _summary(results, findings, truncated=len(findings) > args.max_findings)
    findings = findings[: args.max_findings]
    summary["reported"] = len(findings)
    report = {
        "version": VERSION,
        "summary": summary,
        "findings": [asdict(f) for f in findings],
        "errors": [{"path": r.path, "message": e} for r in results for e in r.errors],
    }
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(_format_text(report))
    print(f"naming-scan: {len(results)} files, {len(findings)} findings", file=sys.stderr)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
