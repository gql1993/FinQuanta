"""交易与引擎事件类型常量（参考 vn.py 事件命名习惯，简化版）。"""

# 行情
EVENT_TICK = "eTick"
EVENT_BAR = "eBar"

# 订单与成交
EVENT_ORDER = "eOrder"
EVENT_ORDER_REJECT = "eOrderReject"
EVENT_TRADE = "eTrade"
EVENT_CANCEL = "eCancel"

# 账户
EVENT_ACCOUNT = "eAccount"
EVENT_POSITION = "ePosition"

# 日志
EVENT_LOG = "eLog"
