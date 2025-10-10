# -*- coding: utf-8 -*-
"""
Agent核心数据模型

这个模块包含所有Agent系统使用的数据结构，
采用高内聚设计，所有相关数据模型集中管理。
"""

import time
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


class AgentState(Enum):
    """Agent状态枚举 - 定义Agent生命周期的所有状态"""
    INITIALIZING = "initializing"    # 初始化阶段
    ANALYZING = "analyzing"          # 分析阶段
    QUESTIONING = "questioning"      # 提问阶段
    REVIEWING = "reviewing"          # 审查阶段
    COMPLETED = "completed"          # 完成状态
    ERROR = "error"                  # 错误状态


@dataclass
class AgentMessage:
    """Agent消息结构 - 对话系统的基础单元"""
    role: str                                    # 'system', 'user', 'assistant'
    content: str                                 # 消息内容
    timestamp: float = field(default_factory=time.time)  # 时间戳
    metadata: Dict = field(default_factory=dict)         # 元数据


@dataclass
class AgentContext:
    """Agent分析上下文 - 包含所有分析所需的信息"""
    # 基础文件信息
    file_path: str
    file_content: str
    changed_lines: List[int]
    diff_content: str
    language: str

    # MR相关信息
    mr_title: str = ""
    mr_description: str = ""

    # 配置信息
    review_config: Dict = field(default_factory=dict)

    # 对话历史和状态
    conversation_history: List[AgentMessage] = field(default_factory=list)
    current_analysis_focus: str = ""
    gathered_information: Dict = field(default_factory=dict)


@dataclass
class AgentQuestion:
    """Agent问题结构 - 多轮对话中的问题单元"""
    question_id: str
    question_text: str
    question_type: str  # 'clarification', 'detail_request', 'confirmation'
    context_needed: Dict = field(default_factory=dict)
    priority: int = 1   # 1-5, 1最高优先级


@dataclass
class AgentAnalysisResult:
    """Agent分析结果 - 包含完整的分析输出"""
    # 核心结果
    issues: List = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    # 分析元信息
    confidence_score: float = 0.0               # 置信度 0-1
    analysis_depth: str = "shallow"             # shallow, medium, deep
    questions_asked: int = 0                    # 提问次数
    conversation_turns: int = 0                 # 对话轮数

    # 扩展信息
    reasoning_process: str = ""                 # 推理过程
    performance_metrics: Dict = field(default_factory=dict)  # 性能指标


@dataclass
class CodeIssue:
    """代码问题结构 - 与现有系统兼容的问题表示"""
    line_number: int
    severity: str       # 'error', 'warning', 'info'
    category: str       # 'security', 'performance', 'quality', 'best_practices', 'logic'
    message: str
    suggestion: Optional[str] = None
    confidence: float = 0.8  # AI 确信程度 (0.0-1.0)