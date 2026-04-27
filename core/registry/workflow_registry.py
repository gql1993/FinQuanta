"""
Workflow registry skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    display_name: str
    trigger: str
    handler_path: str


def get_workflow_registry() -> dict[str, WorkflowDefinition]:
    return {
        "scan_pipeline": WorkflowDefinition(
            key="scan_pipeline",
            display_name="SEPA Scan Pipeline",
            trigger="task:scan",
            handler_path="core.application.task_service:run_scan_task",
        ),
        "openclaw_pipeline": WorkflowDefinition(
            key="openclaw_pipeline",
            display_name="OpenClaw Full Pipeline",
            trigger="task:pipeline",
            handler_path="core.application.openclaw_service:run_openclaw_pipeline",
        ),
        "openclaw_learning": WorkflowDefinition(
            key="openclaw_learning",
            display_name="OpenClaw Learning Workflow",
            trigger="task:learn",
            handler_path="core.application.openclaw_service:run_openclaw_learning",
        ),
        "verify_calibration": WorkflowDefinition(
            key="verify_calibration",
            display_name="Trend Verify Calibration",
            trigger="task:verify.calibrate",
            handler_path="core.application.verify_service:calibrate_verify",
        ),
    }


def list_registered_workflows() -> list[dict]:
    return [
        {
            "key": definition.key,
            "display_name": definition.display_name,
            "trigger": definition.trigger,
            "handler_path": definition.handler_path,
        }
        for definition in get_workflow_registry().values()
    ]
