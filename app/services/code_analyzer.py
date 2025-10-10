# -*- coding: utf-8 -*-
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class CodeIssue:
    line_number: int
    severity: str  # 'error', 'warning', 'info'
    category: str  # 'syntax', 'security', 'performance', 'style', 'logic'
    message: str
    suggestion: Optional[str] = None
    confidence: float = 0.8  # AI 确信程度 (0.0-1.0)


class CodeAnalyzer:
    def __init__(self, rules_config: Optional[Dict] = None):
        self.rules_config = rules_config or self._get_default_rules()

    def _get_default_rules(self) -> Dict:
        """获取默认的代码检查规则"""
        return {
            'python': {
                'syntax': True,
                'security': True,
                'performance': True,
                'style': True,
                'logic': True
            },
            'javascript': {
                'syntax': True,
                'security': True,
                'performance': True,
                'style': True,
                'logic': True
            },
            'java': {
                'syntax': True,
                'security': True,
                'performance': True,
                'style': True,
                'logic': True
            },
            'cpp': {
                'syntax': True,
                'security': True,
                'performance': True,
                'style': True,
                'logic': True
            }
        }

    def analyze_file(self, file_path: str, file_content: str,
                    changed_lines: List[int]) -> List[CodeIssue]:
        """分析文件内容，返回问题列表"""
        file_extension = self._get_file_extension(file_path)
        language = self._detect_language(file_extension)

        if not language:
            return []

        issues = []

        # 根据语言选择分析方法
        if language == 'python':
            issues.extend(self._analyze_python(file_content, changed_lines))
        elif language == 'javascript':
            issues.extend(self._analyze_javascript(file_content, changed_lines))
        elif language == 'java':
            issues.extend(self._analyze_java(file_content, changed_lines))
        elif language == 'cpp':
            issues.extend(self._analyze_cpp(file_content, changed_lines))

        # 只返回变更行的问题
        return [issue for issue in issues if issue.line_number in changed_lines]

    def _get_file_extension(self, file_path: str) -> str:
        """获取文件扩展名"""
        return file_path.split('.')[-1].lower()

    def _detect_language(self, extension: str) -> Optional[str]:
        """根据文件扩展名检测编程语言"""
        language_map = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'javascript',
            'jsx': 'javascript',
            'tsx': 'javascript',
            'java': 'java',
            'cpp': 'cpp',
            'cc': 'cpp',
            'cxx': 'cpp',
            'c++': 'cpp',
            'h': 'cpp',
            'hpp': 'cpp',
            'hxx': 'cpp',
            'c': 'cpp'
        }
        return language_map.get(extension)

    def _analyze_python(self, content: str, changed_lines: List[int]) -> List[CodeIssue]:
        """分析Python代码"""
        import re
        import ast

        issues = []
        lines = content.split('\n')

        # 语法检查
        try:
            ast.parse(content)
        except SyntaxError as e:
            issues.append(CodeIssue(
                line_number=e.lineno or 1,
                severity='error',
                category='syntax',
                message=f"语法错误: {e.msg}",
                suggestion="请检查语法并修复错误"
            ))

        # 安全性检查
        security_patterns = [
            (r'eval\s*\(', '使用eval()函数存在安全风险', '考虑使用ast.literal_eval()'),
            (r'exec\s*\(', '使用exec()函数存在安全风险', '避免执行动态代码'),
            (r'os\.system\s*\(', '使用os.system()存在命令注入风险', '使用subprocess模块'),
        ]

        for i, line in enumerate(lines, 1):
            for pattern, message, suggestion in security_patterns:
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        line_number=i,
                        severity='warning',
                        category='security',
                        message=message,
                        suggestion=suggestion
                    ))

        return issues

    def _analyze_javascript(self, content: str, changed_lines: List[int]) -> List[CodeIssue]:
        """分析JavaScript代码"""
        import re

        issues = []
        lines = content.split('\n')

        # 安全性检查
        security_patterns = [
            (r'eval\s*\(', '使用eval()函数存在安全风险', '避免使用eval()'),
            (r'innerHTML\s*=', '使用innerHTML可能导致XSS攻击', '使用textContent'),
        ]

        for i, line in enumerate(lines, 1):
            for pattern, message, suggestion in security_patterns:
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        line_number=i,
                        severity='warning',
                        category='security',
                        message=message,
                        suggestion=suggestion
                    ))

        return issues

    def _analyze_java(self, content: str, changed_lines: List[int]) -> List[CodeIssue]:
        """分析Java代码"""
        import re

        issues = []
        lines = content.split('\n')

        # 安全性检查
        security_patterns = [
            (r'Runtime\.getRuntime\(\)\.exec', '使用Runtime.exec()存在命令注入风险', '验证输入'),
        ]

        for i, line in enumerate(lines, 1):
            for pattern, message, suggestion in security_patterns:
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        line_number=i,
                        severity='warning',
                        category='security',
                        message=message,
                        suggestion=suggestion
                    ))

        return issues
    def _analyze_cpp(self, content: str, changed_lines: List[int]) -> List[CodeIssue]:
        """分析C++代码"""
        import re

        issues = []
        lines = content.split('\n')

        # 安全性检查
        security_patterns = [
            (r"gets\s*\(", "使用gets()函数存在缓冲区溢出风险", "使用fgets()或std::getline()替代"),
            (r"strcpy\s*\(", "使用strcpy()可能导致缓冲区溢出", "使用strncpy()或std::string"),
            (r"sprintf\s*\(", "使用sprintf()存在缓冲区溢出风险", "使用snprintf()或std::stringstream"),
            (r"strcat\s*\(", "使用strcat()可能导致缓冲区溢出", "使用strncat()或std::string"),
            (r"system\s*\(", "使用system()函数存在命令注入风险", "验证输入或使用更安全的替代方案"),
        ]

        # 性能检查
        performance_patterns = [
            (r"std::endl", "频繁使用std::endl可能影响性能", "考虑使用\"\\n\""),
            (r"\.size\(\)\s*==\s*0", "检查容器是否为空的方式不够高效", "使用.empty()方法"),
            (r"new\s+\w+\[", "使用原始数组可能导致内存管理问题", "考虑使用std::vector或std::array"),
        ]

        # 代码风格检查
        style_patterns = [
            (r"using\s+namespace\s+std\s*;", "在头文件中使用using namespace std不是好习惯", "在.cpp文件中使用或使用具体的using声明"),
            (r"#define\s+\w+\s+\d+", "使用#define定义常量", "考虑使用const变量或enum class"),
        ]

        for i, line in enumerate(lines, 1):
            # 安全性检查
            for pattern, message, suggestion in security_patterns:
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        line_number=i,
                        severity="warning",
                        category="security",
                        message=message,
                        suggestion=suggestion
                    ))

            # 性能检查
            for pattern, message, suggestion in performance_patterns:
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        line_number=i,
                        severity="info",
                        category="performance",
                        message=message,
                        suggestion=suggestion
                    ))

            # 代码风格检查
            for pattern, message, suggestion in style_patterns:
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        line_number=i,
                        severity="info",
                        category="style",
                        message=message,
                        suggestion=suggestion
                    ))

        return issues
