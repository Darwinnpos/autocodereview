# -*- coding: utf-8 -*-
import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .gitlab_client import GitLabClient
from .comment_generator import CommentGenerator
from .ai_analyzer import AICodeAnalyzer, AIAnalysisContext, CodeIssue
from ..models.user import UserConfig, UserConfigManager
from ..models.review import ReviewDatabase
from ..models.auth import AuthDatabase
import threading


class ReviewService:
    def __init__(self, config_manager: UserConfigManager, db_path: str = "reviews.db"):
        self.config_manager = config_manager
        self.db = ReviewDatabase(db_path)
        self.auth_db = AuthDatabase()
        self.logger = self._setup_logger()
        # 进度跟踪存储 (内存中临时存储)
        self._progress_storage = {}
        self._progress_lock = threading.Lock()

    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('ReviewService')
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def create_review_record(self, username: str, mr_url: str) -> Optional[int]:
        """创建审查记录并返回review_id"""
        try:
            self.logger.info(f"create_review_record called with username: {username}, mr_url: {mr_url}")

            # 获取用户信息
            user = self.auth_db.get_user_by_username(username)
            self.logger.info(f"Found user: {user.username if user else 'None'} (ID: {user.id if user else 'None'})")
            if user is None:
                self.logger.error("User not found, returning None")
                return None

            # 获取MR基本信息
            user_config = self.config_manager.load_user_config(str(user.id))
            self.logger.info(f"User config loaded: {user_config is not None}")
            if user_config:
                self.logger.info(f"GitLab URL: {user_config.gitlab_url}")
            if not user_config:
                self.logger.error("User config not found, returning None")
                return None

            self.logger.info("Creating GitLab client...")
            gitlab_client = GitLabClient(user_config.gitlab_url, user_config.access_token)

            self.logger.info("Parsing MR URL...")
            project_path, project_id, mr_iid = gitlab_client.parse_mr_url(mr_url)
            self.logger.info(f"Parsed MR URL - project_path: {project_path}, project_id: {project_id}, mr_iid: {mr_iid}")

            self.logger.info("Getting MR info...")
            mr_info = gitlab_client.get_mr_info(project_id, mr_iid)
            self.logger.info(f"MR info retrieved: {mr_info is not None}")
            if mr_info:
                self.logger.info(f"MR info keys: {list(mr_info.keys()) if isinstance(mr_info, dict) else 'Not a dict'}")
            if not mr_info:
                self.logger.error("Failed to get MR info, returning None")
                return None

            # 创建审查记录
            review_data = {
                'user_id': username,
                'mr_url': mr_url,
                'project_path': project_path,
                'project_id': project_id,
                'mr_iid': mr_iid,
                'mr_title': mr_info.get('title', ''),
                'mr_author': mr_info.get('author', {}).get('name', ''),
                'source_branch': mr_info.get('source_branch', ''),
                'target_branch': mr_info.get('target_branch', '')
            }

            review_id = self.db.create_review_record(review_data)
            self.logger.info(f"Created review record with ID: {review_id}")
            return review_id

        except Exception as e:
            self.logger.error(f"Error creating review record: {e}")
            return None

    def perform_review(self, username: str, mr_url: str, review_id: int = None) -> Dict:
        """执行完整的代码审查流程"""
        try:
            # 1. 获取用户信息
            self.logger.info(f"Starting code review for user {username}, MR: {mr_url}")
            user = self.auth_db.get_user_by_username(username)

            if user is None:
                return {
                    'success': False,
                    'error': f'用户不存在: {username}',
                    'error_code': 'USER_NOT_FOUND'
                }

            # 检查用户是否配置了GitLab
            if not user.gitlab_url or not user.access_token:
                return {
                    'success': False,
                    'error': '请先在个人资料中配置GitLab信息',
                    'error_code': 'GITLAB_CONFIG_MISSING'
                }

            # 2. 初始化GitLab客户端
            gitlab_client = GitLabClient(user.gitlab_url, user.access_token)

            # 获取GitLab用户信息，如果reviewer_name为空则使用GitLab用户名
            reviewer_name = user.reviewer_name
            if not reviewer_name:
                try:
                    gitlab_user_info = gitlab_client.get_current_user()
                    reviewer_name = gitlab_user_info.get('username', username)
                    self.logger.info(f"Using GitLab username as reviewer name: {reviewer_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to get GitLab user info, using system username: {e}")
                    reviewer_name = username

            # 创建用户配置对象
            user_config = UserConfig(
                user_id=username,
                gitlab_url=user.gitlab_url,
                access_token=user.access_token,
                reviewer_name=reviewer_name
            )

            # 添加AI配置到用户配置对象（作为额外属性）
            user_config.ai_api_url = user.ai_api_url
            user_config.ai_api_key = user.ai_api_key
            user_config.ai_model = user.ai_model

            # 3. 解析MR URL并获取基本信息
            try:
                project_path, project_id, mr_iid = gitlab_client.parse_mr_url(mr_url)
                mr_info = gitlab_client.get_mr_info(project_id, mr_iid)

                # 如果没有传入review_id，创建新的审查记录
                if review_id is None:
                    review_data = {
                        'user_id': user.id,
                        'mr_url': mr_url,
                        'project_path': project_path,
                        'project_id': project_id,
                        'mr_iid': mr_iid,
                        'mr_title': mr_info.get('title', ''),
                        'mr_author': mr_info.get('author', {}).get('name', ''),
                        'source_branch': mr_info.get('source_branch', ''),
                        'target_branch': mr_info.get('target_branch', '')
                    }
                    review_id = self.db.create_review_record(review_data)
                    self.logger.info(f"Created review record with ID: {review_id}")

            except Exception as e:
                self.logger.error(f"Failed to get MR info: {e}")
                error_msg = f'无法获取MR信息: {str(e)}'
                if review_id:
                    self.db.fail_review_record(review_id, error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': 'MR_INFO_ERROR',
                    'review_id': review_id
                }

            # 4. 获取文件变更
            try:
                changes = gitlab_client.get_mr_changes(project_id, mr_iid)
                self.logger.info(f"Found {len(changes)} changed files")
            except Exception as e:
                self.logger.error(f"Failed to get MR changes: {e}")
                error_msg = f'无法获取文件变更: {str(e)}'
                if review_id:
                    self.db.fail_review_record(review_id, error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': 'CHANGES_ERROR',
                    'review_id': review_id
                }

            # 5. 分析每个变更的文件
            all_issues = []
            analyzed_files = []
            issue_records = []

            # 初始化AI分析器
            if not user.ai_api_key:
                error_msg = 'AI API密钥未配置，无法进行代码分析'
                if review_id:
                    self.db.fail_review_record(review_id, error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': 'AI_CONFIG_ERROR',
                    'review_id': review_id
                }

            ai_config = {
                'ai_api_url': user.ai_api_url,
                'ai_api_key': user.ai_api_key,
                'ai_model': user.ai_model
            }
            ai_analyzer = AICodeAnalyzer(ai_config)
            self.logger.info("AI analyzer initialized")

            # 初始化进度跟踪
            # 计算需要分析的文件数（排除删除的文件）
            valid_files = []
            for change in changes:
                if change.get('deleted_file', False):
                    continue
                file_path = change.get('new_path') or change.get('old_path')
                if file_path:
                    valid_files.append(file_path)

            total_files = len(valid_files)
            self.logger.info(f"Total files to analyze: {total_files}")

            # 立即初始化进度，这样前端就能获取到正确的total_files
            self._init_progress(review_id, total_files)

            # 额外的日志用于调试
            self.logger.info(f"Progress initialized immediately for review {review_id} with {total_files} files")

            processed_files = 0
            for change in changes:
                if change.get('deleted_file', False):
                    continue  # 跳过已删除的文件

                file_path = change.get('new_path') or change.get('old_path')
                if not file_path:
                    continue

                self.logger.info(f"Analyzing file: {file_path}")

                try:
                    # 获取变更的行号
                    changed_lines = self._extract_changed_lines(change.get('diff', ''))
                    if not changed_lines:
                        self.logger.info(f"No changed lines found in {file_path}, skipping")
                        continue

                    # 获取完整的源文件内容
                    file_content = self._get_full_file_content(gitlab_client, project_id, file_path, mr_info.get('source_branch', 'main'))
                    if not file_content:
                        self.logger.warning(f"Could not get file content for {file_path}, falling back to diff content")
                        file_content = self._get_file_content_from_diff(change.get('diff', ''))
                        if not file_content:
                            continue

                    # 更新进度 - 显示当前分析的文件
                    self._update_progress(review_id, 'analyzing', processed_files, len(all_issues), file_path)

                    # AI分析
                    ai_issues = []
                    try:
                        # 创建AI分析上下文
                        language = ai_analyzer.get_language_from_file_path(file_path)
                        ai_context = AIAnalysisContext(
                            file_path=file_path,
                            file_content=file_content,
                            changed_lines=changed_lines,
                            diff_content=change.get('diff', ''),
                            language=language,
                            mr_title=mr_info.get('title', ''),
                            mr_description=mr_info.get('description', '')
                        )

                        # 调用AI分析
                        ai_issues = ai_analyzer.analyze_code_with_ai(ai_context)
                        if ai_issues:
                            self.logger.info(f"AI analysis found {len(ai_issues)} issues in {file_path}")

                    except Exception as e:
                        self.logger.warning(f"AI analysis failed for {file_path}: {e}")

                    # 添加到分析文件列表（无论是否有问题都算分析过）
                    analyzed_files.append({
                        'file_path': file_path,
                        'issues_count': len(ai_issues),
                        'issues': ai_issues,
                        'ai_issues': len(ai_issues)
                    })

                    if ai_issues:
                        all_issues.extend(ai_issues)

                        # 将问题保存到issue_records列表，稍后统一处理
                        for issue in ai_issues:
                            issue_records.append({'issue': issue, 'file_path': file_path})

                        self.logger.info(f"Found {len(ai_issues)} AI issues in {file_path}")
                    else:
                        self.logger.info(f"No issues found in {file_path}")

                except Exception as e:
                    self.logger.warning(f"Failed to analyze file {file_path}: {e}")
                    continue
                finally:
                    # 无论成功还是失败都增加处理计数
                    processed_files += 1
                    # 更新进度 - 文件处理完成后（不显示当前文件名）
                    self._update_progress(review_id, 'analyzing', processed_files, len(all_issues))

            # 更新进度 - 开始生成评论
            self._update_progress(review_id, 'generating_comments', processed_files, len(all_issues))

            # 6. 生成评论并保存待确认
            comment_generator = CommentGenerator(user_config.__dict__)
            comments_prepared = 0

            # 为每个问题生成评论文本并保存到数据库
            for issue_record in issue_records:
                try:
                    issue = issue_record['issue']
                    file_path = issue_record['file_path']

                    print(f"DEBUG: Issue type: {type(issue)}")
                    print(f"DEBUG: Issue content: {issue}")

                    comment_text = comment_generator.generate_comment(issue)

                    # 准备问题数据，包含评论文本
                    if isinstance(issue, dict):
                        issue_data = {
                            'file_path': file_path,
                            'line_number': issue.get('line_number', 0),
                            'severity': issue.get('severity', 'info'),
                            'category': issue.get('category', 'general'),
                            'message': issue.get('message', ''),
                            'suggestion': issue.get('suggestion', ''),
                            'comment_text': comment_text
                        }
                    else:
                        issue_data = {
                            'file_path': file_path,
                            'line_number': getattr(issue, 'line_number', 0),
                            'severity': getattr(issue, 'severity', 'info'),
                            'category': getattr(issue, 'category', 'general'),
                            'message': getattr(issue, 'message', ''),
                            'suggestion': getattr(issue, 'suggestion', ''),
                            'comment_text': comment_text
                        }

                    # 保存问题记录到数据库
                    issue_id = self.db.add_issue_record(review_id, issue_data)
                    issue_record['issue_id'] = issue_id
                    comments_prepared += 1

                    # 获取行号用于日志记录
                    if isinstance(issue, dict):
                        line_number = issue.get('line_number', 0)
                    else:
                        line_number = getattr(issue, 'line_number', 0)

                    self.logger.info(f"Prepared comment for {file_path}:{line_number}")

                except Exception as e:
                    # 获取行号用于错误日志记录
                    if isinstance(issue, dict):
                        line_number = issue.get('line_number', 0)
                    else:
                        line_number = getattr(issue, 'line_number', 0)

                    self.logger.error(f"Error preparing comment for {file_path}:{line_number}: {e}")

            # 7. 完成审查记录
            analysis_summary = {
                'total_files_analyzed': len(analyzed_files),
                'total_issues_found': len(all_issues),
                'error_count': len([i for i in all_issues if i.severity == 'error']),
                'warning_count': len([i for i in all_issues if i.severity == 'warning']),
                'info_count': len([i for i in all_issues if i.severity == 'info']),
                'comments_prepared': comments_prepared,
                'comments_posted': 0  # 还没有发布评论
            }

            self.db.complete_review_record(review_id, analysis_summary)

            # 更新进度 - 完成
            self._update_progress(review_id, 'completed', processed_files, len(all_issues))

            # 8. 返回结果
            result = {
                'success': True,
                'review_id': review_id,
                'pending_comments_count': comments_prepared,
                'mr_info': {
                    'title': mr_info.get('title'),
                    'author': mr_info.get('author', {}).get('name'),
                    'source_branch': mr_info.get('source_branch'),
                    'target_branch': mr_info.get('target_branch'),
                    'web_url': mr_info.get('web_url')
                },
                'analysis_summary': {
                    'total_files_analyzed': len(analyzed_files),
                    'total_issues_found': len(all_issues),
                    'issues_by_severity': self._group_issues_by_severity(all_issues),
                    'issues_by_category': self._group_issues_by_category(all_issues)
                },
                'files_analyzed': analyzed_files
            }

            self.logger.info(f"Code review completed for {mr_url}")
            return result

        except Exception as e:
            self.logger.error(f"Unexpected error during review: {e}")
            error_msg = f'代码审查过程中发生错误: {str(e)}'
            if review_id:
                self.db.fail_review_record(review_id, error_msg)
            return {
                'success': False,
                'error': error_msg,
                'error_code': 'UNEXPECTED_ERROR',
                'review_id': review_id
            }

    def get_review_details(self, review_id: int) -> Optional[Dict]:
        """获取审查详细信息"""
        review = self.db.get_review_record(review_id)
        if not review:
            return None

        issues = self.db.get_review_issues(review_id)
        comments = self.db.get_review_comments(review_id)

        return {
            'review': review,
            'issues': issues,
            'comments': comments
        }

    def get_user_review_history(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Dict]:
        """获取用户的审查历史"""
        return self.db.get_user_reviews(user_id, limit, offset)

    def get_review_statistics(self, user_id: str = None, days: int = 30) -> Dict:
        """获取审查统计信息"""
        return self.db.get_review_statistics(user_id, days)

    def search_reviews(self, query: str, user_id: str = None, limit: int = 20) -> List[Dict]:
        """搜索审查记录"""
        return self.db.search_reviews(query, user_id, limit)

    def delete_review(self, review_id: int) -> bool:
        """删除审查记录"""
        try:
            self.db.delete_review_record(review_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete review {review_id}: {e}")
            return False

    def export_review_data(self, review_id: int) -> Dict:
        """导出审查数据"""
        return self.db.export_review_data(review_id)

    def get_pending_comments(self, review_id: int) -> List[Dict]:
        """获取待确认的评论"""
        return self.db.get_pending_comments(review_id)

    def confirm_comment(self, review_id: int, issue_id: int) -> bool:
        """确认并发布单个评论"""
        try:
            # 获取问题详情
            issue = self._get_issue_by_id(issue_id)
            if not issue or issue['review_id'] != review_id:
                return False

            # 如果已经确认，先发布到GitLab
            if self.db.confirm_comment(issue_id):
                # 获取审查信息
                review = self.db.get_review_record(review_id)
                if not review:
                    self.logger.error(f"Review record not found for review_id: {review_id}")
                    return False

                # 从数据库获取用户配置
                user = self.auth_db.get_user_by_id(review['user_id'])
                if not user:
                    self.logger.error(f"User not found for user_id: {review['user_id']}")
                    return False

                if not user.gitlab_url or not user.access_token:
                    self.logger.error(f"GitLab configuration missing for user: {user.username}")
                    return False

                # 发布评论到GitLab
                gitlab_client = GitLabClient(user.gitlab_url, user.access_token)
                success = gitlab_client.add_mr_comment(
                    review['project_id'],
                    review['mr_iid'],
                    issue['comment_text'],
                    issue['file_path'],
                    issue['line_number']
                )

                if success:
                    self.db.update_comment_gitlab_id(issue_id, "posted")
                    return True
                else:
                    self.logger.error(f"Failed to post comment to GitLab for issue {issue_id}")
                    return False

            return False
        except Exception as e:
            self.logger.error(f"Error confirming comment {issue_id}: {e}")
            return False

    def reject_comment(self, issue_id: int) -> bool:
        """拒绝评论"""
        return self.db.reject_comment(issue_id)

    def bulk_confirm_comments(self, review_id: int, issue_ids: List[int]) -> Dict:
        """批量确认评论"""
        try:
            # 确认评论
            confirmed_count = self.db.bulk_confirm_comments(issue_ids)

            # 获取审查信息
            review = self.db.get_review_record(review_id)
            if not review:
                return {'success': False, 'error': '审查记录不存在'}

            # 从数据库获取用户配置
            user = self.auth_db.get_user_by_id(review['user_id'])
            if not user:
                return {'success': False, 'error': f'用户不存在: {review["user_id"]}'}

            if not user.gitlab_url or not user.access_token:
                return {'success': False, 'error': f'GitLab配置缺失: {user.username}'}

            gitlab_client = GitLabClient(user.gitlab_url, user.access_token)
            posted_count = 0

            # 发布确认的评论到GitLab
            for issue_id in issue_ids:
                issue = self._get_issue_by_id(issue_id)
                if issue and issue['comment_status'] == 'confirmed':
                    success = gitlab_client.add_mr_comment(
                        review['project_id'],
                        review['mr_iid'],
                        issue['comment_text'],
                        issue['file_path'],
                        issue['line_number']
                    )

                    if success:
                        self.db.update_comment_gitlab_id(issue_id, "posted")
                        posted_count += 1

            return {
                'success': True,
                'confirmed_count': confirmed_count,
                'posted_count': posted_count
            }

        except Exception as e:
            self.logger.error(f"Error bulk confirming comments: {e}")
            return {'success': False, 'error': str(e)}

    def _get_issue_by_id(self, issue_id: int) -> Optional[Dict]:
        """根据ID获取问题详情"""
        conn = self.db.db_path
        import sqlite3
        conn = sqlite3.connect(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM issues WHERE id = ?', (issue_id,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def _get_file_content_from_diff(self, diff: str) -> str:
        """从diff中提取新文件内容"""
        lines = diff.split('\n')
        content_lines = []

        for line in lines:
            if line.startswith('+') and not line.startswith('+++'):
                content_lines.append(line[1:])  # 去掉+号
            elif not line.startswith('-') and not line.startswith('@@') and not line.startswith('\\'):
                if not line.startswith('+++') and not line.startswith('---'):
                    content_lines.append(line)

        return '\n'.join(content_lines)

    def _extract_changed_lines(self, diff: str) -> List[int]:
        """从diff中提取变更的行号"""
        lines = diff.split('\n')
        changed_lines = []
        current_line = 0

        for line in lines:
            if line.startswith('@@'):
                # 解析行号范围
                import re
                match = re.search(r'@@ -\d+,?\d* \+(\d+),?\d* @@', line)
                if match:
                    current_line = int(match.group(1)) - 1
            elif line.startswith('+') and not line.startswith('+++'):
                current_line += 1
                changed_lines.append(current_line)
            elif not line.startswith('-') and not line.startswith('\\'):
                if not line.startswith('+++') and not line.startswith('---') and not line.startswith('@@'):
                    current_line += 1

        return changed_lines

    def _group_issues_by_severity(self, issues: List[CodeIssue]) -> Dict[str, int]:
        """按严重程度分组问题"""
        severity_counts = {'error': 0, 'warning': 0, 'info': 0}
        for issue in issues:
            # 检查issue是字典还是对象
            if isinstance(issue, dict):
                severity = issue.get('severity', 'info')
            else:
                severity = getattr(issue, 'severity', 'info')

            if severity in severity_counts:
                severity_counts[severity] += 1
        return severity_counts

    def _group_issues_by_category(self, issues: List[CodeIssue]) -> Dict[str, int]:
        """按类别分组问题"""
        category_counts = {}
        for issue in issues:
            # 检查issue是字典还是对象
            if isinstance(issue, dict):
                category = issue.get('category', 'general')
            else:
                category = getattr(issue, 'category', 'general')

            category_counts[category] = category_counts.get(category, 0) + 1
        return category_counts

    def validate_mr_url(self, mr_url: str) -> Tuple[bool, Optional[str]]:
        """验证MR URL格式"""
        import re
        pattern = r'https?://[^/]+/.+/-/merge_requests/\d+'
        if re.match(pattern, mr_url):
            return True, None
        else:
            return False, "MR URL格式不正确，应该类似：https://gitlab.com/group/project/-/merge_requests/123"

    def test_gitlab_connection(self, user_config: UserConfig) -> Tuple[bool, Optional[str]]:
        """测试GitLab连接"""
        try:
            gitlab_client = GitLabClient(user_config.gitlab_url, user_config.access_token)

            # 尝试获取用户信息
            import requests
            url = f"{user_config.gitlab_url}/api/v4/user"
            headers = {'Authorization': f'Bearer {user_config.access_token}'}
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return True, None
            else:
                return False, f"GitLab连接失败: {response.status_code} - {response.text}"

        except Exception as e:
            return False, f"连接测试失败: {str(e)}"

    def _get_full_file_content(self, gitlab_client: GitLabClient, project_id: str, file_path: str, branch: str = 'main') -> Optional[str]:
        """获取完整的源文件内容"""
        try:
            import requests

            # 使用GitLab API获取文件内容
            url = f"{gitlab_client.gitlab_url}/api/v4/projects/{project_id}/repository/files/{file_path.replace('/', '%2F')}/raw"
            params = {'ref': branch}
            headers = gitlab_client.headers

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.text
            else:
                self.logger.warning(f"Failed to get file content for {file_path}: {response.status_code}")
                return None

        except Exception as e:
            self.logger.warning(f"Error getting file content for {file_path}: {e}")
            return None

    # ============ 进度管理方法 ============

    def _init_progress(self, review_id: int, total_files: int):
        """初始化审查进度"""
        self.db.init_review_progress(review_id, total_files)
        self.logger.info(f"Initialized progress for review {review_id} with {total_files} files")

    def _update_progress(self, review_id: int, status: str, processed_files: int, total_issues: int, current_file: str = None):
        """更新审查进度"""
        self.db.update_review_progress(review_id, status, processed_files, total_issues, current_file)
        self.logger.info(f"Progress updated for review {review_id}: {processed_files} files processed, {total_issues} issues, current: {current_file}")

    def get_review_progress(self, review_id: int) -> Optional[Dict]:
        """获取审查进度"""
        # 首先从进度表获取
        progress = self.db.get_review_progress(review_id)
        if progress:
            self.logger.info(f"Retrieved progress for review {review_id}: {progress}")
            return progress

        # 如果进度表中没有，检查审查记录状态
        review = self.db.get_review_record(review_id)
        if review:
            self.logger.info(f"No progress record found, using review status: {review['status']}")
            # 根据数据库状态构造进度信息
            if review['status'] == 'completed':
                return {
                    'status': 'completed',
                    'total_files': review.get('total_files_analyzed', 0),
                    'processed_files': review.get('total_files_analyzed', 0),
                    'total_issues': review.get('total_issues_found', 0),
                    'current_file': None
                }
            elif review['status'] == 'failed':
                return {
                    'status': 'failed',
                    'total_files': 0,
                    'processed_files': 0,
                    'total_issues': 0,
                    'current_file': None
                }
            elif review['status'] == 'pending':
                # 对于pending状态，返回正在准备的状态
                return {
                    'status': 'preparing',
                    'total_files': 0,  # 显示为0直到计算出真实数量
                    'processed_files': 0,
                    'total_issues': 0,
                    'current_file': None
                }

        return None

    def get_review_final_result(self, review_id: int) -> Optional[Dict]:
        """获取审查最终结果"""
        review = self.db.get_review_record(review_id)
        if not review:
            return None

        if review['status'] != 'completed':
            return None

        # 获取待确认评论数量
        pending_comments = self.db.get_pending_comments(review_id)

        # 构造结果数据
        result = {
            'review_id': review_id,
            'pending_comments_count': len(pending_comments),
            'mr_info': {
                'title': review.get('mr_title'),
                'author': review.get('mr_author'),
                'source_branch': review.get('source_branch'),
                'target_branch': review.get('target_branch'),
                'web_url': review.get('mr_url')  # 简化处理，实际应该构造web_url
            },
            'analysis_summary': {
                'total_files_analyzed': review.get('total_files_analyzed', 0),
                'total_issues_found': review.get('total_issues_found', 0),
                'issues_by_severity': {
                    'error': review.get('error_count', 0),
                    'warning': review.get('warning_count', 0),
                    'info': review.get('info_count', 0)
                }
            }
        }

        # 清理进度记录
        self.db.delete_review_progress(review_id)

        return result