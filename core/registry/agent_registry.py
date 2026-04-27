"""
Agent registry for FinQuanta's multi-agent pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    display_name: str
    role: str
    module_path: str
    entrypoint: str
    stage: str
    capabilities: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    safety_level: str = "read_only"


def get_agent_registry() -> dict[str, AgentDefinition]:
    return {
        "intelligence": AgentDefinition(
            key="intelligence",
            display_name="情报智能体",
            role="采集行情、事件、基金和板块事实，不直接给交易建议",
            module_path="desktop.agents",
            entrypoint="IntelligenceAgent.gather",
            stage="sense",
            capabilities=("market_snapshot", "board_context", "event_summary", "fund_flow"),
            inputs=("boards",),
            outputs=("intel_report", "intel_prompt"),
        ),
        "analysis": AgentDefinition(
            key="analysis",
            display_name="分析智能体",
            role="对候选股进行趋势、动量、量能和多因子评分",
            module_path="desktop.agents",
            entrypoint="AnalysisAgent.analyze",
            stage="analyze",
            capabilities=("candidate_scoring", "market_regime_detection", "signal_extraction"),
            inputs=("intel_report", "boards"),
            outputs=("candidates", "market_regime", "analysis_prompt"),
        ),
        "verification": AgentDefinition(
            key="verification",
            display_name="验证智能体",
            role="基于走势验证历史和失败归因对候选股做风险验收",
            module_path="desktop.agents",
            entrypoint="VerificationAgent.verify",
            stage="verify",
            capabilities=("historical_failure_check", "risk_tagging", "candidate_verdict"),
            inputs=("analysis_report", "trend_verify_records"),
            outputs=("verified_candidates", "questionable_candidates", "rejected_candidates"),
        ),
        "decision": AgentDefinition(
            key="decision",
            display_name="决策智能体",
            role="综合情报、分析、验证和持仓上下文生成交易决策",
            module_path="desktop.agents",
            entrypoint="DecisionAgent.decide",
            stage="decide",
            capabilities=("llm_decision", "portfolio_context_reasoning", "trade_instruction_generation"),
            inputs=("intel_prompt", "analysis_prompt", "verification_prompt", "portfolio_context"),
            outputs=("raw_decisions", "analysis"),
            safety_level="trade_recommendation",
        ),
        "coordinator": AgentDefinition(
            key="coordinator",
            display_name="协调者智能体",
            role="编排 OpenClaw 流程、执行分流、失败恢复和学习调参",
            module_path="desktop.agents",
            entrypoint="CoordinatorAgent",
            stage="orchestrate",
            capabilities=("pipeline_plan", "stage_routing", "execution_policy", "failure_recovery", "policy_adaptation"),
            inputs=("pipeline_results", "coordinator_policy", "learning_feedback"),
            outputs=("stage_plan", "routing", "execution_plan", "recoveries", "next_action"),
            safety_level="orchestration",
        ),
        "verification_guardrail": AgentDefinition(
            key="verification_guardrail",
            display_name="验证守门",
            role="对最终决策施加半硬约束，拦截高风险买入并标注存疑买入",
            module_path="desktop.agents",
            entrypoint="_apply_verification_guardrails",
            stage="guardrail",
            capabilities=("blocked_buy_filter", "questionable_buy_annotation", "audit_summary"),
            inputs=("raw_decisions", "verification_report"),
            outputs=("filtered_decisions", "blocked_buys", "annotated_buys"),
            safety_level="trade_guardrail",
        ),
        "risk": AgentDefinition(
            key="risk",
            display_name="风险智能体",
            role="统一评估组合持仓、VaR、回撤、现金比例和舆情风险",
            module_path="desktop.agents",
            entrypoint="RiskAgent.assess_openclaw",
            stage="risk",
            capabilities=("portfolio_risk_check", "var_check", "drawdown_check", "sentiment_risk_check"),
            inputs=("pipeline_results", "portfolio_state", "portfolio_risk"),
            outputs=("risk_summary", "warnings", "checks"),
            safety_level="risk_control",
        ),
        "approval": AgentDefinition(
            key="approval",
            display_name="审批智能体",
            role="执行前逐条评估交易请求，输出通过、拒绝和跳过清单",
            module_path="desktop.agents",
            entrypoint="ApprovalAgent.review_decisions",
            stage="approval",
            capabilities=("trade_request_validation", "risk_policy_check", "pre_execution_approval"),
            inputs=("decisions", "mode", "latest_price"),
            outputs=("approved_decisions", "rejected_decisions", "approval_summary"),
            safety_level="trade_approval",
        ),
    }


def list_registered_agents() -> list[dict]:
    return [
        {
            "key": definition.key,
            "display_name": definition.display_name,
            "role": definition.role,
            "module_path": definition.module_path,
            "entrypoint": definition.entrypoint,
            "stage": definition.stage,
            "capabilities": list(definition.capabilities),
            "inputs": list(definition.inputs),
            "outputs": list(definition.outputs),
            "safety_level": definition.safety_level,
        }
        for definition in get_agent_registry().values()
    ]
