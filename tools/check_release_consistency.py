"""Dependency-free release metadata and integration quality checks."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def require_semver(label: str, value: str) -> None:
    if not SEMVER.fullmatch(value):
        raise SystemExit(f"{label} is not semantic version X.Y.Z: {value!r}")


def python_constant(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"), path.as_posix())
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = ast.literal_eval(statement.value)
                    if isinstance(value, str):
                        return value
    raise SystemExit(f"{name} not found in {path.relative_to(ROOT)}")


def matched_value(path: Path, pattern: str, label: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise SystemExit(f"{label} not found in {path.relative_to(ROOT)}")
    return match.group(1)


def main() -> None:
    server_python = python_constant(
        ROOT / "roomhub/server/app/config.py", "VERSION"
    )
    server_addon = matched_value(
        ROOT / "roomhub/server/config.yaml",
        r"^version:\s*['\"]?([^'\"\s]+)",
        "add-on version",
    )
    if server_python != server_addon:
        raise SystemExit(
            f"server version mismatch: app={server_python}, add-on={server_addon}"
        )
    require_semver("server version", server_python)

    endpoint = matched_value(
        ROOT / "firmware/endpoint/CMakeLists.txt",
        r"^project\(roomhub_endpoint VERSION ([^)]+)\)$",
        "endpoint version",
    )
    require_semver("endpoint version", endpoint)

    integration_dir = ROOT / "custom_components/roomhub"
    documents = {
        path: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(integration_dir.rglob("*.json"))
    }
    manifest = documents[integration_dir / "manifest.json"]
    if manifest.get("domain") != "roomhub":
        raise SystemExit("integration manifest domain must be roomhub")
    require_semver("integration version", manifest.get("version", ""))
    if documents[integration_dir / "strings.json"] != documents[
        integration_dir / "translations/en.json"
    ]:
        raise SystemExit("strings.json and translations/en.json differ")

    installer_package = json.loads(
        (ROOT / "installer/vendor/esp-web-tools/package.json").read_text(
            encoding="utf-8"
        )
    )
    require_semver(
        "vendored esp-web-tools version", installer_package.get("version", "")
    )
    print(
        "Release metadata consistent: "
        f"server {server_python}, endpoint {endpoint}, "
        f"integration {manifest['version']}"
    )


if __name__ == "__main__":
    main()
