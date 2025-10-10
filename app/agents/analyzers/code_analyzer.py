# -*- coding: utf-8 -*-
"""
代码分析Agent - 重构后的高内聚低耦合版本

将原来的ai_agent.py重构为专门化的代码分析器，
继承BaseAgent并使用ConversationManager，实现职责分离。
"""

from typing import Dict

from ..core.base_agent import BaseAgent
from ..core.conversation import ConversationManager
from ..core.data_models import AgentContext, AgentAnalysisResult, AgentState


class CodeAnalyzer(BaseAgent):
    """
    代码分析Agent - 专注于代码质量、逻辑、性能等方面的分析

    高内聚：所有代码分析相关的逻辑都在这个类中
    低耦合：依赖抽象接口，不直接依赖具体的AI API或其他模块
    """

    def __init__(self, config: Dict):
        """
        初始化代码分析器

        Args:
            config: 包含AI配置和分析参数的字典
        """
        super().__init__(config)

        # 创建对话管理器 - 委托模式，职责分离
        self.conversation_manager = ConversationManager(config)

        # 代码分析特有的配置
        self.severity_level = config.get('review_severity_level', 'standard')

    def _execute_analysis(self, context: AgentContext) -> AgentAnalysisResult:
        """
        执行代码分析的核心逻辑

        采用多阶段分析策略：
        1. 初始分析
        2. 深度质疑（如果需要）
        3. 综合评估

        Args:
            context: 分析上下文

        Returns:
            AgentAnalysisResult: 分析结果
        """
        result = AgentAnalysisResult()

        try:
            # 第一阶段：初始化对话
            self.logger.info(f"[Phase 1/4] Initializing conversation for {context.file_path}")
            self._setup_conversation(context)

            # 第二阶段：执行初始分析
            self.logger.info(f"[Phase 2/4] Performing initial analysis for {context.file_path}")
            initial_analysis = self._perform_initial_analysis(context)
            result.issues.extend(initial_analysis.get('issues', []))
            self.logger.info(f"Initial analysis found {len(result.issues)} issues (turn 1)")

            # 第三阶段：深度询问（如果需要）
            if self._should_ask_questions(initial_analysis, context):
                self.state = AgentState.QUESTIONING
                self.logger.info(f"[Phase 3/4] Entering questioning phase - complexity indicators triggered")
                questions = self.conversation_manager.generate_questions(context, initial_analysis)
                self.logger.info(f"Generated {len(questions)} questions for deeper analysis")

                for idx, question in enumerate(questions[:self.max_questions_per_file], 1):
                    self.logger.info(f"Turn {1 + idx}: Asking question - {question.question_text[:80]}...")
                    answer = self.conversation_manager.ask_question(context, question)
                    if answer:
                        context.gathered_information[question.question_id] = answer
                        result.questions_asked += 1
                        self.logger.info(f"Turn {1 + idx}: Received answer ({len(answer)} chars)")
            else:
                self.logger.info(f"[Phase 3/4] Skipping questioning phase - file is straightforward")

            # 第四阶段：综合分析
            final_turn = 2 + result.questions_asked
            self.logger.info(f"[Phase 4/4] Performing comprehensive analysis (turn {final_turn})")
            final_analysis = self._perform_comprehensive_analysis(context, result)
            result.issues = final_analysis.get('issues', [])
            result.recommendations = final_analysis.get('recommendations', [])
            result.confidence_score = final_analysis.get('confidence', 0.8)

            total_turns = len(context.conversation_history) // 2  # 每轮包含user+assistant两条消息
            self.logger.info(f"Analysis complete: {len(result.issues)} issues found in {total_turns} turns, confidence: {result.confidence_score:.2f}")

            return result

        except Exception as e:
            self.logger.error(f"Code analysis failed: {e}")
            raise

    def _setup_conversation(self, context: AgentContext) -> None:
        """
        设置分析对话的系统提示

        Args:
            context: 分析上下文
        """
        system_prompt = self._build_system_prompt(context)
        self.conversation_manager.initialize_conversation(context, system_prompt)

    def _perform_initial_analysis(self, context: AgentContext) -> Dict:
        """
        执行初始代码分析

        Args:
            context: 分析上下文

        Returns:
            Dict: 初始分析结果
        """
        analysis_prompt = self._build_initial_analysis_prompt(context)
        response = self.conversation_manager.send_message_and_get_response(
            context, analysis_prompt, "initial_analysis"
        )
        return self.conversation_manager.parse_json_response(response)

    def _should_ask_questions(self, initial_analysis: Dict, context: AgentContext) -> bool:
        """
        判断是否需要进一步提问

        Args:
            initial_analysis: 初始分析结果
            context: 分析上下文

        Returns:
            bool: 是否需要提问
        """
        # 复杂度指标
        complexity_indicators = [
            len(initial_analysis.get('issues', [])) > 5,  # 问题较多
            any(issue.get('severity') == 'error' for issue in initial_analysis.get('issues', [])),  # 有严重错误
            len(context.changed_lines) > 100,  # 变更行数较多
            'unclear' in initial_analysis.get('notes', '').lower(),  # AI标记不清楚
            'need more context' in initial_analysis.get('notes', '').lower()  # 需要更多上下文
        ]

        return (any(complexity_indicators) and
                len(context.conversation_history) < self.max_conversation_turns)

    def _perform_comprehensive_analysis(self, context: AgentContext, partial_result: AgentAnalysisResult) -> Dict:
        """
        执行综合分析

        Args:
            context: 分析上下文
            partial_result: 部分分析结果

        Returns:
            Dict: 综合分析结果
        """
        comprehensive_prompt = f"""
基于完整的对话历史和收集的信息，对代码进行最终综合分析。

已收集的信息：
{context.gathered_information}

初步发现的问题数量：{len(partial_result.issues)}

**重要提醒**：
- ✅ 只报告确认的代码问题和需要改进的地方
- ❌ 不要报告好的实践或正面观察
- ❌ 不要报告"代码规范良好"、"命名合理"这类表扬性内容
- 如果经过深入分析后确认代码质量良好，返回空的issues数组

请提供最终的代码审查结果，包括：
1. 确认的代码问题列表（只包含需要改进的地方，JSON格式）
2. 具体的改进建议（针对问题的修复方案）

返回JSON格式：
{{
    "issues": [
        {{
            "line_number": 行号,
            "severity": "error|warning|info",
            "category": "logic|performance|security|style|best_practices",
            "message": "问题描述",
            "suggestion": "修复建议",
            "confidence": 0.8
        }}
    ],
    "recommendations": [/* 改进建议 */]
}}

**在提交每个问题前，请进行自我检查**：
1. ✓ 回到完整文件内容，确认该行号标记了 ">>>"
2. ✓ 如果附近有多个 ">>>" 行，确认选择的是"原因"行而非"结果"行
3. ✓ 确认问题描述准确且针对变更后的代码

**重要**：每个 issue 必须包含 confidence 字段，根据你对该问题的确信程度设置：
- 0.9-1.0: 非常确定（明显bug、安全问题）
- 0.7-0.9: 很确定（违反最佳实践）
- 0.5-0.7: 较确定（可能的问题）
- 0.0-0.5: 不太确定（建议）

**行号选择规则**：
- line_number 必须是代码中标记 ">>>" 的变更行号
- 回顾完整文件内容，只选择带 ">>>" 标记的行
- 当多行都是变更行时，遵循"原因"优先于"结果"原则：
  - 控制语句（if/while/for）> 语句块内容
  - 函数/类声明 > 函数/类内部
  - 变量定义 > 变量使用
"""

        response = self.conversation_manager.send_message_and_get_response(
            context, comprehensive_prompt, "comprehensive_analysis"
        )
        return self.conversation_manager.parse_json_response(response)

    def _build_system_prompt(self, context: AgentContext) -> str:
        """
        构建系统提示词

        Args:
            context: 分析上下文

        Returns:
            str: 系统提示词
        """
        return f"""你是一个专业的代码审查AI Agent，具备多轮对话能力。

你的任务是对{context.language}代码进行深度分析。你可以：
1. 进行初始分析并识别潜在问题
2. 提出澄清问题来获取更多上下文
3. 基于收集的信息提供综合评估

审查严格程度：{self.severity_level}
文件路径：{context.file_path}
MR标题：{context.mr_title}

请始终以专业、建设性的方式提供反馈。
"""

    def _build_initial_analysis_prompt(self, context: AgentContext) -> str:
        """
        构建初始分析提示词

        Args:
            context: 分析上下文

        Returns:
            str: 初始分析提示词
        """
        return f"""
请对上述代码变更进行初始分析，**只报告需要改进的地方**，重点关注：

1. 代码质量问题（bug、逻辑错误）
2. 潜在的安全风险
3. 性能问题和资源泄漏
4. 违反最佳实践的地方
5. 代码规范和风格问题

**重要说明**：
- ✅ 只报告存在问题、需要改进的代码
- ❌ 不要报告已经符合规范的好的实践
- ❌ 不要报告正面的观察或表扬性质的内容
- 如果代码质量良好、没有发现问题，返回空的issues数组

**错误示例**（不要这样做）：
❌ "问题：头文件保护宏命名规范良好" - 这是好的实践，不是问题
❌ "问题：代码格式规范" - 这是正面评价，不是问题

**正确示例**：
✅ "问题：缺少空指针检查，可能导致段错误"
✅ "问题：未释放动态分配的内存，存在内存泄漏风险"

如果你发现需要更多信息才能准确判断的地方，请在notes字段中说明。

返回JSON格式：
{{
    "issues": [
        {{
            "line_number": 行号,
            "severity": "error|warning|info",
            "category": "logic|performance|security|style|best_practices",
            "message": "问题描述（只描述需要改进的地方）",
            "suggestion": "具体的修复建议",
            "confidence": 0.8
        }}
    ],
    "notes": "需要进一步了解的信息"
}}

**在提交每个问题前，请进行自我检查**：
1. ✓ 回到完整文件内容，确认该行号标记了 ">>>"
2. ✓ 如果附近有多个 ">>>" 行，确认选择的是"原因"行而非"结果"行
3. ✓ 确认问题描述针对的是变更后的新代码，而非旧代码

**confidence 说明**：
- 每个问题都应该包含 confidence 字段 (0.0-1.0)
- 0.9-1.0: 非常确定的问题（如明显的bug、安全漏洞）
- 0.7-0.9: 很可能是问题（如违反最佳实践）
- 0.5-0.7: 可能是问题（需要人工确认）
- 0.0-0.5: 不太确定（建议性质的改进）

**重要：行号选择规则（必须严格遵守）**

1. **只能选择变更行**：
   - 完整文件中标记了 ">>>" 的行才是变更行
   - line_number 必须是带 ">>>" 标记的行号
   - 报告问题前，请确认该行号在代码中标记了 ">>>"

2. **"原因"优先于"结果"原则**：
   - 选择引入问题的代码行，而不是受问题影响的代码行
   - 选择控制流的起点，而不是控制流的内部
   - 选择定义/声明，而不是使用/调用（当定义本身有问题时）

3. **具体行的选择顺序**（当多行都是变更行时）：
   - 控制语句（if/while/for/switch）> 语句块内容
   - 函数/类声明 > 函数/类内部实现
   - 变量定义 > 变量使用
   - 资源分配 > 资源释放
   - 前置条件 > 主体逻辑

**示例1：控制语句 vs 语句块内容**
```
  17 >>>     if (condition) {{           // 控制语句（原因）
  18 >>>         statement;              // 语句块内容（结果）
  19 >>>     }}
```
如果问题是条件判断有误，选择第17行（控制语句）

**示例2：未变更的原因，变更的结果**
```
  17          if (b == 0) {{              // 旧代码，问题的原因但未变更
  18              throw exception;        // 旧代码
  19 >>>      }}
  20 >>>      return a / b;               // 新增的行
```
虽然问题根源在第17行，但因为它不是变更行，选择第20行（最相关的变更行）

**示例3：都是变更行时的选择**
```
  15 >>>     if (condition) {{           // 控制语句（原因）
  16 >>>         action1();              // 受控制的语句（结果）
  17 >>>         action2();              // 受控制的语句（结果）
  18 >>>     }}
```
如果问题是条件判断逻辑，选择第15行（控制流起点）而非第16/17行
"""