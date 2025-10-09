# -*- coding: utf-8 -*-
"""
权限管理器 - 权限系统的中央协调器

高内聚设计：集中管理所有权限相关的核心逻辑
- 权限决策协调
- 安全策略执行
- 用户授权管理
- 审计日志记录
"""

import time
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass

from .policies import SecurityPolicy, OperationPolicy, AgentSecurityPolicy, SecurityContext, OperationType, AuthorizationLevel
from .authorizer import UserAuthorizer, AuthorizationRequest, AuthorizationStatus


@dataclass
class PermissionDecision:
    """权限决策结果"""
    allowed: bool
    authorization_level: AuthorizationLevel
    message: str
    request_id: Optional[str] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PermissionManager:
    """
    权限管理器 - Agent系统权限控制的中央协调器

    核心职责：
    1. 协调安全策略和用户授权
    2. 提供统一的权限检查接口
    3. 管理权限决策流程
    4. 记录和审计所有权限相关操作

    设计原则：
    - 默认拒绝：未明确允许的操作默认禁止
    - 最小权限：仅授予完成任务所需的最小权限
    - 用户控制：所有写入操作需要用户明确授权
    """

    def __init__(self, config: Dict):
        """
        初始化权限管理器

        Args:
            config: 权限管理配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 初始化安全策略
        self.operation_policy = OperationPolicy()
        self.agent_security_policy = AgentSecurityPolicy(self.operation_policy)

        # 初始化用户授权管理器
        auth_config = config.get('authorization', {})
        self.user_authorizer = UserAuthorizer(auth_config)

        # 权限决策缓存（可选）
        self.enable_caching = config.get('enable_permission_caching', False)
        self.permission_cache: Dict[str, PermissionDecision] = {}
        self.cache_ttl = config.get('cache_ttl', 300)  # 5分钟

        self.logger.info("PermissionManager initialized with strict security policies")

    def check_permission(self, security_context: SecurityContext) -> PermissionDecision:
        """
        检查操作权限 - 权限系统的主要入口

        Args:
            security_context: 安全上下文

        Returns:
            PermissionDecision: 权限决策结果
        """
        try:
            # 1. 检查缓存（如果启用）
            if self.enable_caching:
                cached_decision = self._get_cached_decision(security_context)
                if cached_decision:
                    return cached_decision

            # 2. 基础安全策略评估
            authorization_level = self.agent_security_policy.evaluate_permission(security_context)

            # 3. 根据授权级别处理
            decision = self._process_authorization_level(security_context, authorization_level)

            # 4. 记录决策
            self._log_permission_decision(security_context, decision)

            # 5. 缓存决策（如果启用且为自动操作）
            if self.enable_caching and authorization_level == AuthorizationLevel.AUTOMATIC:
                self._cache_decision(security_context, decision)

            return decision

        except Exception as e:
            self.logger.error(f"Error in permission check: {e}")
            # 安全失败 - 默认拒绝
            return PermissionDecision(
                allowed=False,
                authorization_level=AuthorizationLevel.FORBIDDEN,
                message=f"Permission check failed: {str(e)}"
            )

    def _process_authorization_level(self, security_context: SecurityContext,
                                   authorization_level: AuthorizationLevel) -> PermissionDecision:
        """
        处理授权级别

        Args:
            security_context: 安全上下文
            authorization_level: 授权级别

        Returns:
            PermissionDecision: 权限决策
        """
        if authorization_level == AuthorizationLevel.FORBIDDEN:
            return PermissionDecision(
                allowed=False,
                authorization_level=authorization_level,
                message=f"Operation {security_context.operation_type.value} is forbidden"
            )

        elif authorization_level == AuthorizationLevel.AUTOMATIC:
            return PermissionDecision(
                allowed=True,
                authorization_level=authorization_level,
                message="Operation automatically authorized"
            )

        elif authorization_level == AuthorizationLevel.USER_CONFIRM:
            return self._handle_user_confirmation(security_context, authorization_level)

        elif authorization_level == AuthorizationLevel.ADMIN_APPROVE:
            return PermissionDecision(
                allowed=False,
                authorization_level=authorization_level,
                message="Admin approval required (not implemented)"
            )

        else:
            # 未知授权级别 - 默认拒绝
            return PermissionDecision(
                allowed=False,
                authorization_level=AuthorizationLevel.FORBIDDEN,
                message=f"Unknown authorization level: {authorization_level}"
            )

    def _handle_user_confirmation(self, security_context: SecurityContext,
                                authorization_level: AuthorizationLevel) -> PermissionDecision:
        """
        处理需要用户确认的操作

        Args:
            security_context: 安全上下文
            authorization_level: 授权级别

        Returns:
            PermissionDecision: 权限决策
        """
        try:
            # 创建授权请求
            description = self._generate_authorization_description(security_context)
            auth_request = self.user_authorizer.request_authorization(
                security_context=security_context,
                required_level=authorization_level,
                description=description
            )

            return PermissionDecision(
                allowed=False,  # 暂时不允许，需要等待用户确认
                authorization_level=authorization_level,
                message="Waiting for user confirmation",
                request_id=auth_request.request_id,
                metadata={
                    'auth_request': auth_request,
                    'requires_user_action': True
                }
            )

        except Exception as e:
            self.logger.error(f"Failed to create authorization request: {e}")
            return PermissionDecision(
                allowed=False,
                authorization_level=AuthorizationLevel.FORBIDDEN,
                message=f"Failed to create authorization request: {str(e)}"
            )

    def wait_for_user_authorization(self, request_id: str, timeout: Optional[float] = None) -> PermissionDecision:
        """
        等待用户授权结果

        Args:
            request_id: 授权请求ID
            timeout: 超时时间

        Returns:
            PermissionDecision: 最终权限决策
        """
        try:
            status = self.user_authorizer.wait_for_authorization(request_id, timeout)

            if status == AuthorizationStatus.APPROVED:
                return PermissionDecision(
                    allowed=True,
                    authorization_level=AuthorizationLevel.USER_CONFIRM,
                    message="Operation approved by user",
                    request_id=request_id
                )
            else:
                reason = self._get_denial_reason(status)
                return PermissionDecision(
                    allowed=False,
                    authorization_level=AuthorizationLevel.USER_CONFIRM,
                    message=f"Operation not approved: {reason}",
                    request_id=request_id
                )

        except Exception as e:
            self.logger.error(f"Error waiting for user authorization: {e}")
            return PermissionDecision(
                allowed=False,
                authorization_level=AuthorizationLevel.FORBIDDEN,
                message=f"Authorization failed: {str(e)}",
                request_id=request_id
            )

    def get_pending_authorizations(self, user_id: Optional[str] = None) -> List[AuthorizationRequest]:
        """
        获取待处理的授权请求

        Args:
            user_id: 用户ID（可选）

        Returns:
            List[AuthorizationRequest]: 待处理请求列表
        """
        return self.user_authorizer.get_pending_requests(user_id)

    def approve_authorization(self, request_id: str, approved_by: str) -> bool:
        """
        批准授权请求

        Args:
            request_id: 请求ID
            approved_by: 批准人

        Returns:
            bool: 是否成功批准
        """
        try:
            response = self.user_authorizer.approve_request(request_id, approved_by)
            success = response.status == AuthorizationStatus.APPROVED

            if success:
                self.logger.info(f"Authorization {request_id} approved by {approved_by}")
            else:
                self.logger.warning(f"Failed to approve authorization {request_id}: {response.message}")

            return success

        except Exception as e:
            self.logger.error(f"Error approving authorization {request_id}: {e}")
            return False

    def deny_authorization(self, request_id: str, denied_by: str, reason: str = "") -> bool:
        """
        拒绝授权请求

        Args:
            request_id: 请求ID
            denied_by: 拒绝人
            reason: 拒绝原因

        Returns:
            bool: 是否成功拒绝
        """
        try:
            response = self.user_authorizer.deny_request(request_id, denied_by, reason)
            success = response.status == AuthorizationStatus.DENIED

            if success:
                self.logger.info(f"Authorization {request_id} denied by {denied_by}: {reason}")
            else:
                self.logger.warning(f"Failed to deny authorization {request_id}: {response.message}")

            return success

        except Exception as e:
            self.logger.error(f"Error denying authorization {request_id}: {e}")
            return False

    def validate_agent_operation(self, operation_type: OperationType,
                                user_id: str,
                                **kwargs) -> PermissionDecision:
        """
        验证Agent操作权限的便捷方法

        Args:
            operation_type: 操作类型
            user_id: 用户ID
            **kwargs: 其他上下文参数

        Returns:
            PermissionDecision: 权限决策
        """
        security_context = SecurityContext(
            user_id=user_id,
            session_id=kwargs.get('session_id', ''),
            operation_type=operation_type,
            resource_path=kwargs.get('resource_path'),
            target_system=kwargs.get('target_system'),
            additional_metadata=kwargs.get('metadata', {})
        )

        return self.check_permission(security_context)

    def _generate_authorization_description(self, security_context: SecurityContext) -> str:
        """生成授权描述"""
        operation_name = security_context.operation_type.value.replace('_', ' ').title()

        if security_context.resource_path:
            return f"{operation_name}: {security_context.resource_path}"
        elif security_context.target_system:
            return f"{operation_name} on {security_context.target_system}"
        else:
            return operation_name

    def _get_denial_reason(self, status: AuthorizationStatus) -> str:
        """获取拒绝原因"""
        reasons = {
            AuthorizationStatus.DENIED: "explicitly denied by user",
            AuthorizationStatus.EXPIRED: "request expired",
            AuthorizationStatus.CANCELLED: "request was cancelled"
        }
        return reasons.get(status, f"unknown status: {status.value}")

    def _log_permission_decision(self, security_context: SecurityContext, decision: PermissionDecision):
        """记录权限决策"""
        self.logger.info(
            f"Permission decision: user={security_context.user_id}, "
            f"operation={security_context.operation_type.value}, "
            f"allowed={decision.allowed}, "
            f"level={decision.authorization_level.value}, "
            f"request_id={decision.request_id}"
        )

    def _get_cache_key(self, security_context: SecurityContext) -> str:
        """生成缓存键"""
        return f"{security_context.user_id}:{security_context.operation_type.value}:{security_context.resource_path}"

    def _get_cached_decision(self, security_context: SecurityContext) -> Optional[PermissionDecision]:
        """获取缓存的决策"""
        cache_key = self._get_cache_key(security_context)
        cached = self.permission_cache.get(cache_key)

        if cached and time.time() - cached.metadata.get('cached_at', 0) < self.cache_ttl:
            return cached

        # 清理过期缓存
        if cached:
            del self.permission_cache[cache_key]

        return None

    def _cache_decision(self, security_context: SecurityContext, decision: PermissionDecision):
        """缓存权限决策"""
        cache_key = self._get_cache_key(security_context)
        decision.metadata['cached_at'] = time.time()
        self.permission_cache[cache_key] = decision

    def get_permission_statistics(self) -> Dict:
        """
        获取权限系统统计信息

        Returns:
            Dict: 统计信息
        """
        auth_stats = self.user_authorizer.get_authorization_statistics()

        return {
            'authorization_stats': auth_stats,
            'cache_size': len(self.permission_cache) if self.enable_caching else 0,
            'security_policies': {
                'allowed_operations': len(self.operation_policy.get_allowed_operations()),
                'forbidden_operations': len(self.operation_policy.forbidden_operations)
            }
        }