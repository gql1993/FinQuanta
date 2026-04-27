from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "infra" / "dashboard_examples"

DEFAULT_DATASOURCE_YAML = """apiVersion: 1
datasources:
  - name: FinQuanta Tempo
    uid: tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
    editable: true
  - name: FinQuanta Loki
    uid: loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: true
  - name: FinQuanta Infinity
    uid: infinity
    type: yesoreyeram-infinity-datasource
    access: proxy
    isDefault: false
    editable: true
    jsonData:
      allowedHosts:
        - "*"
"""

DEFAULT_DASHBOARD_PROVIDER_YAML = """apiVersion: 1
providers:
  - name: FinQuanta Dashboards
    orgId: 1
    folder: FinQuanta
    type: file
    disableDeletion: false
    allowUiUpdates: true
    options:
      path: {dashboards_path}
"""


def _replace_api_base(content: str, api_base: str) -> str:
    return content.replace("http://127.0.0.1:9000", api_base.rstrip("/"))


def _write_text(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def setup_grafana_provisioning(output_dir: Path, api_base: str, overwrite: bool = False) -> dict:
    datasources_dir = output_dir / "datasources"
    dashboards_cfg_dir = output_dir / "dashboards"
    dashboard_json_dir = output_dir / "dashboards_json"

    datasource_file = datasources_dir / "finquanta-infinity.yaml"
    provider_file = dashboards_cfg_dir / "finquanta-dashboards.yaml"

    _write_text(datasource_file, DEFAULT_DATASOURCE_YAML, overwrite=overwrite)
    _write_text(
        provider_file,
        DEFAULT_DASHBOARD_PROVIDER_YAML.format(
            dashboards_path="/var/lib/grafana/dashboards/finquanta"
        ),
        overwrite=overwrite,
    )

    dashboards_written: list[str] = []
    for src in sorted(EXAMPLES_DIR.glob("*.json")):
        data = json.loads(src.read_text(encoding="utf-8"))
        text = json.dumps(data, ensure_ascii=False, indent=2)
        text = _replace_api_base(text, api_base=api_base)
        dst = dashboard_json_dir / src.name
        _write_text(dst, text + "\n", overwrite=overwrite)
        dashboards_written.append(str(dst))

    return {
        "output_dir": str(output_dir),
        "datasource_file": str(datasource_file),
        "provider_file": str(provider_file),
        "provider_dashboards_path": "/var/lib/grafana/dashboards/finquanta",
        "dashboards_count": len(dashboards_written),
        "dashboards": dashboards_written,
        "api_base": api_base.rstrip("/"),
        "overwrite": bool(overwrite),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Grafana provisioning files for FinQuanta dashboards.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "infra" / "grafana" / "provisioning"),
        help="Grafana provisioning root directory.",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000"),
        help="FinQuanta API base URL used in dashboard JSON URLs.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing provisioning files.")
    args = parser.parse_args()

    result = setup_grafana_provisioning(
        output_dir=Path(args.output_dir),
        api_base=str(args.api_base),
        overwrite=bool(args.overwrite),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
