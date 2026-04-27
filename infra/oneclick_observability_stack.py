from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
COMPOSE_FILE = INFRA / "observability" / "docker-compose.observability.yml"
LOGS_DIR = ROOT / "logs" / "observability"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.setup_grafana_provisioning import setup_grafana_provisioning


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return int(proc.returncode), output.strip()


def command_exists(name: str) -> bool:
    return bool(shutil.which(name))


def is_port_in_use(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        return sock.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        sock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="One-click observability stack setup (Grafana + Tempo).")
    parser.add_argument("--api-base", default=os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--up", action="store_true", help="Run docker compose up -d after provisioning.")
    parser.add_argument("--down", action="store_true", help="Run docker compose down.")
    parser.add_argument("--skip-checks", action="store_true", help="Skip docker/port pre-checks.")
    args = parser.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    provisioning = setup_grafana_provisioning(
        output_dir=INFRA / "grafana" / "provisioning",
        api_base=str(args.api_base),
        overwrite=bool(args.overwrite),
    )

    result: dict[str, object] = {
        "provisioning": provisioning,
        "compose_file": str(COMPOSE_FILE),
        "logs_dir": str(LOGS_DIR),
        "commands": [],
    }

    checks: dict[str, object] = {
        "docker_available": command_exists("docker"),
        "recommended_grafana_plugin": "yesoreyeram-infinity-datasource",
        "ports_in_use": {str(p): is_port_in_use(p) for p in (3000, 3100, 3200, 4318)},
    }
    result["checks"] = checks

    if not args.skip_checks and not bool(checks["docker_available"]):
        result["error"] = "docker command not found"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    compose_cmd = ["docker", "compose", "-f", str(COMPOSE_FILE)]
    if args.down:
        code, output = run_command(compose_cmd + ["down"], cwd=ROOT)
        result["commands"].append({"cmd": "down", "exit_code": code, "output": output})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code

    if args.up:
        if not args.skip_checks:
            occupied = [port for port, in_use in checks["ports_in_use"].items() if in_use]
            if occupied:
                result["error"] = f"ports already in use: {', '.join(occupied)}"
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 3
        code, output = run_command(compose_cmd + ["up", "-d"], cwd=ROOT)
        result["commands"].append({"cmd": "up -d", "exit_code": code, "output": output})
        if code == 0:
            result["urls"] = {
                "grafana": "http://127.0.0.1:3000",
                "tempo": "http://127.0.0.1:3200",
                "loki": "http://127.0.0.1:3100",
                "tempo_otlp_http": "http://127.0.0.1:4318/v1/traces",
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code

    result["next"] = [
        f"docker compose -f {COMPOSE_FILE} up -d",
        f"docker compose -f {COMPOSE_FILE} down",
    ]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
