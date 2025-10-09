# -*- coding: utf-8 -*-
"""
对话管理器

高内聚设计 - 专门负责Agent的对话逻辑管理，
包括消息历史、AI API调用、响应解析等所有对话相关功能。
"""

import json
import requests
import logging
from typing import List, Dict, Optional

from .data_models import AgentMessage, AgentContext, AgentQuestion


class ConversationManager:
    """
    对话管理器 - 高内聚的对话逻辑组件

    将所有与对话相关的功能集中在一个类中：
    - 消息历史管理
    - AI API调用
    - 响应解析
    - 问题生成和处理
    """

    def __init__(self, ai_config: Dict):
        """
        初始化对话管理器

        Args:
            ai_config: AI配置，包含API地址、密钥、模型等
        """
        # 支持两种key格式：带ai_前缀和不带前缀（兼容性）
        self.ai_api_url = ai_config.get('api_url') or ai_config.get('ai_api_url', 'https://api.openai.com/v1')
        self.ai_api_key = ai_config.get('api_key') or ai_config.get('ai_api_key', '')
        self.ai_model = ai_config.get('model') or ai_config.get('ai_model', 'gpt-3.5-turbo')
        self.logger = logging.getLogger(__name__)

    def initialize_conversation(self, context: AgentContext, system_prompt: str) -> None:
        """
        初始化对话会话

        Args:
            context: Agent上下文
            system_prompt: 系统提示词
        """
        # 添加系统消息
        system_message = AgentMessage(
            role="system",
            content=system_prompt,
            metadata={"phase": "initialization"}
        )
        context.conversation_history.append(system_message)

        # 添加代码上下文消息
        code_context = self._build_code_context(context)
        code_message = AgentMessage(
            role="user",
            content=code_context,
            metadata={"phase": "code_submission", "file_path": context.file_path}
        )
        context.conversation_history.append(code_message)

    def send_message_and_get_response(self, context: AgentContext, message: str, phase: str = "analysis") -> str:
        """
        发送消息并获取AI响应

        Args:
            context: Agent上下文
            message: 要发送的消息内容
            phase: 当前阶段标识

        Returns:
            str: AI的响应内容
        """
        # 添加用户消息到历史
        user_message = AgentMessage(
            role="user",
            content=message,
            metadata={"phase": phase}
        )
        context.conversation_history.append(user_message)

        # 调用AI API
        turn_number = len(context.conversation_history) // 2 + 1
        self.logger.info(f"Sending message to AI (turn {turn_number}, phase: {phase}, message length: {len(message)} chars)")
        response = self._call_ai_api(context.conversation_history)
        self.logger.info(f"Received AI response (turn {turn_number}, response length: {len(response)} chars)")

        # 添加AI响应到历史
        ai_message = AgentMessage(
            role="assistant",
            content=response,
            metadata={"phase": phase}
        )
        context.conversation_history.append(ai_message)

        return response

    def generate_questions(self, context: AgentContext, initial_analysis: Dict) -> List[AgentQuestion]:
        """
        基于初始分析生成澄清问题

        Args:
            context: Agent上下文
            initial_analysis: 初始分析结果

        Returns:
            List[AgentQuestion]: 生成的问题列表
        """
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
            self.logger.info(f"Requesting AI to generate clarification questions based on initial analysis")
            response = self._call_ai_api([
                AgentMessage(role="user", content=question_prompt)
            ])

            questions_data = json.loads(response)
            questions = []

            for q_data in questions_data.get('questions', [])[:3]:
                question = AgentQuestion(
                    question_id=q_data.get('question_id', f"q_{len(questions)}"),
                    question_text=q_data.get('question_text', ''),
                    question_type=q_data.get('question_type', 'clarification'),
                    context_needed=q_data.get('context_needed', {}),
                    priority=q_data.get('priority', 3)
                )
                questions.append(question)
                self.logger.info(f"Generated question {len(questions)}: {question.question_text[:60]}... (priority: {question.priority})")

            sorted_questions = sorted(questions, key=lambda x: x.priority)
            self.logger.info(f"Successfully generated {len(sorted_questions)} questions for deeper analysis")
            return sorted_questions

        except Exception as e:
            self.logger.error(f"Failed to generate questions: {e}")
            return []

    def ask_question(self, context: AgentContext, question: AgentQuestion) -> Optional[str]:
        """
        提出问题并获取回答

        Args:
            context: Agent上下文
            question: 要提出的问题

        Returns:
            Optional[str]: AI的回答，如果失败则返回None
        """
        question_prompt = f"""
针对正在分析的代码文件 {context.file_path}，我需要更多信息来提供准确的审查：

问题：{question.question_text}

请基于代码内容和变更上下文回答这个问题。如果信息不足以回答，请说明原因。
"""

        try:
            return self.send_message_and_get_response(
                context,
                question_prompt,
                phase=f"questioning_{question.question_id}"
            )
        except Exception as e:
            self.logger.error(f"Failed to ask question {question.question_id}: {e}")
            return None

    def parse_json_response(self, response: str) -> Dict:
        """
        解析AI的JSON响应

        Args:
            response: AI响应字符串

        Returns:
            Dict: 解析后的字典，如果解析失败则返回默认结构
        """
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # 如果不是JSON，返回默认结构并包含原始响应
            return {
                "issues": [],
                "confidence": 0.5,
                "notes": response[:500],  # 截取前500字符作为注释
                "recommendations": []
            }

    def _build_code_context(self, context: AgentContext) -> str:
        """
        构建代码上下文消息

        Args:
            context: Agent上下文

        Returns:
            str: 格式化的代码上下文
        """
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

    def _call_ai_api(self, messages: List[AgentMessage]) -> str:
        """
        调用AI API获取响应

        Args:
            messages: 消息历史列表

        Returns:
            str: AI的响应内容

        Raises:
            requests.exceptions.RequestException: API调用失败时
        """
        # 转换为OpenAI API格式
        api_messages = []
        for msg in messages:
            api_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        headers = {
            'Content-Type': 'application/json'
        }

        # 仅在API密钥存在时添加Authorization头（本地服务可能不需要）
        if self.ai_api_key:
            headers['Authorization'] = f'Bearer {self.ai_api_key}'

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