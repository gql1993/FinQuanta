"""AI 助手 - 自然语言交互式量化操作"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="AI 助手", page_icon="🤖", layout="wide")

from services.ai_service import chat_with_ai, AI_PROVIDERS

st.title("🤖 AI 量化助手")
st.caption("自然语言驱动的智能交易助手 — 选股 / 分析 / 建仓 / 风控")

# ---- Sidebar: Model Configuration ----
with st.sidebar:
    st.markdown("### AI 模型设置")

    provider_names = list(AI_PROVIDERS.keys())
    provider = st.selectbox("选择模型厂商", provider_names, key="ai_provider_sel")
    cfg = AI_PROVIDERS[provider]

    st.caption(cfg["note"])

    # API Key
    if provider == "Ollama (本地)":
        api_key = "ollama"
        st.info("请确保 Ollama 已在本地运行 (localhost:11434)")
    elif provider == "自定义":
        api_key = st.text_input("API Key", type="password", key="ai_key")
        custom_url = st.text_input("API Base URL", value="http://localhost:8000/v1",
                                    key="custom_url", placeholder="https://api.example.com/v1")
        custom_model = st.text_input("模型名称", key="custom_model", placeholder="例如: gpt-4o")
    else:
        api_key = st.text_input("API Key", type="password", key="ai_key")
        if cfg["key_url"]:
            st.caption(f"[获取 Key]({cfg['key_url']})")

    # Model selection
    if provider != "自定义":
        models = cfg["models"]
        default_idx = models.index(cfg["default_model"]) if cfg["default_model"] in models else 0
        selected_model = st.selectbox("选择模型", models, index=default_idx, key="ai_model_sel")
    else:
        selected_model = st.session_state.get("custom_model", "")

    # Store in session_state for other pages
    st.session_state["ai_provider"] = provider
    st.session_state["ai_api_key"] = api_key
    st.session_state["ai_model"] = selected_model

    st.divider()
    if st.button("🗑️ 清空对话", width="stretch"):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.markdown("#### 💡 使用提示")
    st.markdown("""
    **你可以这样说:**
    - "帮我选股" → SEPA 扫描
    - "分析 600519" → 个股分析
    - "查看持仓" → 模拟仓状态
    - "买入 603881 2000股"
    - "卖出 002975"
    - "市场环境怎么样"
    - "什么是趋势模板"
    - "VCP 形态怎么识别"
    """)

# ---- Quick action buttons ----
cols = st.columns(6)
quick_prompts = [
    ("📡 选股", "帮我选出目前最好的10只候选股"),
    ("📊 市场", "当前市场环境如何？适合买入吗？"),
    ("💼 持仓", "查看我的模拟仓持仓情况和风控状态"),
    ("📈 分析", "帮我分析 603881 的技术形态"),
    ("🛒 买入", "帮我买入 603881 2000股"),
    ("📖 策略", "解释什么是 VCP 形态和趋势模板"),
]

for i, (label, prompt) in enumerate(quick_prompts):
    if cols[i].button(label, width="stretch", key=f"quick_{i}"):
        st.session_state["pending_prompt"] = prompt

# ---- Validate API Key ----
_ready = True
if provider == "Ollama (本地)":
    pass
elif provider == "自定义":
    if not api_key or not selected_model:
        _ready = False
        st.warning("请在左侧设置 API Key、Base URL 和模型名称")
elif not api_key:
    _ready = False
    st.warning(f"请在左侧设置 {provider} 的 API Key")
    st.markdown(f"""
    #### 快速开始
    | 厂商 | 特点 | 获取 Key |
    |------|------|---------|
    | **DeepSeek** | 性价比高，中文最强 | [platform.deepseek.com]({AI_PROVIDERS['DeepSeek']['key_url']}) |
    | **OpenAI** | 功能最全，生态成熟 | [platform.openai.com]({AI_PROVIDERS['OpenAI']['key_url']}) |
    | **Google Gemini** | 免费额度大 | [aistudio.google.com]({AI_PROVIDERS['Google Gemini']['key_url']}) |
    | **Claude** | 推理能力强 | [console.anthropic.com]({AI_PROVIDERS['Claude']['key_url']}) |
    | **通义千问** | 国内访问快 | [dashscope.console.aliyun.com]({AI_PROVIDERS['通义千问']['key_url']}) |
    | **Ollama** | 本地免费 | 安装 [ollama.com](https://ollama.com) |
    """)

# ---- Display model badge ----
if _ready:
    st.caption(f"当前模型: **{provider}** / `{selected_model}`"
               f"{'　✅ 支持工具调用' if cfg.get('supports_tools') else '　⚠️ 不支持工具调用'}")

# ---- Chat history ----
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle pending quick prompt
pending = st.session_state.pop("pending_prompt", None)

# Chat input
user_input = st.chat_input("和 AI 助手对话... 例如: 帮我选股 / 分析603881 / 查看持仓")

prompt = pending or user_input

if prompt and _ready:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"{provider} 思考中..."):
            try:
                custom_url = st.session_state.get("custom_url", "") if provider == "自定义" else ""
                reply = chat_with_ai(
                    st.session_state.messages, provider, api_key,
                    model=selected_model, custom_base_url=custom_url,
                )
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                error_msg = str(e)
                st.error(f"AI 调用失败: {error_msg}")
                if "api_key" in error_msg.lower() or "auth" in error_msg.lower() or "401" in error_msg:
                    st.info("API Key 无效或已过期，请检查后重试")
                elif "model" in error_msg.lower() or "404" in error_msg:
                    st.info(f"模型 `{selected_model}` 不可用，请换一个模型")
                elif "rate" in error_msg.lower() or "429" in error_msg:
                    st.info("请求过于频繁，请稍后再试")
