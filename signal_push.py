"""
交易信号推送模块
当选股雷达发现突破信号时，可通过微信（Server酱/企业微信）或邮件推送通知。

配置优先级: 页面设置（JSON持久化）> 环境变量
"""
import os
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime

logger = logging.getLogger(__name__)

_PUSH_CONFIG_FILE = os.path.join("data_cache", "push_config.json")


def _load_push_config() -> dict:
    if os.path.exists(_PUSH_CONFIG_FILE):
        try:
            with open(_PUSH_CONFIG_FILE, "r", encoding="utf-8") as f:
                obj = json.load(f)
                return obj if isinstance(obj, dict) else {}
        except Exception:
            pass
    return {}


def save_push_config(cfg: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_PUSH_CONFIG_FILE), exist_ok=True)
        with open(_PUSH_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_push_config() -> dict:
    """合并本地配置和环境变量（本地优先）。"""
    file_cfg = _load_push_config()
    return {
        "serverchan_key": file_cfg.get("serverchan_key") or os.environ.get("PUSH_SERVERCHAN_KEY", ""),
        "wecom_webhook": file_cfg.get("wecom_webhook") or os.environ.get("PUSH_WECOM_WEBHOOK", ""),
        "email_to": file_cfg.get("email_to") or os.environ.get("PUSH_EMAIL_TO", ""),
        "email_from": file_cfg.get("email_from") or os.environ.get("PUSH_EMAIL_FROM", ""),
        "email_password": file_cfg.get("email_password") or os.environ.get("PUSH_EMAIL_PASSWORD", ""),
        "email_smtp": file_cfg.get("email_smtp") or os.environ.get("PUSH_EMAIL_SMTP", "smtp.qq.com"),
        "email_port": int(file_cfg.get("email_port") or os.environ.get("PUSH_EMAIL_PORT", "465")),
    }


def push_signal(title: str, content: str, channels: list[str] | None = None) -> dict[str, bool]:
    """
    推送信号消息。
    channels: 指定渠道列表，默认 None = 自动检测已配置的渠道全推。
    返回 {channel: success}。
    """
    cfg = get_push_config()
    results = {}
    auto = channels is None

    if auto or "serverchan" in (channels or []):
        key = cfg.get("serverchan_key", "").strip()
        if key:
            results["serverchan"] = _push_serverchan(key, title, content)

    if auto or "wecom" in (channels or []):
        webhook = cfg.get("wecom_webhook", "").strip()
        if webhook:
            results["wecom"] = _push_wecom(webhook, title, content)

    if auto or "email" in (channels or []):
        to_addr = cfg.get("email_to", "").strip()
        if to_addr:
            results["email"] = _push_email(title, content, to_addr, cfg)

    if not results:
        logger.info("signal_push: 未配置任何推送渠道，跳过推送。")
    return results


def push_screening_results(candidates: list[dict], strategy_name: str = "") -> dict[str, bool]:
    """将选股雷达突破候选推送出去（自动格式化）。"""
    if not candidates:
        return {}
    breakouts = [c for c in candidates if c.get("突破") == "突破!"]
    if not breakouts:
        return {}

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"📡 选股雷达突破信号 [{strategy_name or '综合'}] {ts}"
    lines = [f"共发现 {len(breakouts)} 只突破候选：\n"]
    for c in breakouts[:15]:
        lines.append(
            f"- {c.get('代码', '')} {c.get('名称', '')}  "
            f"RS={c.get('RS', '-')}  评分={c.get('评分', '-')}  "
            f"价格={c.get('价格', '-')}  板块={c.get('板块', '-')}"
        )
    if len(breakouts) > 15:
        lines.append(f"\n... 及其他 {len(breakouts) - 15} 只")

    content = "\n".join(lines)
    return push_signal(title, content)


def _push_serverchan(key: str, title: str, content: str) -> bool:
    """Server酱推送（微信）。标题限32字，免费版每天5条。"""
    # 标题截断至 32 字符
    if len(title) > 32:
        title = title[:30] + ".."

    url = f"https://sctapi.ftqq.com/{key}.send"
    data = urllib.parse.urlencode({
        "title": title,
        "desp": content,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode("utf-8", errors="ignore"))
        ok = body.get("code") == 0 or body.get("errno") == 0
        if not ok:
            logger.warning("serverchan push failed: %s", body)
        return ok
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8", errors="ignore"))
            err_msg = err_body.get("message", str(e))
            logger.warning("serverchan push rejected: %s", err_msg)
            # 次数限制 → 不算致命错误，静默处理
            if "次数限制" in err_msg:
                logger.info("serverchan daily limit reached (free: 5/day)")
                return False
        except Exception:
            pass
        logger.error("serverchan push HTTP error: %s", e)
        return False
    except Exception as e:
        logger.error("serverchan push error: %s", e)
        return False


def _push_wecom(webhook: str, title: str, content: str) -> bool:
    """企业微信机器人推送。"""
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"content": f"## {title}\n\n{content}"},
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            webhook, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode("utf-8", errors="ignore"))
        ok = body.get("errcode") == 0
        if not ok:
            logger.warning("wecom push failed: %s", body)
        return ok
    except Exception as e:
        logger.error("wecom push error: %s", e)
        return False


def _push_email(title: str, content: str, to_addr: str, cfg: dict | None = None) -> bool:
    """邮件推送（SMTP SSL）。"""
    import smtplib
    from email.mime.text import MIMEText

    cfg = cfg or get_push_config()
    from_addr = cfg.get("email_from", "").strip()
    password = cfg.get("email_password", "").strip()
    smtp_host = cfg.get("email_smtp", "smtp.qq.com").strip()
    smtp_port = int(cfg.get("email_port", 465))

    if not from_addr or not password:
        logger.warning("email push skipped: PUSH_EMAIL_FROM or PUSH_EMAIL_PASSWORD not set")
        return False

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
            server.login(from_addr, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception as e:
        logger.error("email push error: %s", e)
        return False
