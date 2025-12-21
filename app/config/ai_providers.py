# -*- coding: utf-8 -*-
"""
AI提供商配置模板
"""

AI_PROVIDERS = {
    'openai': {
        'name': 'OpenAI',
        'description': 'OpenAI官方API服务',
        'api_url': 'https://api.openai.com/v1',
        'models': [
            {'id': 'gpt-4-turbo-preview', 'name': 'GPT-4 Turbo', 'description': '最强大的模型，推荐用于代码审查'},
            {'id': 'gpt-4', 'name': 'GPT-4', 'description': '强大的模型，准确性高'},
            {'id': 'gpt-3.5-turbo', 'name': 'GPT-3.5 Turbo', 'description': '快速且经济的选择'},
        ],
        'default_model': 'gpt-3.5-turbo',
        'requires_api_key': True,
        'api_key_placeholder': 'sk-...',
        'docs_url': 'https://platform.openai.com/docs/api-reference'
    },
    'deepseek': {
        'name': 'DeepSeek',
        'description': 'DeepSeek AI服务',
        'api_url': 'https://api.deepseek.com/v1',
        'models': [
            {'id': 'deepseek-chat', 'name': 'DeepSeek Chat', 'description': '通用对话模型'},
            {'id': 'deepseek-coder', 'name': 'DeepSeek Coder', 'description': '专为代码优化的模型，推荐用于代码审查'},
        ],
        'default_model': 'deepseek-coder',
        'requires_api_key': True,
        'api_key_placeholder': 'sk-...',
        'docs_url': 'https://platform.deepseek.com/api-docs'
    },
    'openwebui': {
        'name': 'Open WebUI',
        'description': '自托管的OpenWebUI服务（兼容OpenAI API）',
        'api_url': 'http://localhost:8080/api/v1',  # 默认本地地址
        'models': [
            {'id': 'llama3', 'name': 'Llama 3', 'description': 'Meta开源模型'},
            {'id': 'mixtral', 'name': 'Mixtral', 'description': 'Mistral AI混合专家模型'},
            {'id': 'qwen', 'name': 'Qwen', 'description': '通义千问模型'},
            {'id': 'custom', 'name': '自定义模型', 'description': '在Open WebUI中配置的其他模型'},
        ],
        'default_model': 'llama3',
        'requires_api_key': False,  # Open WebUI可能不需要API key
        'api_key_placeholder': '留空或输入Open WebUI的API密钥',
        'custom_url_allowed': True,  # 允许自定义API URL
        'docs_url': 'https://docs.openwebui.com/'
    },
    'azure': {
        'name': 'Azure OpenAI',
        'description': 'Microsoft Azure OpenAI服务',
        'api_url': 'https://{resource-name}.openai.azure.com',  # 需要替换resource-name
        'models': [
            {'id': 'gpt-4', 'name': 'GPT-4', 'description': 'GPT-4模型'},
            {'id': 'gpt-35-turbo', 'name': 'GPT-3.5 Turbo', 'description': 'GPT-3.5 Turbo模型'},
        ],
        'default_model': 'gpt-35-turbo',
        'requires_api_key': True,
        'api_key_placeholder': '输入Azure OpenAI API密钥',
        'custom_url_allowed': True,
        'docs_url': 'https://learn.microsoft.com/azure/ai-services/openai/'
    },
    'custom': {
        'name': '自定义API',
        'description': '兼容OpenAI API格式的自定义服务',
        'api_url': '',  # 用户需要输入
        'models': [
            {'id': 'custom-model', 'name': '自定义模型', 'description': '输入您的模型ID'},
        ],
        'default_model': 'custom-model',
        'requires_api_key': True,
        'api_key_placeholder': '输入API密钥（如果需要）',
        'custom_url_allowed': True,
        'custom_model_allowed': True,
        'docs_url': ''
    }
}

def get_provider_config(provider_id: str) -> dict:
    """获取AI提供商配置"""
    return AI_PROVIDERS.get(provider_id, AI_PROVIDERS['custom'])

def get_all_providers() -> dict:
    """获取所有AI提供商"""
    return AI_PROVIDERS

def get_provider_models(provider_id: str) -> list:
    """获取AI提供商的可用模型列表"""
    provider = get_provider_config(provider_id)
    return provider.get('models', [])
