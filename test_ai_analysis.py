#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试AI代码分析功能
"""

import sys
sys.path.append('.')

from app.services.ai_analyzer import AICodeAnalyzer, AIAnalysisContext


def test_ai_analyzer():
    """测试AI分析器"""

    # 测试配置
    ai_config = {
        'ai_api_url': 'https://api.openai.com/v1',  # 替换为你的API URL
        'ai_api_key': 'your-api-key-here',  # 替换为你的API密钥
        'ai_model': 'gpt-3.5-turbo'
    }

    # 创建AI分析器
    analyzer = AICodeAnalyzer(ai_config)

    # 测试代码（包含一些常见问题）
    test_code = '''def process_user_input(user_input):
    # 不安全的代码示例
    result = eval(user_input)  # 安全风险：使用eval

    # 性能问题示例
    data = []
    for i in range(1000):
        data.append(i * 2)  # 可以优化为列表推导式

    return result

def sql_query(user_id):
    # SQL注入风险
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query
'''

    # 创建分析上下文
    context = AIAnalysisContext(
        file_path='test.py',
        file_content=test_code,
        changed_lines=[2, 6, 7, 8, 12, 13],  # 假设这些行是变更的
        diff_content='''
@@ -1,13 +1,13 @@
+def process_user_input(user_input):
+    # 不安全的代码示例
+    result = eval(user_input)  # 安全风险：使用eval
+
+    # 性能问题示例
+    data = []
+    for i in range(1000):
+        data.append(i * 2)  # 可以优化为列表推导式
+
+    return result
+
+def sql_query(user_id):
+    # SQL注入风险
+    query = f"SELECT * FROM users WHERE id = {user_id}"
+    return query
''',
        language='python',
        mr_title='添加用户输入处理功能',
        mr_description='这个MR添加了处理用户输入的新功能'
    )

    print("🚀 开始AI代码分析测试...")
    print(f"测试代码长度: {len(test_code)} 字符")
    print(f"变更行: {context.changed_lines}")
    print()

    # 如果没有API密钥，就创建模拟结果
    if ai_config['ai_api_key'] == 'your-api-key-here':
        print("⚠️  未配置真实API密钥，显示模拟分析结果:")

        # 模拟AI分析结果
        mock_issues = [
            {
                "line_number": 2,
                "severity": "error",
                "category": "security",
                "message": "使用eval()函数存在严重安全风险，可能导致代码注入攻击",
                "suggestion": "使用ast.literal_eval()替代eval()，或者实现安全的输入验证机制"
            },
            {
                "line_number": 7,
                "severity": "warning",
                "category": "performance",
                "message": "循环中重复调用append()方法效率较低",
                "suggestion": "使用列表推导式: data = [i * 2 for i in range(1000)]"
            },
            {
                "line_number": 13,
                "severity": "error",
                "category": "security",
                "message": "字符串格式化可能导致SQL注入攻击",
                "suggestion": "使用参数化查询或ORM避免SQL注入风险"
            }
        ]

        print(f"🔍 发现 {len(mock_issues)} 个问题:")
        for i, issue in enumerate(mock_issues, 1):
            print(f"\n{i}. 第{issue['line_number']}行 - {issue['severity'].upper()}")
            print(f"   类别: {issue['category']}")
            print(f"   问题: {issue['message']}")
            print(f"   建议: {issue['suggestion']}")

    else:
        # 真实AI分析
        try:
            issues = analyzer.analyze_code_with_ai(context)

            if issues:
                print(f"🔍 AI分析发现 {len(issues)} 个问题:")
                for i, issue in enumerate(issues, 1):
                    print(f"\n{i}. 第{issue.line_number}行 - {issue.severity.upper()}")
                    print(f"   类别: {issue.category}")
                    print(f"   问题: {issue.message}")
                    print(f"   建议: {issue.suggestion}")
            else:
                print("✅ AI分析未发现问题")

        except Exception as e:
            print(f"❌ AI分析失败: {e}")

    print("\n" + "="*50)
    print("📋 AI提示词特性:")
    print("✓ 支持完整源代码上下文分析")
    print("✓ 重点关注变更行及其周围代码")
    print("✓ 包含diff信息用于理解变更意图")
    print("✓ 支持多种编程语言检测")
    print("✓ 涵盖安全、性能、质量、最佳实践等维度")
    print("✓ 返回结构化的JSON格式结果")
    print("✓ 提供具体的修改建议")


if __name__ == '__main__':
    test_ai_analyzer()