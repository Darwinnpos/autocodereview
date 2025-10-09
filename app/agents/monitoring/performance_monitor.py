# -*- coding: utf-8 -*-
"""
Agent性能监控系统 - 监控Agent系统的性能指标和运行状态

高内聚设计：专注于性能监控的所有方面
- 性能指标收集
- 实时监控数据
- 性能分析和报告
- 性能告警机制
"""

import time
import threading
import logging
import psutil
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

from ..core.data_models import AgentState


class MetricType(Enum):
    """指标类型枚举"""
    COUNTER = "counter"      # 计数器
    GAUGE = "gauge"         # 仪表盘（瞬时值）
    HISTOGRAM = "histogram"  # 直方图
    TIMER = "timer"         # 计时器


class AlertLevel(Enum):
    """告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    type: MetricType
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    metric_name: str
    condition: str  # 条件表达式，如 "> 1000", "< 0.8"
    level: AlertLevel
    enabled: bool = True
    cooldown_seconds: int = 300  # 冷却时间
    last_triggered: float = 0.0


@dataclass
class PerformanceAlert:
    """性能告警"""
    rule_name: str
    metric_name: str
    current_value: float
    threshold: str
    level: AlertLevel
    message: str
    timestamp: float
    resolved: bool = False


class PerformanceMonitor:
    """
    Agent性能监控器 - 收集和分析Agent系统性能数据

    核心职责：
    1. 实时收集Agent性能指标
    2. 监控系统资源使用情况
    3. 分析性能趋势和异常
    4. 生成性能报告和告警
    5. 提供性能优化建议
    """

    def __init__(self, config: Dict):
        """
        初始化性能监控器

        Args:
            config: 监控配置
        """
        self.config = config
        self.collection_interval = config.get('collection_interval', 10)  # 10秒
        self.history_size = config.get('history_size', 1000)  # 保留1000个历史数据点
        self.enable_system_metrics = config.get('enable_system_metrics', True)

        # 指标存储
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.history_size))
        self.current_metrics: Dict[str, PerformanceMetric] = {}

        # 告警系统
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: List[PerformanceAlert] = []
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []

        # Agent特定指标
        self.agent_metrics: Dict[str, Dict[str, Any]] = defaultdict(dict)

        # 线程安全锁
        self.metrics_lock = threading.RLock()
        self.alerts_lock = threading.RLock()

        self.logger = logging.getLogger(__name__)

        # 启动监控线程
        self._start_monitoring()

    def record_metric(self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE,
                     tags: Optional[Dict[str, str]] = None, unit: str = "",
                     description: str = "") -> None:
        """
        记录性能指标

        Args:
            name: 指标名称
            value: 指标值
            metric_type: 指标类型
            tags: 标签
            unit: 单位
            description: 描述
        """
        with self.metrics_lock:
            timestamp = time.time()

            metric = PerformanceMetric(
                name=name,
                type=metric_type,
                value=value,
                timestamp=timestamp,
                tags=tags or {},
                unit=unit,
                description=description
            )

            # 存储历史数据
            self.metrics[name].append(metric)

            # 更新当前值
            self.current_metrics[name] = metric

            # 检查告警
            self._check_alerts(metric)

    def record_agent_operation(self, agent_id: str, operation: str,
                              duration: float, success: bool,
                              additional_data: Optional[Dict] = None) -> None:
        """
        记录Agent操作指标

        Args:
            agent_id: Agent ID
            operation: 操作名称
            duration: 持续时间（秒）
            success: 是否成功
            additional_data: 额外数据
        """
        # 记录操作时间
        self.record_metric(
            f"agent.{operation}.duration",
            duration,
            MetricType.TIMER,
            tags={"agent_id": agent_id, "success": str(success)},
            unit="seconds",
            description=f"Agent {operation} operation duration"
        )

        # 记录操作计数
        counter_name = f"agent.{operation}.total"
        current_count = self.get_current_metric_value(counter_name, 0)
        self.record_metric(
            counter_name,
            current_count + 1,
            MetricType.COUNTER,
            tags={"agent_id": agent_id},
            description=f"Total {operation} operations"
        )

        # 记录成功率
        success_key = f"agent.{operation}.success"
        error_key = f"agent.{operation}.error"

        if success:
            success_count = self.get_current_metric_value(success_key, 0)
            self.record_metric(success_key, success_count + 1, MetricType.COUNTER)
        else:
            error_count = self.get_current_metric_value(error_key, 0)
            self.record_metric(error_key, error_count + 1, MetricType.COUNTER)

        # 更新Agent特定指标
        with self.metrics_lock:
            if agent_id not in self.agent_metrics:
                self.agent_metrics[agent_id] = {
                    'total_operations': 0,
                    'successful_operations': 0,
                    'failed_operations': 0,
                    'total_duration': 0.0,
                    'average_duration': 0.0,
                    'last_operation': time.time()
                }

            agent_data = self.agent_metrics[agent_id]
            agent_data['total_operations'] += 1
            agent_data['total_duration'] += duration
            agent_data['average_duration'] = agent_data['total_duration'] / agent_data['total_operations']
            agent_data['last_operation'] = time.time()

            if success:
                agent_data['successful_operations'] += 1
            else:
                agent_data['failed_operations'] += 1

            # 添加额外数据
            if additional_data:
                agent_data.update(additional_data)

    def record_resource_usage(self, agent_id: str, cpu_percent: float,
                             memory_mb: float, additional_resources: Optional[Dict] = None) -> None:
        """
        记录Agent资源使用情况

        Args:
            agent_id: Agent ID
            cpu_percent: CPU使用百分比
            memory_mb: 内存使用量（MB）
            additional_resources: 额外资源数据
        """
        tags = {"agent_id": agent_id}

        self.record_metric(
            "agent.resource.cpu_percent",
            cpu_percent,
            MetricType.GAUGE,
            tags=tags,
            unit="percent",
            description="Agent CPU usage percentage"
        )

        self.record_metric(
            "agent.resource.memory_mb",
            memory_mb,
            MetricType.GAUGE,
            tags=tags,
            unit="MB",
            description="Agent memory usage in MB"
        )

        if additional_resources:
            for resource_name, value in additional_resources.items():
                self.record_metric(
                    f"agent.resource.{resource_name}",
                    value,
                    MetricType.GAUGE,
                    tags=tags
                )

    def get_current_metric_value(self, name: str, default: float = 0.0) -> float:
        """
        获取当前指标值

        Args:
            name: 指标名称
            default: 默认值

        Returns:
            float: 当前指标值
        """
        with self.metrics_lock:
            metric = self.current_metrics.get(name)
            return metric.value if metric else default

    def get_metric_history(self, name: str, limit: Optional[int] = None) -> List[PerformanceMetric]:
        """
        获取指标历史数据

        Args:
            name: 指标名称
            limit: 返回数量限制

        Returns:
            List[PerformanceMetric]: 历史数据
        """
        with self.metrics_lock:
            history = list(self.metrics.get(name, []))
            if limit:
                history = history[-limit:]
            return history

    def get_agent_performance_summary(self, agent_id: str) -> Dict[str, Any]:
        """
        获取Agent性能摘要

        Args:
            agent_id: Agent ID

        Returns:
            Dict[str, Any]: 性能摘要
        """
        with self.metrics_lock:
            agent_data = self.agent_metrics.get(agent_id, {})

            # 计算成功率
            total_ops = agent_data.get('total_operations', 0)
            successful_ops = agent_data.get('successful_operations', 0)
            success_rate = (successful_ops / total_ops * 100) if total_ops > 0 else 0

            return {
                'agent_id': agent_id,
                'total_operations': total_ops,
                'success_rate': success_rate,
                'average_duration': agent_data.get('average_duration', 0.0),
                'last_operation': agent_data.get('last_operation', 0),
                'failed_operations': agent_data.get('failed_operations', 0),
                'current_cpu': self.get_current_metric_value(f"agent.resource.cpu_percent", 0),
                'current_memory': self.get_current_metric_value(f"agent.resource.memory_mb", 0)
            }

    def get_system_performance_summary(self) -> Dict[str, Any]:
        """
        获取系统整体性能摘要

        Returns:
            Dict[str, Any]: 系统性能摘要
        """
        with self.metrics_lock:
            # 聚合所有Agent的指标
            total_agents = len(self.agent_metrics)
            total_operations = sum(data.get('total_operations', 0) for data in self.agent_metrics.values())
            total_successful = sum(data.get('successful_operations', 0) for data in self.agent_metrics.values())

            overall_success_rate = (total_successful / total_operations * 100) if total_operations > 0 else 0

            # 平均响应时间
            avg_durations = [data.get('average_duration', 0) for data in self.agent_metrics.values() if data.get('average_duration', 0) > 0]
            overall_avg_duration = sum(avg_durations) / len(avg_durations) if avg_durations else 0

            return {
                'total_agents': total_agents,
                'total_operations': total_operations,
                'overall_success_rate': overall_success_rate,
                'overall_average_duration': overall_avg_duration,
                'active_alerts': len(self.active_alerts),
                'system_cpu': self.get_current_metric_value("system.cpu_percent", 0),
                'system_memory': self.get_current_metric_value("system.memory_percent", 0),
                'timestamp': time.time()
            }

    def add_alert_rule(self, rule: AlertRule) -> None:
        """
        添加告警规则

        Args:
            rule: 告警规则
        """
        with self.alerts_lock:
            self.alert_rules[rule.name] = rule
            self.logger.info(f"Added alert rule: {rule.name}")

    def remove_alert_rule(self, rule_name: str) -> bool:
        """
        移除告警规则

        Args:
            rule_name: 规则名称

        Returns:
            bool: 是否移除成功
        """
        with self.alerts_lock:
            if rule_name in self.alert_rules:
                del self.alert_rules[rule_name]
                self.logger.info(f"Removed alert rule: {rule_name}")
                return True
            return False

    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """
        添加告警回调函数

        Args:
            callback: 回调函数
        """
        self.alert_callbacks.append(callback)

    def get_active_alerts(self) -> List[PerformanceAlert]:
        """
        获取活跃告警

        Returns:
            List[PerformanceAlert]: 活跃告警列表
        """
        with self.alerts_lock:
            return [alert for alert in self.active_alerts if not alert.resolved]

    def resolve_alert(self, alert: PerformanceAlert) -> None:
        """
        解决告警

        Args:
            alert: 告警对象
        """
        with self.alerts_lock:
            alert.resolved = True
            self.logger.info(f"Resolved alert: {alert.rule_name}")

    def _check_alerts(self, metric: PerformanceMetric) -> None:
        """检查告警条件"""
        with self.alerts_lock:
            for rule in self.alert_rules.values():
                if not rule.enabled or rule.metric_name != metric.name:
                    continue

                # 检查冷却时间
                if time.time() - rule.last_triggered < rule.cooldown_seconds:
                    continue

                # 评估条件
                if self._evaluate_alert_condition(metric.value, rule.condition):
                    alert = PerformanceAlert(
                        rule_name=rule.name,
                        metric_name=metric.name,
                        current_value=metric.value,
                        threshold=rule.condition,
                        level=rule.level,
                        message=f"Metric {metric.name} triggered alert rule {rule.name}: "
                               f"current value {metric.value} {rule.condition}",
                        timestamp=time.time()
                    )

                    self.active_alerts.append(alert)
                    rule.last_triggered = time.time()

                    # 触发回调
                    for callback in self.alert_callbacks:
                        try:
                            callback(alert)
                        except Exception as e:
                            self.logger.error(f"Error in alert callback: {e}")

                    self.logger.warning(f"Alert triggered: {alert.message}")

    def _evaluate_alert_condition(self, value: float, condition: str) -> bool:
        """评估告警条件"""
        try:
            # 简单的条件解析 (>, <, >=, <=, ==, !=)
            condition = condition.strip()
            for op in ['>=', '<=', '==', '!=', '>', '<']:
                if op in condition:
                    threshold = float(condition.replace(op, '').strip())
                    if op == '>':
                        return value > threshold
                    elif op == '<':
                        return value < threshold
                    elif op == '>=':
                        return value >= threshold
                    elif op == '<=':
                        return value <= threshold
                    elif op == '==':
                        return value == threshold
                    elif op == '!=':
                        return value != threshold
            return False
        except:
            return False

    def _collect_system_metrics(self) -> None:
        """收集系统级指标"""
        if not self.enable_system_metrics:
            return

        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            self.record_metric(
                "system.cpu_percent",
                cpu_percent,
                MetricType.GAUGE,
                unit="percent",
                description="System CPU usage percentage"
            )

            # 内存使用
            memory = psutil.virtual_memory()
            self.record_metric(
                "system.memory_percent",
                memory.percent,
                MetricType.GAUGE,
                unit="percent",
                description="System memory usage percentage"
            )

            self.record_metric(
                "system.memory_available_mb",
                memory.available / 1024 / 1024,
                MetricType.GAUGE,
                unit="MB",
                description="System available memory in MB"
            )

            # 磁盘使用
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            self.record_metric(
                "system.disk_percent",
                disk_percent,
                MetricType.GAUGE,
                unit="percent",
                description="System disk usage percentage"
            )

        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")

    def _start_monitoring(self) -> None:
        """启动监控线程"""
        def monitoring_worker():
            while True:
                try:
                    self._collect_system_metrics()
                    time.sleep(self.collection_interval)
                except Exception as e:
                    self.logger.error(f"Error in monitoring thread: {e}")

        monitoring_thread = threading.Thread(target=monitoring_worker, daemon=True)
        monitoring_thread.start()
        self.logger.info("Performance monitoring started")

    def export_metrics(self, format_type: str = "json") -> str:
        """
        导出指标数据

        Args:
            format_type: 导出格式 (json, csv, prometheus)

        Returns:
            str: 导出的数据
        """
        if format_type == "json":
            import json
            data = {
                'current_metrics': {
                    name: {
                        'value': metric.value,
                        'timestamp': metric.timestamp,
                        'type': metric.type.value,
                        'unit': metric.unit
                    }
                    for name, metric in self.current_metrics.items()
                },
                'agent_metrics': self.agent_metrics,
                'active_alerts': [
                    {
                        'rule_name': alert.rule_name,
                        'metric_name': alert.metric_name,
                        'current_value': alert.current_value,
                        'level': alert.level.value,
                        'message': alert.message,
                        'timestamp': alert.timestamp
                    }
                    for alert in self.get_active_alerts()
                ]
            }
            return json.dumps(data, indent=2)

        # 其他格式可以后续扩展
        raise NotImplementedError(f"Export format {format_type} not implemented")