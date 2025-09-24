# -*- coding: utf-8 -*-
import sqlite3
import threading
import logging
from contextlib import contextmanager
from typing import Generator
import queue
import time


class DatabaseConnectionManager:
    """数据库连接池管理器，优化并发访问"""

    def __init__(self, db_path: str, max_connections: int = 10, timeout: int = 30):
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self.pool = queue.Queue(maxsize=max_connections)
        self.active_connections = 0
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

        # 初始化连接池
        self._initialize_pool()

    def _initialize_pool(self):
        """初始化连接池"""
        try:
            # 创建初始连接
            for _ in range(min(3, self.max_connections)):
                conn = self._create_connection()
                if conn:
                    self.pool.put(conn)
                    self.active_connections += 1
        except Exception as e:
            self.logger.error(f"Failed to initialize connection pool: {e}")

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=False  # 允许跨线程使用
            )

            # 优化SQLite设置
            conn.execute("PRAGMA journal_mode=WAL")  # WAL模式支持并发读取
            conn.execute("PRAGMA synchronous=NORMAL")  # 平衡性能和安全性
            conn.execute("PRAGMA cache_size=10000")  # 增大缓存
            conn.execute("PRAGMA temp_store=MEMORY")  # 临时表存储在内存中
            conn.execute("PRAGMA mmap_size=268435456")  # 启用内存映射

            # 设置行工厂，返回字典格式
            conn.row_factory = sqlite3.Row

            return conn
        except Exception as e:
            self.logger.error(f"Failed to create database connection: {e}")
            return None

    def _get_connection(self) -> sqlite3.Connection:
        """从连接池获取连接"""
        try:
            # 尝试从池中获取连接
            try:
                conn = self.pool.get(timeout=5)
                # 检查连接是否有效
                if self._is_connection_valid(conn):
                    return conn
                else:
                    # 连接无效，关闭并创建新连接
                    try:
                        conn.close()
                    except:
                        pass
                    self.active_connections -= 1
            except queue.Empty:
                pass

            # 如果池中没有可用连接，尝试创建新连接
            with self.lock:
                if self.active_connections < self.max_connections:
                    conn = self._create_connection()
                    if conn:
                        self.active_connections += 1
                        return conn

                # 等待可用连接
                try:
                    conn = self.pool.get(timeout=self.timeout)
                    if self._is_connection_valid(conn):
                        return conn
                    else:
                        self.active_connections -= 1
                        raise sqlite3.OperationalError("Connection is not valid")
                except queue.Empty:
                    raise sqlite3.OperationalError("Database connection pool timeout")

        except Exception as e:
            self.logger.error(f"Failed to get database connection: {e}")
            raise

    def _return_connection(self, conn: sqlite3.Connection):
        """归还连接到连接池"""
        if conn and self._is_connection_valid(conn):
            try:
                # 确保事务已提交或回滚
                conn.rollback()
                self.pool.put(conn, timeout=1)
            except queue.Full:
                # 连接池已满，关闭连接
                try:
                    conn.close()
                    self.active_connections -= 1
                except:
                    pass
            except Exception as e:
                self.logger.error(f"Error returning connection to pool: {e}")
                try:
                    conn.close()
                    self.active_connections -= 1
                except:
                    pass
        else:
            # 连接无效，减少活动连接计数
            if conn:
                try:
                    conn.close()
                except:
                    pass
            self.active_connections -= 1

    def _is_connection_valid(self, conn: sqlite3.Connection) -> bool:
        """检查连接是否有效"""
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except:
            return False

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """上下文管理器，自动管理连接"""
        conn = None
        try:
            conn = self._get_connection()
            yield conn
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise e
        finally:
            if conn:
                self._return_connection(conn)

    def execute_query(self, query: str, params: tuple = None, fetch_all: bool = True):
        """执行查询操作"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if fetch_all:
                return cursor.fetchall()
            else:
                return cursor.fetchone()

    def execute_update(self, query: str, params: tuple = None) -> int:
        """执行更新操作"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.rowcount

    def execute_batch(self, queries_and_params: list) -> bool:
        """批量执行操作"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for query, params in queries_and_params:
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Batch execution failed: {e}")
                raise

    def close_all(self):
        """关闭所有连接"""
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except:
                pass
        self.active_connections = 0

    def get_stats(self) -> dict:
        """获取连接池统计信息"""
        return {
            'active_connections': self.active_connections,
            'max_connections': self.max_connections,
            'available_connections': self.pool.qsize(),
            'pool_utilization': f"{(self.active_connections / self.max_connections) * 100:.1f}%"
        }


# 全局连接池实例
_auth_db_manager = None
_review_db_manager = None


def get_auth_db_manager() -> DatabaseConnectionManager:
    """获取认证数据库连接管理器"""
    global _auth_db_manager
    if _auth_db_manager is None:
        _auth_db_manager = DatabaseConnectionManager('auth.db')
    return _auth_db_manager


def get_review_db_manager() -> DatabaseConnectionManager:
    """获取审查数据库连接管理器"""
    global _review_db_manager
    if _review_db_manager is None:
        _review_db_manager = DatabaseConnectionManager('reviews.db')
    return _review_db_manager


def close_all_connections():
    """关闭所有数据库连接"""
    global _auth_db_manager, _review_db_manager
    if _auth_db_manager:
        _auth_db_manager.close_all()
    if _review_db_manager:
        _review_db_manager.close_all()