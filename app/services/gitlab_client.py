# -*- coding: utf-8 -*-
import re
import requests
from typing import Dict, List, Optional, Tuple


class GitLabClient:
    def __init__(self, gitlab_url: str, access_token: str):
        self.gitlab_url = gitlab_url.rstrip('/')
        self.access_token = access_token
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

    def parse_mr_url(self, mr_url: str) -> Tuple[str, str, int]:
        """解析MR URL，提取项目路径和MR ID"""
        pattern = r'https?://[^/]+/(.+)/-/merge_requests/(\d+)'
        match = re.match(pattern, mr_url)
        if not match:
            raise ValueError("Invalid GitLab MR URL format")

        project_path = match.group(1)
        mr_iid = int(match.group(2))

        # 获取项目ID
        project_id = self._get_project_id(project_path)

        return project_path, project_id, mr_iid

    def _get_project_id(self, project_path: str) -> str:
        """根据项目路径获取项目ID"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_path.replace('/', '%2F')}"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            raise Exception(f"Failed to get project info: {response.text}")

        return str(response.json()['id'])

    def get_current_user(self) -> Dict:
        """获取当前用户信息"""
        url = f"{self.gitlab_url}/api/v4/user"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            raise Exception(f"Failed to get current user info: {response.text}")

        return response.json()

    def get_mr_info(self, project_id: str, mr_iid: int) -> Dict:
        """获取MR基本信息"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            raise Exception(f"Failed to get MR info: {response.text}")

        return response.json()

    def get_mr_changes(self, project_id: str, mr_iid: int) -> List[Dict]:
        """获取MR的文件变更"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/changes"
        print(f"DEBUG: Requesting MR changes from URL: {url}")
        print(f"DEBUG: Headers: {self.headers}")

        # 添加参数以获取完整的diff信息
        params = {
            'access_raw_diffs': 'true'  # 获取原始diff
        }

        response = requests.get(url, headers=self.headers, params=params)
        print(f"DEBUG: Response status: {response.status_code}")

        if response.status_code != 200:
            print(f"DEBUG: Response content: {response.text}")
            raise Exception(f"Failed to get MR changes (status {response.status_code}): {response.text}")

        response_data = response.json()
        changes = response_data.get('changes', [])
        print(f"DEBUG: Found {len(changes)} changes in MR")

        # 添加详细的diff调试信息
        for i, change in enumerate(changes):
            file_path = change.get('new_path') or change.get('old_path', 'unknown')
            diff_content = change.get('diff', '')
            print(f"DEBUG: Change {i}: file={file_path}, diff_size={len(diff_content)} bytes")
            if len(diff_content) == 0:
                print(f"DEBUG: No diff content for {file_path}")
            else:
                # 显示diff的前100个字符
                diff_preview = diff_content[:100].replace('\n', '\\n')
                print(f"DEBUG: Diff preview for {file_path}: {diff_preview}...")

        return changes

    def add_mr_comment(self, project_id: str, mr_iid: int, comment: str,
                      file_path: Optional[str] = None, line_number: Optional[int] = None) -> bool:
        """添加MR评论（支持行级评论）"""
        try:
            if file_path and line_number:
                # 添加行级评论（需要获取commit SHA）
                mr_info = self.get_mr_info(project_id, mr_iid)
                if not mr_info:
                    return False

                commit_sha = mr_info.get('sha') or mr_info.get('source_branch_sha')
                if not commit_sha:
                    print(f"DEBUG: Cannot get commit SHA for line comment, falling back to general comment")
                    # 如果无法获取commit SHA，添加一般性评论并注明文件和行号
                    comment = f"**{file_path}:{line_number}**\n\n{comment}"
                    url = f"{self.gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
                    data = {'body': comment}
                else:
                    # 添加行级评论
                    url = f"{self.gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/discussions"
                    data = {
                        'body': comment,
                        'position': {
                            'position_type': 'text',
                            'new_path': file_path,
                            'new_line': line_number,
                            'base_sha': mr_info.get('diff_refs', {}).get('base_sha'),
                            'start_sha': mr_info.get('diff_refs', {}).get('start_sha'),
                            'head_sha': mr_info.get('diff_refs', {}).get('head_sha')
                        }
                    }
            else:
                # 添加一般性MR评论
                url = f"{self.gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
                data = {'body': comment}

            print(f"DEBUG: Posting comment to URL: {url}")
            print(f"DEBUG: Comment data: {data}")

            response = requests.post(url, json=data, headers=self.headers)
            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response content: {response.text}")

            return response.status_code in [200, 201]

        except Exception as e:
            print(f"DEBUG: Error posting comment: {e}")
            return False

    def get_file_content(self, project_id: str, file_path: str, ref: str) -> Optional[str]:
        """获取文件内容"""
        try:
            # URL编码文件路径
            import urllib.parse
            encoded_path = urllib.parse.quote(file_path, safe='')

            url = f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/files/{encoded_path}/raw"
            params = {'ref': ref}

            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code == 200:
                return response.text
            else:
                print(f"Failed to get file content: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Error getting file content: {e}")
            return None