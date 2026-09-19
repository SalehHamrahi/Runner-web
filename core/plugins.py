from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

LOGGER = logging.getLogger("runner.plugins")

HOOKS = {
    "on_event",
    "on_match_finished",
    "on_tournament_finished",
}


@dataclass(frozen=True)
class PluginInfo:
    name: str
    version: str
    description: str
    hooks: tuple[str, ...]
    path: Path
    enabled: bool = True


@dataclass(frozen=True)
class LoadedPlugin:
    info: PluginInfo
    module: ModuleType


def _plugin_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path for path in root.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("_")
    )


def _load_module(path: Path) -> ModuleType:
    module_name = f"runner_plugin_{path.stem}_{abs(hash(path.resolve())):x}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _info_from_module(module: ModuleType, path: Path) -> PluginInfo:
    meta = getattr(module, "PLUGIN", None)
    if not isinstance(meta, dict):
        raise ValueError("PLUGIN must be a dictionary")

    name = str(meta.get("name") or path.stem).strip()
    version = str(meta.get("version") or "0.1.0").strip()
    description = str(meta.get("description") or "").strip()
    declared_hooks = meta.get("hooks")
    if declared_hooks is None:
        declared_hooks = [hook for hook in HOOKS if callable(getattr(module, hook, None))]
    if not isinstance(declared_hooks, (list, tuple, set)):
        raise ValueError("PLUGIN['hooks'] must be a list, tuple, or set")
    hooks = tuple(sorted({str(hook) for hook in declared_hooks}))
    unknown = set(hooks) - HOOKS
    if unknown:
        raise ValueError(f"unsupported hooks: {', '.join(sorted(unknown))}")
    return PluginInfo(name=name, version=version, description=description, hooks=hooks, path=path)


def discover_plugins(root: Path) -> list[PluginInfo]:
    results: list[PluginInfo] = []
    for path in _plugin_files(root):
        try:
            module = _load_module(path)
            results.append(_info_from_module(module, path))
        except Exception as exc:  # discovery should never break Runner
            LOGGER.warning("Plugin %s skipped: %s", path.name, exc)
    return results


def load_plugins(root: Path) -> list[LoadedPlugin]:
    results: list[LoadedPlugin] = []
    for path in _plugin_files(root):
        try:
            module = _load_module(path)
            info = _info_from_module(module, path)
            results.append(LoadedPlugin(info=info, module=module))
        except Exception as exc:
            LOGGER.warning("Plugin %s skipped: %s", path.name, exc)
    return results


def run_hook(root: Path, hook: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if hook not in HOOKS:
        raise ValueError(f"Unsupported plugin hook: {hook}")
    payload = dict(context or {})
    results: list[dict[str, Any]] = []
    for plugin in load_plugins(root):
        if hook not in plugin.info.hooks:
            continue
        handler = getattr(plugin.module, hook, None)
        if not callable(handler):
            continue
        try:
            value = handler(dict(payload))
            results.append({"plugin": plugin.info.name, "hook": hook, "result": value})
        except Exception as exc:
            LOGGER.exception("Plugin %s failed in %s", plugin.info.name, hook)
            results.append({"plugin": plugin.info.name, "hook": hook, "error": str(exc)})
    return results


def plugin_summary(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "name": info.name,
            "version": info.version,
            "description": info.description,
            "hooks": list(info.hooks),
            "path": str(info.path),
        }
        for info in discover_plugins(root)
    ]


def plugin_details(root: Path, name: str) -> dict[str, Any] | None:
    normalized = name.strip().lower()
    for info in discover_plugins(root):
        if info.name.lower() == normalized:
            return {
                "name": info.name,
                "version": info.version,
                "description": info.description,
                "hooks": list(info.hooks),
                "path": str(info.path),
            }
    return None


def write_plugin_template(root: Path, name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name).strip("_") or "example"
    path = root / f"{safe}.py"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(
        '''PLUGIN = {\n    "name": "''' + safe + '''",\n    "version": "0.1.0",\n    "description": "Runner plugin",\n    "hooks": ["on_match_finished"],\n}\n\n\ndef on_match_finished(context):\n    # context contains tournament_id, match_id, db_path and event data.\n    return {"ok": True, "match_id": context.get("match_id")}\n''',
        encoding="utf-8",
    )
    return path
