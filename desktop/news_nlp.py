"""
新闻 NLP 情感分析模块
用规则引擎 + 打分模型做情感分析，替代简单关键词匹配。
支持：情感极性分析、行业关联度、事件影响评估。
"""
import re
from dataclasses import dataclass

# 情感词典
_POSITIVE = {
    "利好": 3, "突破": 2, "超预期": 3, "增长": 2, "大涨": 3,
    "涨停": 3, "创新高": 3, "加码": 2, "扶持": 2, "政策支持": 3,
    "翻倍": 3, "放量": 2, "龙头": 2, "景气": 2, "爆发": 3,
    "强势": 2, "反弹": 1, "回暖": 1, "机遇": 2, "催化": 2,
    "提速": 2, "扩产": 2, "订单": 2, "需求旺盛": 3, "业绩预增": 3,
    "获批": 2, "中标": 2, "战略合作": 2, "国产替代": 3, "自主可控": 3,
    "市占率提升": 2, "毛利率提升": 2, "净利润增长": 3,
}

_NEGATIVE = {
    "利空": -3, "下跌": -2, "暴跌": -3, "减持": -2, "亏损": -3,
    "退市": -3, "处罚": -2, "制裁": -3, "暂停": -2, "限制": -2,
    "风险": -1, "调查": -2, "违规": -2, "下调": -1, "萎缩": -2,
    "跌停": -3, "破发": -2, "清仓": -3, "爆雷": -3, "暴雷": -3,
    "业绩下滑": -3, "营收下降": -2, "毛利率下降": -2, "负债率上升": -2,
    "商誉减值": -3, "计提": -2, "亏损扩大": -3, "产能过剩": -2,
}

_INDUSTRY_KEYWORDS = {
    "芯片": ["芯片", "半导体", "晶圆", "光刻", "封测", "IC", "存储"],
    "人工智能": ["AI", "人工智能", "大模型", "算力", "GPT", "深度学习", "机器学习"],
    "新能源": ["新能源", "光伏", "锂电", "储能", "充电桩", "风电", "氢能"],
    "军工": ["军工", "国防", "导弹", "航天", "战斗机", "雷达"],
    "医药": ["创新药", "医药", "医疗", "CRO", "疫苗", "器械"],
    "消费": ["白酒", "食品", "零售", "消费", "餐饮", "家电"],
    "金融": ["银行", "券商", "保险", "信托", "基金"],
    "地产": ["房地产", "地产", "楼市", "住宅", "商业地产"],
}

_URGENCY_KEYWORDS = {
    "紧急": 3, "重磅": 3, "突发": 3, "刚刚": 2, "快讯": 2,
    "独家": 2, "首次": 2, "历史性": 3, "里程碑": 3,
}


@dataclass
class SentimentResult:
    text: str = ""
    sentiment_score: float = 0.0
    sentiment_label: str = "中性"
    confidence: float = 0.0
    industries: list = None
    urgency: int = 0
    key_phrases: list = None


def analyze_sentiment(text: str) -> SentimentResult:
    """分析单条新闻的情感。"""
    result = SentimentResult(text=text[:100])

    # 情感打分
    pos_score = sum(v for k, v in _POSITIVE.items() if k in text)
    neg_score = sum(v for k, v in _NEGATIVE.items() if k in text)
    total = pos_score + neg_score

    if total > 2:
        result.sentiment_label = "强烈看多"
        result.confidence = min(95, 50 + total * 5)
    elif total > 0:
        result.sentiment_label = "偏多"
        result.confidence = 40 + total * 8
    elif total < -2:
        result.sentiment_label = "强烈看空"
        result.confidence = min(95, 50 + abs(total) * 5)
    elif total < 0:
        result.sentiment_label = "偏空"
        result.confidence = 40 + abs(total) * 8
    else:
        result.sentiment_label = "中性"
        result.confidence = 30
    result.sentiment_score = total

    # 行业关联
    result.industries = []
    for industry, keywords in _INDUSTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            result.industries.append(industry)

    # 紧急度
    result.urgency = sum(v for k, v in _URGENCY_KEYWORDS.items() if k in text)

    # 关键短语提取
    result.key_phrases = []
    for kw in list(_POSITIVE.keys()) + list(_NEGATIVE.keys()):
        if kw in text:
            result.key_phrases.append(kw)

    return result


def batch_analyze(news_list: list[dict]) -> list[dict]:
    """批量分析新闻列表情感。"""
    for news in news_list:
        text = news.get("title", "") + " " + news.get("digest", "")
        result = analyze_sentiment(text)
        news["nlp_score"] = result.sentiment_score
        news["nlp_label"] = result.sentiment_label
        news["nlp_confidence"] = result.confidence
        news["nlp_industries"] = result.industries
        news["nlp_urgency"] = result.urgency
        news["nlp_phrases"] = result.key_phrases[:5]
    return news_list
