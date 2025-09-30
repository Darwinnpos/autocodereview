# -*- coding: utf-8 -*-
import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .gitlab_client import GitLabClient
from .comment_generator import CommentGenerator
from .ai_analyzer import AICodeAnalyzer, AIAnalysisContext, CodeIssue
# UserConfig和UserConfigManager已废弃，现在使用AuthDatabase
from ..models.review import ReviewDatabase
from ..models.auth import AuthDatabase
import threading


class ReviewService:
    def __init__(self, config_manager=None, db_path: str = "reviews.db"):
        # config_manager参数已废弃，保留用于向后兼容
        self.db = ReviewDatabase(db_path)
        self.auth_db = AuthDatabase()
        self.logger = self._setup_logger()
        # 进度跟踪存储 (内存中临时存储)
        self._progress_storage = {}
        self._progress_lock = threading.Lock()
        # 用于跟踪可取消的审查进程
        self._cancellation_flags = {}
        self._cancellation_lock = threading.Lock()

    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger(f'ReviewService.{id(self)}')  # 使用实例ID避免重复
        logger.setLevel(logging.INFO)

        # 检查是否已经有handler，避免重复添加
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            # 防止日志向上级logger传播，避免重复
            logger.propagate = False

        return logger

    def create_review_record(self, username: str, mr_url: str) -> int:
        """创建审查记录并返回review_id"""
        try:
            self.logger.info(f"create_review_record called with username: {username}, mr_url: {mr_url}")

            # 获取用户信息
            user = self.auth_db.get_user_by_username(username)
            self.logger.info(f"Found user: {user.username if user else 'None'} (ID: {user.id if user else 'None'})")
            if user is None:
                self.logger.error("User not found")
                raise ValueError("用户信息错误：未找到用户账户，请重新登录")

            # 获取MR基本信息 - 从AuthDatabase获取最新配置
            if not user.gitlab_url or not user.access_token:
                self.logger.error("GitLab config not found in user profile")
                raise ValueError("配置错误：请在个人资料中配置GitLab连接信息（URL和访问令牌）")

            self.logger.info(f"GitLab URL from user profile: {user.gitlab_url}")

            # 创建临时配置对象用于兼容性
            class TempConfig:
                def __init__(self, gitlab_url, access_token, reviewer_name):
                    self.gitlab_url = gitlab_url
                    self.access_token = access_token
                    self.reviewer_name = reviewer_name

            user_config = TempConfig(user.gitlab_url, user.access_token, user.reviewer_name or "AutoCodeReview")

            self.logger.info("Creating GitLab client...")
            try:
                gitlab_client = GitLabClient(user_config.gitlab_url, user_config.access_token)
            except Exception as e:
                self.logger.error(f"Failed to create GitLab client: {e}")
                raise ValueError(f"GitLab连接失败：无法连接到GitLab服务器，请检查URL和访问令牌配置 - {str(e)}")

            self.logger.info("Parsing MR URL...")
            try:
                project_path, project_id, mr_iid = gitlab_client.parse_mr_url(mr_url)
                self.logger.info(f"Parsed MR URL - project_path: {project_path}, project_id: {project_id}, mr_iid: {mr_iid}")
            except Exception as e:
                self.logger.error(f"Failed to parse MR URL: {e}")
                raise ValueError(f"GitLab错误：无效的Merge Request URL格式 - {str(e)}")

            self.logger.info("Getting MR info...")
            try:
                mr_info = gitlab_client.get_mr_info(project_id, mr_iid)
                self.logger.info(f"MR info retrieved: {mr_info is not None}")
                if mr_info:
                    self.logger.info(f"MR info keys: {list(mr_info.keys()) if isinstance(mr_info, dict) else 'Not a dict'}")
            except Exception as e:
                self.logger.error(f"Failed to get MR info: {e}")
                if "401" in str(e) or "Unauthorized" in str(e):
                    raise ValueError("GitLab认证失败：访问令牌无效或已过期，请更新个人资料中的GitLab访问令牌")
                elif "403" in str(e) or "Forbidden" in str(e):
                    raise ValueError("GitLab权限不足：您没有权限访问该项目或Merge Request")
                elif "404" in str(e) or "Not Found" in str(e):
                    raise ValueError("GitLab资源未找到：项目或Merge Request不存在，请检查URL是否正确")
                else:
                    raise ValueError(f"GitLab API错误：无法获取Merge Request信息 - {str(e)}")

            if not mr_info:
                raise ValueError("GitLab错误：无法获取Merge Request详细信息，请检查URL和权限")

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

            try:
                review_id = self.db.create_review_record(review_data)
                self.logger.info(f"Created review record with ID: {review_id}")
                if not review_id:
                    raise ValueError("数据库错误：无法创建审查记录，请联系系统管理员")
                return review_id
            except Exception as db_e:
                self.logger.error(f"Database error creating review record: {db_e}")
                raise ValueError(f"数据库错误：创建审查记录失败 - {str(db_e)}")

        except ValueError as ve:
            # ValueError包含了我们自定义的用户友好错误信息
            self.logger.error(f"Error creating review record: {ve}")
            raise ve
        except Exception as e:
            self.logger.error(f"Unexpected error creating review record: {e}")
            raise ValueError(f"系统错误：创建审查记录时发生未知错误 - {str(e)}")

    def perform_review(self, username: str, mr_url: str, review_id: int = None) -> Dict:
        """执行完整的代码审查流程"""
        try:
            # 初始化取消标志
            if review_id:
                with self._cancellation_lock:
                    self._cancellation_flags[review_id] = False

            # 1. 获取用户信息（重新获取以确保是最新配置）
            self.logger.info(f"Starting code review for user {username}, MR: {mr_url}")
            user = self.auth_db.get_user_by_username(username)
            self.logger.info(f"User GitLab URL in perform_review: {user.gitlab_url if user else 'User not found'}")

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

            # 创建临时配置对象（替代废弃的UserConfig）
            class TempUserConfig:
                def __init__(self, user_id, gitlab_url, access_token, reviewer_name):
                    self.user_id = user_id
                    self.gitlab_url = gitlab_url
                    self.access_token = access_token
                    self.reviewer_name = reviewer_name

            user_config = TempUserConfig(
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

            if not user.ai_api_url:
                error_msg = 'AI API URL未配置，无法进行代码分析'
                if review_id:
                    self.db.fail_review_record(review_id, error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': 'AI_CONFIG_ERROR',
                    'review_id': review_id
                }

            if not user.ai_model:
                error_msg = 'AI模型未配置，无法进行代码分析'
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
                'ai_model': user.ai_model,
                'review_severity_level': getattr(user, 'review_severity_level', 'standard')
            }
            ai_analyzer = AICodeAnalyzer(ai_config)
             
            # 验证AI模型是否可用
            try:
                if not ai_analyzer.validate_model_availability():
                    error_msg = f'AI模型 "{user.ai_model}" 不可用，请检查AI配置'
                    if review_id:
                        self.db.fail_review_record(review_id, error_msg)
                    return {
                        'success': False,
                        'error': error_msg,
                        'error_code': 'AI_MODEL_UNAVAILABLE',
                        'review_id': review_id
                    }
            except Exception as e:
                error_msg = f'AI模型验证失败: {str(e)}'
                if review_id:
                    self.db.fail_review_record(review_id, error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': 'AI_MODEL_VALIDATION_ERROR',
                    'review_id': review_id
                }
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
                # 检查是否被取消
                if self._is_review_cancelled(review_id):
                    self.logger.info(f"Review {review_id} was cancelled, stopping analysis")
                    self.db.cancel_review_record(review_id, "用户手动取消")
                    return {
                        'success': False,
                        'error': '审查已被用户取消',
                        'error_code': 'CANCELLED_BY_USER',
                        'review_id': review_id
                    }

                if change.get('deleted_file', False):
                    continue  # 跳过已删除的文件

                file_path = change.get('new_path') or change.get('old_path')
                if not file_path:
                    continue

                self.logger.info(f"Analyzing file: {file_path}")

                try:
                    # 获取变更的行号
                    diff_content = change.get('diff', '')
                    changed_lines = self._extract_changed_lines(diff_content)

                    # 添加详细的调试日志
                    diff_size = len(diff_content)
                    self.logger.info(f"Processing {file_path}: diff size = {diff_size} bytes, changed lines = {len(changed_lines)}")

                    if not changed_lines:
                        if diff_size > 0:
                            self.logger.warning(f"File {file_path} has diff content ({diff_size} bytes) but no changed lines found - possible large diff truncation")
                            # 对于有diff但没有解析到变更行的情况，可能是大文件导致的diff截断
                            if diff_size > 10000:  # 如果diff超过10KB，可能是大文件问题
                                analyzed_files.append({
                                    'file_path': file_path,
                                    'issues_count': 0,
                                    'issues': [],
                                    'ai_issues': 0,
                                    'skipped': True,
                                    'skip_reason': f'文件变更过大 (diff: {diff_size} bytes)，无法解析变更行，已跳过审查'
                                })
                                continue
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
                            mr_description=mr_info.get('description', ''),
                            review_config=user.review_config
                        )

                        # 调用AI分析
                        ai_issues = ai_analyzer.analyze_code_with_ai(ai_context)
                        if ai_issues:
                            self.logger.info(f"AI analysis found {len(ai_issues)} issues in {file_path}")

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
                        error_message = str(e)
                        # 检查是否是文件过大的错误
                        if "文件过大警告" in error_message or "超过AI模型token限制" in error_message:
                            # 文件过大，记录警告但继续处理其他文件
                            self.logger.warning(f"Skipping large file {file_path}: {e}")
                            # 添加到跳过文件列表，但不添加问题
                            analyzed_files.append({
                                'file_path': file_path,
                                'issues_count': 0,
                                'issues': [],
                                'ai_issues': 0,
                                'skipped': True,
                                'skip_reason': error_message
                            })
                            continue
                        else:
                            # 其他AI分析错误，终止整个审查流程
                            self.logger.error(f"AI analysis failed for {file_path}: {e}")
                            error_msg = f'AI代码分析失败: {str(e)}'
                            if review_id:
                                self.db.fail_review_record(review_id, error_msg)
                            return {
                                'success': False,
                                'error': error_msg,
                                'error_code': 'AI_ANALYSIS_FAILED',
                                'review_id': review_id,
                                'failed_file': file_path
                            }

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

            # 统计跳过的文件
            skipped_files = [f for f in analyzed_files if f.get('skipped', False)]

            # 7. 完成审查记录
            analysis_summary = {
                'total_files_analyzed': len(analyzed_files),
                'total_files_skipped': len(skipped_files),
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
                    'total_files_skipped': len(skipped_files),
                    'total_issues_found': len(all_issues),
                    'issues_by_severity': self._group_issues_by_severity(all_issues),
                    'issues_by_category': self._group_issues_by_category(all_issues),
                    'skipped_files': [{'file_path': f['file_path'], 'skip_reason': f['skip_reason']}
                                    for f in skipped_files]
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

    def get_pending_comments(self, review_id: int, include_context: bool = False) -> List[Dict]:
        """获取待确认的评论"""
        pending_comments = self.db.get_pending_comments(review_id)

        # 如果不需要代码上下文，直接返回
        if not include_context:
            return pending_comments

        # 获取审查信息以获取项目路径
        review = self.db.get_review_record(review_id)
        if not review:
            return pending_comments

        # 为每个评论添加代码上下文
        for comment in pending_comments:
            try:
                # 获取代码上下文（前后5行）
                code_context = self._get_code_context_for_review(
                    review,
                    comment['file_path'],
                    comment['line_number']
                )
                comment['code_context'] = code_context
            except Exception as e:
                self.logger.warning(f"Failed to get code context for {comment['file_path']}:{comment['line_number']}: {e}")
                comment['code_context'] = None

        return pending_comments

    def get_comment_code_context(self, review_id: int, issue_id: int) -> Dict:
        """获取单个评论的代码上下文"""
        try:
            # 获取问题详情
            issue = self._get_issue_by_id(issue_id)
            if not issue or issue['review_id'] != review_id:
                return None

            # 获取审查信息
            review = self.db.get_review_record(review_id)
            if not review:
                return None

            # 获取代码上下文
            return self._get_code_context_for_review(
                review,
                issue['file_path'],
                issue['line_number']
            )

        except Exception as e:
            self.logger.error(f"Error getting code context for comment {issue_id}: {e}")
            return None

    def _get_code_context_for_review(self, review: Dict, file_path: str, line_number: int, context_lines: int = 5) -> Dict:
        """为指定审查获取代码上下文"""
        try:
            # 获取用户配置 - 尝试不同的方法获取用户
            user = None
            if review['user_id'].isdigit():
                # 如果是数字，作为用户ID查询
                user = self.auth_db.get_user_by_id(int(review['user_id']))
            else:
                # 如果是字符串，作为用户名查询
                user = self.auth_db.get_user_by_username(review['user_id'])

            if not user or not user.gitlab_url or not user.access_token:
                self.logger.warning(f"User or GitLab config missing for user: {review['user_id']}")
                return None

            # 创建GitLab客户端
            gitlab_client = GitLabClient(user.gitlab_url, user.access_token)

            # 获取文件内容
            file_content = gitlab_client.get_file_content(
                review['project_id'],
                file_path,
                review['source_branch']
            )

            if not file_content:
                self.logger.warning(f"Could not get file content for {file_path}")
                return None

            # 分割文件内容为行
            lines = file_content.split('\n')

            # 计算上下文范围
            start_line = max(1, line_number - context_lines)
            end_line = min(len(lines), line_number + context_lines)
            target_index = line_number - 1  # 转换为0基索引

            # 验证目标行是否存在
            if target_index < 0 or target_index >= len(lines):
                self.logger.warning(f"Target line {line_number} out of range for file {file_path}")
                return None

            # 提取上下文行
            lines_before = []
            lines_after = []
            target_line = lines[target_index] if target_index < len(lines) else ''

            # 获取目标行之前的行
            for i in range(start_line - 1, target_index):
                if i >= 0 and i < len(lines):
                    lines_before.append({
                        'line_number': i + 1,
                        'content': lines[i]
                    })

            # 获取目标行之后的行
            for i in range(target_index + 1, min(len(lines), end_line)):
                lines_after.append({
                    'line_number': i + 1,
                    'content': lines[i]
                })

            return {
                'lines_before': lines_before,
                'target_line': {
                    'line_number': line_number,
                    'content': target_line
                },
                'lines_after': lines_after,
                'start_line_number': start_line,
                'end_line_number': end_line,
                'target_line_number': line_number,
                'file_path': file_path
            }

        except Exception as e:
            self.logger.error(f"Error getting code context for review: {e}")
            return None

    def _get_code_context(self, mr_url: str, file_path: str, line_number: int, context_lines: int = 5) -> Dict:
        """获取指定文件行的代码上下文"""
        try:
            # 清理MR URL，移除可能的/diffs后缀
            clean_mr_url = mr_url.rstrip('/diffs')

            # 从reviews表中获取用户信息
            review = self.db.get_review_by_mr_url(clean_mr_url)
            if not review:
                # 如果找不到，尝试原始URL
                review = self.db.get_review_by_mr_url(mr_url)
                if not review:
                    return None

            # 获取用户配置
            user = self.auth_db.get_user_by_username(review['user_id'])
            if not user or not user.gitlab_url or not user.access_token:
                return None

            # 创建GitLab客户端
            gitlab_client = GitLabClient(user.gitlab_url, user.access_token)

            # 获取文件内容
            file_content = gitlab_client.get_file_content(
                review['project_id'],
                file_path,
                review['source_branch']
            )

            if not file_content:
                return None

            # 分割文件内容为行
            lines = file_content.split('\n')

            # 计算上下文范围
            start_line = max(1, line_number - context_lines)
            end_line = min(len(lines), line_number + context_lines)
            target_index = line_number - 1  # 转换为0基索引

            # 验证目标行是否存在
            if target_index < 0 or target_index >= len(lines):
                return None

            # 提取上下文行
            lines_before = []
            lines_after = []
            target_line = lines[target_index] if target_index < len(lines) else ''

            # 获取目标行之前的行
            for i in range(start_line - 1, target_index):
                if i >= 0 and i < len(lines):
                    lines_before.append({
                        'line_number': i + 1,
                        'content': lines[i]
                    })

            # 获取目标行之后的行
            for i in range(target_index + 1, min(len(lines), end_line)):
                lines_after.append({
                    'line_number': i + 1,
                    'content': lines[i]
                })

            return {
                'lines_before': lines_before,
                'target_line': {
                    'line_number': line_number,
                    'content': target_line
                },
                'lines_after': lines_after,
                'start_line_number': start_line,
                'end_line_number': end_line,
                'target_line_number': line_number,
                'file_path': file_path
            }

        except Exception as e:
            self.logger.error(f"Error getting code context: {e}")
            return None

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

                # 从数据库获取用户配置 (user_id存储的是用户名)
                user = self.auth_db.get_user_by_username(review['user_id'])
                if not user:
                    self.logger.error(f"User not found for username: {review['user_id']}")
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
                    # 更新审查记录中的comments_posted计数
                    issue = self._get_issue_by_id(issue_id)
                    if issue:
                        self.db.update_comments_posted_count(issue['review_id'], 1)
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

            # 从数据库获取用户配置 (user_id存储的是用户名)
            user = self.auth_db.get_user_by_username(review['user_id'])
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

            # 更新审查记录中的comments_posted计数
            if posted_count > 0:
                self.db.update_comments_posted_count(review_id, posted_count)

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

    def test_gitlab_connection(self, user_config) -> Tuple[bool, Optional[str]]:
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
            # 降低日志级别，减少频繁查询的日志输出
            self.logger.debug(f"Retrieved progress for review {review_id}: {progress}")
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
                    'current_file': None,
                    'error_message': review.get('error_message')  # 添加具体的错误信息
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

    def cancel_review(self, review_id: int) -> bool:
        """取消正在进行的审查"""
        try:
            # 获取审查记录
            review = self.db.get_review_record(review_id)
            if not review:
                self.logger.error(f"Review {review_id} not found for cancellation")
                return False

            # 检查状态是否允许取消
            if review['status'] in ['completed', 'failed', 'cancelled']:
                self.logger.warning(f"Cannot cancel review {review_id} with status {review['status']}")
                return False

            # 设置取消标志
            with self._cancellation_lock:
                self._cancellation_flags[review_id] = True

            # 更新数据库状态
            success = self.db.cancel_review_record(review_id, "用户手动取消")

            if success:
                # 清理进度记录
                self.db.delete_review_progress(review_id)
                self.logger.info(f"Review {review_id} successfully cancelled")

                # 清理取消标志
                with self._cancellation_lock:
                    self._cancellation_flags.pop(review_id, None)

                return True
            else:
                self.logger.error(f"Failed to cancel review {review_id} in database")
                return False

        except Exception as e:
            self.logger.error(f"Error cancelling review {review_id}: {e}")
            return False

    def _is_review_cancelled(self, review_id: int) -> bool:
        """检查审查是否被取消"""
        if not review_id:
            return False

        with self._cancellation_lock:
            return self._cancellation_flags.get(review_id, False)