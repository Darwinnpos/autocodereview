# -*- coding: utf-8 -*-
"""
任务调度器 - 智能任务分解和分配

高内聚设计：专注于任务管理的所有方面
- 任务分解策略
- 优先级计算
- 依赖关系分析
- 负载均衡
"""

import hashlib
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ..core.data_models import AgentContext


class TaskPriority(Enum):
    """任务优先级枚举"""
    CRITICAL = 1    # 关键文件（如核心业务逻辑）
    HIGH = 2        # 高优先级文件（如安全相关）
    MEDIUM = 3      # 中等优先级文件
    LOW = 4         # 低优先级文件（如配置文件）


class TaskComplexity(Enum):
    """任务复杂度枚举"""
    SIMPLE = 1      # 简单文件（小变更、简单逻辑）
    MODERATE = 2    # 中等复杂度
    COMPLEX = 3     # 复杂文件（大变更、复杂逻辑）


@dataclass
class AnalysisTask:
    """分析任务数据结构"""
    task_id: str
    file_path: str
    context: AgentContext
    priority: TaskPriority
    complexity: TaskComplexity
    estimated_time: int  # 预估分析时间（秒）
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他任务ID
    agent_requirements: Dict = field(default_factory=dict)  # Agent要求
    created_at: float = field(default_factory=lambda: __import__('time').time())


@dataclass
class TaskBatch:
    """任务批次 - 可并行执行的任务组"""
    batch_id: str
    tasks: List[AnalysisTask]
    estimated_total_time: int
    max_parallel_agents: int


class TaskScheduler:
    """
    任务调度器 - 智能分解MR为可执行的分析任务

    核心职责：
    1. 分析文件复杂度和优先级
    2. 识别文件间依赖关系
    3. 生成最优的执行计划
    4. 支持并行和串行混合调度
    """

    def __init__(self, config: Dict):
        """
        初始化任务调度器

        Args:
            config: 调度配置
        """
        self.config = config
        self.max_parallel_tasks = config.get('max_parallel_tasks', 4)
        self.max_analysis_time_per_file = config.get('max_analysis_time_per_file', 600)
        self.logger = logging.getLogger(__name__)

        # 文件优先级规则
        self.priority_rules = {
            # 关键文件模式
            'critical_patterns': [
                r'.*/(main|index|app)\.(py|js|ts|java|go)$',
                r'.*/models?/.*\.(py|js|ts|java|go)$',
                r'.*/services?/.*\.(py|js|ts|java|go)$',
                r'.*/controllers?/.*\.(py|js|ts|java|go)$',
            ],
            # 高优先级文件模式
            'high_patterns': [
                r'.*/auth.*\.(py|js|ts|java|go)$',
                r'.*/security.*\.(py|js|ts|java|go)$',
                r'.*/(api|endpoints?)/.*\.(py|js|ts|java|go)$',
                r'.*/database.*\.(py|js|ts|java|go)$',
            ],
            # 低优先级文件模式
            'low_patterns': [
                r'.*\.(md|txt|yml|yaml|json)$',
                r'.*/tests?/.*$',
                r'.*/docs?/.*$',
                r'.*/(config|settings?).*$',
            ]
        }

    def create_execution_plan(self, mr_changes: List[Dict], mr_info: Dict) -> List[TaskBatch]:
        """
        创建执行计划 - 将MR变更转换为优化的任务批次

        Args:
            mr_changes: GitLab MR变更列表
            mr_info: MR基本信息

        Returns:
            List[TaskBatch]: 优化后的任务批次列表
        """
        # 1. 创建分析任务
        tasks = self._create_analysis_tasks(mr_changes, mr_info)

        # 2. 分析任务依赖关系
        self._analyze_task_dependencies(tasks)

        # 3. 计算任务复杂度和时间估算
        self._calculate_task_metrics(tasks)

        # 4. 按优先级和依赖关系排序
        sorted_tasks = self._sort_tasks_by_priority_and_dependencies(tasks)

        # 5. 分组为可并行执行的批次
        task_batches = self._group_tasks_into_batches(sorted_tasks)

        self.logger.info(f"Created execution plan: {len(task_batches)} batches, "
                        f"{len(tasks)} total tasks")

        return task_batches

    def _create_analysis_tasks(self, mr_changes: List[Dict], mr_info: Dict) -> List[AnalysisTask]:
        """
        从MR变更创建分析任务

        Args:
            mr_changes: MR变更列表
            mr_info: MR信息

        Returns:
            List[AnalysisTask]: 分析任务列表
        """
        tasks = []

        for i, change in enumerate(mr_changes):
            if change.get('deleted_file', False):
                continue  # 跳过已删除的文件

            file_path = change.get('new_path') or change.get('old_path')
            if not file_path:
                continue

            # 生成任务ID
            task_id = self._generate_task_id(file_path, mr_info.get('iid', 0))

            # 创建基础AgentContext（稍后由编排器填充完整信息）
            context = AgentContext(
                file_path=file_path,
                file_content="",  # 将由编排器填充
                changed_lines=[],  # 将由编排器填充
                diff_content=change.get('diff', ''),
                language="",  # 将由编排器推断
                mr_title=mr_info.get('title', ''),
                mr_description=mr_info.get('description', '')
            )

            # 确定任务优先级
            priority = self._determine_task_priority(file_path)

            # 创建任务
            task = AnalysisTask(
                task_id=task_id,
                file_path=file_path,
                context=context,
                priority=priority,
                complexity=TaskComplexity.MODERATE,  # 初始值，稍后计算
                estimated_time=300  # 初始估算5分钟
            )

            tasks.append(task)

        return tasks

    def _analyze_task_dependencies(self, tasks: List[AnalysisTask]) -> None:
        """
        分析任务间的依赖关系

        Args:
            tasks: 任务列表，就地修改添加依赖信息
        """
        import re

        # 构建文件路径到任务ID的映射
        path_to_task = {task.file_path: task.task_id for task in tasks}

        for task in tasks:
            dependencies = []

            # 分析import/include依赖
            diff_content = task.context.diff_content
            if diff_content:
                # 提取import语句（Python、JavaScript、TypeScript等）
                import_patterns = [
                    r'from\s+([^\s]+)\s+import',  # Python: from module import
                    r'import\s+([^\s;]+)',        # Python/JS: import module
                    r'#include\s*[<"]([^>"]+)[>"]',  # C/C++: #include
                    r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',  # Node.js: require
                ]

                for pattern in import_patterns:
                    matches = re.findall(pattern, diff_content, re.MULTILINE)
                    for match in matches:
                        # 尝试匹配到任务列表中的文件
                        for other_task in tasks:
                            if match in other_task.file_path and other_task.task_id != task.task_id:
                                if other_task.task_id not in dependencies:
                                    dependencies.append(other_task.task_id)

            task.dependencies = dependencies

        self.logger.info(f"Analyzed dependencies for {len(tasks)} tasks")

    def _calculate_task_metrics(self, tasks: List[AnalysisTask]) -> None:
        """
        计算任务复杂度和时间估算

        Args:
            tasks: 任务列表，就地修改添加度量信息
        """
        for task in tasks:
            # 计算复杂度
            task.complexity = self._calculate_file_complexity(task)

            # 估算分析时间
            task.estimated_time = self._estimate_analysis_time(task)

    def _calculate_file_complexity(self, task: AnalysisTask) -> TaskComplexity:
        """
        计算文件复杂度

        Args:
            task: 分析任务

        Returns:
            TaskComplexity: 文件复杂度
        """
        diff_content = task.context.diff_content
        diff_size = len(diff_content)

        # 计算变更行数（粗略估算）
        added_lines = diff_content.count('\n+')
        removed_lines = diff_content.count('\n-')
        total_changes = added_lines + removed_lines

        # 复杂度评分
        complexity_score = 0

        # 基于变更规模
        if total_changes > 100:
            complexity_score += 3
        elif total_changes > 50:
            complexity_score += 2
        elif total_changes > 10:
            complexity_score += 1

        # 基于diff大小
        if diff_size > 10000:  # 10KB
            complexity_score += 2
        elif diff_size > 5000:  # 5KB
            complexity_score += 1

        # 基于文件类型
        if task.file_path.endswith(('.py', '.js', '.ts', '.java', '.cpp', '.go')):
            complexity_score += 1  # 代码文件更复杂

        # 基于关键词（复杂逻辑指标）
        complex_keywords = ['if', 'for', 'while', 'try', 'catch', 'class', 'function', 'async']
        for keyword in complex_keywords:
            if keyword in diff_content.lower():
                complexity_score += 0.5

        # 映射到枚举
        if complexity_score >= 5:
            return TaskComplexity.COMPLEX
        elif complexity_score >= 2:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.SIMPLE

    def _estimate_analysis_time(self, task: AnalysisTask) -> int:
        """
        估算分析时间

        Args:
            task: 分析任务

        Returns:
            int: 估算时间（秒）
        """
        base_time = {
            TaskComplexity.SIMPLE: 120,    # 2分钟
            TaskComplexity.MODERATE: 300,  # 5分钟
            TaskComplexity.COMPLEX: 600    # 10分钟
        }

        estimated = base_time[task.complexity]

        # 根据优先级调整（高优先级分配更多时间进行深度分析）
        if task.priority == TaskPriority.CRITICAL:
            estimated = int(estimated * 1.5)
        elif task.priority == TaskPriority.HIGH:
            estimated = int(estimated * 1.2)

        return min(estimated, self.max_analysis_time_per_file)

    def _determine_task_priority(self, file_path: str) -> TaskPriority:
        """
        确定任务优先级

        Args:
            file_path: 文件路径

        Returns:
            TaskPriority: 任务优先级
        """
        import re

        # 检查关键文件模式
        for pattern in self.priority_rules['critical_patterns']:
            if re.match(pattern, file_path, re.IGNORECASE):
                return TaskPriority.CRITICAL

        # 检查高优先级模式
        for pattern in self.priority_rules['high_patterns']:
            if re.match(pattern, file_path, re.IGNORECASE):
                return TaskPriority.HIGH

        # 检查低优先级模式
        for pattern in self.priority_rules['low_patterns']:
            if re.match(pattern, file_path, re.IGNORECASE):
                return TaskPriority.LOW

        # 默认中等优先级
        return TaskPriority.MEDIUM

    def _sort_tasks_by_priority_and_dependencies(self, tasks: List[AnalysisTask]) -> List[AnalysisTask]:
        """
        按优先级和依赖关系排序任务

        Args:
            tasks: 原始任务列表

        Returns:
            List[AnalysisTask]: 排序后的任务列表
        """
        # 拓扑排序处理依赖关系，同时考虑优先级
        sorted_tasks = []
        remaining_tasks = tasks.copy()
        task_map = {task.task_id: task for task in tasks}

        while remaining_tasks:
            # 找到没有未完成依赖的任务
            ready_tasks = []
            for task in remaining_tasks:
                dependencies_satisfied = all(
                    dep_id not in [t.task_id for t in remaining_tasks]
                    for dep_id in task.dependencies
                )
                if dependencies_satisfied:
                    ready_tasks.append(task)

            if not ready_tasks:
                # 如果有循环依赖，选择优先级最高的任务
                ready_tasks = [min(remaining_tasks, key=lambda t: t.priority.value)]
                self.logger.warning("Possible circular dependency detected, forcing task selection")

            # 在准备好的任务中按优先级排序
            ready_tasks.sort(key=lambda t: (t.priority.value, t.complexity.value))

            # 添加到结果列表
            for task in ready_tasks:
                sorted_tasks.append(task)
                remaining_tasks.remove(task)

        return sorted_tasks

    def _group_tasks_into_batches(self, sorted_tasks: List[AnalysisTask]) -> List[TaskBatch]:
        """
        将排序后的任务分组为可并行执行的批次

        Args:
            sorted_tasks: 排序后的任务列表

        Returns:
            List[TaskBatch]: 任务批次列表
        """
        batches = []
        current_batch_tasks = []
        current_batch_time = 0
        batch_counter = 0

        for task in sorted_tasks:
            # 检查是否可以添加到当前批次
            can_add_to_current = (
                len(current_batch_tasks) < self.max_parallel_tasks and
                current_batch_time + task.estimated_time <= self.max_analysis_time_per_file * 2 and
                self._can_run_in_parallel(task, current_batch_tasks)
            )

            if can_add_to_current and current_batch_tasks:
                # 添加到当前批次
                current_batch_tasks.append(task)
                current_batch_time = max(current_batch_time, task.estimated_time)
            else:
                # 创建新批次
                if current_batch_tasks:
                    batch = TaskBatch(
                        batch_id=f"batch_{batch_counter}",
                        tasks=current_batch_tasks,
                        estimated_total_time=current_batch_time,
                        max_parallel_agents=len(current_batch_tasks)
                    )
                    batches.append(batch)
                    batch_counter += 1

                # 开始新批次
                current_batch_tasks = [task]
                current_batch_time = task.estimated_time

        # 添加最后一个批次
        if current_batch_tasks:
            batch = TaskBatch(
                batch_id=f"batch_{batch_counter}",
                tasks=current_batch_tasks,
                estimated_total_time=current_batch_time,
                max_parallel_agents=len(current_batch_tasks)
            )
            batches.append(batch)

        return batches

    def _can_run_in_parallel(self, task: AnalysisTask, current_batch: List[AnalysisTask]) -> bool:
        """
        检查任务是否可以与当前批次中的任务并行运行

        Args:
            task: 要检查的任务
            current_batch: 当前批次中的任务

        Returns:
            bool: 是否可以并行运行
        """
        # 检查依赖关系
        current_batch_ids = [t.task_id for t in current_batch]
        if any(dep_id in current_batch_ids for dep_id in task.dependencies):
            return False

        # 检查是否有任务依赖当前任务
        for batch_task in current_batch:
            if task.task_id in batch_task.dependencies:
                return False

        # 可以并行运行
        return True

    def _generate_task_id(self, file_path: str, mr_iid: int) -> str:
        """
        生成任务ID

        Args:
            file_path: 文件路径
            mr_iid: MR ID

        Returns:
            str: 任务ID
        """
        content = f"{mr_iid}_{file_path}"
        return f"task_{hashlib.md5(content.encode()).hexdigest()[:8]}"