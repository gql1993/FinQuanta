"""
AI 助手服务
支持 DeepSeek / OpenAI / Ollama，通过 Function Calling 执行交易操作。
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SYSTEM_PROMPT = """你是一个专业的 A 股量化交易助手，基于 Mark Minervini《股票魔法师》的 SEPA 策略体系。

你的核心知识:
1. 趋势模板 8 大条件: 确认股票处于 Stage 2 上升阶段
2. VCP (波动收缩形态): 识别基底构建中波动率逐步收窄的低风险入场点
3. RS 相对强度评级: 衡量个股相对大盘的表现强度 (≥70 为强势)
4. 风险管理: 8% 硬止损、渐进式止盈、时间止损、高潮顶检测

你可以帮助用户:
- 筛选符合 SEPA 条件的潜力股
- 分析个股的技术形态和买入时机
- 管理模拟仓（买入/卖出）
- 运行策略回测
- 解读市场环境
- 解释策略规则

回答要简洁专业，使用中文。对于具体操作，先分析再给出建议。"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "screen_stocks",
            "description": "运行 SEPA 选股扫描，返回评分最高的候选股列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "sample_size": {"type": "integer", "description": "扫描股票数量", "default": 300},
                    "top_n": {"type": "integer", "description": "返回前N只", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_stock",
            "description": "分析个股：趋势模板、VCP形态、RS评级、均线位置",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 603881"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_portfolio",
            "description": "查看当前模拟仓持仓情况、盈亏和风控状态",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buy_stock",
            "description": "在模拟仓中买入股票",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码"},
                    "shares": {"type": "integer", "description": "买入股数（100的整数倍）"},
                    "price": {"type": "number", "description": "买入价格（0=使用最新价）"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sell_stock",
            "description": "在模拟仓中卖出股票",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码"},
                    "reason": {"type": "string", "description": "卖出原因"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "market_status",
            "description": "查看当前A股大盘市场环境状态（分布日分析）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    """执行工具函数，返回结果文本"""
    try:
        if name == "screen_stocks":
            from services.stock_service import run_screening
            sample = args.get("sample_size", 300)
            top_n = args.get("top_n", 10)
            results = run_screening(sample)[:top_n]
            if not results:
                return "当前无股票通过筛选条件"
            lines = ["选股结果:\n"]
            lines.append(f"{'代码':>8} {'名称':<8} {'价格':>7} {'RS':>3} {'评分':>5} {'VCP':>3} {'距枢纽':>6} {'突破':>4}")
            for r in results:
                lines.append(f"{r['代码']:>8} {r['名称']:<8} {r['价格']:>7} {r['RS']:>3} "
                             f"{r['评分']:>5} {r['VCP']:>3} {r['距枢纽%']:>5.1f}% {r['突破']:>4}")
            return "\n".join(lines)

        elif name == "analyze_stock":
            from services.stock_service import analyze_stock
            code = args["code"]
            result = analyze_stock(code)
            if result is None:
                return f"无法获取 {code} 数据"
            vcp = result["vcp"]
            lines = [
                f"个股分析: {code} {result['name']}",
                f"  现价: {result['close']}  MA50: {result['ma50']}  MA150: {result['ma150']}  MA200: {result['ma200']}",
                f"  52周高: {result['high_52w']}  52周低: {result['low_52w']}",
                f"  RS评级: {result['rs_rating']:.0f}",
                f"  趋势模板: {'通过' if result['trend_pass'] else '未通过'}",
                f"  VCP形态: {'有' if vcp['has_vcp'] else '无'}  收缩{vcp.get('num_contractions', 0)}次",
                f"  枢纽价: {vcp.get('pivot_price', 0):.2f}  突破: {'是' if vcp.get('breakout_today') else '否'}",
            ]
            return "\n".join(lines)

        elif name == "check_portfolio":
            from services.portfolio_service import get_portfolio, get_portfolio_summary
            state = get_portfolio()
            summary = get_portfolio_summary(state)
            lines = [
                f"模拟仓概况:",
                f"  总资产: ¥{summary['total_equity']:,.0f}  收益: {summary['total_return']:+.2f}%",
                f"  现金: ¥{summary['cash']:,.0f}  持仓: ¥{summary['position_value']:,.0f}  仓位: {summary['position_ratio']:.0f}%",
                f"  持仓 {summary['num_positions']} 只:",
            ]
            for p in summary["positions"]:
                lines.append(f"    {p['代码']} {p['名称']} {p['股数']}股 买入{p['买入价']} 现{p['现价']} 盈亏{p['盈亏%']:+.1f}%")
            return "\n".join(lines)

        elif name == "buy_stock":
            from services.portfolio_service import get_portfolio, execute_buy, calc_position_size
            from services.stock_service import get_daily_data, get_stock_names
            code = args["code"]
            names = get_stock_names()
            name = names.get(code, code)
            price = args.get("price", 0)
            if price <= 0:
                df = get_daily_data(code)
                if df is not None and not df.empty:
                    price = float(df["close"].iloc[-1])
                else:
                    return f"无法获取 {code} 价格"
            state = get_portfolio()
            shares = args.get("shares", 0)
            if shares <= 0:
                shares = calc_position_size(state, price)
            ok, msg = execute_buy(state, code, name, price, shares)
            return msg

        elif name == "sell_stock":
            from services.portfolio_service import get_portfolio, execute_sell
            from services.stock_service import get_daily_data
            code = args["code"]
            reason = args.get("reason", "AI 指令卖出")
            state = get_portfolio()
            pos = next((p for p in state.positions if p["code"] == code), None)
            if pos is None:
                return f"未持有 {code}"
            df = get_daily_data(code)
            price = float(df["close"].iloc[-1]) if df is not None and not df.empty else pos["entry_price"]
            ok, msg = execute_sell(state, code, price, reason)
            return msg

        elif name == "market_status":
            from services.stock_service import get_market_regime
            regime = get_market_regime()
            status = "健康（适合买入）" if regime["market_ok"] else "偏弱（建议谨慎）"
            return f"市场环境: {status}\n分布日: {regime['dist_count']}/5\n(25个交易日内超过5个分布日为市场转弱)"

        return f"未知工具: {name}"
    except Exception as e:
        return f"执行出错: {str(e)}"


AI_PROVIDERS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "key_url": "https://platform.deepseek.com/api_keys",
        "supports_tools": True,
        "note": "性价比高，中文最强，支持 Function Calling",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "default_model": "gpt-4o-mini",
        "key_url": "https://platform.openai.com/api-keys",
        "supports_tools": True,
        "note": "功能最全，Function Calling 最稳定",
    },
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default_model": "gemini-2.0-flash",
        "key_url": "https://aistudio.google.com/apikey",
        "supports_tools": True,
        "note": "免费额度大，多模态能力强",
    },
    "Claude": {
        "base_url": "https://api.anthropic.com/v1/",
        "models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
        "default_model": "claude-sonnet-4-20250514",
        "key_url": "https://console.anthropic.com/settings/keys",
        "supports_tools": True,
        "note": "推理能力强，代码分析出色",
        "use_anthropic": True,
    },
    "通义千问": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "default_model": "qwen-plus",
        "key_url": "https://dashscope.console.aliyun.com/apiKey",
        "supports_tools": True,
        "note": "阿里云，中文好，国内访问快",
    },
    "Ollama (本地)": {
        "base_url": "http://localhost:11434/v1",
        "models": ["qwen2.5:7b", "qwen2.5:14b", "llama3.1:8b", "deepseek-r1:8b", "gemma2:9b"],
        "default_model": "qwen2.5:7b",
        "key_url": "",
        "supports_tools": False,
        "note": "本地部署，免费，需先安装 Ollama",
    },
    "自定义": {
        "base_url": "",
        "models": [],
        "default_model": "",
        "key_url": "",
        "supports_tools": True,
        "note": "兼容 OpenAI API 格式的任意服务",
    },
}


def get_ai_client(provider: str, api_key: str, model: str = "",
                   custom_base_url: str = ""):
    """获取 OpenAI 兼容客户端"""
    cfg = AI_PROVIDERS.get(provider, {})

    if provider == "Claude" and cfg.get("use_anthropic"):
        try:
            from anthropic import Anthropic
            return Anthropic(api_key=api_key), "anthropic"
        except ImportError:
            from openai import OpenAI
            return OpenAI(api_key=api_key, base_url=cfg["base_url"]), "openai"

    from openai import OpenAI

    if provider == "自定义":
        base_url = custom_base_url or "http://localhost:8000/v1"
    elif provider == "Ollama (本地)":
        base_url = cfg["base_url"]
        api_key = "ollama"
    else:
        base_url = cfg["base_url"]

    return OpenAI(api_key=api_key, base_url=base_url), "openai"


def get_model_name(provider: str, selected_model: str = "") -> str:
    if selected_model:
        return selected_model
    cfg = AI_PROVIDERS.get(provider, {})
    return cfg.get("default_model", "gpt-4o-mini")


def chat_with_ai(messages: list, provider: str, api_key: str,
                  model: str = "", custom_base_url: str = "") -> str:
    """与 AI 对话，支持 Function Calling"""
    client, client_type = get_ai_client(provider, api_key, model, custom_base_url)
    model_name = get_model_name(provider, model)
    cfg = AI_PROVIDERS.get(provider, {})

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # Claude via Anthropic SDK
    if client_type == "anthropic":
        resp = client.messages.create(
            model=model_name,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return resp.content[0].text

    # OpenAI-compatible path
    try:
        kwargs = dict(model=model_name, messages=full_messages)
        if cfg.get("supports_tools", True):
            kwargs["tools"] = TOOLS
            kwargs["tool_choice"] = "auto"
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        err = str(e).lower()
        if "tool" in err or "function" in err or "unsupported" in err:
            response = client.chat.completions.create(
                model=model_name, messages=full_messages,
            )
        else:
            raise

    msg = response.choices[0].message

    if msg.tool_calls:
        tool_results = []
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            result = execute_tool(fn_name, fn_args)
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        follow_up = full_messages + [msg.model_dump()] + tool_results
        try:
            final = client.chat.completions.create(
                model=model_name, messages=follow_up,
            )
            return final.choices[0].message.content
        except Exception:
            return "\n\n".join(tr["content"] for tr in tool_results)

    return msg.content or ""
