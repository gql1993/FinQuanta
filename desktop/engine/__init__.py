"""FinQuanta 交易主干：事件引擎、OMS、Paper/Real 网关、主引擎。"""

from desktop.engine.event_engine import EventEngine, get_default_engine
from desktop.engine.main_engine import MainEngine, get_default_main_engine
from desktop.engine.paper_gateway import PaperGateway
from desktop.engine.real_gateway import RealGateway

__all__ = [
    "EventEngine",
    "get_default_engine",
    "MainEngine",
    "get_default_main_engine",
    "PaperGateway",
    "RealGateway",
]

