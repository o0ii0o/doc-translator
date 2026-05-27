"""配置加载与环境变量解析"""

import os
import re
from pathlib import Path
from typing import Optional

import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def load_config(config_path: Optional[Path] = None) -> dict:
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def resolve_env_value(value: str) -> str:
    """将 ${VAR_NAME} 替换为对应环境变量的值"""

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return _ENV_PATTERN.sub(replacer, value)


def get_llm_api_key(llm_config: dict) -> str:
    """获取 LLM API Key，优先级：环境变量 > config 中的值（支持 ${VAR}）"""
    for env_name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(env_name):
            return os.environ[env_name]

    api_key = llm_config.get("api_key", "")
    if api_key:
        api_key = resolve_env_value(str(api_key))

    if api_key and not api_key.startswith("${"):
        return api_key

    raise ValueError(
        "未设置有效的 LLM API Key。请在 PowerShell 中执行：\n"
        '  $env:DEEPSEEK_API_KEY = "sk-xxx"   # 使用 DeepSeek 时\n'
        '  或 $env:OPENAI_API_KEY = "sk-xxx"  # 使用 OpenAI 时'
    )


def get_mineru_token(mineru_config: dict) -> str:
    """获取 MinerU API Token"""
    if os.environ.get("MINERU_API_KEY"):
        return os.environ["MINERU_API_KEY"]

    token = mineru_config.get("api_token", "")
    if token:
        token = resolve_env_value(str(token))

    if token and not token.startswith("${"):
        return token

    raise ValueError(
        "未设置 MinerU API Token。请在 PowerShell 中执行：\n"
        '  $env:MINERU_API_KEY = "你的Token"'
    )
