# -*- coding: utf-8 -*-
"""
资源管理器 - 智能Agent资源分配和管理

高内聚设计：专注于资源管理的所有方面
- Agent实例池管理
- 负载均衡和调度
- 性能监控和优化
- 资源使用统计
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future

from ..analyzers.code_analyzer import CodeAnalyzer
from ..core.data_models import AgentState
from .task_scheduler import AnalysisTask


class AgentStatus(Enum):
    """Agent状态枚举"""
    IDLE = "idle"           # 空闲
    BUSY = "busy"           # 忙碌
    ERROR = "error"         # 错误状态
    OFFLINE = "offline"     # 离线


@dataclass
class AgentInstance:
    """Agent实例信息"""
    agent_id: str
    agent: CodeAnalyzer
    status: AgentStatus
    current_task_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    total_tasks_completed: int = 0
    total_analysis_time: float = 0.0
    average_response_time: float = 0.0
    error_count: int = 0
    performance_score: float = 1.0  # 性能评分 0-1


@dataclass
class ResourceMetrics:
    """资源使用指标"""
    total_agents: int
    active_agents: int
    idle_agents: int
    busy_agents: int
    error_agents: int
    total_tasks_in_queue: int
    average_queue_wait_time: float
    system_load: float  # 0-1
    throughput_per_minute: float


class ResourceManager:
    """
    资源管理器 - 管理Agent实例池和资源分配

    核心职责：
    1. Agent实例池管理（创建、销毁、复用）
    2. 负载均衡和任务分配
    3. 性能监控和优化
    4. 资源使用统计和报告
    """

    def __init__(self, config: Dict):
        """
        初始化资源管理器

        Args:
            config: 资源管理配置
        """
        self.config = config
        self.min_agents = config.get('min_agents', 8)  # 默认8个并发Agent
        self.max_agents = config.get('max_agents', 32)  # 最大支持32个并发Agent
        self.agent_timeout = config.get('agent_timeout', 600)  # 10分钟
        self.auto_scale = config.get('auto_scale', True)

        # Agent实例池
        self.agent_pool: Dict[str, AgentInstance] = {}
        self.task_queue: List[AnalysisTask] = []
        self.running_tasks: Dict[str, Future] = {}

        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=self.max_agents)

        # 锁和同步
        self.pool_lock = threading.RLock()
        self.queue_lock = threading.RLock()
        self.metrics_lock = threading.RLock()

        # 性能指标
        self.metrics = ResourceMetrics(
            total_agents=0,
            active_agents=0,
            idle_agents=0,
            busy_agents=0,
            error_agents=0,
            total_tasks_in_queue=0,
            average_queue_wait_time=0.0,
            system_load=0.0,
            throughput_per_minute=0.0
        )

        self.logger = logging.getLogger(__name__)

        # 初始化最小数量的Agent
        self._initialize_agent_pool()

        # 启动监控线程
        self._start_monitoring()

    def _initialize_agent_pool(self) -> None:
        """初始化Agent池"""
        with self.pool_lock:
            for i in range(self.min_agents):
                self._create_agent_instance()

        self.logger.info(f"Initialized agent pool with {self.min_agents} agents")

    def _create_agent_instance(self) -> str:
        """
        创建新的Agent实例

        Returns:
            str: 新创建的Agent ID
        """
        agent_id = f"agent_{int(time.time() * 1000)}_{len(self.agent_pool)}"

        try:
            # 创建Agent实例
            agent = CodeAnalyzer(self.config)

            # 创建Agent实例信息
            agent_instance = AgentInstance(
                agent_id=agent_id,
                agent=agent,
                status=AgentStatus.IDLE
            )

            self.agent_pool[agent_id] = agent_instance
            self.logger.info(f"Created agent instance: {agent_id}")

            return agent_id

        except Exception as e:
            self.logger.error(f"Failed to create agent instance: {e}")
            raise

    def assign_task(self, task: AnalysisTask) -> Optional[Future]:
        """
        分配任务给最优的Agent

        Args:
            task: 要分配的分析任务

        Returns:
            Optional[Future]: 任务执行的Future对象，如果无可用Agent则返回None
        """
        with self.pool_lock:
            # 1. 寻找最优的空闲Agent
            best_agent = self._find_best_available_agent()

            if not best_agent:
                # 2. 尝试自动扩容
                if self._can_scale_up():
                    agent_id = self._create_agent_instance()
                    best_agent = self.agent_pool[agent_id]
                else:
                    # 3. 添加到队列等待
                    with self.queue_lock:
                        self.task_queue.append(task)
                    self.logger.info(f"Task {task.task_id} queued, no available agents")
                    return None

            # 4. 分配任务给Agent
            return self._execute_task_with_agent(task, best_agent)

    def _find_best_available_agent(self) -> Optional[AgentInstance]:
        """
        找到最优的可用Agent

        Returns:
            Optional[AgentInstance]: 最优Agent实例，如果没有可用则返回None
        """
        available_agents = [
            agent for agent in self.agent_pool.values()
            if agent.status == AgentStatus.IDLE
        ]

        if not available_agents:
            return None

        # 按性能评分排序，选择最优Agent
        best_agent = max(available_agents, key=lambda a: (
            a.performance_score,
            -a.average_response_time,
            a.total_tasks_completed
        ))

        return best_agent

    def _can_scale_up(self) -> bool:
        """
        检查是否可以扩容

        Returns:
            bool: 是否可以扩容
        """
        return (
            self.auto_scale and
            len(self.agent_pool) < self.max_agents and
            self._get_system_load() > 0.8
        )

    def _execute_task_with_agent(self, task: AnalysisTask, agent_instance: AgentInstance) -> Future:
        """
        使用指定Agent执行任务

        Args:
            task: 分析任务
            agent_instance: Agent实例

        Returns:
            Future: 任务执行的Future对象
        """
        # 更新Agent状态
        agent_instance.status = AgentStatus.BUSY
        agent_instance.current_task_id = task.task_id
        agent_instance.last_activity = time.time()

        # 提交任务到线程池
        future = self.executor.submit(self._run_task, task, agent_instance)
        self.running_tasks[task.task_id] = future

        # 添加完成回调
        future.add_done_callback(lambda f: self._on_task_completed(task, agent_instance, f))

        self.logger.info(f"Assigned task {task.task_id} to agent {agent_instance.agent_id}")
        return future

    def _run_task(self, task: AnalysisTask, agent_instance: AgentInstance):
        """
        执行具体的分析任务

        Args:
            task: 分析任务
            agent_instance: Agent实例

        Returns:
            分析结果
        """
        start_time = time.time()

        try:
            # 执行Agent分析
            result = agent_instance.agent.analyze(task.context)

            # 更新性能指标
            execution_time = time.time() - start_time
            self._update_agent_performance(agent_instance, execution_time, success=True)

            return result

        except Exception as e:
            # 错误处理
            execution_time = time.time() - start_time
            self._update_agent_performance(agent_instance, execution_time, success=False)

            agent_instance.status = AgentStatus.ERROR
            agent_instance.error_count += 1

            self.logger.error(f"Agent {agent_instance.agent_id} failed to execute task "
                            f"{task.task_id}: {e}")
            raise

    def _on_task_completed(self, task: AnalysisTask, agent_instance: AgentInstance, future: Future):
        """
        任务完成回调

        Args:
            task: 完成的任务
            agent_instance: 执行任务的Agent实例
            future: 任务的Future对象
        """
        with self.pool_lock:
            # 更新Agent状态
            agent_instance.status = AgentStatus.IDLE
            agent_instance.current_task_id = None
            agent_instance.last_activity = time.time()

            # 从运行任务中移除
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]

            # 检查是否有队列中的任务
            self._process_queued_tasks()

    def _update_agent_performance(self, agent_instance: AgentInstance, execution_time: float,
                                 success: bool):
        """
        更新Agent性能指标

        Args:
            agent_instance: Agent实例
            execution_time: 执行时间
            success: 是否成功
        """
        if success:
            agent_instance.total_tasks_completed += 1
            agent_instance.total_analysis_time += execution_time

            # 更新平均响应时间
            if agent_instance.total_tasks_completed > 0:
                agent_instance.average_response_time = (
                    agent_instance.total_analysis_time / agent_instance.total_tasks_completed
                )

            # 更新性能评分
            agent_instance.performance_score = self._calculate_performance_score(agent_instance)

    def _calculate_performance_score(self, agent_instance: AgentInstance) -> float:
        """
        计算Agent性能评分

        Args:
            agent_instance: Agent实例

        Returns:
            float: 性能评分 0-1
        """
        if agent_instance.total_tasks_completed == 0:
            return 1.0

        # 成功率
        success_rate = 1.0 - (agent_instance.error_count /
                             max(agent_instance.total_tasks_completed + agent_instance.error_count, 1))

        # 速度评分（基于平均响应时间）
        avg_time = agent_instance.average_response_time
        speed_score = max(0.1, min(1.0, 300 / max(avg_time, 30)))  # 5分钟为基准

        # 综合评分
        performance_score = (success_rate * 0.7 + speed_score * 0.3)

        return max(0.1, min(1.0, performance_score))

    def _process_queued_tasks(self):
        """处理队列中的任务"""
        with self.queue_lock:
            if not self.task_queue:
                return

            # 获取队列中的下一个任务
            task = self.task_queue.pop(0)

            # 尝试分配给可用Agent
            self.assign_task(task)

    def _get_system_load(self) -> float:
        """
        获取系统负载

        Returns:
            float: 系统负载 0-1
        """
        with self.pool_lock:
            if not self.agent_pool:
                return 0.0

            busy_agents = sum(1 for agent in self.agent_pool.values()
                             if agent.status == AgentStatus.BUSY)

            return busy_agents / len(self.agent_pool)

    def _start_monitoring(self):
        """启动监控线程"""
        def monitor():
            while True:
                try:
                    self._update_metrics()
                    self._cleanup_inactive_agents()
                    time.sleep(30)  # 每30秒更新一次
                except Exception as e:
                    self.logger.error(f"Monitoring error: {e}")

        monitoring_thread = threading.Thread(target=monitor, daemon=True)
        monitoring_thread.start()

    def _update_metrics(self):
        """更新系统指标"""
        with self.metrics_lock:
            with self.pool_lock:
                agent_statuses = [agent.status for agent in self.agent_pool.values()]

                self.metrics.total_agents = len(self.agent_pool)
                self.metrics.idle_agents = agent_statuses.count(AgentStatus.IDLE)
                self.metrics.busy_agents = agent_statuses.count(AgentStatus.BUSY)
                self.metrics.error_agents = agent_statuses.count(AgentStatus.ERROR)
                self.metrics.active_agents = self.metrics.busy_agents + self.metrics.idle_agents

            with self.queue_lock:
                self.metrics.total_tasks_in_queue = len(self.task_queue)

            self.metrics.system_load = self._get_system_load()

    def _cleanup_inactive_agents(self):
        """清理不活跃的Agent"""
        current_time = time.time()
        agents_to_remove = []

        with self.pool_lock:
            for agent_id, agent in self.agent_pool.items():
                # 检查超时的Agent
                if (agent.status != AgentStatus.BUSY and
                    current_time - agent.last_activity > self.agent_timeout and
                    len(self.agent_pool) > self.min_agents):
                    agents_to_remove.append(agent_id)

            # 移除不活跃的Agent
            for agent_id in agents_to_remove:
                del self.agent_pool[agent_id]
                self.logger.info(f"Removed inactive agent: {agent_id}")

    def get_metrics(self) -> ResourceMetrics:
        """
        获取当前资源指标

        Returns:
            ResourceMetrics: 资源使用指标
        """
        with self.metrics_lock:
            return self.metrics

    def shutdown(self):
        """关闭资源管理器"""
        self.logger.info("Shutting down resource manager...")
        self.executor.shutdown(wait=True)

        with self.pool_lock:
            self.agent_pool.clear()

        self.logger.info("Resource manager shutdown complete")