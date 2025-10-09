# -*- coding: utf-8 -*-
"""
用户授权管理器 - 处理用户授权确认和权限决策

高内聚设计：专注于用户授权管理的所有方面
- 授权请求处理
- 用户确认管理
- 权限决策记录
- 审计日志记录
"""

import time
import uuid
import threading
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from .policies import SecurityContext, AuthorizationLevel, OperationType


class AuthorizationStatus(Enum):
    """授权状态枚举"""
    PENDING = "pending"      # 等待确认
    APPROVED = "approved"    # 已批准
    DENIED = "denied"        # 已拒绝
    EXPIRED = "expired"      # 已过期
    CANCELLED = "cancelled"  # 已取消


@dataclass
class AuthorizationRequest:
    """授权请求"""
    request_id: str
    user_id: str
    operation_type: OperationType
    description: str
    security_context: SecurityContext
    required_level: AuthorizationLevel
    status: AuthorizationStatus = AuthorizationStatus.PENDING
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 300)  # 5分钟过期
    approved_at: Optional[float] = None
    approved_by: Optional[str] = None
    denial_reason: Optional[str] = None


@dataclass
class AuthorizationResponse:
    """授权响应"""
    request_id: str
    status: AuthorizationStatus
    message: str = ""
    metadata: Dict = field(default_factory=dict)


class UserAuthorizer:
    """
    用户授权管理器 - 管理需要用户确认的操作

    核心职责：
    1. 处理授权请求
    2. 管理用户确认流程
    3. 记录授权决策
    4. 提供授权状态查询
    """

    def __init__(self, config: Dict):
        """
        初始化用户授权管理器

        Args:
            config: 授权配置
        """
        self.config = config
        self.request_timeout = config.get('request_timeout', 300)  # 5分钟
        self.max_pending_requests = config.get('max_pending_requests', 50)

        # 存储授权请求
        self.pending_requests: Dict[str, AuthorizationRequest] = {}
        self.completed_requests: Dict[str, AuthorizationRequest] = {}

        # 线程安全锁
        self.requests_lock = threading.RLock()

        # 事件回调
        self.authorization_callbacks: Dict[str, Callable] = {}

        self.logger = logging.getLogger(__name__)

        # 启动清理线程
        self._start_cleanup_thread()

    def request_authorization(self, security_context: SecurityContext,
                            required_level: AuthorizationLevel,
                            description: str = "") -> AuthorizationRequest:
        """
        请求用户授权

        Args:
            security_context: 安全上下文
            required_level: 所需授权级别
            description: 操作描述

        Returns:
            AuthorizationRequest: 授权请求对象
        """
        # 生成请求ID
        request_id = f"auth_{uuid.uuid4().hex[:8]}"

        # 创建授权请求
        auth_request = AuthorizationRequest(
            request_id=request_id,
            user_id=security_context.user_id,
            operation_type=security_context.operation_type,
            description=description or self._generate_description(security_context),
            security_context=security_context,
            required_level=required_level
        )

        with self.requests_lock:
            # 检查待处理请求数量
            if len(self.pending_requests) >= self.max_pending_requests:
                self._cleanup_expired_requests()

            if len(self.pending_requests) >= self.max_pending_requests:
                raise RuntimeError("Too many pending authorization requests")

            # 存储请求
            self.pending_requests[request_id] = auth_request

        self.logger.info(f"Created authorization request {request_id} for user {auth_request.user_id}")
        return auth_request

    def approve_request(self, request_id: str, approved_by: str) -> AuthorizationResponse:
        """
        批准授权请求

        Args:
            request_id: 请求ID
            approved_by: 批准人

        Returns:
            AuthorizationResponse: 授权响应
        """
        with self.requests_lock:
            auth_request = self.pending_requests.get(request_id)

            if not auth_request:
                return AuthorizationResponse(
                    request_id=request_id,
                    status=AuthorizationStatus.DENIED,
                    message="Authorization request not found"
                )

            # 检查是否过期
            if time.time() > auth_request.expires_at:
                auth_request.status = AuthorizationStatus.EXPIRED
                self._move_to_completed(request_id, auth_request)
                return AuthorizationResponse(
                    request_id=request_id,
                    status=AuthorizationStatus.EXPIRED,
                    message="Authorization request has expired"
                )

            # 批准请求
            auth_request.status = AuthorizationStatus.APPROVED
            auth_request.approved_at = time.time()
            auth_request.approved_by = approved_by

            # 移动到已完成列表
            self._move_to_completed(request_id, auth_request)

            # 触发回调
            self._trigger_callback(request_id, auth_request)

            self.logger.info(f"Approved authorization request {request_id} by {approved_by}")

            return AuthorizationResponse(
                request_id=request_id,
                status=AuthorizationStatus.APPROVED,
                message="Authorization approved"
            )

    def deny_request(self, request_id: str, denied_by: str, reason: str = "") -> AuthorizationResponse:
        """
        拒绝授权请求

        Args:
            request_id: 请求ID
            denied_by: 拒绝人
            reason: 拒绝原因

        Returns:
            AuthorizationResponse: 授权响应
        """
        with self.requests_lock:
            auth_request = self.pending_requests.get(request_id)

            if not auth_request:
                return AuthorizationResponse(
                    request_id=request_id,
                    status=AuthorizationStatus.DENIED,
                    message="Authorization request not found"
                )

            # 拒绝请求
            auth_request.status = AuthorizationStatus.DENIED
            auth_request.approved_by = denied_by  # 记录决策人
            auth_request.denial_reason = reason

            # 移动到已完成列表
            self._move_to_completed(request_id, auth_request)

            # 触发回调
            self._trigger_callback(request_id, auth_request)

            self.logger.info(f"Denied authorization request {request_id} by {denied_by}: {reason}")

            return AuthorizationResponse(
                request_id=request_id,
                status=AuthorizationStatus.DENIED,
                message=f"Authorization denied: {reason}"
            )

    def get_pending_requests(self, user_id: Optional[str] = None) -> List[AuthorizationRequest]:
        """
        获取待处理的授权请求

        Args:
            user_id: 用户ID（可选，用于过滤）

        Returns:
            List[AuthorizationRequest]: 待处理请求列表
        """
        with self.requests_lock:
            requests = list(self.pending_requests.values())

            if user_id:
                requests = [req for req in requests if req.user_id == user_id]

            # 按创建时间排序
            requests.sort(key=lambda x: x.created_at)

            return requests

    def get_request_status(self, request_id: str) -> Optional[AuthorizationRequest]:
        """
        获取授权请求状态

        Args:
            request_id: 请求ID

        Returns:
            Optional[AuthorizationRequest]: 请求状态，如果不存在则返回None
        """
        with self.requests_lock:
            # 先检查待处理请求
            if request_id in self.pending_requests:
                return self.pending_requests[request_id]

            # 再检查已完成请求
            if request_id in self.completed_requests:
                return self.completed_requests[request_id]

            return None

    def wait_for_authorization(self, request_id: str, timeout: Optional[float] = None) -> AuthorizationStatus:
        """
        等待授权结果

        Args:
            request_id: 请求ID
            timeout: 超时时间（秒），None表示使用默认超时

        Returns:
            AuthorizationStatus: 最终授权状态
        """
        if timeout is None:
            timeout = self.request_timeout

        start_time = time.time()

        while time.time() - start_time < timeout:
            auth_request = self.get_request_status(request_id)

            if not auth_request:
                return AuthorizationStatus.CANCELLED

            if auth_request.status != AuthorizationStatus.PENDING:
                return auth_request.status

            time.sleep(1)  # 等待1秒后重新检查

        # 超时处理
        self._expire_request(request_id)
        return AuthorizationStatus.EXPIRED

    def cancel_request(self, request_id: str) -> bool:
        """
        取消授权请求

        Args:
            request_id: 请求ID

        Returns:
            bool: 是否成功取消
        """
        with self.requests_lock:
            auth_request = self.pending_requests.get(request_id)

            if not auth_request:
                return False

            auth_request.status = AuthorizationStatus.CANCELLED
            self._move_to_completed(request_id, auth_request)

            self.logger.info(f"Cancelled authorization request {request_id}")
            return True

    def register_callback(self, request_id: str, callback: Callable[[AuthorizationRequest], None]):
        """
        注册授权结果回调

        Args:
            request_id: 请求ID
            callback: 回调函数
        """
        self.authorization_callbacks[request_id] = callback

    def _generate_description(self, security_context: SecurityContext) -> str:
        """生成操作描述"""
        operation_descriptions = {
            OperationType.POST_COMMENT: "发布代码评审评论到GitLab",
            OperationType.ACCESS_EXTERNAL_API: f"访问外部API: {security_context.target_system}",
            OperationType.READ_FILE: f"读取文件: {security_context.resource_path}",
            OperationType.ANALYZE_CODE: "使用AI分析代码",
            OperationType.GENERATE_COMMENT: "生成评审评论"
        }

        return operation_descriptions.get(
            security_context.operation_type,
            f"执行操作: {security_context.operation_type.value}"
        )

    def _move_to_completed(self, request_id: str, auth_request: AuthorizationRequest):
        """将请求移动到已完成列表"""
        if request_id in self.pending_requests:
            del self.pending_requests[request_id]

        self.completed_requests[request_id] = auth_request

        # 限制已完成请求的数量
        if len(self.completed_requests) > 1000:
            # 删除最旧的请求
            oldest_id = min(self.completed_requests.keys(),
                          key=lambda x: self.completed_requests[x].created_at)
            del self.completed_requests[oldest_id]

    def _trigger_callback(self, request_id: str, auth_request: AuthorizationRequest):
        """触发授权结果回调"""
        callback = self.authorization_callbacks.get(request_id)
        if callback:
            try:
                callback(auth_request)
            except Exception as e:
                self.logger.error(f"Error in authorization callback for {request_id}: {e}")
            finally:
                # 清理回调
                del self.authorization_callbacks[request_id]

    def _expire_request(self, request_id: str):
        """使请求过期"""
        with self.requests_lock:
            auth_request = self.pending_requests.get(request_id)
            if auth_request:
                auth_request.status = AuthorizationStatus.EXPIRED
                self._move_to_completed(request_id, auth_request)

    def _cleanup_expired_requests(self):
        """清理过期的请求"""
        current_time = time.time()
        expired_ids = []

        with self.requests_lock:
            for request_id, auth_request in self.pending_requests.items():
                if current_time > auth_request.expires_at:
                    expired_ids.append(request_id)

            for request_id in expired_ids:
                self._expire_request(request_id)

        if expired_ids:
            self.logger.info(f"Cleaned up {len(expired_ids)} expired authorization requests")

    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_worker():
            while True:
                try:
                    self._cleanup_expired_requests()
                    time.sleep(60)  # 每分钟清理一次
                except Exception as e:
                    self.logger.error(f"Error in cleanup thread: {e}")

        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()

    def get_authorization_statistics(self) -> Dict:
        """
        获取授权统计信息

        Returns:
            Dict: 统计信息
        """
        with self.requests_lock:
            total_completed = len(self.completed_requests)
            approved_count = sum(1 for req in self.completed_requests.values()
                               if req.status == AuthorizationStatus.APPROVED)
            denied_count = sum(1 for req in self.completed_requests.values()
                             if req.status == AuthorizationStatus.DENIED)
            expired_count = sum(1 for req in self.completed_requests.values()
                              if req.status == AuthorizationStatus.EXPIRED)

            return {
                'pending_requests': len(self.pending_requests),
                'total_completed': total_completed,
                'approved_count': approved_count,
                'denied_count': denied_count,
                'expired_count': expired_count,
                'approval_rate': approved_count / max(total_completed, 1) * 100
            }