# -*- coding: utf-8 -*-
"""
Agent编排模块

负责管理多个Agent的协调工作、任务分配、资源调度和结果聚合。
采用高内聚低耦合设计，确保编排逻辑的独立性和可扩展性。
"""

from .orchestrator import AgentOrchestrator
from .task_scheduler import TaskScheduler
from .resource_manager import ResourceManager

__all__ = [
    'AgentOrchestrator',
    'TaskScheduler',
    'ResourceManager'
]