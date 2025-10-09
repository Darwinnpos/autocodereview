# -*- coding: utf-8 -*-
"""
安全策略模块 - 定义Agent系统的安全策略和操作控制

高内聚设计：集中管理所有安全策略的定义和验证
- 操作权限策略
- 安全边界控制
- 风险评估规则
- 审计要求定义
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from abc import ABC, abstractmethod

from ..agents.core.data_models import AgentContext, AgentAnalysisResult


class OperationType(Enum):
    """操作类型枚举"""
    READ_FILE = "read_file"                    # 读取文件
    ANALYZE_CODE = "analyze_code"              # 分析代码
    GENERATE_COMMENT = "generate_comment"      # 生成评论
    POST_COMMENT = "post_comment"              # 发布评论到GitLab
    MODIFY_CODE = "modify_code"                # 修改代码（禁止）
    ACCESS_EXTERNAL_API = "access_external_api"  # 访问外部API
    EXECUTE_COMMAND = "execute_command"        # 执行系统命令（禁止）


class RiskLevel(Enum):
    """风险等级枚举"""
    LOW = 1      # 低风险：读取操作
    MEDIUM = 2   # 中风险：分析和生成
    HIGH = 3     # 高风险：写入操作
    CRITICAL = 4 # 关键风险：系统操作（禁止）


class AuthorizationLevel(Enum):
    """授权级别枚举"""
    AUTOMATIC = "automatic"      # 自动授权
    USER_CONFIRM = "user_confirm"  # 需要用户确认
    ADMIN_APPROVE = "admin_approve"  # 需要管理员批准
    FORBIDDEN = "forbidden"      # 完全禁止


@dataclass
class SecurityContext:
    """安全上下文"""
    user_id: str
    session_id: str
    operation_type: OperationType
    resource_path: Optional[str] = None
    target_system: Optional[str] = None  # GitLab, AI API等
    additional_metadata: Dict = field(default_factory=dict)


@dataclass
class PermissionRule:
    """权限规则"""
    operation_type: OperationType
    risk_level: RiskLevel
    authorization_level: AuthorizationLevel
    conditions: Dict = field(default_factory=dict)
    description: str = ""


class SecurityPolicy(ABC):
    """安全策略抽象基类"""

    @abstractmethod
    def evaluate_permission(self, context: SecurityContext) -> AuthorizationLevel:
        """
        评估操作权限

        Args:
            context: 安全上下文

        Returns:
            AuthorizationLevel: 所需授权级别
        """
        pass

    @abstractmethod
    def get_risk_level(self, operation_type: OperationType) -> RiskLevel:
        """
        获取操作风险级别

        Args:
            operation_type: 操作类型

        Returns:
            RiskLevel: 风险级别
        """
        pass


class OperationPolicy(SecurityPolicy):
    """
    操作策略 - 定义Agent允许和禁止的操作

    核心原则：
    1. 只读操作 - 允许读取代码和分析
    2. 生成操作 - 允许生成评论和建议
    3. 写入操作 - 需要人工确认
    4. 系统操作 - 完全禁止
    """

    def __init__(self):
        """初始化操作策略"""
        self.permission_rules = self._initialize_permission_rules()
        self.forbidden_operations = {
            OperationType.MODIFY_CODE,
            OperationType.EXECUTE_COMMAND
        }

        # 外部API白名单
        self.allowed_external_apis = {
            'openai.com',
            'api.openai.com',
            'gitlab.com'  # 用户配置的GitLab实例
        }

    def _initialize_permission_rules(self) -> Dict[OperationType, PermissionRule]:
        """初始化权限规则"""
        return {
            OperationType.READ_FILE: PermissionRule(
                operation_type=OperationType.READ_FILE,
                risk_level=RiskLevel.LOW,
                authorization_level=AuthorizationLevel.AUTOMATIC,
                description="读取文件内容进行分析"
            ),

            OperationType.ANALYZE_CODE: PermissionRule(
                operation_type=OperationType.ANALYZE_CODE,
                risk_level=RiskLevel.MEDIUM,
                authorization_level=AuthorizationLevel.AUTOMATIC,
                description="使用AI分析代码"
            ),

            OperationType.GENERATE_COMMENT: PermissionRule(
                operation_type=OperationType.GENERATE_COMMENT,
                risk_level=RiskLevel.MEDIUM,
                authorization_level=AuthorizationLevel.AUTOMATIC,
                description="生成评审评论"
            ),

            OperationType.POST_COMMENT: PermissionRule(
                operation_type=OperationType.POST_COMMENT,
                risk_level=RiskLevel.HIGH,
                authorization_level=AuthorizationLevel.USER_CONFIRM,
                description="发布评论到GitLab"
            ),

            OperationType.ACCESS_EXTERNAL_API: PermissionRule(
                operation_type=OperationType.ACCESS_EXTERNAL_API,
                risk_level=RiskLevel.MEDIUM,
                authorization_level=AuthorizationLevel.AUTOMATIC,
                conditions={'whitelist_only': True},
                description="访问外部API"
            ),

            OperationType.MODIFY_CODE: PermissionRule(
                operation_type=OperationType.MODIFY_CODE,
                risk_level=RiskLevel.CRITICAL,
                authorization_level=AuthorizationLevel.FORBIDDEN,
                description="修改代码（禁止操作）"
            ),

            OperationType.EXECUTE_COMMAND: PermissionRule(
                operation_type=OperationType.EXECUTE_COMMAND,
                risk_level=RiskLevel.CRITICAL,
                authorization_level=AuthorizationLevel.FORBIDDEN,
                description="执行系统命令（禁止操作）"
            )
        }

    def evaluate_permission(self, context: SecurityContext) -> AuthorizationLevel:
        """
        评估操作权限

        Args:
            context: 安全上下文

        Returns:
            AuthorizationLevel: 所需授权级别
        """
        # 检查禁止操作
        if context.operation_type in self.forbidden_operations:
            return AuthorizationLevel.FORBIDDEN

        # 获取基础权限规则
        rule = self.permission_rules.get(context.operation_type)
        if not rule:
            # 未定义的操作默认禁止
            return AuthorizationLevel.FORBIDDEN

        # 检查特殊条件
        authorization_level = rule.authorization_level

        # 外部API访问检查
        if context.operation_type == OperationType.ACCESS_EXTERNAL_API:
            authorization_level = self._evaluate_external_api_access(context, rule)

        # 发布评论的额外检查
        elif context.operation_type == OperationType.POST_COMMENT:
            authorization_level = self._evaluate_comment_posting(context, rule)

        return authorization_level

    def _evaluate_external_api_access(self, context: SecurityContext, rule: PermissionRule) -> AuthorizationLevel:
        """评估外部API访问权限"""
        target = context.target_system
        if not target:
            return AuthorizationLevel.FORBIDDEN

        # 检查是否在白名单中
        is_allowed = any(allowed in target.lower() for allowed in self.allowed_external_apis)

        if not is_allowed:
            return AuthorizationLevel.FORBIDDEN

        return rule.authorization_level

    def _evaluate_comment_posting(self, context: SecurityContext, rule: PermissionRule) -> AuthorizationLevel:
        """评估评论发布权限"""
        # 发布评论始终需要用户确认
        return AuthorizationLevel.USER_CONFIRM

    def get_risk_level(self, operation_type: OperationType) -> RiskLevel:
        """获取操作风险级别"""
        rule = self.permission_rules.get(operation_type)
        return rule.risk_level if rule else RiskLevel.CRITICAL

    def is_operation_allowed(self, operation_type: OperationType) -> bool:
        """
        检查操作是否被允许

        Args:
            operation_type: 操作类型

        Returns:
            bool: 是否允许操作
        """
        return operation_type not in self.forbidden_operations

    def get_allowed_operations(self) -> Set[OperationType]:
        """
        获取所有允许的操作类型

        Returns:
            Set[OperationType]: 允许的操作集合
        """
        all_operations = set(OperationType)
        return all_operations - self.forbidden_operations


class AgentSecurityPolicy(SecurityPolicy):
    """
    Agent专用安全策略 - 针对Agent系统的特殊安全要求

    扩展操作策略，添加Agent特定的安全控制：
    - Agent实例隔离
    - 资源使用限制
    - 会话安全管理
    """

    def __init__(self, operation_policy: OperationPolicy):
        """
        初始化Agent安全策略

        Args:
            operation_policy: 基础操作策略
        """
        self.operation_policy = operation_policy
        self.max_session_duration = 3600  # 1小时
        self.max_api_calls_per_session = 100
        self.max_file_size_bytes = 1024 * 1024  # 1MB

    def evaluate_permission(self, context: SecurityContext) -> AuthorizationLevel:
        """
        评估Agent操作权限

        Args:
            context: 安全上下文

        Returns:
            AuthorizationLevel: 所需授权级别
        """
        # 首先检查基础操作权限
        base_authorization = self.operation_policy.evaluate_permission(context)

        if base_authorization == AuthorizationLevel.FORBIDDEN:
            return AuthorizationLevel.FORBIDDEN

        # Agent特定的安全检查
        agent_authorization = self._evaluate_agent_specific_security(context)

        # 返回更严格的授权级别
        return max(base_authorization, agent_authorization, key=lambda x: x.value)

    def _evaluate_agent_specific_security(self, context: SecurityContext) -> AuthorizationLevel:
        """评估Agent特定的安全要求"""
        # 检查文件大小限制
        if (context.operation_type == OperationType.READ_FILE and
            context.additional_metadata.get('file_size', 0) > self.max_file_size_bytes):
            return AuthorizationLevel.USER_CONFIRM

        # 检查API调用频率
        session_api_calls = context.additional_metadata.get('session_api_calls', 0)
        if session_api_calls > self.max_api_calls_per_session:
            return AuthorizationLevel.USER_CONFIRM

        return AuthorizationLevel.AUTOMATIC

    def get_risk_level(self, operation_type: OperationType) -> RiskLevel:
        """获取操作风险级别"""
        return self.operation_policy.get_risk_level(operation_type)

    def validate_agent_context(self, agent_context: AgentContext) -> bool:
        """
        验证Agent上下文的安全性

        Args:
            agent_context: Agent上下文

        Returns:
            bool: 上下文是否安全
        """
        # 检查文件路径安全性
        if not self._is_safe_file_path(agent_context.file_path):
            return False

        # 检查内容大小
        if len(agent_context.file_content) > self.max_file_size_bytes:
            return False

        return True

    def _is_safe_file_path(self, file_path: str) -> bool:
        """
        检查文件路径是否安全

        Args:
            file_path: 文件路径

        Returns:
            bool: 路径是否安全
        """
        # 禁止的路径模式
        forbidden_patterns = [
            '../',           # 目录遍历
            '/..',           # 目录遍历
            '/etc/',         # 系统配置
            '/proc/',        # 系统进程
            '/dev/',         # 设备文件
            '~/',            # 用户主目录
        ]

        file_path_lower = file_path.lower()
        return not any(pattern in file_path_lower for pattern in forbidden_patterns)