# -*- coding: utf-8 -*-
import os
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime


class ReviewDatabase:
    def __init__(self, db_path: str = "reviews.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                mr_url TEXT NOT NULL,
                project_path TEXT NOT NULL,
                project_id TEXT NOT NULL,
                mr_iid INTEGER NOT NULL,
                mr_title TEXT NOT NULL,
                mr_author TEXT NOT NULL,
                source_branch TEXT NOT NULL,
                target_branch TEXT NOT NULL,
                total_files_analyzed INTEGER DEFAULT 0,
                total_issues_found INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                info_count INTEGER DEFAULT 0,
                comments_posted INTEGER DEFAULT 0,
                comment_errors_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT
            )
        ''')

        # 创建问题表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                suggestion TEXT,
                comment_text TEXT NOT NULL,
                comment_status TEXT DEFAULT 'pending',
                gitlab_comment_id TEXT,
                created_at TEXT NOT NULL,
                confirmed_at TEXT,
                FOREIGN KEY (review_id) REFERENCES reviews (id)
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_issues_review_id ON issues (review_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_issues_status ON issues (comment_status)')

        # 创建进度表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_progress (
                review_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                total_files INTEGER DEFAULT 0,
                processed_files INTEGER DEFAULT 0,
                total_issues INTEGER DEFAULT 0,
                current_file TEXT,
                last_update TEXT NOT NULL,
                FOREIGN KEY (review_id) REFERENCES reviews (id)
            )
        ''')

        conn.commit()
        conn.close()

    def create_review_record(self, review_data: Dict) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO reviews (
                user_id, mr_url, project_path, project_id, mr_iid,
                mr_title, mr_author, source_branch, target_branch,
                created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            review_data['user_id'], review_data['mr_url'], review_data.get('project_path', ''),
            review_data.get('project_id', ''), review_data.get('mr_iid', 0),
            review_data.get('mr_title', ''), review_data.get('mr_author', ''),
            review_data.get('source_branch', ''), review_data.get('target_branch', ''),
            datetime.now().isoformat(), 'pending'
        ))

        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return review_id

    def complete_review_record(self, review_id: int, summary: Dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE reviews SET
                total_files_analyzed = ?,
                total_issues_found = ?,
                error_count = ?,
                warning_count = ?,
                info_count = ?,
                comments_posted = ?,
                comment_errors_count = ?,
                completed_at = ?,
                status = 'completed'
            WHERE id = ?
        ''', (
            summary.get('total_files_analyzed', 0),
            summary.get('total_issues_found', 0),
            summary.get('error_count', 0),
            summary.get('warning_count', 0),
            summary.get('info_count', 0),
            summary.get('comments_posted', 0),
            summary.get('comment_errors_count', 0),
            datetime.now().isoformat(),
            review_id
        ))

        conn.commit()
        conn.close()

    def fail_review_record(self, review_id: int, error_message: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE reviews SET
                status = 'failed',
                error_message = ?,
                completed_at = ?
            WHERE id = ?
        ''', (error_message, datetime.now().isoformat(), review_id))

        conn.commit()
        conn.close()

    def add_issue_record(self, review_id: int, issue_data: Dict) -> int:
        """添加问题记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO issues (
                review_id, file_path, line_number, severity, category,
                message, suggestion, comment_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            review_id,
            issue_data['file_path'],
            issue_data['line_number'],
            issue_data['severity'],
            issue_data['category'],
            issue_data['message'],
            issue_data.get('suggestion'),
            issue_data['comment_text'],
            datetime.now().isoformat()
        ))

        issue_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return issue_id

    def get_pending_comments(self, review_id: int) -> List[Dict]:
        """获取待确认的评论"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM issues
            WHERE review_id = ? AND comment_status = 'pending'
            ORDER BY file_path, line_number
        ''', (review_id,))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def confirm_comment(self, issue_id: int) -> bool:
        """确认单个评论"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE issues SET
                comment_status = 'confirmed',
                confirmed_at = ?
            WHERE id = ? AND comment_status = 'pending'
        ''', (datetime.now().isoformat(), issue_id))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def reject_comment(self, issue_id: int) -> bool:
        """拒绝单个评论"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE issues SET
                comment_status = 'rejected',
                confirmed_at = ?
            WHERE id = ? AND comment_status = 'pending'
        ''', (datetime.now().isoformat(), issue_id))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def bulk_confirm_comments(self, issue_ids: List[int]) -> int:
        """批量确认评论"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        confirmed_count = 0
        confirmed_at = datetime.now().isoformat()

        for issue_id in issue_ids:
            cursor.execute('''
                UPDATE issues SET
                    comment_status = 'confirmed',
                    confirmed_at = ?
                WHERE id = ? AND comment_status = 'pending'
            ''', (confirmed_at, issue_id))
            confirmed_count += cursor.rowcount

        conn.commit()
        conn.close()
        return confirmed_count

    def update_comment_gitlab_id(self, issue_id: int, gitlab_comment_id: str):
        """更新GitLab评论ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE issues SET
                gitlab_comment_id = ?,
                comment_status = 'posted'
            WHERE id = ?
        ''', (gitlab_comment_id, issue_id))

        conn.commit()
        conn.close()

    def get_review_record(self, review_id: int) -> Optional[Dict]:
        """获取审查记录"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM reviews WHERE id = ?', (review_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_review_issues(self, review_id: int) -> List[Dict]:
        """获取审查的问题列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM issues
            WHERE review_id = ?
            ORDER BY file_path, line_number
        ''', (review_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_review_comments(self, review_id: int) -> List[Dict]:
        """获取审查的评论列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM issues
            WHERE review_id = ? AND comment_status != 'pending'
            ORDER BY file_path, line_number
        ''', (review_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_user_reviews(self, user_id: str = None, limit: int = 10, offset: int = 0) -> List[Dict]:
        """获取用户的审查记录，如果user_id为None则获取所有记录（管理员功能）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if user_id is None:
            # 管理员查看所有审查记录
            cursor.execute('''
                SELECT * FROM reviews
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
        else:
            # 普通用户查看自己的审查记录
            cursor.execute('''
                SELECT * FROM reviews
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_review_statistics(self, user_id: str = None, days: int = 30) -> Dict:
        """获取审查统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 时间范围
        from datetime import datetime, timedelta
        since_date = (datetime.now() - timedelta(days=days)).isoformat()

        if user_id is None:
            # 全局统计
            cursor.execute('SELECT COUNT(*) FROM reviews WHERE created_at > ?', (since_date,))
            total_reviews = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM reviews WHERE status = "completed" AND created_at > ?', (since_date,))
            completed_reviews = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM reviews WHERE status = "failed" AND created_at > ?', (since_date,))
            failed_reviews = cursor.fetchone()[0]

            cursor.execute('SELECT SUM(total_issues_found) FROM reviews WHERE created_at > ?', (since_date,))
            total_issues = cursor.fetchone()[0] or 0

            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM reviews WHERE created_at > ?', (since_date,))
            active_users = cursor.fetchone()[0]
        else:
            # 用户统计
            cursor.execute('SELECT COUNT(*) FROM reviews WHERE user_id = ? AND created_at > ?', (user_id, since_date))
            total_reviews = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM reviews WHERE user_id = ? AND status = "completed" AND created_at > ?', (user_id, since_date))
            completed_reviews = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM reviews WHERE user_id = ? AND status = "failed" AND created_at > ?', (user_id, since_date))
            failed_reviews = cursor.fetchone()[0]

            cursor.execute('SELECT SUM(total_issues_found) FROM reviews WHERE user_id = ? AND created_at > ?', (user_id, since_date))
            total_issues = cursor.fetchone()[0] or 0

            active_users = 1 if total_reviews > 0 else 0

        conn.close()

        return {
            'total_reviews': total_reviews,
            'completed_reviews': completed_reviews,
            'failed_reviews': failed_reviews,
            'total_issues': total_issues,
            'active_users': active_users,
            'success_rate': round(completed_reviews / total_reviews * 100, 1) if total_reviews > 0 else 0,
            'days': days
        }

    def search_reviews(self, query: str, user_id: str = None, limit: int = 20) -> List[Dict]:
        return []  # Simplified

    def delete_review_record(self, review_id: int):
        pass  # Simplified

    def export_review_data(self, review_id: int) -> Dict:
        return {}  # Simplified

    # ============ 进度管理方法 ============

    def init_review_progress(self, review_id: int, total_files: int):
        """初始化审查进度"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO review_progress
            (review_id, status, total_files, processed_files, total_issues, current_file, last_update)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (review_id, 'analyzing', total_files, 0, 0, None, datetime.now().isoformat()))

        conn.commit()
        conn.close()

    def update_review_progress(self, review_id: int, status: str, processed_files: int, total_issues: int, current_file: str = None):
        """更新审查进度"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE review_progress
            SET status = ?, processed_files = ?, total_issues = ?, current_file = ?, last_update = ?
            WHERE review_id = ?
        ''', (status, processed_files, total_issues, current_file, datetime.now().isoformat(), review_id))

        conn.commit()
        conn.close()

    def get_review_progress(self, review_id: int) -> Optional[Dict]:
        """获取审查进度"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM review_progress WHERE review_id = ?', (review_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def delete_review_progress(self, review_id: int):
        """删除审查进度记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM review_progress WHERE review_id = ?', (review_id,))

        conn.commit()
        conn.close()