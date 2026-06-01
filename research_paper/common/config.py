"""Configuration helpers for paper-only experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "None"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Load the small YAML subset used by paper configs when PyYAML is absent."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while indent <= stack[-1][0] and len(stack) > 1:
            stack.pop()
        container = stack[-1][1]

        if line.startswith("- "):
            if not isinstance(container, list):
                raise ValueError(f"Invalid YAML list item: {raw}")
            container.append(_parse_scalar(line[2:]))
            continue

        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"Invalid YAML line: {raw}")
        key = key.strip()
        value = value.strip()

        if not isinstance(container, dict):
            raise ValueError(f"Invalid YAML mapping item: {raw}")

        if value == ">":
            block_lines: list[str] = []
            while i < len(lines):
                candidate = lines[i]
                candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                if candidate.strip() and candidate_indent <= indent:
                    break
                block_lines.append(candidate.strip())
                i += 1
            container[key] = " ".join(part for part in block_lines if part)
            continue

        if value:
            container[key] = _parse_scalar(value)
            continue

        next_non_empty = ""
        for probe in lines[i:]:
            if probe.strip() and not probe.lstrip().startswith("#"):
                next_non_empty = probe.strip()
                break
        child: dict[str, Any] | list[Any] = [] if next_non_empty.startswith("- ") else {}
        container[key] = child
        stack.append((indent, child))

    return root


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
    except ModuleNotFoundError:
        loaded = _minimal_yaml_load(text)

    if not isinstance(loaded, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return loaded


def validate_isolation(config: dict[str, Any]) -> None:
    isolation = config.get("isolation", {})
    forbidden_true_flags = {
        "production_imports_allowed",
        "allow_live_trading",
        "allow_notifications",
        "allow_production_database_writes",
    }
    unsafe = [name for name in forbidden_true_flags if isolation.get(name) is True]
    if unsafe:
        raise RuntimeError(f"Unsafe research isolation flags are enabled: {', '.join(sorted(unsafe))}")
