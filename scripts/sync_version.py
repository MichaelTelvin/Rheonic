#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"


def read_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("VERSION is empty")
    return version


def pep440_from_semver(version: str) -> str:
    return re.sub(r"-beta\.(\d+)$", r"b\1", version)


def replace_first(pattern: str, replacement: str, path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, original, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"Could not update version in {path}")
    path.write_text(updated, encoding="utf-8")


def update_package_json(path: Path, version: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = version
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def update_package_lock(path: Path, version: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = version
    packages = payload.get("packages")
    if isinstance(packages, dict) and "" in packages and isinstance(packages[""], dict):
        packages[""]["version"] = version
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    version = read_version()
    python_version = pep440_from_semver(version)

    replace_first(r'^version = "[^"]+"$', f'version = "{version}"', ROOT / "backend/pyproject.toml")
    replace_first(r'^version = "[^"]+"$', f'version = "{python_version}"', ROOT / "sdk-python/pyproject.toml")

    update_package_json(ROOT / "frontend/package.json", version)
    update_package_lock(ROOT / "frontend/package-lock.json", version)
    update_package_json(ROOT / "sdk-node/package.json", version)
    update_package_lock(ROOT / "sdk-node/package-lock.json", version)


if __name__ == "__main__":
    main()
