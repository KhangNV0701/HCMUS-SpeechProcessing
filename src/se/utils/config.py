"""Tiny YAML config system with inheritance and dotted CLI overrides.

A config file may contain a top-level ``base:`` key pointing (relative to the
file) to another YAML file. The child is deep-merged on top of the base.

CLI overrides use dotted keys, e.g. ``train.epochs=10 loss.metric=0``. Values
are parsed with ``yaml.safe_load`` so ``true``, ``1e-4``, ``[1, 2]`` work.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Iterable

import yaml


class Config(dict):
    """dict with attribute access (read-only convenience)."""

    def __getattr__(self, item: str) -> Any:
        try:
            value = self[item]
        except KeyError as exc:  # pragma: no cover - debugging aid
            raise AttributeError(item) from exc
        return value

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    @staticmethod
    def wrap(obj: Any) -> Any:
        if isinstance(obj, dict):
            return Config({k: Config.wrap(v) for k, v in obj.items()})
        if isinstance(obj, list):
            return [Config.wrap(v) for v in obj]
        return obj

    def to_dict(self) -> dict:
        def unwrap(o: Any) -> Any:
            if isinstance(o, dict):
                return {k: unwrap(v) for k, v in o.items()}
            if isinstance(o, list):
                return [unwrap(v) for v in o]
            return o

        return unwrap(self)


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    base = data.pop("base", None)
    if base is not None:
        base_path = (path.parent / base).resolve()
        data = deep_merge(_load_yaml(base_path), data)
    return data


def apply_overrides(cfg: dict, overrides: Iterable[str]) -> dict:
    cfg = copy.deepcopy(cfg)
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"Override must look like key.sub=value, got {item!r}")
        key, raw = item.split("=", 1)
        value = yaml.safe_load(raw)
        node = cfg
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return cfg


def load_config(path: str | Path, overrides: Iterable[str] = ()) -> Config:
    cfg = _load_yaml(Path(path).resolve())
    cfg = apply_overrides(cfg, overrides)
    return Config.wrap(cfg)


def save_config(cfg: dict, path: str | Path) -> None:
    data = cfg.to_dict() if isinstance(cfg, Config) else cfg
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
