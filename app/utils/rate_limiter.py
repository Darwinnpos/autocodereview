# -*- coding: utf-8 -*-
import time
import threading
from collections import defaultdict, deque
from functools import wraps
from flask import request, jsonify, g
import logging


class RateLimiter:
    """基于令牌桶算法的限流器"""

    def __init__(self, capacity: int = 100, refill_rate: float = 10.0, window_size: int = 3600):
        """
        初始化限流器
        :param capacity: 令牌桶容量
        :param refill_rate: 令牌补充速率（令牌/秒）
        :param window_size: 窗口大小（秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.window_size = window_size
        self.buckets = defaultdict(lambda: {'tokens': capacity, 'last_refill': time.time()})
        self.request_history = defaultdict(lambda: deque())
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

    def _refill_bucket(self, key: str):
        """补充令牌桶"""
        bucket = self.buckets[key]
        now = time.time()
        time_passed = now - bucket['last_refill']

        # 计算应该添加的令牌数量
        tokens_to_add = time_passed * self.refill_rate
        bucket['tokens'] = min(self.capacity, bucket['tokens'] + tokens_to_add)
        bucket['last_refill'] = now

    def _clean_history(self, key: str):
        """清理过期的请求历史"""
        history = self.request_history[key]
        cutoff_time = time.time() - self.window_size

        while history and history[0] < cutoff_time:
            history.popleft()

    def consume_token(self, key: str, tokens: int = 1) -> bool:
        """消费令牌"""
        with self.lock:
            self._refill_bucket(key)
            bucket = self.buckets[key]

            if bucket['tokens'] >= tokens:
                bucket['tokens'] -= tokens
                # 记录请求时间
                self.request_history[key].append(time.time())
                self._clean_history(key)
                return True
            return False

    def get_remaining_tokens(self, key: str) -> float:
        """获取剩余令牌数量"""
        with self.lock:
            self._refill_bucket(key)
            return self.buckets[key]['tokens']

    def get_request_count(self, key: str) -> int:
        """获取窗口期内的请求次数"""
        with self.lock:
            self._clean_history(key)
            return len(self.request_history[key])

    def get_rate_limit_info(self, key: str) -> dict:
        """获取限流信息"""
        with self.lock:
            self._refill_bucket(key)
            self._clean_history(key)

            return {
                'remaining_tokens': int(self.buckets[key]['tokens']),
                'capacity': self.capacity,
                'requests_in_window': len(self.request_history[key]),
                'window_size': self.window_size,
                'refill_rate': self.refill_rate
            }


class ConcurrentRequestLimiter:
    """并发请求限制器"""

    def __init__(self, max_concurrent: int = 50):
        self.max_concurrent = max_concurrent
        self.active_requests = defaultdict(int)
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

    def acquire(self, key: str) -> bool:
        """获取并发请求槽位"""
        with self.lock:
            if self.active_requests[key] >= self.max_concurrent:
                return False
            self.active_requests[key] += 1
            return True

    def release(self, key: str):
        """释放并发请求槽位"""
        with self.lock:
            if self.active_requests[key] > 0:
                self.active_requests[key] -= 1

    def get_active_count(self, key: str) -> int:
        """获取当前活跃请求数量"""
        with self.lock:
            return self.active_requests[key]

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self.lock:
            total_active = sum(self.active_requests.values())
            return {
                'total_active_requests': total_active,
                'max_concurrent': self.max_concurrent,
                'utilization': f"{(total_active / self.max_concurrent) * 100:.1f}%",
                'active_by_key': dict(self.active_requests)
            }


# 全局限流器实例
_rate_limiter = RateLimiter(capacity=100, refill_rate=10.0)  # 每秒10个令牌，最大100个
_concurrent_limiter = ConcurrentRequestLimiter(max_concurrent=50)  # 最大50个并发请求
_review_limiter = RateLimiter(capacity=20, refill_rate=2.0)  # 代码审查专用限制器


def get_client_key() -> str:
    """获取客户端标识"""
    # 优先使用用户ID，其次使用IP地址
    if hasattr(g, 'current_user') and g.current_user:
        return f"user_{g.current_user}"

    # 获取真实IP（考虑代理）
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        ip = request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    elif request.environ.get('HTTP_X_REAL_IP'):
        ip = request.environ['HTTP_X_REAL_IP']
    else:
        ip = request.environ.get('REMOTE_ADDR', 'unknown')

    return f"ip_{ip}"


def rate_limit(limiter_type='default', tokens=1):
    """
    限流装饰器
    :param limiter_type: 限流器类型 ('default', 'review', 'concurrent')
    :param tokens: 消费的令牌数量
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_key = get_client_key()

            if limiter_type == 'review':
                limiter = _review_limiter
            else:
                limiter = _rate_limiter

            if limiter_type == 'concurrent':
                # 并发限制
                if not _concurrent_limiter.acquire(client_key):
                    return jsonify({
                        'error': '服务器繁忙，请稍后重试',
                        'error_code': 'TOO_MANY_CONCURRENT_REQUESTS'
                    }), 429

                try:
                    return f(*args, **kwargs)
                finally:
                    _concurrent_limiter.release(client_key)
            else:
                # 频率限制
                if not limiter.consume_token(client_key, tokens):
                    rate_info = limiter.get_rate_limit_info(client_key)
                    return jsonify({
                        'error': '请求过于频繁，请稍后重试',
                        'error_code': 'RATE_LIMIT_EXCEEDED',
                        'retry_after': int(tokens / limiter.refill_rate),
                        'rate_limit_info': rate_info
                    }), 429

                return f(*args, **kwargs)

        return decorated_function

    return decorator


def get_rate_limit_stats() -> dict:
    """获取限流统计信息"""
    return {
        'rate_limiter': {
            'capacity': _rate_limiter.capacity,
            'refill_rate': _rate_limiter.refill_rate,
            'active_keys': len(_rate_limiter.buckets)
        },
        'review_limiter': {
            'capacity': _review_limiter.capacity,
            'refill_rate': _review_limiter.refill_rate,
            'active_keys': len(_review_limiter.buckets)
        },
        'concurrent_limiter': _concurrent_limiter.get_stats()
    }