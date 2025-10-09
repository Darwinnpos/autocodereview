# -*- coding: utf-8 -*-
"""
Agent会话管理器 - 管理Agent的会话状态和上下文传递

高内聚设计：专注于会话管理的所有方面
- 会话生命周期管理
- 上下文状态保持
- 会话间数据传递
- 会话安全和隔离
"""

import time
import uuid
import threading
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from .data_models import AgentState, AgentMessage, AgentContext


class SessionStatus(Enum):
    """会话状态枚举"""
    ACTIVE = "active"        # 活跃会话
    IDLE = "idle"           # 空闲会话
    PAUSED = "paused"       # 暂停会话
    COMPLETED = "completed"  # 已完成会话
    EXPIRED = "expired"     # 已过期会话
    ERROR = "error"         # 错误状态


@dataclass
class SessionContext:
    """会话上下文数据"""
    session_id: str
    user_id: str
    created_at: float
    last_activity: float
    status: SessionStatus = SessionStatus.ACTIVE
    agent_context: Optional[AgentContext] = None
    conversation_history: List[AgentMessage] = field(default_factory=list)
    session_metadata: Dict[str, Any] = field(default_factory=dict)
    shared_context: Dict[str, Any] = field(default_factory=dict)  # 跨Agent共享的上下文
    analysis_progress: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossSessionContext:
    """跨会话上下文 - 用于在多个相关会话间传递信息"""
    context_id: str
    related_sessions: List[str]
    shared_data: Dict[str, Any]
    created_at: float
    expires_at: float


class SessionManager:
    """
    Agent会话管理器 - 管理Agent的会话状态和上下文

    核心职责：
    1. 会话生命周期管理（创建、维护、销毁）
    2. 会话状态跟踪和更新
    3. 上下文数据保持和传递
    4. 会话间协作和数据共享
    5. 会话安全隔离和权限控制
    """

    def __init__(self, config: Dict):
        """
        初始化会话管理器

        Args:
            config: 会话管理配置
        """
        self.config = config
        self.session_timeout = config.get('session_timeout', 3600)  # 1小时
        self.max_sessions_per_user = config.get('max_sessions_per_user', 10)
        self.max_conversation_history = config.get('max_conversation_history', 100)
        self.cleanup_interval = config.get('cleanup_interval', 300)  # 5分钟

        # 会话存储
        self.active_sessions: Dict[str, SessionContext] = {}
        self.cross_session_contexts: Dict[str, CrossSessionContext] = {}

        # 用户会话映射
        self.user_sessions: Dict[str, List[str]] = {}

        # 线程安全锁
        self.sessions_lock = threading.RLock()
        self.cross_context_lock = threading.RLock()

        self.logger = logging.getLogger(__name__)

        # 启动清理线程
        self._start_cleanup_thread()

    def create_session(self, user_id: str, initial_context: Optional[AgentContext] = None,
                      session_metadata: Optional[Dict] = None) -> str:
        """
        创建新的Agent会话

        Args:
            user_id: 用户ID
            initial_context: 初始Agent上下文
            session_metadata: 会话元数据

        Returns:
            str: 会话ID
        """
        with self.sessions_lock:
            # 检查用户会话数量限制
            user_session_count = len(self.user_sessions.get(user_id, []))
            if user_session_count >= self.max_sessions_per_user:
                # 清理最旧的会话
                self._cleanup_oldest_user_session(user_id)

            # 生成会话ID
            session_id = f"session_{uuid.uuid4().hex[:12]}"

            # 创建会话上下文
            current_time = time.time()
            session_context = SessionContext(
                session_id=session_id,
                user_id=user_id,
                created_at=current_time,
                last_activity=current_time,
                agent_context=initial_context,
                session_metadata=session_metadata or {}
            )

            # 存储会话
            self.active_sessions[session_id] = session_context

            # 更新用户会话映射
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = []
            self.user_sessions[user_id].append(session_id)

            self.logger.info(f"Created session {session_id} for user {user_id}")
            return session_id

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """
        获取会话上下文

        Args:
            session_id: 会话ID

        Returns:
            Optional[SessionContext]: 会话上下文，如果不存在则返回None
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                # 更新最后活动时间
                session.last_activity = time.time()
                session.status = SessionStatus.ACTIVE
            return session

    def update_session_context(self, session_id: str, agent_context: AgentContext) -> bool:
        """
        更新会话的Agent上下文

        Args:
            session_id: 会话ID
            agent_context: 新的Agent上下文

        Returns:
            bool: 是否更新成功
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                session.agent_context = agent_context
                session.last_activity = time.time()
                self.logger.debug(f"Updated context for session {session_id}")
                return True
            return False

    def add_conversation_message(self, session_id: str, message: AgentMessage) -> bool:
        """
        添加对话消息到会话历史

        Args:
            session_id: 会话ID
            message: Agent消息

        Returns:
            bool: 是否添加成功
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                session.conversation_history.append(message)

                # 限制历史记录长度
                if len(session.conversation_history) > self.max_conversation_history:
                    session.conversation_history = session.conversation_history[-self.max_conversation_history:]

                session.last_activity = time.time()
                self.logger.debug(f"Added message to session {session_id} conversation")
                return True
            return False

    def get_conversation_history(self, session_id: str, limit: Optional[int] = None) -> List[AgentMessage]:
        """
        获取会话对话历史

        Args:
            session_id: 会话ID
            limit: 返回消息数量限制

        Returns:
            List[AgentMessage]: 对话历史消息
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                history = session.conversation_history
                if limit:
                    history = history[-limit:]
                return history.copy()
            return []

    def set_session_metadata(self, session_id: str, key: str, value: Any) -> bool:
        """
        设置会话元数据

        Args:
            session_id: 会话ID
            key: 元数据键
            value: 元数据值

        Returns:
            bool: 是否设置成功
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                session.session_metadata[key] = value
                session.last_activity = time.time()
                return True
            return False

    def get_session_metadata(self, session_id: str, key: str, default: Any = None) -> Any:
        """
        获取会话元数据

        Args:
            session_id: 会话ID
            key: 元数据键
            default: 默认值

        Returns:
            Any: 元数据值
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                return session.session_metadata.get(key, default)
            return default

    def share_context_between_sessions(self, source_session_id: str,
                                     target_session_id: str,
                                     context_data: Dict[str, Any]) -> bool:
        """
        在会话间共享上下文数据

        Args:
            source_session_id: 源会话ID
            target_session_id: 目标会话ID
            context_data: 要共享的上下文数据

        Returns:
            bool: 是否共享成功
        """
        with self.sessions_lock:
            source_session = self.active_sessions.get(source_session_id)
            target_session = self.active_sessions.get(target_session_id)

            if source_session and target_session:
                # 在目标会话中设置共享上下文
                target_session.shared_context.update(context_data)
                target_session.last_activity = time.time()

                self.logger.info(f"Shared context from session {source_session_id} to {target_session_id}")
                return True
            return False

    def create_cross_session_context(self, related_sessions: List[str],
                                   shared_data: Dict[str, Any],
                                   lifetime_seconds: int = 3600) -> str:
        """
        创建跨会话上下文

        Args:
            related_sessions: 相关会话ID列表
            shared_data: 共享数据
            lifetime_seconds: 生存时间（秒）

        Returns:
            str: 跨会话上下文ID
        """
        with self.cross_context_lock:
            context_id = f"cross_ctx_{uuid.uuid4().hex[:8]}"
            current_time = time.time()

            cross_context = CrossSessionContext(
                context_id=context_id,
                related_sessions=related_sessions.copy(),
                shared_data=shared_data.copy(),
                created_at=current_time,
                expires_at=current_time + lifetime_seconds
            )

            self.cross_session_contexts[context_id] = cross_context

            self.logger.info(f"Created cross-session context {context_id} for sessions: {related_sessions}")
            return context_id

    def get_cross_session_context(self, context_id: str) -> Optional[CrossSessionContext]:
        """
        获取跨会话上下文

        Args:
            context_id: 跨会话上下文ID

        Returns:
            Optional[CrossSessionContext]: 跨会话上下文，如果不存在或已过期则返回None
        """
        with self.cross_context_lock:
            cross_context = self.cross_session_contexts.get(context_id)
            if cross_context and time.time() <= cross_context.expires_at:
                return cross_context
            elif cross_context:
                # 已过期，删除
                del self.cross_session_contexts[context_id]
            return None

    def pause_session(self, session_id: str) -> bool:
        """
        暂停会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否暂停成功
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                session.status = SessionStatus.PAUSED
                session.last_activity = time.time()
                self.logger.info(f"Paused session {session_id}")
                return True
            return False

    def resume_session(self, session_id: str) -> bool:
        """
        恢复会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否恢复成功
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session and session.status == SessionStatus.PAUSED:
                session.status = SessionStatus.ACTIVE
                session.last_activity = time.time()
                self.logger.info(f"Resumed session {session_id}")
                return True
            return False

    def complete_session(self, session_id: str) -> bool:
        """
        完成会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否完成成功
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                session.status = SessionStatus.COMPLETED
                session.last_activity = time.time()
                self.logger.info(f"Completed session {session_id}")
                return True
            return False

    def end_session(self, session_id: str) -> bool:
        """
        结束并删除会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否结束成功
        """
        with self.sessions_lock:
            session = self.active_sessions.get(session_id)
            if session:
                # 从用户会话映射中移除
                user_id = session.user_id
                if user_id in self.user_sessions:
                    if session_id in self.user_sessions[user_id]:
                        self.user_sessions[user_id].remove(session_id)
                    if not self.user_sessions[user_id]:
                        del self.user_sessions[user_id]

                # 删除会话
                del self.active_sessions[session_id]

                self.logger.info(f"Ended session {session_id}")
                return True
            return False

    def get_user_sessions(self, user_id: str) -> List[SessionContext]:
        """
        获取用户的所有活跃会话

        Args:
            user_id: 用户ID

        Returns:
            List[SessionContext]: 用户会话列表
        """
        with self.sessions_lock:
            user_session_ids = self.user_sessions.get(user_id, [])
            sessions = []
            for session_id in user_session_ids:
                session = self.active_sessions.get(session_id)
                if session:
                    sessions.append(session)
            return sessions

    def get_session_statistics(self) -> Dict[str, Any]:
        """
        获取会话统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        with self.sessions_lock:
            total_sessions = len(self.active_sessions)
            status_counts = {}

            for session in self.active_sessions.values():
                status = session.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            with self.cross_context_lock:
                cross_contexts = len(self.cross_session_contexts)

            return {
                'total_sessions': total_sessions,
                'status_distribution': status_counts,
                'total_users': len(self.user_sessions),
                'cross_session_contexts': cross_contexts,
                'average_sessions_per_user': total_sessions / max(len(self.user_sessions), 1)
            }

    def _cleanup_oldest_user_session(self, user_id: str):
        """清理用户最旧的会话"""
        user_session_ids = self.user_sessions.get(user_id, [])
        if user_session_ids:
            # 找到最旧的会话
            oldest_session_id = None
            oldest_time = float('inf')

            for session_id in user_session_ids:
                session = self.active_sessions.get(session_id)
                if session and session.last_activity < oldest_time:
                    oldest_time = session.last_activity
                    oldest_session_id = session_id

            if oldest_session_id:
                self.end_session(oldest_session_id)
                self.logger.info(f"Cleaned up oldest session {oldest_session_id} for user {user_id}")

    def _cleanup_expired_sessions(self):
        """清理过期的会话"""
        current_time = time.time()
        expired_sessions = []

        with self.sessions_lock:
            for session_id, session in self.active_sessions.items():
                if current_time - session.last_activity > self.session_timeout:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                session = self.active_sessions[session_id]
                session.status = SessionStatus.EXPIRED
                self.end_session(session_id)

        if expired_sessions:
            self.logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

    def _cleanup_expired_cross_contexts(self):
        """清理过期的跨会话上下文"""
        current_time = time.time()
        expired_contexts = []

        with self.cross_context_lock:
            for context_id, cross_context in self.cross_session_contexts.items():
                if current_time > cross_context.expires_at:
                    expired_contexts.append(context_id)

            for context_id in expired_contexts:
                del self.cross_session_contexts[context_id]

        if expired_contexts:
            self.logger.info(f"Cleaned up {len(expired_contexts)} expired cross-session contexts")

    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_worker():
            while True:
                try:
                    self._cleanup_expired_sessions()
                    self._cleanup_expired_cross_contexts()
                    time.sleep(self.cleanup_interval)
                except Exception as e:
                    self.logger.error(f"Error in cleanup thread: {e}")

        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        self.logger.info("Session cleanup thread started")