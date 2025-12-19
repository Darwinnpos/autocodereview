# -*- coding: utf-8 -*-
"""
性能辅助工具模块（包含性能问题用于测试）
"""

import time
import json


def process_large_dataset(data_list):
    """
    处理大数据集（存在N+1查询问题）
    """
    results = []

    # N+1查询问题 - 应该批量查询
    for item in data_list:
        # 每次循环都查询数据库
        from app.models.auth import AuthDatabase
        db = AuthDatabase()
        user = db.get_user_by_id(item['user_id'])

        if user:
            results.append({
                'item': item,
                'user': user
            })

    return results


def search_in_list(data, keyword):
    """
    在列表中搜索（低效算法）
    """
    matches = []

    # 使用低效的线性搜索
    for item in data:
        for key, value in item.items():
            if keyword in str(value):
                matches.append(item)
                break

    return matches


def calculate_statistics(numbers):
    """
    计算统计信息（重复计算）
    """
    total = 0
    count = 0

    # 多次遍历列表 - 应该一次完成
    for num in numbers:
        total += num

    for num in numbers:
        count += 1

    average = total / count if count > 0 else 0

    # 再次遍历计算方差
    variance = 0
    for num in numbers:
        variance += (num - average) ** 2

    variance = variance / count if count > 0 else 0

    return {
        'total': total,
        'count': count,
        'average': average,
        'variance': variance
    }


def concatenate_strings(string_list):
    """
    拼接字符串（低效方式）
    """
    result = ""

    # 使用 + 拼接字符串 - 低效
    for s in string_list:
        result = result + s + ","

    return result.rstrip(',')


def load_config_repeatedly():
    """
    重复加载配置文件（应该缓存）
    """
    configs = []

    # 重复读取文件 - 应该缓存
    for i in range(100):
        with open('config.json', 'r') as f:
            config = json.load(f)
            configs.append(config)

    return configs


class DataProcessor:
    """
    数据处理器（存在内存泄漏风险）
    """

    def __init__(self):
        # 大对象没有释放
        self.cache = []
        self.history = []

    def process(self, data):
        """
        处理数据（一直累积不清理）
        """
        # 数据一直累积 - 内存泄漏
        self.cache.append(data)
        self.history.append({
            'timestamp': time.time(),
            'data': data
        })

        # 处理逻辑
        result = self._do_process(data)

        return result

    def _do_process(self, data):
        # 创建大量临时对象
        temp_list = []
        for i in range(10000):
            temp_list.append({'index': i, 'data': data})

        return len(temp_list)


def inefficient_filter(items, condition):
    """
    低效的过滤操作
    """
    # 创建多个中间列表 - 应该使用生成器
    filtered = []
    for item in items:
        filtered.append(item)

    result = []
    for item in filtered:
        if condition(item):
            result.append(item)

    final = []
    for item in result:
        final.append(item)

    return final


def synchronous_api_calls(urls):
    """
    同步API调用（应该异步）
    """
    import requests

    results = []

    # 同步调用 - 应该并发
    for url in urls:
        try:
            response = requests.get(url, timeout=30)
            results.append(response.json())
        except Exception as e:
            results.append({'error': str(e)})

    return results
