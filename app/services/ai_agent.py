# -*- coding: utf-8 -*-
import json
import requests
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import time

class AgentState(Enum):
    """Agent状态枚举"""
    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    QUESTIONING = "questioning"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    ERROR = "error"

@dataclass
class AgentMessage:
    """Agent消息结构"""
    role: str  # 'system', 'user', 'assistant'
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

@dataclass
class AgentContext:
    """Agent上下文信息"""
    file_path: str
    file_content: str
    changed_lines: List[int]
    diff_content: str
    language: str
    mr_title: str = ""
    mr_description: str = ""
    review_config: Dict = field(default_factory=dict)
    conversation_history: List[AgentMessage] = field(default_factory=list)
    current_analysis_focus: str = ""
    gathered_information: Dict = field(default_factory=dict)

@dataclass
class AgentQuestion:
    """Agent问题结构"""
    question_id: str
    question_text: str
    question_type: str  # 'clarification', 'detail_request', 'confirmation'
    context_needed: Dict = field(default_factory=dict)
    priority: int = 1  # 1-5, 1最高

@dataclass
class AgentAnalysisResult:
    """Agent分析结果"""
    issues: List = field(default_factory=list)
    confidence_score: float = 0.0
    analysis_depth: str = "shallow"  # shallow, medium, deep
    recommendations: List[str] = field(default_factory=list)
    questions_asked: int = 0
    conversation_turns: int = 0

class AICodeReviewAgent:
    """AI代码审查Agent - 支持多轮对话的智能分析"""

    def __init__(self, ai_config: Dict):
        self.ai_api_url = ai_config.get('ai_api_url', 'https://api.openai.com/v1')
        self.ai_api_key = ai_config.get('ai_api_key', '')
        self.ai_model = ai_config.get('ai_model', 'gpt-3.5-turbo')
        self.severity_level = ai_config.get('review_severity_level', 'standard')
        self.max_conversation_turns = ai_config.get('max_conversation_turns', 5)
        self.max_questions_per_file = ai_config.get('max_questions_per_file', 3)

        self.logger = logging.getLogger(__name__)
        self.state = AgentState.INITIALIZING

    def analyze_code_with_agent(self, context: AgentContext) -> AgentAnalysisResult:
        """使用Agent模式进行代码分析"""
        self.state = AgentState.INITIALIZING
        result = AgentAnalysisResult()

        try:
            # 第一阶段：初始分析
            self._initialize_conversation(context)
            initial_analysis = self._perform_initial_analysis(context)
            result.issues.extend(initial_analysis.get('issues', []))

            # 第二阶段：深度询问（如果需要）
            if self._should_ask_questions(initial_analysis, context):
                self.state = AgentState.QUESTIONING
                questions = self._generate_clarification_questions(context, initial_analysis)

                for question in questions[:self.max_questions_per_file]:
                    answer = self._ask_question_and_get_response(question, context)
                    if answer:
                        context.gathered_information[question.question_id] = answer
                        result.questions_asked += 1

            # 第三阶段：综合分析
            self.state = AgentState.REVIEWING
            final_analysis = self._perform_comprehensive_analysis(context, result)
            result.issues = final_analysis.get('issues', [])
            result.recommendations = final_analysis.get('recommendations', [])
            result.confidence_score = final_analysis.get('confidence', 0.8)

            self.state = AgentState.COMPLETED
            result.conversation_turns = len(context.conversation_history)
            result.analysis_depth = self._determine_analysis_depth(result)

            return result

        except Exception as e:
            self.state = AgentState.ERROR
            self.logger.error(f"Agent analysis failed: {e}")
            raise Exception(f"Agent代码分析失败：{str(e)}")

    def _initialize_conversation(self, context: AgentContext):
        """初始化对话"""
        system_message = AgentMessage(
            role="system",
            content=self._build_system_prompt(context),
            metadata={"phase": "initialization"}
        )
        context.conversation_history.append(system_message)

        # 添加代码上下文
        code_message = AgentMessage(
            role="user",
            content=self._build_code_context(context),
            metadata={"phase": "code_submission", "file_path": context.file_path}
        )
        context.conversation_history.append(code_message)

    def _perform_initial_analysis(self, context: AgentContext) -> Dict:
        """执行初始分析"""
        self.state = AgentState.ANALYZING

        prompt = self._build_initial_analysis_prompt(context)
        response = self._call_ai_api_with_history(context.conversation_history + [
            AgentMessage(role="user", content=prompt)
        ])

        # 解析初始分析结果
        analysis_result = self._parse_analysis_response(response)

        # 记录AI响应
        ai_message = AgentMessage(
            role="assistant",
            content=response,
            metadata={"phase": "initial_analysis", "parsed_result": analysis_result}
        )
        context.conversation_history.append(ai_message)

        return analysis_result

    def _should_ask_questions(self, initial_analysis: Dict, context: AgentContext) -> bool:
        """判断是否需要进一步提问"""
        # 如果发现复杂问题或不确定的地方，需要进一步询问
        complexity_indicators = [
            len(initial_analysis.get('issues', [])) > 5,  # 问题较多
            any(issue.get('severity') == 'error' for issue in initial_analysis.get('issues', [])),  # 有严重错误
            len(context.changed_lines) > 100,  # 变更行数较多
            'unclear' in initial_analysis.get('notes', '').lower(),  # AI标记不清楚
            'need more context' in initial_analysis.get('notes', '').lower()  # 需要更多上下文
        ]

        return any(complexity_indicators) and len(context.conversation_history) < self.max_conversation_turns

    def _generate_clarification_questions(self, context: AgentContext, initial_analysis: Dict) -> List[AgentQuestion]:
        """生成澄清问题"""
        questions = []

        # 基于初始分析生成问题
        question_prompt = f"""
基于初始分析结果，生成最多3个澄清问题来获取更准确的代码审查结果。

初始分析：{json.dumps(initial_analysis, ensure_ascii=False, indent=2)}

请生成JSON格式的问题列表，每个问题包含：
- question_id: 唯一标识
- question_text: 问题内容
- question_type: 问题类型（clarification/detail_request/confirmation）
- priority: 优先级(1-5)
- context_needed: 需要的上下文信息

返回格式：
{{"questions": [...]}}
"""

        try:
            response = self._call_ai_api_with_history([
                AgentMessage(role="user", content=question_prompt)
            ])

            questions_data = json.loads(response)
            for q_data in questions_data.get('questions', [])[:3]:
                question = AgentQuestion(
                    question_id=q_data.get('question_id', f"q_{len(questions)}"),
                    question_text=q_data.get('question_text', ''),
                    question_type=q_data.get('question_type', 'clarification'),
                    context_needed=q_data.get('context_needed', {}),
                    priority=q_data.get('priority', 3)
                )
                questions.append(question)

        except Exception as e:
            self.logger.error(f"Failed to generate questions: {e}")

        return sorted(questions, key=lambda x: x.priority)

    def _ask_question_and_get_response(self, question: AgentQuestion, context: AgentContext) -> Optional[str]:
        """提问并获取响应"""
        try:
            # 构建问题提示
            question_prompt = f"""
针对正在分析的代码文件 {context.file_path}，我需要更多信息来提供准确的审查：

问题：{question.question_text}

请基于代码内容和变更上下文回答这个问题。如果信息不足以回答，请说明原因。
"""

            # 记录问题
            question_message = AgentMessage(
                role="user",
                content=question_prompt,
                metadata={"phase": "questioning", "question_id": question.question_id}
            )
            context.conversation_history.append(question_message)

            # 获取AI响应
            response = self._call_ai_api_with_history(context.conversation_history)

            # 记录响应
            answer_message = AgentMessage(
                role="assistant",
                content=response,
                metadata={"phase": "answering", "question_id": question.question_id}
            )
            context.conversation_history.append(answer_message)

            return response

        except Exception as e:
            self.logger.error(f"Failed to ask question {question.question_id}: {e}")
            return None

    def _perform_comprehensive_analysis(self, context: AgentContext, partial_result: AgentAnalysisResult) -> Dict:
        """执行综合分析"""
        # 整合所有收集的信息进行最终分析
        comprehensive_prompt = f"""
基于完整的对话历史和收集的信息，对代码进行最终综合分析。

已收集的信息：
{json.dumps(context.gathered_information, ensure_ascii=False, indent=2)}

初步发现的问题数量：{len(partial_result.issues)}

请提供最终的代码审查结果，包括：
1. 确认的代码问题列表
2. 具体的改进建议
3. 分析的置信度评分（0-1）

返回JSON格式结果。
"""

        try:
            response = self._call_ai_api_with_history(context.conversation_history + [
                AgentMessage(role="user", content=comprehensive_prompt)
            ])

            return self._parse_analysis_response(response)

        except Exception as e:
            self.logger.error(f"Comprehensive analysis failed: {e}")
            return {"issues": partial_result.issues, "recommendations": [], "confidence": 0.5}

    def _build_system_prompt(self, context: AgentContext) -> str:
        """构建系统提示"""
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

    def _build_code_context(self, context: AgentContext) -> str:
        """构建代码上下文"""
        return f"""
## 代码文件信息
文件路径：{context.file_path}
编程语言：{context.language}
变更行数：{len(context.changed_lines)}

## 变更内容
```diff
{context.diff_content}
```

## 完整文件内容
```{context.language}
{context.file_content}
```
"""

    def _build_initial_analysis_prompt(self, context: AgentContext) -> str:
        """构建初始分析提示"""
        return f"""
请对上述代码进行初始分析，重点关注：

1. 代码质量问题
2. 潜在的bug或逻辑错误
3. 性能问题
4. 安全风险
5. 最佳实践违反

如果你发现需要更多信息才能准确判断的地方，请在notes字段中说明。

返回JSON格式：
{{
    "issues": [...],
    "confidence": 0.8,
    "notes": "需要进一步了解的信息"
}}
"""

    def _call_ai_api_with_history(self, messages: List[AgentMessage]) -> str:
        """使用对话历史调用AI API"""
        # 转换为OpenAI API格式
        api_messages = []
        for msg in messages:
            api_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        headers = {
            'Authorization': f'Bearer {self.ai_api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.ai_model,
            'messages': api_messages,
            'temperature': 0.1,
            'max_tokens': 4000
        }

        try:
            response = requests.post(
                f"{self.ai_api_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=600
            )
            response.raise_for_status()

            response_data = response.json()
            return response_data['choices'][0]['message']['content']

        except requests.exceptions.RequestException as e:
            self.logger.error(f"AI API call failed: {e}")
            raise

    def _parse_analysis_response(self, response: str) -> Dict:
        """解析分析响应"""
        try:
            # 尝试解析JSON响应
            return json.loads(response)
        except json.JSONDecodeError:
            # 如果不是JSON，尝试提取结构化信息
            return {
                "issues": [],
                "confidence": 0.5,
                "notes": response[:500],  # 截取前500字符作为注释
                "recommendations": []
            }

    def _determine_analysis_depth(self, result: AgentAnalysisResult) -> str:
        """确定分析深度"""
        if result.questions_asked >= 2 and result.conversation_turns >= 4:
            return "deep"
        elif result.questions_asked >= 1 or result.conversation_turns >= 3:
            return "medium"
        else:
            return "shallow"

    def get_language_from_file_path(self, file_path: str) -> str:
        """从文件路径推断编程语言"""
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'jsx',
            '.tsx': 'tsx',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust',
            '.php': 'php',
            '.rb': 'ruby',
            '.cs': 'csharp',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.sh': 'bash',
            '.sql': 'sql',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.less': 'less',
            '.json': 'json',
            '.xml': 'xml',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.md': 'markdown'
        }

        for ext, lang in extension_map.items():
            if file_path.lower().endswith(ext):
                return lang

        return 'text'  # 默认返回text

    def convert_to_code_issues(self, agent_result: AgentAnalysisResult, file_path: str) -> List:
        """将Agent分析结果转换为CodeIssue格式，保持与现有系统兼容"""
        from .ai_analyzer import CodeIssue

        code_issues = []
        for issue_data in agent_result.issues:
            if isinstance(issue_data, dict):
                # 从Agent的issue字典创建CodeIssue
                code_issue = CodeIssue(
                    line_number=issue_data.get('line_number', 1),
                    severity=issue_data.get('severity', 'info'),
                    category=issue_data.get('category', 'general'),
                    message=issue_data.get('message', ''),
                    suggestion=issue_data.get('suggestion')
                )
                code_issues.append(code_issue)

        return code_issues