from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "review_topic.yml"
PLACEHOLDER_PATTERNS = [
    re.compile(r"\b(?:TODO|TBD)\b", re.I),
    re.compile(r"\b(?:REPLACE|YOUR|EDIT)_WITH_[A-Z0-9_]+\b", re.I),
    re.compile(r"<[^>\n]+>"),
    re.compile(r"\{\{[^}\n]+\}\}"),
]


def add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=os.getenv("REVIEW_CONFIG"),
        help="Review topic YAML config. Defaults to config/review_topic.yml or REVIEW_CONFIG.",
    )


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")
    validate_no_placeholders(config, config_path)
    config["_config_path"] = str(config_path)
    return config


def find_placeholders(value: Any, path: str = "") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            matches.extend(find_placeholders(child, child_path))
        return matches
    if isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(find_placeholders(child, f"{path}[{index}]"))
        return matches
    if isinstance(value, str):
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(value):
                matches.append(path or "<root>")
                break
    return matches


def validate_no_placeholders(config: dict[str, Any], config_path: Path) -> None:
    placeholders = find_placeholders(config)
    if not placeholders:
        return
    preview = ", ".join(placeholders[:8])
    suffix = "" if len(placeholders) <= 8 else f", ... ({len(placeholders)} total)"
    raise ValueError(
        f"Review config still contains placeholder values in {config_path}: {preview}{suffix}. "
        "Edit config/review_topic.yml or pass a completed file with --config before running workflow scripts."
    )


def get_nested(config: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    current: Any = config
    for key in dotted_key.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def resolve_path(config: dict[str, Any], dotted_key: str, default: str) -> Path:
    value = get_nested(config, dotted_key, default)
    path = Path(str(value))
    return path if path.is_absolute() else PROJECT_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def render_template(template: str, variables: dict[str, Any]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return " ".join(rendered.split())


def lower_terms(values: list[Any] | None) -> list[str]:
    return [str(value).lower() for value in values or []]
