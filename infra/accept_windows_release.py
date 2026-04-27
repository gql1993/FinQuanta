from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def _load_release_info(root: Path) -> dict:
    path = root / "RELEASE_INFO.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def _tail_text(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[-limit:], True


def _run_step(name: str, cmd: list[str], cwd: Path, output_limit: int) -> dict:
    print(f"\n[STEP] {name}")
    print(" ".join(cmd))
    started_at = datetime.now().isoformat(timespec="seconds")
    start = time.time()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = round(time.time() - start, 3)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
    if proc.returncode == 0:
        print(f"[PASS] {name}")
        status = "pass"
    else:
        print(f"[FAIL] {name}: exit_code={proc.returncode}")
        status = "fail"
    stdout_tail, stdout_truncated = _tail_text(stdout, output_limit)
    stderr_tail, stderr_truncated = _tail_text(stderr, output_limit)
    return {
        "name": name,
        "command": cmd,
        "started_at": started_at,
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "status": status,
        "stdout": stdout_tail,
        "stderr": stderr_tail,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


def _write_report(root: Path, report_path: Path, args: argparse.Namespace, steps: list[dict], ok: bool) -> None:
    payload = {
        "status": "pass" if ok else "fail",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "release_info": _load_release_info(root),
        "options": {
            "skip_checksum": bool(args.skip_checksum),
            "strict_preflight": not bool(args.non_strict_preflight),
            "check_deps": bool(args.check_deps),
            "strict_deps": bool(args.strict_deps),
            "smoke_openclaw": bool(args.smoke_openclaw),
            "check_trade_safety": bool(args.check_trade_safety),
            "require_buy_disabled": bool(args.require_buy_disabled),
            "require_simulation_pass": bool(args.require_simulation_pass),
            "openclaw_e2e": bool(args.openclaw_e2e),
            "task_name": args.task_name,
            "report_output_limit": int(args.report_output_limit),
        },
        "steps": steps,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FinQuanta Windows release acceptance checks in order.")
    parser.add_argument("--root", default=".", help="Package root directory.")
    parser.add_argument("--skip-checksum", action="store_true", help="Skip checksum verification.")
    parser.add_argument("--non-strict-preflight", action="store_true", help="Do not fail on preflight warnings.")
    parser.add_argument("--check-deps", action="store_true", help="Check Python runtime dependencies after preflight.")
    parser.add_argument("--strict-deps", action="store_true", help="Fail if optional runtime dependencies are missing.")
    parser.add_argument("--smoke-openclaw", action="store_true", help="Run strict OpenClaw daemon smoke after preflight.")
    parser.add_argument("--check-trade-safety", action="store_true", help="Run read-only real trading channel safety checks.")
    parser.add_argument("--require-buy-disabled", action="store_true", help="Require unattended buy to remain disabled in trade safety checks.")
    parser.add_argument("--require-simulation-pass", action="store_true", help="Require unattended simulation gate to be passed in safety/e2e checks.")
    parser.add_argument("--openclaw-e2e", action="store_true", help="Run read-only unattended OpenClaw end-to-end checks.")
    parser.add_argument("--task-name", default="FinQuantaApiService", help="Windows scheduled task name for smoke.")
    parser.add_argument("--report", default="ACCEPTANCE_REPORT.json", help="Acceptance report path, relative to package root by default.")
    parser.add_argument("--report-output-limit", type=int, default=12000, help="Max stdout/stderr chars stored per step.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    ok = True
    steps: list[dict] = []

    if not args.skip_checksum:
        step = _run_step(
            "verify_checksums",
            [sys.executable, "infra/verify_windows_release.py", "--root", str(root)],
            root,
            args.report_output_limit,
        )
        steps.append(step)
        ok &= step["status"] == "pass"

    preflight_cmd = [sys.executable, "infra/check_windows_release_ready.py", "--root", str(root)]
    if not args.non_strict_preflight:
        preflight_cmd.append("--strict")
    if args.skip_checksum:
        preflight_cmd.append("--skip-checksum")
    step = _run_step("release_preflight", preflight_cmd, root, args.report_output_limit)
    steps.append(step)
    ok &= step["status"] == "pass"

    if args.check_deps:
        deps_cmd = [sys.executable, "infra/check_runtime_dependencies.py"]
        if args.strict_deps:
            deps_cmd.append("--strict")
        step = _run_step("runtime_dependencies", deps_cmd, root, args.report_output_limit)
        steps.append(step)
        ok &= step["status"] == "pass"

    if args.smoke_openclaw:
        step = _run_step(
            "openclaw_strict_smoke",
            [
                sys.executable,
                "infra/smoke_openclaw_daemon.py",
                "--require-task",
                "--require-daemon-active",
                "--require-last-run",
                "--require-ready",
                "--require-security-ready",
                "--task-name",
                args.task_name,
            ],
            root,
            args.report_output_limit,
        )
        steps.append(step)
        ok &= step["status"] == "pass"

    if args.check_trade_safety:
        trade_cmd = [
            sys.executable,
            "infra/check_trade_channel_safety.py",
            "--require-last-run-success",
            "--output-json",
            "logs/trade_channel_safety_report.json",
        ]
        if args.require_buy_disabled:
            trade_cmd.append("--require-buy-disabled")
        if args.require_simulation_pass:
            trade_cmd.append("--require-simulation-pass")
        step = _run_step("trade_channel_safety", trade_cmd, root, args.report_output_limit)
        steps.append(step)
        ok &= step["status"] == "pass"

    if args.openclaw_e2e:
        e2e_cmd = [
            sys.executable,
            "infra/e2e_openclaw_unattended.py",
            "--output",
            "logs/openclaw_unattended_e2e_report.json",
        ]
        if args.require_buy_disabled:
            e2e_cmd.append("--require-buy-disabled")
        if args.require_simulation_pass:
            e2e_cmd.append("--require-simulation-pass")
        step = _run_step("openclaw_unattended_e2e", e2e_cmd, root, args.report_output_limit)
        steps.append(step)
        ok &= step["status"] == "pass"

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = root / report_path
    _write_report(root, report_path, args, steps, ok)
    print(f"[REPORT] {report_path}")
    print("\n[RESULT] PASS" if ok else "\n[RESULT] FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
