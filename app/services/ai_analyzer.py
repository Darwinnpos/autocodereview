# -*- coding: utf-8 -*-
import json
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging


@dataclass
class CodeIssue:
    line_number: int
    severity: str  # 'error', 'warning', 'info'
    category: str  # 'security', 'performance', 'quality', 'best_practices', 'logic'
    message: str
    suggestion: Optional[str] = None


@dataclass
class AIAnalysisContext:
    """AI分析上下文"""
    file_path: str
    file_content: str
    changed_lines: List[int]
    diff_content: str
    language: str
    mr_title: str = ""
    mr_description: str = ""


class AICodeAnalyzer:
    """AI驱动的代码分析器"""

    def __init__(self, ai_config: Dict):
        self.ai_api_url = ai_config.get('ai_api_url', 'https://api.openai.com/v1')
        self.ai_api_key = ai_config.get('ai_api_key', '')
        self.ai_model = ai_config.get('ai_model', 'gpt-3.5-turbo')
        self.severity_level = ai_config.get('review_severity_level', 'standard')
        self.logger = logging.getLogger(__name__)

    def analyze_code_with_ai(self, context: AIAnalysisContext) -> List[CodeIssue]:
        """使用AI分析代码"""
        if not self.ai_api_key:
            self.logger.warning("AI API key not configured, skipping AI analysis")
            return []

        try:
            # 构建AI分析提示词
            prompt = self._build_analysis_prompt(context)

            # 调用AI API
            response = self._call_ai_api(prompt)

            # 解析AI响应
            issues = self._parse_ai_response(response, context)

            # 根据严重程度等级过滤结果
            filtered_issues = self._filter_issues_by_severity(issues)

            return filtered_issues

        except requests.exceptions.Timeout as e:
            self.logger.error(f"AI API timeout: {e}")
            raise Exception(f"AI服务超时：请求超过30秒未响应，请稍后重试")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"AI API connection error: {e}")
            raise Exception(f"AI服务连接失败：无法连接到AI API服务器，请检查网络连接和API URL配置")
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 0
            if status_code == 401:
                raise Exception("AI服务认证失败：API密钥无效或已过期，请在个人资料中更新AI API密钥")
            elif status_code == 403:
                raise Exception("AI服务权限不足：当前API密钥没有足够权限，请检查API密钥设置")
            elif status_code == 429:
                raise Exception("AI服务请求限制：API请求过于频繁，请稍后重试")
            elif status_code == 500:
                raise Exception("AI服务内部错误：AI服务器暂时不可用，请稍后重试")
            else:
                raise Exception(f"AI API错误：HTTP {status_code} - {str(e)}")
        except json.JSONDecodeError as e:
            self.logger.error(f"AI API response parsing error: {e}")
            raise Exception("AI服务响应格式错误：无法解析API响应，请稍后重试")
        except Exception as e:
            self.logger.error(f"AI analysis failed: {e}")
            raise Exception(f"AI代码分析失败：{str(e)}")

    def _build_analysis_prompt(self, context: AIAnalysisContext) -> str:
        """构建AI分析提示词"""

        # 获取变更行的代码片段
        changed_code_snippets = self._extract_changed_code_snippets(
            context.file_content, context.changed_lines
        )

        prompt = f"""你是一个专业的代码审查专家。请分析以下代码变更，重点关注新增和修改的部分。

**文件路径**: {context.file_path}
**编程语言**: {context.language}
**MR标题**: {context.mr_title}

**修改后的完整源代码** (当前版本):
```{context.language}
{context.file_content}
```

**代码变更差异(diff)** (显示从旧版本到新版本的变化):
```diff
{context.diff_content}
```

**新增/修改的代码行** (第{', '.join(map(str, context.changed_lines))}行，这些是修改后的新代码):
{changed_code_snippets}

**重要说明**:
- 上述"完整源代码"是修改**后**的版本（即当前最新代码）
- "代码变更差异"中以"+"开头的行是新增/修改**后**的代码
- "代码变更差异"中以"-"开头的行是删除/修改**前**的代码
- 请重点分析新增/修改后的代码（即"+"开头的行对应的内容）

请从以下维度分析新增/修改后的代码：

1. **安全性 (Security)**:
   - SQL注入、XSS、CSRF等安全漏洞
   - 敏感信息泄露
   - 输入验证缺失
   - 权限控制问题

2. **性能 (Performance)**:
   - 算法复杂度问题
   - 内存泄露风险
   - 不必要的循环或计算
   - 数据库查询优化

3. **代码质量 (Quality)**:
   - 代码可读性
   - 命名规范
   - 函数/方法设计
   - 异常处理

4. **最佳实践 (Best Practices)**:
   - 设计模式使用
   - 框架特定的最佳实践
   - 代码重构建议

5. **逻辑错误 (Logic)**:
   - 潜在的运行时错误
   - 边界条件处理
   - 逻辑漏洞

**分析要求**:
- 只分析新增/修改的代码行及其直接相关的上下文
- 重点关注修改后的代码可能存在的问题
- 不要分析整个文件，只关注变更部分

请以JSON格式返回分析结果，格式如下：
```json
[
  {{
    "line_number": 行号,
    "severity": "error|warning|info",
    "category": "security|performance|quality|best_practices|logic",
    "message": "问题描述（描述修改后代码的问题）",
    "suggestion": "具体的修改建议（针对当前修改后的代码）",
    "confidence": 0.8
  }}
]
```

要求：
- 只返回JSON，不要其他文字
- line_number必须是新增/修改行中的一个
- severity: error(严重问题), warning(潜在问题), info(建议优化)
- confidence: 0.0-1.0，表示问题的确信度
- message和suggestion都应该针对修改**后**的代码
- 如果没有问题，返回空数组[]
"""

        return prompt

    def _extract_changed_code_snippets(self, file_content: str, changed_lines: List[int]) -> str:
        """提取变更行的代码片段"""
        lines = file_content.split('\n')
        snippets = []

        for line_num in sorted(changed_lines):
            if 1 <= line_num <= len(lines):
                # 提供上下文（前后各2行）
                start = max(0, line_num - 3)
                end = min(len(lines), line_num + 2)

                context_lines = []
                for i in range(start, end):
                    if i + 1 == line_num:
                        # 标记这是新增/修改后的代码行
                        marker = ">>> [新增/修改] "
                    else:
                        marker = "    "
                    context_lines.append(f"{marker}{i + 1}: {lines[i]}")

                snippets.append(f"修改后的代码行 {line_num} (当前版本):\n" + "\n".join(context_lines))

        return "\n\n".join(snippets)

    def _call_ai_api(self, prompt: str) -> Dict[str, Any]:
        """调用AI API"""
        url = f"{self.ai_api_url.rstrip('/')}/chat/completions"

        headers = {
            'Authorization': f'Bearer {self.ai_api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.ai_model,
            'messages': [
                {
                    'role': 'system',
                    'content': '你是一个专业的代码审查专家。请仔细分析代码并返回标准JSON格式的结果。'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.1,  # 降低随机性，提高一致性
            'max_tokens': 2000
        }

        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()

        return response.json()

    def _parse_ai_response(self, response: Dict[str, Any], context: AIAnalysisContext) -> List[CodeIssue]:
        """解析AI响应"""
        try:
            # 提取AI返回的内容
            content = response['choices'][0]['message']['content'].strip()

            # 尝试提取JSON部分
            if '```json' in content:
                json_start = content.find('```json') + 7
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()
            elif '[' in content and ']' in content:
                # 找到第一个[和最后一个]
                start = content.find('[')
                end = content.rfind(']') + 1
                content = content[start:end]

            # 解析JSON
            ai_issues = json.loads(content)

            # 转换为CodeIssue对象
            code_issues = []
            for issue_data in ai_issues:
                # 验证line_number是否在变更行中
                line_number = issue_data.get('line_number', 0)
                if line_number not in context.changed_lines:
                    self.logger.warning(f"AI returned line {line_number} not in changed lines {context.changed_lines}")
                    continue

                # 验证必需字段
                if not all(key in issue_data for key in ['severity', 'category', 'message']):
                    self.logger.warning(f"AI response missing required fields: {issue_data}")
                    continue

                code_issue = CodeIssue(
                    line_number=line_number,
                    severity=issue_data['severity'],
                    category=issue_data['category'],
                    message=issue_data['message'],
                    suggestion=issue_data.get('suggestion', '请考虑修改此处代码')
                )

                code_issues.append(code_issue)

            self.logger.info(f"AI analysis found {len(code_issues)} issues")
            return code_issues

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse AI response as JSON: {e}")
            self.logger.debug(f"AI response content: {response}")
            return []
        except KeyError as e:
            self.logger.error(f"Unexpected AI response format: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error parsing AI response: {e}")
            return []

    def get_language_from_file_path(self, file_path: str) -> str:
        """根据文件路径检测编程语言"""
        extension = file_path.split('.')[-1].lower()
        language_map = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'jsx': 'javascript',
            'tsx': 'typescript',
            'java': 'java',
            'cpp': 'cpp',
            'cc': 'cpp',
            'cxx': 'cpp',
            'c++': 'cpp',
            'h': 'cpp',
            'hpp': 'cpp',
            'c': 'c',
            'go': 'go',
            'rs': 'rust',
            'php': 'php',
            'rb': 'ruby',
            'cs': 'csharp',
            'html': 'html',
            'css': 'css',
            'sql': 'sql',
            'sh': 'bash',
            'yml': 'yaml',
            'yaml': 'yaml',
            'json': 'json',
            'xml': 'xml'
        }
        return language_map.get(extension, 'text')

    def _filter_issues_by_severity(self, issues: List[CodeIssue]) -> List[CodeIssue]:
        """根据严重程度等级过滤问题"""
        if not issues:
            return issues

        # 定义各等级允许的严重程度
        allowed_severities = {
            'strict': ['error', 'warning', 'info'],      # 严格模式：检查所有问题
            'standard': ['error', 'warning'],            # 标准模式：检查错误和警告
            'relaxed': ['error']                         # 宽松模式：只检查错误
        }

        current_allowed = allowed_severities.get(self.severity_level, ['error', 'warning'])

        # 过滤问题
        filtered_issues = []
        for issue in issues:
            # 检查issue是字典还是对象
            if isinstance(issue, dict):
                severity = issue.get('severity', 'info')
            else:
                severity = getattr(issue, 'severity', 'info')

            if severity in current_allowed:
                filtered_issues.append(issue)
            else:
                self.logger.debug(f"过滤掉严重程度为 {severity} 的问题（当前等级：{self.severity_level}）")

        self.logger.info(f"严重程度过滤：{len(issues)} -> {len(filtered_issues)} （等级：{self.severity_level}）")
        return filtered_issues