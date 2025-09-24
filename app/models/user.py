# -*- coding: utf-8 -*-
import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class UserConfig:
    user_id: str
    gitlab_url: str
    access_token: str
    reviewer_name: str = "AutoCodeReview"
    add_labels: bool = True
    add_reviewer_signature: bool = True
    add_overall_rating: bool = True
    analysis_rules: Dict[str, Dict[str, bool]] = None
    custom_templates: List[Dict] = None
    add_context: Dict = None
    notification_settings: Dict = None
    created_at: str = None
    updated_at: str = None

    def __post_init__(self):
        if self.analysis_rules is None:
            self.analysis_rules = {
                'python': {'syntax': True, 'security': True, 'performance': True, 'style': True, 'logic': True},
                'javascript': {'syntax': True, 'security': True, 'performance': True, 'style': True, 'logic': True},
                'java': {'syntax': True, 'security': True, 'performance': True, 'style': True, 'logic': True},
                'cpp': {'syntax': True, 'security': True, 'performance': True, 'style': True, 'logic': True}
            }
        if self.custom_templates is None:
            self.custom_templates = []
        if self.add_context is None:
            self.add_context = {'severity_levels': ['error', 'warning'], 'categories': ['security', 'syntax']}
        if self.notification_settings is None:
            self.notification_settings = {'email_notifications': False}
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()


class UserConfigManager:
    def __init__(self, config_dir: str = "user_configs"):
        self.config_dir = config_dir
        os.makedirs(config_dir, exist_ok=True)

    def _get_config_file_path(self, user_id: str) -> str:
        return os.path.join(self.config_dir, f"{user_id}.json")

    def save_user_config(self, config: UserConfig) -> bool:
        try:
            config_file = self._get_config_file_path(config.user_id)
            config_dict = asdict(config)
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to save user config: {e}")
            return False

    def load_user_config(self, user_id: str) -> Optional[UserConfig]:
        try:
            config_file = self._get_config_file_path(user_id)
            if not os.path.exists(config_file):
                return None
            with open(config_file, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            return UserConfig(**config_dict)
        except Exception as e:
            print(f"Failed to load user config: {e}")
            return None

    def update_user_config(self, user_id: str, updates: Dict[str, Any]) -> bool:
        try:
            config = self.load_user_config(user_id)
            if config is None:
                return False
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            config.updated_at = datetime.now().isoformat()
            return self.save_user_config(config)
        except Exception as e:
            print(f"Failed to update user config: {e}")
            return False

    def delete_user_config(self, user_id: str) -> bool:
        try:
            config_file = self._get_config_file_path(user_id)
            if os.path.exists(config_file):
                os.remove(config_file)
            return True
        except Exception as e:
            print(f"Failed to delete user config: {e}")
            return False

    def validate_config(self, config: UserConfig) -> List[str]:
        errors = []
        if not config.user_id:
            errors.append("用户ID不能为空")
        if not config.gitlab_url:
            errors.append("GitLab URL不能为空")
        if not config.access_token:
            errors.append("访问令牌不能为空")
        return errors