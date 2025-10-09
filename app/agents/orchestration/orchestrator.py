# -*- coding: utf-8 -*-
"""
Agent编排器 - 协调整个Agent系统的工作流程

高内聚设计：统一管理Agent系统的所有协调逻辑
- 工作流程编排
- 任务分发和监控
- 结果收集和聚合
- 进度跟踪和报告
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import Future, as_completed

from .task_scheduler import TaskScheduler, TaskBatch, AnalysisTask
from .resource_manager import ResourceManager
from ..core.data_models import AgentContext, AgentAnalysisResult
from ..core.session_manager import SessionManager
from ..core.error_handler import AgentErrorHandler
from ..monitoring.performance_monitor import PerformanceMonitor
from ...services.gitlab_client import GitLabClient


class OrchestrationState(Enum):
    """编排状态枚举"""
    INITIALIZING = "initializing"
    PLANNING = "planning"
    EXECUTING = "executing"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class OrchestrationProgress:
    """编排进度信息"""
    state: OrchestrationState
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    current_batch: int
    total_batches: int
    estimated_completion_time: Optional[float] = None
    current_operations: List[str] = field(default_factory=list)


@dataclass
class OrchestrationResult:
    """编排结果"""
    review_id: str
    total_files_analyzed: int
    total_issues_found: int
    analysis_summary: Dict
    file_results: List[Dict]
    execution_time: float
    performance_metrics: Dict


class AgentOrchestrator:
    """
    Agent编排器 - 协调多Agent系统的核心控制器

    核心职责：
    1. 接收MR审查请求，制定执行计划
    2. 协调TaskScheduler和ResourceManager
    3. 监控执行进度，处理异常情况
    4. 聚合分析结果，生成最终报告
    """

    def __init__(self, task_scheduler: TaskScheduler, resource_manager: ResourceManager, config: Dict):
        """
        初始化编排器

        Args:
            task_scheduler: 任务调度器
            resource_manager: 资源管理器
            config: 编排配置
        """
        self.config = config
        self.task_scheduler = task_scheduler
        self.resource_manager = resource_manager

        # 初始化会话管理器
        session_config = config.get('session_manager', {
            'session_timeout': 3600,
            'max_sessions_per_user': 10,
            'max_conversation_history': 100,
            'cleanup_interval': 300
        })
        self.session_manager = SessionManager(session_config)

        # 初始化性能监控器
        monitor_config = config.get('performance_monitor', {
            'collection_interval': 10,
            'history_size': 1000,
            'enable_system_metrics': True
        })
        self.performance_monitor = PerformanceMonitor(monitor_config)

        # 初始化错误处理器
        error_handler_config = config.get('error_handler', {
            'enable_auto_recovery': True,
            'max_concurrent_recoveries': 5,
            'error_retention_hours': 24
        })
        self.error_handler = AgentErrorHandler(error_handler_config)

        self.logger = logging.getLogger(__name__)

        # 注册性能监控告警规则
        self._setup_performance_alerts()

        self.logger.info("AgentOrchestrator initialized with enhanced monitoring and error handling")

        # 编排状态
        self.current_orchestrations: Dict[str, OrchestrationProgress] = {}
        self.progress_callbacks: Dict[str, Callable] = {}

        # 性能统计
        self.total_orchestrations = 0
        self.successful_orchestrations = 0
        self.failed_orchestrations = 0

    def process_mr_review(self, mr_changes: List[Dict], mr_info: Dict, ai_config: Dict) -> 'OrchestrationResult':
        """
        处理MR审查（简化接口，用于ReviewService集成）- 并行执行

        Args:
            mr_changes: MR变更列表
            mr_info: MR信息
            ai_config: AI配置

        Returns:
            OrchestrationResult: 编排结果
        """
        from ..analyzers.code_analyzer import CodeAnalyzer
        from ..core.data_models import AgentContext
        from concurrent.futures import as_completed

        file_results = []
        total_issues = 0

        try:
            # 定义单个文件分析函数
            def analyze_file(change: Dict) -> Dict:
                file_path = change.get('new_path', '')
                self.logger.info(f"[Parallel] Starting analysis for {file_path}")

                # 创建Agent并分析
                agent = CodeAnalyzer(ai_config)
                language = agent.get_language_from_file_path(file_path)

                context = AgentContext(
                    file_path=file_path,
                    file_content=change.get('file_content', ''),
                    changed_lines=change.get('changed_lines', []),
                    diff_content=change.get('diff', ''),
                    language=language,
                    mr_title=mr_info.get('title', ''),
                    mr_description=mr_info.get('description', ''),
                    review_config={'severity_threshold': ai_config.get('review_severity_level', 'standard')}
                )

                result = agent.analyze(context)
                issues = agent.convert_to_code_issues(result, file_path)

                self.logger.info(f"[Parallel] Completed analysis for {file_path}: {len(issues)} issues found")

                return {
                    'file_path': file_path,
                    'issues': issues
                }

            # 并行提交所有文件分析任务
            self.logger.info(f"[Orchestrator] Starting parallel analysis of {len(mr_changes)} files")
            futures = {}
            for change in mr_changes:
                future = self.resource_manager.executor.submit(analyze_file, change)
                futures[future] = change.get('new_path', 'unknown')

            # 收集结果（按完成顺序）
            completed_count = 0
            for future in as_completed(futures):
                try:
                    result = future.result()
                    file_results.append(result)
                    total_issues += len(result['issues'])
                    completed_count += 1
                    self.logger.info(f"[Orchestrator] Progress: {completed_count}/{len(mr_changes)} files analyzed")
                except Exception as e:
                    file_path = futures[future]
                    self.logger.error(f"[Parallel] Error analyzing {file_path}: {e}")
                    file_results.append({
                        'file_path': file_path,
                        'issues': []
                    })

            self.logger.info(f"[Orchestrator] Parallel analysis complete: {total_issues} total issues found")

            # 返回成功结果
            return type('OrchestrationResult', (), {
                'success': True,
                'file_results': file_results,
                'total_issues_found': total_issues,
                'error': None
            })()

        except Exception as e:
            self.logger.error(f"Error in process_mr_review: {e}")
            return type('OrchestrationResult', (), {
                'success': False,
                'file_results': [],
                'total_issues_found': 0,
                'error': str(e)
            })()

    def start_review_orchestration(self, review_id: str, mr_url: str, user_config: Dict,
                                  gitlab_client: GitLabClient,
                                  progress_callback: Optional[Callable] = None) -> Future:
        """
        启动代码审查编排流程

        Args:
            review_id: 审查ID
            mr_url: MR URL
            user_config: 用户配置
            gitlab_client: GitLab客户端
            progress_callback: 进度回调函数

        Returns:
            Future: 编排任务的Future对象
        """
        self.total_orchestrations += 1

        # 注册进度回调
        if progress_callback:
            self.progress_callbacks[review_id] = progress_callback

        # 初始化进度跟踪
        progress = OrchestrationProgress(
            state=OrchestrationState.INITIALIZING,
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            current_batch=0,
            total_batches=0
        )
        self.current_orchestrations[review_id] = progress

        # 提交编排任务
        future = self.resource_manager.executor.submit(
            self._execute_orchestration,
            review_id, mr_url, user_config, gitlab_client
        )

        # 添加完成回调
        future.add_done_callback(lambda f: self._on_orchestration_completed(review_id, f))

        self.logger.info(f"Started orchestration for review {review_id}")
        return future

    def _execute_orchestration(self, review_id: str, mr_url: str, user_config: Dict,
                              gitlab_client: GitLabClient) -> OrchestrationResult:
        """
        执行编排流程

        Args:
            review_id: 审查ID
            mr_url: MR URL
            user_config: 用户配置
            gitlab_client: GitLab客户端

        Returns:
            OrchestrationResult: 编排结果
        """
        start_time = time.time()
        progress = self.current_orchestrations[review_id]

        try:
            # 阶段1：规划阶段
            progress.state = OrchestrationState.PLANNING
            self._notify_progress(review_id, progress)

            execution_plan = self._create_execution_plan(mr_url, gitlab_client, user_config)
            progress.total_tasks = sum(len(batch.tasks) for batch in execution_plan)
            progress.total_batches = len(execution_plan)

            # 阶段2：执行阶段
            progress.state = OrchestrationState.EXECUTING
            self._notify_progress(review_id, progress)

            file_results = self._execute_analysis_plan(review_id, execution_plan, gitlab_client, user_config)

            # 阶段3：聚合阶段
            progress.state = OrchestrationState.AGGREGATING
            self._notify_progress(review_id, progress)

            orchestration_result = self._aggregate_results(review_id, file_results, start_time)

            # 完成
            progress.state = OrchestrationState.COMPLETED
            self._notify_progress(review_id, progress)

            self.successful_orchestrations += 1
            return orchestration_result

        except Exception as e:
            progress.state = OrchestrationState.ERROR
            self._notify_progress(review_id, progress)
            self.failed_orchestrations += 1
            self.logger.error(f"Orchestration failed for review {review_id}: {e}")
            raise

    def _create_execution_plan(self, mr_url: str, gitlab_client: GitLabClient,
                              user_config: Dict) -> List[TaskBatch]:
        """
        创建执行计划

        Args:
            mr_url: MR URL
            gitlab_client: GitLab客户端
            user_config: 用户配置

        Returns:
            List[TaskBatch]: 执行计划
        """
        # 解析MR信息
        project_path, project_id, mr_iid = gitlab_client.parse_mr_url(mr_url)
        mr_info = gitlab_client.get_mr_info(project_id, mr_iid)
        mr_changes = gitlab_client.get_mr_changes(project_id, mr_iid)

        # 使用任务调度器创建执行计划
        execution_plan = self.task_scheduler.create_execution_plan(mr_changes, mr_info)

        # 填充完整的上下文信息
        self._enrich_task_contexts(execution_plan, gitlab_client, project_id, mr_info, user_config)

        return execution_plan

    def _enrich_task_contexts(self, execution_plan: List[TaskBatch], gitlab_client: GitLabClient,
                             project_id: str, mr_info: Dict, user_config: Dict):
        """
        填充任务上下文的完整信息

        Args:
            execution_plan: 执行计划
            gitlab_client: GitLab客户端
            project_id: 项目ID
            mr_info: MR信息
            user_config: 用户配置
        """
        for batch in execution_plan:
            for task in batch.tasks:
                try:
                    # 获取完整文件内容
                    file_content = gitlab_client.get_file_content(
                        project_id, task.file_path, mr_info.get('source_branch', 'main')
                    )

                    if file_content:
                        # 更新上下文
                        task.context.file_content = file_content
                        task.context.language = self._detect_language(task.file_path)
                        task.context.changed_lines = self._extract_changed_lines(task.context.diff_content)
                        task.context.review_config = user_config.get('review_config', {})

                        self.logger.debug(f"Enriched context for task {task.task_id}")
                    else:
                        self.logger.warning(f"Could not get file content for {task.file_path}")

                except Exception as e:
                    self.logger.error(f"Failed to enrich context for task {task.task_id}: {e}")

    def _execute_analysis_plan(self, review_id: str, execution_plan: List[TaskBatch],
                              gitlab_client: GitLabClient, user_config: Dict) -> List[Dict]:
        """
        执行分析计划

        Args:
            review_id: 审查ID
            execution_plan: 执行计划
            gitlab_client: GitLab客户端
            user_config: 用户配置

        Returns:
            List[Dict]: 文件分析结果列表
        """
        all_results = []
        progress = self.current_orchestrations[review_id]

        for batch_index, batch in enumerate(execution_plan):
            progress.current_batch = batch_index + 1
            progress.current_operations = [f"批次 {batch_index + 1}: 分析 {len(batch.tasks)} 个文件"]
            self._notify_progress(review_id, progress)

            # 并行执行批次中的任务
            batch_results = self._execute_task_batch(review_id, batch)
            all_results.extend(batch_results)

            # 更新进度
            progress.completed_tasks += len([r for r in batch_results if r.get('success')])
            progress.failed_tasks += len([r for r in batch_results if not r.get('success')])

        return all_results

    def _execute_task_batch(self, review_id: str, batch: TaskBatch) -> List[Dict]:
        """
        执行任务批次

        Args:
            review_id: 审查ID
            batch: 任务批次

        Returns:
            List[Dict]: 批次执行结果
        """
        # 提交所有任务到资源管理器
        task_futures = {}
        for task in batch.tasks:
            future = self.resource_manager.assign_task(task)
            if future:
                task_futures[task.task_id] = (task, future)

        # 等待所有任务完成
        results = []
        for task_id, (task, future) in task_futures.items():
            try:
                # 等待任务完成
                agent_result = future.result(timeout=task.estimated_time + 60)

                # 转换为兼容格式
                file_result = {
                    'task_id': task_id,
                    'file_path': task.file_path,
                    'success': True,
                    'analysis_result': agent_result,
                    'issues_count': len(agent_result.issues),
                    'analysis_depth': agent_result.analysis_depth,
                    'conversation_turns': agent_result.conversation_turns,
                    'confidence_score': agent_result.confidence_score,
                    'execution_time': getattr(agent_result, 'execution_time', 0)
                }

                results.append(file_result)
                self.logger.info(f"Task {task_id} completed successfully")

            except Exception as e:
                # 任务执行失败
                error_result = {
                    'task_id': task_id,
                    'file_path': task.file_path,
                    'success': False,
                    'error': str(e),
                    'issues_count': 0
                }

                results.append(error_result)
                self.logger.error(f"Task {task_id} failed: {e}")

        return results

    def _aggregate_results(self, review_id: str, file_results: List[Dict],
                          start_time: float) -> OrchestrationResult:
        """
        聚合分析结果

        Args:
            review_id: 审查ID
            file_results: 文件分析结果
            start_time: 开始时间

        Returns:
            OrchestrationResult: 聚合后的结果
        """
        successful_results = [r for r in file_results if r.get('success')]
        failed_results = [r for r in file_results if not r.get('success')]

        # 统计信息
        total_issues = sum(r.get('issues_count', 0) for r in successful_results)
        execution_time = time.time() - start_time

        # 分析摘要
        analysis_summary = {
            'total_files': len(file_results),
            'successful_analyses': len(successful_results),
            'failed_analyses': len(failed_results),
            'total_issues_found': total_issues,
            'average_confidence': self._calculate_average_confidence(successful_results),
            'analysis_depth_distribution': self._calculate_depth_distribution(successful_results),
            'execution_time_seconds': execution_time
        }

        # 性能指标
        performance_metrics = {
            'resource_utilization': self.resource_manager.get_metrics(),
            'average_task_time': execution_time / max(len(file_results), 1),
            'throughput': len(file_results) / max(execution_time / 60, 1),  # 文件/分钟
            'success_rate': len(successful_results) / max(len(file_results), 1)
        }

        return OrchestrationResult(
            review_id=review_id,
            total_files_analyzed=len(successful_results),
            total_issues_found=total_issues,
            analysis_summary=analysis_summary,
            file_results=file_results,
            execution_time=execution_time,
            performance_metrics=performance_metrics
        )

    def _calculate_average_confidence(self, results: List[Dict]) -> float:
        """计算平均置信度"""
        if not results:
            return 0.0

        confidences = [r.get('confidence_score', 0) for r in results]
        return sum(confidences) / len(confidences)

    def _calculate_depth_distribution(self, results: List[Dict]) -> Dict:
        """计算分析深度分布"""
        distribution = {'shallow': 0, 'medium': 0, 'deep': 0}

        for result in results:
            depth = result.get('analysis_depth', 'shallow')
            if depth in distribution:
                distribution[depth] += 1

        return distribution

    def _detect_language(self, file_path: str) -> str:
        """检测文件语言"""
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust'
        }

        for ext, lang in extension_map.items():
            if file_path.lower().endswith(ext):
                return lang

        return 'text'

    def _extract_changed_lines(self, diff_content: str) -> List[int]:
        """提取变更行号"""
        import re

        changed_lines = []
        current_line = 0

        for line in diff_content.split('\n'):
            if line.startswith('@@'):
                # 解析行号信息
                match = re.search(r'\+(\d+)', line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith('+') and not line.startswith('+++'):
                changed_lines.append(current_line)
                current_line += 1
            elif not line.startswith('-'):
                current_line += 1

        return changed_lines

    def _notify_progress(self, review_id: str, progress: OrchestrationProgress):
        """通知进度更新"""
        if review_id in self.progress_callbacks:
            try:
                self.progress_callbacks[review_id](progress)
            except Exception as e:
                self.logger.error(f"Progress callback failed for {review_id}: {e}")

    def _on_orchestration_completed(self, review_id: str, future: Future):
        """编排完成回调"""
        # 清理进度跟踪
        if review_id in self.current_orchestrations:
            del self.current_orchestrations[review_id]

        if review_id in self.progress_callbacks:
            del self.progress_callbacks[review_id]

        self.logger.info(f"Orchestration completed for review {review_id}")

    def get_orchestration_status(self, review_id: str) -> Optional[OrchestrationProgress]:
        """
        获取编排状态

        Args:
            review_id: 审查ID

        Returns:
            Optional[OrchestrationProgress]: 编排进度信息
        """
        return self.current_orchestrations.get(review_id)

    def cancel_orchestration(self, review_id: str) -> bool:
        """
        取消编排

        Args:
            review_id: 审查ID

        Returns:
            bool: 是否成功取消
        """
        if review_id in self.current_orchestrations:
            progress = self.current_orchestrations[review_id]
            progress.state = OrchestrationState.CANCELLED
            self._notify_progress(review_id, progress)
            return True

        return False

    def get_system_statistics(self) -> Dict:
        """
        获取系统统计信息

        Returns:
            Dict: 系统统计信息
        """
        resource_metrics = self.resource_manager.get_metrics()

        return {
            'orchestration_stats': {
                'total_orchestrations': self.total_orchestrations,
                'successful_orchestrations': self.successful_orchestrations,
                'failed_orchestrations': self.failed_orchestrations,
                'success_rate': self.successful_orchestrations / max(self.total_orchestrations, 1),
                'active_orchestrations': len(self.current_orchestrations)
            },
            'resource_stats': {
                'total_agents': resource_metrics.total_agents,
                'active_agents': resource_metrics.active_agents,
                'system_load': resource_metrics.system_load,
                'tasks_in_queue': resource_metrics.total_tasks_in_queue
            }
        }

    def _setup_performance_alerts(self):
        """设置性能监控告警规则"""
        from ..monitoring.performance_monitor import AlertRule, AlertLevel, MetricType

        # CPU使用率告警
        self.performance_monitor.add_alert_rule(AlertRule(
            name="high_cpu_usage",
            metric_name="system.cpu_percent",
            condition="> 80",
            level=AlertLevel.WARNING
        ))

        # 内存使用率告警
        self.performance_monitor.add_alert_rule(AlertRule(
            name="high_memory_usage",
            metric_name="system.memory_percent",
            condition="> 85",
            level=AlertLevel.WARNING
        ))

        # Agent操作失败率告警
        self.performance_monitor.add_alert_rule(AlertRule(
            name="high_error_rate",
            metric_name="agent.analyze.error",
            condition="> 10",
            level=AlertLevel.ERROR
        ))

        # 告警回调
        def on_alert(alert):
            self.logger.warning(f"Performance alert: {alert.message}")

        self.performance_monitor.add_alert_callback(on_alert)

    def get_health_status(self) -> Dict:
        """
        获取编排器健康状态

        Returns:
            Dict: 健康状态信息
        """
        return {
            'orchestrator': {
                'status': 'healthy',
                'active_orchestrations': len(self.current_orchestrations),
                'total_orchestrations': self.total_orchestrations
            },
            'performance': self.performance_monitor.get_system_performance_summary(),
            'errors': self.error_handler.get_error_statistics(),
            'sessions': self.session_manager.get_session_statistics(),
            'resources': {
                'agent_pool_size': len(self.resource_manager.agent_pool),
                'active_agents': len([a for a in self.resource_manager.agent_pool.values() if a.status != 'idle'])
            }
        }

    def shutdown(self):
        """关闭编排器"""
        self.logger.info("Shutting down orchestrator...")
        self.resource_manager.shutdown()
        self.current_orchestrations.clear()
        self.progress_callbacks.clear()
        self.logger.info("Orchestrator shutdown complete")