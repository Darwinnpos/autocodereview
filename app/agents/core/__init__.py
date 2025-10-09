# -*- coding: utf-8 -*-
"""
Agent核心模块 - 高内聚设计

包含Agent系统的核心抽象和基础组件：
- AgentState: Agent状态枚举
- AgentMessage: 消息传递结构
- AgentContext: 分析上下文
- BaseAgent: Agent基础抽象类
- ConversationManager: 对话管理器
"""

from .data_models import AgentState, AgentMessage, AgentContext, AgentQuestion, AgentAnalysisResult
from .base_agent import BaseAgent
from .conversation import ConversationManager

__all__ = [
    'AgentState',
    'AgentMessage',
    'AgentContext',
    'AgentQuestion',
    'AgentAnalysisResult',
    'BaseAgent',
    'ConversationManager'
]