# -*- coding: utf-8 -*-
from typing import Dict, List, Optional
from dataclasses import dataclass
from .code_analyzer import CodeIssue


@dataclass
class CommentTemplate:
    category: str
    severity: str
    template: str
    priority: int


class CommentGenerator:
    def __init__(self, user_config: Optional[Dict] = None):
        self.user_config = user_config or {}
        self.templates = self._load_comment_templates()

    def _load_comment_templates(self) -> List[CommentTemplate]:
        """加载评论模板"""
        default_templates = [
            CommentTemplate(
                category='security',
                severity='error',
                template='🚨 **安全风险**: {message}\n\n**建议**: {suggestion}',
                priority=1
            ),
            CommentTemplate(
                category='syntax',
                severity='error',
                template='❌ **语法错误**: {message}\n\n**建议**: {suggestion}',
                priority=1
            ),
            CommentTemplate(
                category='performance',
                severity='warning',
                template='⚡ **性能优化**: {message}\n\n**建议**: {suggestion}',
                priority=3
            ),
            CommentTemplate(
                category='style',
                severity='info',
                template='🎨 **代码风格**: {message}\n\n**建议**: {suggestion}',
                priority=5
            ),
            CommentTemplate(
                category='general',
                severity='info',
                template='📝 **代码审查**: {message}\n\n**建议**: {suggestion}',
                priority=5
            )
        ]
        return sorted(default_templates, key=lambda x: x.priority)

    def generate_comment(self, issue) -> str:
        """为代码问题生成评论"""
        template = self._find_matching_template(issue)

        # 检查issue是字典还是对象
        if isinstance(issue, dict):
            message = issue.get('message', '')
            suggestion = issue.get('suggestion', '请考虑修改此处代码')
            category = issue.get('category', 'general')
            severity = issue.get('severity', 'info')
        else:
            message = getattr(issue, 'message', '')
            suggestion = getattr(issue, 'suggestion', '请考虑修改此处代码')
            category = getattr(issue, 'category', 'general')
            severity = getattr(issue, 'severity', 'info')

        comment = template.template.format(
            message=message,
            suggestion=suggestion or "请考虑修改此处代码",
            category=category,
            severity=severity
        )

        return comment

    def _find_matching_template(self, issue) -> CommentTemplate:
        """查找匹配的评论模板"""
        # 检查issue是字典还是对象
        if isinstance(issue, dict):
            issue_category = issue.get('category', 'general')
            issue_severity = issue.get('severity', 'info')
        else:
            issue_category = getattr(issue, 'category', 'general')
            issue_severity = getattr(issue, 'severity', 'info')

        for template in self.templates:
            if (template.category == issue_category and
                template.severity == issue_severity):
                return template

        for template in self.templates:
            if template.category == issue_category:
                return template

        for template in self.templates:
            if template.category == 'general':
                return template

        return CommentTemplate(
            category='general',
            severity='info',
            template='{message}\n\n{suggestion}',
            priority=10
        )

    def generate_summary_comment(self, issues: List[CodeIssue]) -> str:
        """生成代码审查总结评论"""
        if not issues:
            return "## ✅ 代码审查通过\n\n🎉 恭喜！本次代码审查未发现明显问题。"

        summary_parts = [
            "## 📋 代码审查总结",
            "",
            f"本次审查共发现 **{len(issues)}** 个问题："
        ]

        # 统计各严重程度问题数量
        error_count = 0
        warning_count = 0
        info_count = 0

        for i in issues:
            if isinstance(i, dict):
                severity = i.get('severity', 'info')
            else:
                severity = getattr(i, 'severity', 'info')

            if severity == 'error':
                error_count += 1
            elif severity == 'warning':
                warning_count += 1
            elif severity == 'info':
                info_count += 1

        if error_count > 0:
            summary_parts.append(f"- ❌ 错误: {error_count} 个")
        if warning_count > 0:
            summary_parts.append(f"- ⚠️ 警告: {warning_count} 个")
        if info_count > 0:
            summary_parts.append(f"- 💡 建议: {info_count} 个")

        return "\n".join(summary_parts)