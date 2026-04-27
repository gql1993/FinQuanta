from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REQUIRED_FILES = [
    "requirements.txt",
    ".env.api.example",
    ".env.api.production.example",
    "start_api.bat",
    "start_api_service.bat",
    "install_api_task.bat",
    "install_api_windows_service.bat",
    "smoke_openclaw_daemon.bat",
    "check_trade_channel_safety.bat",
    "e2e_openclaw_unattended.bat",
    "replay_openclaw_history.bat",
    "accept_windows_release.bat",
    "check_runtime_dependencies.bat",
    "verify_windows_release.bat",
    "DEPLOYMENT_MANIFEST.md",
    "DEPLOYMENT_CHECKSUMS.sha256",
    "RELEASE_INFO.json",
]

REQUIRED_DIRS = [
    "api_server",
    "core",
    "desktop",
    "infra",
    "infrastructure",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.replace("\x00", "").strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip().lstrip("\ufeff")] = value.strip()
    return values


def _verify_checksums(root: Path, manifest: Path) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    changed: list[str] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            changed.append(f"<invalid manifest line: {line}>")
            continue
        expected, rel = parts[0].lower(), parts[1].strip()
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        if _sha256(path).lower() != expected:
            changed.append(rel)
    return missing, changed


def _is_placeholder(value: str) -> bool:
    text = str(value or "").strip()
    return not text or text.upper().startswith("CHANGE_ME")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight-check an unpacked FinQuanta Windows deployment package.")
    parser.add_argument("--root", default=".", help="Package root directory.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--skip-checksum", action="store_true", help="Skip DEPLOYMENT_CHECKSUMS.sha256 validation.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < (3, 10):
        errors.append(f"Python >= 3.10 required, current is {sys.version.split()[0]}")

    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")
    for rel in REQUIRED_DIRS:
        if not (root / rel).is_dir():
            errors.append(f"missing required directory: {rel}")

    env_path = root / ".env.api"
    if not env_path.exists():
        warnings.append(".env.api not found; copy .env.api.example to .env.api and edit it before installing service/task")
    else:
        env = _read_env(env_path)
        is_prod = env.get("FINQUANTA_ENV", "").lower() == "prod"
        if env.get("FINQUANTA_API_AUTOSTART_DAEMON") != "1":
            warnings.append("FINQUANTA_API_AUTOSTART_DAEMON is not 1; unattended daemon may not start with API")
        if not env.get("FINQUANTA_API_BASE"):
            warnings.append("FINQUANTA_API_BASE is empty in .env.api")
        if is_prod and env.get("FINQUANTA_DB_BACKEND", "").lower() == "sqlite":
            warnings.append("FINQUANTA_DB_BACKEND=sqlite in prod; PostgreSQL is recommended for unattended production API")
        if is_prod and env.get("FINQUANTA_DB_BACKEND", "").lower() == "postgres" and _is_placeholder(env.get("FINQUANTA_POSTGRES_DSN", "")):
            warnings.append("FINQUANTA_POSTGRES_DSN is empty or still uses CHANGE_ME placeholder")
        if is_prod and env.get("FINQUANTA_CORS_ORIGINS", "").strip() == "*":
            warnings.append("FINQUANTA_CORS_ORIGINS=* in prod; restrict allowed origins before exposing API")
        if is_prod and _is_placeholder(env.get("FINQUANTA_CORS_ORIGINS", "")):
            warnings.append("FINQUANTA_CORS_ORIGINS is empty or still uses CHANGE_ME placeholder")
        if is_prod and _is_placeholder(env.get("FINQUANTA_OBSERVABILITY_READ_TOKEN", "")):
            warnings.append("FINQUANTA_OBSERVABILITY_READ_TOKEN is empty or still uses CHANGE_ME placeholder")
        gateway_enabled = env.get("FINQUANTA_OPENCLAW_GATEWAY_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
        if is_prod and gateway_enabled and _is_placeholder(env.get("FINQUANTA_OPENCLAW_GATEWAY_TOKEN", "")):
            warnings.append("OpenClaw gateway is enabled but FINQUANTA_OPENCLAW_GATEWAY_TOKEN is empty or still uses CHANGE_ME placeholder")

    manifest = root / "DEPLOYMENT_CHECKSUMS.sha256"
    if not args.skip_checksum and manifest.exists():
        missing, changed = _verify_checksums(root, manifest)
        for rel in missing[:20]:
            errors.append(f"checksum missing file: {rel}")
        for rel in changed[:20]:
            errors.append(f"checksum changed file: {rel}")

    release_info = {}
    release_info_path = root / "RELEASE_INFO.json"
    if release_info_path.exists():
        try:
            release_info = json.loads(release_info_path.read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"RELEASE_INFO.json cannot be parsed: {exc}")

    print(f"ROOT={root}")
    print(f"PYTHON={sys.version.split()[0]}")
    if release_info:
        git = release_info.get("git", {}) or {}
        print(f"PACKAGE={release_info.get('package_name', '-')}")
        print(f"BUILT_AT={release_info.get('built_at', '-')}")
        print(f"GIT_COMMIT={str(git.get('commit', '-') or '-')[:12]}")
        print(f"GIT_BRANCH={git.get('branch', '-')}")
        print(f"GIT_DIRTY={git.get('dirty', '-')}")
    for item in errors:
        print(f"[FAIL] {item}")
    for item in warnings:
        print(f"[WARN] {item}")
    failed = bool(errors) or (args.strict and bool(warnings))
    print("[RESULT] PASS" if not failed else "[RESULT] FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
