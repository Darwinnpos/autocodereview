"""
版本信息管理模块
"""
import os
from pathlib import Path

def get_version():
    """获取应用版本号"""
    try:
        # 获取项目根目录
        root_dir = Path(__file__).parent.parent
        version_file = root_dir / "VERSION"

        if version_file.exists():
            with open(version_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        else:
            return "unknown"
    except Exception:
        return "unknown"

def get_build_info():
    """获取构建信息"""
    try:
        import subprocess
        # 获取Git提交信息
        commit_hash = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()

        # 获取分支信息
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()

        return {
            'commit': commit_hash,
            'branch': branch
        }
    except Exception:
        return {
            'commit': 'unknown',
            'branch': 'unknown'
        }

def get_full_version_info():
    """获取完整版本信息"""
    version = get_version()
    build_info = get_build_info()

    return {
        'version': version,
        'commit': build_info['commit'],
        'branch': build_info['branch'],
        'full_version': f"{version}+{build_info['commit']}"
    }

# 导出版本常量
__version__ = get_version()