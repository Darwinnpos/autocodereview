# -*- coding: utf-8 -*-
"""
Agent错误处理和恢复机制 - 处理Agent系统的错误和异常情况

高内聚设计：专注于错误处理和恢复的所有方面
- 错误分类和识别
- 错误恢复策略
- 重试机制
- 故障隔离
- 错误报告和日志
"""

import time
import traceback
import logging
from typing import Dict, List, Optional, Callable, Any, Type
from dataclasses import dataclass, field
from enum import Enum
import threading
from functools import wraps

from .data_models import AgentState, AgentContext


class ErrorSeverity(Enum):
    """错误严重程度枚举"""
    LOW = "low"          # 低级错误，可以忽略或简单重试
    MEDIUM = "medium"    # 中级错误，需要处理但不影响主流程
    HIGH = "high"        # 高级错误，影响功能但可以恢复
    CRITICAL = "critical"  # 关键错误，需要立即处理


class ErrorCategory(Enum):
    """错误类别枚举"""
    NETWORK = "network"              # 网络错误
    AI_API = "ai_api"               # AI API错误
    PERMISSION = "permission"        # 权限错误
    RESOURCE = "resource"           # 资源错误（内存、文件等）
    VALIDATION = "validation"       # 数据验证错误
    CONFIGURATION = "configuration" # 配置错误
    TIMEOUT = "timeout"             # 超时错误
    UNKNOWN = "unknown"             # 未知错误


class RecoveryStrategy(Enum):
    """恢复策略枚举"""
    RETRY = "retry"                 # 重试
    FALLBACK = "fallback"          # 降级处理
    SKIP = "skip"                  # 跳过
    ESCALATE = "escalate"          # 升级处理
    RESTART = "restart"            # 重启Agent
    ABORT = "abort"                # 中止操作


@dataclass
class ErrorInfo:
    """错误信息"""
    error_id: str
    exception: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    agent_id: Optional[str]
    context: Optional[AgentContext]
    timestamp: float
    stack_trace: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    recovery_strategy: Optional[RecoveryStrategy] = None


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


class AgentErrorHandler:
    """
    Agent错误处理器 - 处理Agent系统的错误和异常

    核心职责：
    1. 错误捕获和分类
    2. 错误恢复策略执行
    3. 重试机制管理
    4. 故障隔离和降级
    5. 错误监控和报告
    """

    def __init__(self, config: Dict):
        """
        初始化错误处理器

        Args:
            config: 错误处理配置
        """
        self.config = config
        self.enable_auto_recovery = config.get('enable_auto_recovery', True)
        self.max_concurrent_recoveries = config.get('max_concurrent_recoveries', 5)
        self.error_retention_hours = config.get('error_retention_hours', 24)

        # 错误分类器
        self.error_classifiers: Dict[Type[Exception], Callable[[Exception], ErrorCategory]] = {}
        self._init_default_classifiers()

        # 恢复策略映射
        self.recovery_strategies: Dict[ErrorCategory, List[RecoveryStrategy]] = {}
        self._init_default_strategies()

        # 错误存储
        self.error_history: List[ErrorInfo] = []
        self.active_recoveries: Dict[str, ErrorInfo] = {}

        # 回调函数
        self.error_callbacks: List[Callable[[ErrorInfo], None]] = []
        self.recovery_callbacks: List[Callable[[ErrorInfo, bool], None]] = []

        # 线程安全锁
        self.errors_lock = threading.RLock()
        self.recoveries_lock = threading.RLock()

        self.logger = logging.getLogger(__name__)

        # 启动清理线程
        self._start_cleanup_thread()

    def _init_default_classifiers(self):
        """初始化默认错误分类器"""
        import requests
        import openai

        # 网络错误
        self.error_classifiers[requests.ConnectionError] = lambda e: ErrorCategory.NETWORK
        self.error_classifiers[requests.Timeout] = lambda e: ErrorCategory.TIMEOUT
        self.error_classifiers[requests.HTTPError] = lambda e: ErrorCategory.NETWORK

        # AI API错误
        if hasattr(openai, 'error'):
            self.error_classifiers[openai.error.RateLimitError] = lambda e: ErrorCategory.AI_API
            self.error_classifiers[openai.error.APIError] = lambda e: ErrorCategory.AI_API
            self.error_classifiers[openai.error.AuthenticationError] = lambda e: ErrorCategory.PERMISSION

        # 权限错误
        self.error_classifiers[PermissionError] = lambda e: ErrorCategory.PERMISSION

        # 资源错误
        self.error_classifiers[MemoryError] = lambda e: ErrorCategory.RESOURCE
        self.error_classifiers[FileNotFoundError] = lambda e: ErrorCategory.RESOURCE

        # 验证错误
        self.error_classifiers[ValueError] = lambda e: ErrorCategory.VALIDATION
        self.error_classifiers[TypeError] = lambda e: ErrorCategory.VALIDATION

        # 超时错误
        self.error_classifiers[TimeoutError] = lambda e: ErrorCategory.TIMEOUT

    def _init_default_strategies(self):
        """初始化默认恢复策略"""
        self.recovery_strategies = {
            ErrorCategory.NETWORK: [RecoveryStrategy.RETRY, RecoveryStrategy.FALLBACK],
            ErrorCategory.AI_API: [RecoveryStrategy.RETRY, RecoveryStrategy.FALLBACK],
            ErrorCategory.PERMISSION: [RecoveryStrategy.ESCALATE, RecoveryStrategy.ABORT],
            ErrorCategory.RESOURCE: [RecoveryStrategy.RETRY, RecoveryStrategy.RESTART],
            ErrorCategory.VALIDATION: [RecoveryStrategy.SKIP, RecoveryStrategy.ABORT],
            ErrorCategory.CONFIGURATION: [RecoveryStrategy.ESCALATE, RecoveryStrategy.ABORT],
            ErrorCategory.TIMEOUT: [RecoveryStrategy.RETRY, RecoveryStrategy.FALLBACK],
            ErrorCategory.UNKNOWN: [RecoveryStrategy.RETRY, RecoveryStrategy.ESCALATE]
        }

    def handle_error(self, exception: Exception, agent_id: Optional[str] = None,
                    context: Optional[AgentContext] = None,
                    metadata: Optional[Dict] = None) -> ErrorInfo:
        """
        处理错误

        Args:
            exception: 异常对象
            agent_id: Agent ID
            context: Agent上下文
            metadata: 额外元数据

        Returns:
            ErrorInfo: 错误信息
        """
        # 生成错误ID
        error_id = f"error_{int(time.time() * 1000)}_{id(exception)}"

        # 分类错误
        category = self._classify_error(exception)
        severity = self._assess_severity(exception, category)

        # 创建错误信息
        error_info = ErrorInfo(
            error_id=error_id,
            exception=exception,
            category=category,
            severity=severity,
            agent_id=agent_id,
            context=context,
            timestamp=time.time(),
            stack_trace=traceback.format_exc(),
            metadata=metadata or {}
        )

        # 存储错误
        with self.errors_lock:
            self.error_history.append(error_info)

        # 记录日志
        self._log_error(error_info)

        # 触发错误回调
        self._trigger_error_callbacks(error_info)

        # 尝试自动恢复
        if self.enable_auto_recovery and self._should_auto_recover(error_info):
            self._initiate_recovery(error_info)

        return error_info

    def _classify_error(self, exception: Exception) -> ErrorCategory:
        """错误分类"""
        exception_type = type(exception)

        # 查找精确匹配
        if exception_type in self.error_classifiers:
            return self.error_classifiers[exception_type](exception)

        # 查找父类匹配
        for exc_type, classifier in self.error_classifiers.items():
            if isinstance(exception, exc_type):
                return classifier(exception)

        # 默认未知类别
        return ErrorCategory.UNKNOWN

    def _assess_severity(self, exception: Exception, category: ErrorCategory) -> ErrorSeverity:
        """评估错误严重程度"""
        # 基于错误类别的默认严重程度
        severity_mapping = {
            ErrorCategory.NETWORK: ErrorSeverity.MEDIUM,
            ErrorCategory.AI_API: ErrorSeverity.MEDIUM,
            ErrorCategory.PERMISSION: ErrorSeverity.HIGH,
            ErrorCategory.RESOURCE: ErrorSeverity.HIGH,
            ErrorCategory.VALIDATION: ErrorSeverity.LOW,
            ErrorCategory.CONFIGURATION: ErrorSeverity.CRITICAL,
            ErrorCategory.TIMEOUT: ErrorSeverity.MEDIUM,
            ErrorCategory.UNKNOWN: ErrorSeverity.MEDIUM
        }

        base_severity = severity_mapping.get(category, ErrorSeverity.MEDIUM)

        # 可以根据具体异常信息调整严重程度
        if isinstance(exception, MemoryError):
            return ErrorSeverity.CRITICAL
        elif isinstance(exception, KeyboardInterrupt):
            return ErrorSeverity.CRITICAL

        return base_severity

    def _should_auto_recover(self, error_info: ErrorInfo) -> bool:
        """判断是否应该自动恢复"""
        # 检查并发恢复数量限制
        with self.recoveries_lock:
            if len(self.active_recoveries) >= self.max_concurrent_recoveries:
                return False

        # 检查严重程度
        if error_info.severity == ErrorSeverity.CRITICAL:
            return False

        # 检查恢复尝试次数
        if error_info.recovery_attempts >= error_info.max_recovery_attempts:
            return False

        return True

    def _initiate_recovery(self, error_info: ErrorInfo) -> None:
        """启动错误恢复"""
        with self.recoveries_lock:
            self.active_recoveries[error_info.error_id] = error_info

        # 获取恢复策略
        strategies = self.recovery_strategies.get(error_info.category, [RecoveryStrategy.ESCALATE])

        # 在后台线程中执行恢复
        recovery_thread = threading.Thread(
            target=self._execute_recovery,
            args=(error_info, strategies),
            daemon=True
        )
        recovery_thread.start()

    def _execute_recovery(self, error_info: ErrorInfo, strategies: List[RecoveryStrategy]) -> None:
        """执行错误恢复"""
        try:
            error_info.recovery_attempts += 1
            success = False

            for strategy in strategies:
                if self._apply_recovery_strategy(error_info, strategy):
                    success = True
                    error_info.recovery_strategy = strategy
                    break

            # 触发恢复回调
            self._trigger_recovery_callbacks(error_info, success)

            if success:
                self.logger.info(f"Successfully recovered from error {error_info.error_id} "
                               f"using strategy {error_info.recovery_strategy.value}")
            else:
                self.logger.warning(f"Failed to recover from error {error_info.error_id}")

        except Exception as e:
            self.logger.error(f"Error during recovery of {error_info.error_id}: {e}")

        finally:
            # 清理活跃恢复
            with self.recoveries_lock:
                self.active_recoveries.pop(error_info.error_id, None)

    def _apply_recovery_strategy(self, error_info: ErrorInfo, strategy: RecoveryStrategy) -> bool:
        """应用恢复策略"""
        try:
            if strategy == RecoveryStrategy.RETRY:
                return self._retry_operation(error_info)
            elif strategy == RecoveryStrategy.FALLBACK:
                return self._apply_fallback(error_info)
            elif strategy == RecoveryStrategy.SKIP:
                return self._skip_operation(error_info)
            elif strategy == RecoveryStrategy.ESCALATE:
                return self._escalate_error(error_info)
            elif strategy == RecoveryStrategy.RESTART:
                return self._restart_agent(error_info)
            elif strategy == RecoveryStrategy.ABORT:
                return self._abort_operation(error_info)
            else:
                return False
        except Exception as e:
            self.logger.error(f"Error applying recovery strategy {strategy.value}: {e}")
            return False

    def _retry_operation(self, error_info: ErrorInfo) -> bool:
        """重试操作"""
        # 实现重试逻辑
        # 这里需要根据具体的Agent操作来实现
        self.logger.info(f"Retrying operation for error {error_info.error_id}")
        # 返回重试是否成功
        return False  # 默认实现，需要子类或配置来定制

    def _apply_fallback(self, error_info: ErrorInfo) -> bool:
        """应用降级策略"""
        self.logger.info(f"Applying fallback for error {error_info.error_id}")
        # 降级处理逻辑
        return True  # 假设降级总是成功的

    def _skip_operation(self, error_info: ErrorInfo) -> bool:
        """跳过操作"""
        self.logger.info(f"Skipping operation for error {error_info.error_id}")
        return True

    def _escalate_error(self, error_info: ErrorInfo) -> bool:
        """升级错误处理"""
        self.logger.warning(f"Escalating error {error_info.error_id}")
        # 可以发送通知、创建工单等
        return True

    def _restart_agent(self, error_info: ErrorInfo) -> bool:
        """重启Agent"""
        if error_info.agent_id:
            self.logger.warning(f"Restarting agent {error_info.agent_id} for error {error_info.error_id}")
            # 实现Agent重启逻辑
            return True
        return False

    def _abort_operation(self, error_info: ErrorInfo) -> bool:
        """中止操作"""
        self.logger.error(f"Aborting operation for error {error_info.error_id}")
        return True

    def _log_error(self, error_info: ErrorInfo) -> None:
        """记录错误日志"""
        log_level = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }.get(error_info.severity, logging.ERROR)

        self.logger.log(log_level,
                       f"Agent error [{error_info.category.value}]: {error_info.exception} "
                       f"(Agent: {error_info.agent_id}, Error ID: {error_info.error_id})")

    def _trigger_error_callbacks(self, error_info: ErrorInfo) -> None:
        """触发错误回调"""
        for callback in self.error_callbacks:
            try:
                callback(error_info)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")

    def _trigger_recovery_callbacks(self, error_info: ErrorInfo, success: bool) -> None:
        """触发恢复回调"""
        for callback in self.recovery_callbacks:
            try:
                callback(error_info, success)
            except Exception as e:
                self.logger.error(f"Error in recovery callback: {e}")

    def add_error_callback(self, callback: Callable[[ErrorInfo], None]) -> None:
        """添加错误回调"""
        self.error_callbacks.append(callback)

    def add_recovery_callback(self, callback: Callable[[ErrorInfo, bool], None]) -> None:
        """添加恢复回调"""
        self.recovery_callbacks.append(callback)

    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        with self.errors_lock:
            total_errors = len(self.error_history)
            if total_errors == 0:
                return {
                    'total_errors': 0,
                    'category_distribution': {},
                    'severity_distribution': {},
                    'recent_errors': []
                }

            # 分类统计
            category_counts = {}
            severity_counts = {}

            for error in self.error_history:
                category = error.category.value
                severity = error.severity.value

                category_counts[category] = category_counts.get(category, 0) + 1
                severity_counts[severity] = severity_counts.get(severity, 0) + 1

            # 最近错误
            recent_errors = self.error_history[-10:]

            return {
                'total_errors': total_errors,
                'category_distribution': category_counts,
                'severity_distribution': severity_counts,
                'active_recoveries': len(self.active_recoveries),
                'recent_errors': [
                    {
                        'error_id': error.error_id,
                        'category': error.category.value,
                        'severity': error.severity.value,
                        'timestamp': error.timestamp,
                        'agent_id': error.agent_id
                    }
                    for error in recent_errors
                ]
            }

    def _cleanup_old_errors(self) -> None:
        """清理旧错误记录"""
        cutoff_time = time.time() - (self.error_retention_hours * 3600)

        with self.errors_lock:
            initial_count = len(self.error_history)
            self.error_history = [
                error for error in self.error_history
                if error.timestamp > cutoff_time
            ]
            removed_count = initial_count - len(self.error_history)

            if removed_count > 0:
                self.logger.info(f"Cleaned up {removed_count} old error records")

    def _start_cleanup_thread(self) -> None:
        """启动清理线程"""
        def cleanup_worker():
            while True:
                try:
                    self._cleanup_old_errors()
                    time.sleep(3600)  # 每小时清理一次
                except Exception as e:
                    self.logger.error(f"Error in cleanup thread: {e}")

        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        self.logger.info("Error cleanup thread started")


def error_handler(error_handler_instance: AgentErrorHandler,
                 agent_id: Optional[str] = None,
                 context: Optional[AgentContext] = None):
    """
    错误处理装饰器

    Args:
        error_handler_instance: 错误处理器实例
        agent_id: Agent ID
        context: Agent上下文
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_info = error_handler_instance.handle_error(
                    exception=e,
                    agent_id=agent_id,
                    context=context,
                    metadata={'function': func.__name__, 'args': str(args)[:200]}
                )
                # 重新抛出异常，让调用者决定如何处理
                raise
        return wrapper
    return decorator