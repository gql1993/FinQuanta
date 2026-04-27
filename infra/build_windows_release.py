from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

INCLUDE_DIRS = [
    ".streamlit",
    "api_server",
    "core",
    "desktop",
    "doc",
    "infra",
    "infrastructure",
    "pages",
    "scripts",
    "services",
    "ui",
]

INCLUDE_GLOBS = [
    "*.bat",
    "*.ps1",
    "*.py",
    "requirements*.txt",
    "README*.md",
    ".env.api*.example",
]

EXCLUDE_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "logs",
    "data_cache",
    "output",
    "claude-code-main",
    "node_modules",
    ".venv",
    "venv",
    "_docx_extract",
    "tests",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".docx",
    ".pptx",
}


def _is_excluded(path: Path) -> bool:
    rel_parts = set(path.relative_to(ROOT).parts)
    if rel_parts & EXCLUDE_PARTS:
        return True
    return path.suffix.lower() in EXCLUDE_SUFFIXES


def _iter_files() -> list[Path]:
    files: set[Path] = set()
    for dirname in INCLUDE_DIRS:
        base = ROOT / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not _is_excluded(path):
                files.add(path)
    for pattern in INCLUDE_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file() and not _is_excluded(path):
                files.add(path)
    return sorted(files, key=lambda item: item.as_posix().lower())


def _copy_files(files: list[Path], target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for src in files:
        rel = src.relative_to(ROOT)
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _write_manifest(target: Path, files: list[Path], package_name: str) -> None:
    manifest = target / "DEPLOYMENT_MANIFEST.md"
    commands = [
        "python -m pip install -r requirements.txt",
        "copy .env.api.example .env.api",
        "accept_windows_release.bat",
        "python -m pip install -r requirements.txt",
        "accept_windows_release.bat --check-deps",
        "start_api.bat",
        "install_api_task.bat --start",
        "accept_windows_release.bat --smoke-openclaw",
        "accept_windows_release.bat --smoke-openclaw --check-trade-safety --require-buy-disabled",
        "smoke_openclaw_daemon.bat --require-task --require-daemon-active --require-last-run --require-ready --require-security-ready",
        "check_trade_channel_safety.bat --require-buy-disabled --require-last-run-success",
        "replay_openclaw_history.bat --output logs\\openclaw_history_replay_report.json",
        "e2e_openclaw_unattended.bat --require-buy-disabled --require-simulation-pass",
    ]
    lines = [
        f"# {package_name}",
        "",
        f"- Built at: {datetime.now().isoformat(timespec='seconds')}",
        f"- File count: {len(files)}",
        "",
        "## Suggested Windows Deployment Commands",
        "",
    ]
    lines.extend([f"```bat\n{cmd}\n```" for cmd in commands])
    lines.extend([
        "",
        "## Notes",
        "",
        "- Runtime data, logs, local databases, virtualenvs, and previous build outputs are intentionally excluded.",
        "- Run `verify_windows_release.bat` after transfer to validate package checksums.",
        "- Run `check_windows_release_ready.bat --strict` before installing the API task/service.",
        "- Or run `accept_windows_release.bat` to execute checksum and strict preflight in order.",
        "- After `pip install`, run `accept_windows_release.bat --check-deps` to verify Python dependencies.",
        "- Acceptance runs write `ACCEPTANCE_REPORT.json` for handover/audit.",
        "- Edit `.env.api` before installing the API task/service in production.",
        "- Change the default API admin password before running strict production smoke checks.",
        "",
    ])
    manifest.write_text("\n".join(lines), encoding="utf-8")


def _git_value(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            shell=False,
            timeout=5,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception:
        pass
    return ""


def _git_dirty_lines() -> list[str]:
    status = _git_value(["status", "--porcelain"])
    return [line for line in status.splitlines() if line.strip()]


def _write_release_info(target: Path, files: list[Path], package_name: str) -> Path:
    dirty_lines = _git_dirty_lines()
    release_info = {
        "package_name": package_name,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git": {
            "branch": _git_value(["rev-parse", "--abbrev-ref", "HEAD"]),
            "commit": _git_value(["rev-parse", "HEAD"]),
            "dirty": bool(dirty_lines),
            "dirty_count": len(dirty_lines),
        },
        "source_file_count": len(files),
        "checksum_manifest": "DEPLOYMENT_CHECKSUMS.sha256",
        "excludes": {
            "parts": sorted(EXCLUDE_PARTS),
            "suffixes": sorted(EXCLUDE_SUFFIXES),
        },
    }
    path = target / "RELEASE_INFO.json"
    path.write_text(json.dumps(release_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksums(target: Path) -> Path:
    checksum_path = target / "DEPLOYMENT_CHECKSUMS.sha256"
    rows = []
    for path in sorted(target.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file() or path == checksum_path:
            continue
        rel = path.relative_to(target).as_posix()
        rows.append(f"{_sha256(path)}  {rel}")
    checksum_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return checksum_path


def _zip_dir(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in source_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(source_dir.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Windows deployment package for FinQuanta.")
    parser.add_argument("--name", default="", help="Package directory name. Defaults to FinQuanta-windows-<timestamp>.")
    parser.add_argument("--output", default="dist/releases", help="Output directory.")
    parser.add_argument("--no-zip", action="store_true", help="Do not create a zip archive.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned files without copying.")
    parser.add_argument("--require-clean-git", action="store_true", help="Fail if git working tree has uncommitted changes.")
    args = parser.parse_args()

    package_name = args.name.strip() or f"FinQuanta-windows-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output_dir = (ROOT / args.output).resolve()
    package_dir = output_dir / package_name
    files = _iter_files()
    dirty_lines = _git_dirty_lines()

    print(f"ROOT={ROOT}")
    print(f"PACKAGE={package_dir}")
    print(f"FILES={len(files)}")
    print(f"GIT_DIRTY={bool(dirty_lines)}")
    if args.require_clean_git and dirty_lines:
        print("[FAIL] git working tree is dirty; commit/stash changes before production release")
        for line in dirty_lines[:20]:
            print(f"[GIT] {line}")
        return 2
    if args.dry_run:
        for path in files:
            print(path.relative_to(ROOT).as_posix())
        return 0

    _copy_files(files, package_dir)
    _write_manifest(package_dir, files, package_name)
    release_info_path = _write_release_info(package_dir, files, package_name)
    print(f"RELEASE_INFO={release_info_path}")
    checksum_path = _write_checksums(package_dir)
    print(f"CHECKSUMS={checksum_path}")
    if not args.no_zip:
        zip_path = output_dir / f"{package_name}.zip"
        _zip_dir(package_dir, zip_path)
        print(f"ZIP={zip_path}")
    print("[RESULT] release package built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
