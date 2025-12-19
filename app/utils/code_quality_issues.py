# -*- coding: utf-8 -*-
"""
代码质量问题示例（用于测试）
"""

import os
import sys


# 全局变量过多
GLOBAL_COUNTER = 0
GLOBAL_DATA = {}
GLOBAL_CONFIG = None
GLOBAL_CACHE = []


def complexFunction(a, b, c, d, e, f):
    """
    复杂函数（太多参数，逻辑复杂）
    """
    # 函数参数太多
    # 缺少类型注解
    # 嵌套层次过深

    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    if e > 0:
                        if f > 0:
                            # 6层嵌套
                            result = a + b + c + d + e + f
                            return result
                        else:
                            return None
                    else:
                        return None
                else:
                    return None
            else:
                return None
        else:
            return None
    else:
        return None


def calculate(x, y, op):
    """
    计算函数（缺少错误处理）
    """
    # 没有验证输入
    # 没有错误处理
    # 可能除零
    if op == '+':
        return x + y
    elif op == '-':
        return x - y
    elif op == '*':
        return x * y
    elif op == '/':
        return x / y  # 除零风险
    else:
        return None


def processData(data):
    """
    数据处理函数（命名不规范，魔法数字）
    """
    # 函数名应该是小写+下划线
    result = []

    for item in data:
        # 魔法数字 - 应该使用常量
        if item['value'] > 100:
            item['status'] = 1
        elif item['value'] > 50:
            item['status'] = 2
        elif item['value'] > 25:
            item['status'] = 3
        else:
            item['status'] = 4

        result.append(item)

    return result


class badClassNaming:
    """
    类命名不规范（应该用PascalCase）
    """

    def __init__(self, Value):
        # 参数命名不规范
        self.Value = Value
        self.data = None

    def DoSomething(self):
        # 方法名应该用小写+下划线
        pass

    def get_value(self):
        return self.Value


def duplicated_code_1():
    """
    重复代码示例1
    """
    data = []
    with open('file1.txt', 'r') as f:
        for line in f:
            data.append(line.strip())

    result = []
    for item in data:
        if len(item) > 0:
            result.append(item.upper())

    return result


def duplicated_code_2():
    """
    重复代码示例2
    """
    data = []
    with open('file2.txt', 'r') as f:
        for line in f:
            data.append(line.strip())

    result = []
    for item in data:
        if len(item) > 0:
            result.append(item.upper())

    return result


def unused_variable_example():
    """
    未使用的变量
    """
    x = 10
    y = 20
    z = 30  # 未使用

    total = x + y  # z没有被使用

    # 未使用的导入
    import json  # 未使用

    return total


def poor_error_handling():
    """
    糟糕的错误处理
    """
    try:
        # 捕获太宽泛
        result = do_something_risky()
        return result
    except:
        # 空的except块
        # 吞掉所有异常
        pass


def do_something_risky():
    """辅助函数"""
    return 42


def long_function():
    """
    超长函数（应该拆分）
    """
    # 步骤1：初始化
    data = []
    config = {}
    state = 0

    # 步骤2：加载数据
    for i in range(100):
        data.append(i)

    # 步骤3：处理数据
    processed = []
    for item in data:
        if item % 2 == 0:
            processed.append(item * 2)
        else:
            processed.append(item * 3)

    # 步骤4：过滤数据
    filtered = []
    for item in processed:
        if item > 50:
            filtered.append(item)

    # 步骤5：转换数据
    transformed = []
    for item in filtered:
        transformed.append({
            'value': item,
            'doubled': item * 2,
            'squared': item ** 2
        })

    # 步骤6：聚合数据
    total = 0
    for item in transformed:
        total += item['value']

    # 步骤7：生成报告
    report = {
        'total': total,
        'count': len(transformed),
        'average': total / len(transformed) if transformed else 0
    }

    # 步骤8：保存结果
    with open('result.txt', 'w') as f:
        f.write(str(report))

    # 应该拆分成多个小函数
    return report


# 没有文档字符串的函数
def mystery_function(x):
    return x * 2 + 1


# 硬编码的配置
API_URL = "http://api.example.com"  # 应该从配置文件读取
API_KEY = "1234567890"  # 硬编码的密钥 - 安全风险
DATABASE_PATH = "/var/data/db.sqlite"  # 硬编码路径
