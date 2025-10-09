# -*- coding: utf-8 -*-
"""
AI Agent模块

这个模块包含了AI代码审查Agent系统的所有核心组件，
采用高内聚低耦合的设计原则，确保模块间的清晰边界。
"""

from .core import AgentState, AgentMessage, AgentContext
from .analyzers import CodeAnalyzer

__all__ = [
    'AgentState',
    'AgentMessage',
    'AgentContext',
    'CodeAnalyzer'
]