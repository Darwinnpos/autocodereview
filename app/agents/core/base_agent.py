# -*- coding: utf-8 -*-
"""
Agent基础抽象类

采用低耦合设计，定义Agent的通用接口和行为模式，
具体的分析逻辑由子类实现，确保扩展性和可测试性。
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

from .data_models import AgentState, AgentContext, AgentAnalysisResult


class BaseAgent(ABC):
    """
    Agent基础抽象类

    定义所有Agent必须实现的核心接口，采用模板方法模式，
    确保不同类型的Agent有统一的执行流程但可以定制具体实现。
    """

    def __init__(self, config: Dict):
        """
        初始化Agent基础配置

        Args:
            config: Agent配置字典，包含API配置、模型参数等
        """
        self.config = config
        self.state = AgentState.INITIALIZING
        self.logger = logging.getLogger(self.__class__.__name__)

        # 从配置中提取通用参数
        self.max_conversation_turns = config.get('max_conversation_turns', 5)
        self.max_questions_per_file = config.get('max_questions_per_file', 3)
        self.timeout_seconds = config.get('timeout_seconds', 600)

    @property
    def current_state(self) -> AgentState:
        """获取当前Agent状态"""
        return self.state

    def analyze(self, context: AgentContext) -> AgentAnalysisResult:
        """
        执行分析的主入口方法 (模板方法)

        定义了标准的分析流程，确保所有Agent都遵循相同的执行模式：
        1. 验证输入
        2. 初始化分析环境
        3. 执行具体分析逻辑
        4. 处理结果
        5. 清理资源

        Args:
            context: 分析上下文

        Returns:
            AgentAnalysisResult: 分析结果
        """
        try:
            # 1. 验证输入
            self._validate_context(context)

            # 2. 初始化分析环境
            self.state = AgentState.INITIALIZING
            self._initialize_analysis(context)

            # 3. 执行具体分析逻辑 (由子类实现)
            self.state = AgentState.ANALYZING
            result = self._execute_analysis(context)

            # 4. 后处理结果
            self.state = AgentState.REVIEWING
            processed_result = self._post_process_result(result, context)

            # 5. 标记完成
            self.state = AgentState.COMPLETED
            return processed_result

        except Exception as e:
            self.state = AgentState.ERROR
            self.logger.error(f"Agent analysis failed: {e}")
            raise

    def _validate_context(self, context: AgentContext) -> None:
        """
        验证分析上下文的有效性

        Args:
            context: 分析上下文

        Raises:
            ValueError: 当上下文无效时
        """
        if not context.file_path:
            raise ValueError("file_path is required")
        if not context.file_content:
            raise ValueError("file_content is required")
        if not context.language:
            raise ValueError("language is required")

    def _initialize_analysis(self, context: AgentContext) -> None:
        """
        初始化分析环境

        可以被子类重写以添加特定的初始化逻辑
        """
        self.logger.info(f"Initializing analysis for {context.file_path}")

    @abstractmethod
    def _execute_analysis(self, context: AgentContext) -> AgentAnalysisResult:
        """
        执行具体的分析逻辑 (抽象方法)

        这是每个Agent子类必须实现的核心方法，
        包含该Agent特有的分析算法和逻辑。

        Args:
            context: 分析上下文

        Returns:
            AgentAnalysisResult: 分析结果
        """
        pass

    def _post_process_result(self, result: AgentAnalysisResult, context: AgentContext) -> AgentAnalysisResult:
        """
        后处理分析结果

        可以被子类重写以添加特定的后处理逻辑，
        如结果过滤、格式化、质量评估等。

        Args:
            result: 原始分析结果
            context: 分析上下文

        Returns:
            AgentAnalysisResult: 处理后的结果
        """
        # 设置基础元信息
        result.conversation_turns = len(context.conversation_history)

        # 计算分析深度
        if result.questions_asked >= 2 and result.conversation_turns >= 4:
            result.analysis_depth = "deep"
        elif result.questions_asked >= 1 or result.conversation_turns >= 3:
            result.analysis_depth = "medium"
        else:
            result.analysis_depth = "shallow"

        return result

    def get_language_from_file_path(self, file_path: str) -> str:
        """
        从文件路径推断编程语言

        这是一个通用工具方法，所有Agent都可以使用
        """
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'jsx',
            '.tsx': 'tsx',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust',
            '.php': 'php',
            '.rb': 'ruby',
            '.cs': 'csharp',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.sh': 'bash',
            '.sql': 'sql',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.less': 'less',
            '.json': 'json',
            '.xml': 'xml',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.md': 'markdown'
        }

        for ext, lang in extension_map.items():
            if file_path.lower().endswith(ext):
                return lang

        return 'text'  # 默认返回text

    def convert_to_code_issues(self, result: AgentAnalysisResult, file_path: str) -> list:
        """
        将Agent分析结果转换为兼容的CodeIssue格式

        这个方法确保了与现有系统的兼容性，
        是低耦合设计的体现 - Agent内部格式与外部接口解耦。
        """
        from .data_models import CodeIssue

        code_issues = []
        for issue_data in result.issues:
            if isinstance(issue_data, dict):
                code_issue = CodeIssue(
                    line_number=issue_data.get('line_number', 1),
                    severity=issue_data.get('severity', 'info'),
                    category=issue_data.get('category', 'general'),
                    message=issue_data.get('message', ''),
                    suggestion=issue_data.get('suggestion'),
                    confidence=issue_data.get('confidence', 0.8)
                )
                code_issues.append(code_issue)

        # 根据严重程度等级过滤问题
        filtered_issues = self._filter_issues_by_severity(code_issues)

        return filtered_issues

    def _filter_issues_by_severity(self, issues: list) -> list:
        """根据严重程度等级过滤问题"""
        if not issues:
            return issues

        # 获取severity_level配置（如果存在）
        severity_level = getattr(self, 'severity_level', 'standard')

        # 定义各等级允许的严重程度
        allowed_severities = {
            'strict': ['error', 'warning', 'info'],      # 严格模式：检查所有问题
            'standard': ['error', 'warning'],            # 标准模式：检查错误和警告
            'relaxed': ['error']                         # 宽松模式：只检查错误
        }

        current_allowed = allowed_severities.get(severity_level, ['error', 'warning'])

        # 过滤问题
        filtered_issues = []
        for issue in issues:
            # 检查issue是字典还是对象
            if isinstance(issue, dict):
                severity = issue.get('severity', 'info')
            else:
                severity = getattr(issue, 'severity', 'info')

            if severity in current_allowed:
                filtered_issues.append(issue)
            else:
                self.logger.debug(f"过滤掉严重程度为 {severity} 的问题（当前等级：{severity_level}）")

        self.logger.info(f"严重程度过滤：{len(issues)} -> {len(filtered_issues)} （等级：{severity_level}）")
        return filtered_issues