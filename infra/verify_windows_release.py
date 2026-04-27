from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"invalid checksum line: {line}")
        rows.append((parts[0].lower(), parts[1].strip()))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a FinQuanta Windows deployment package.")
    parser.add_argument("--root", default=".", help="Package root directory.")
    parser.add_argument("--manifest", default="DEPLOYMENT_CHECKSUMS.sha256", help="Checksum manifest path.")
    parser.add_argument("--quiet", action="store_true", help="Only print the final result.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = root / manifest
    if not manifest.exists():
        raise FileNotFoundError(f"checksum manifest not found: {manifest}")

    rows = _load_manifest(manifest)
    missing: list[str] = []
    changed: list[str] = []
    checked = 0
    for expected, rel in rows:
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        actual = _sha256(path)
        if actual.lower() != expected:
            changed.append(rel)
            continue
        checked += 1

    if not args.quiet:
        print(f"ROOT={root}")
        print(f"MANIFEST={manifest}")
        print(f"CHECKED={checked}")
        print(f"MISSING={len(missing)}")
        print(f"CHANGED={len(changed)}")
        for rel in missing[:20]:
            print(f"[MISSING] {rel}")
        for rel in changed[:20]:
            print(f"[CHANGED] {rel}")

    ok = not missing and not changed
    print("[RESULT] PASS" if ok else "[RESULT] FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
