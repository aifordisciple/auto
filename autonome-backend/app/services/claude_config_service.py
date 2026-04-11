"""
Claude Code API 配置管理服务

负责读取和管理 Claude Code CLI 的 API 配置，支持多种 API 提供商。

支持的 API 提供商：
- 阿里云 GLM5: https://coding.dashscope.aliyuncs.com/apps/anthropic
- Anthropic Claude: https://api.anthropic.com
- OpenRouter: https://openrouter.ai/anthropic
- 自定义兼容端点

配置文件格式（settings.json）:
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "sk-sp-xxx",
    "ANTHROPIC_MODEL": "glm-5",
    "API_TIMEOUT_MS": "3000000"
  }
}
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.logger import log


class ClaudeConfigService:
    """
    Claude Code API 配置管理服务

    功能：
    - 读取项目目录下的 .claude/settings.json 配置
    - 提取环境变量用于执行时注入
    - 验证 API 连接有效性
    - 更新配置（管理员操作）

    配置文件位置：
    - 项目根目录: /opt/data1/public/software/systools/autonome/.claude/settings.json
    """

    # 项目根目录
    PROJECT_ROOT = Path("/opt/data1/public/software/systools/autonome")
    CLAUDE_DIR = PROJECT_ROOT / ".claude"
    SETTINGS_FILE = CLAUDE_DIR / "settings.json"

    # 默认配置
    DEFAULT_SETTINGS = {
        "env": {
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_MODEL": "claude-sonnet-4-6",
            "API_TIMEOUT_MS": "3000000"
        }
    }

    def __init__(self):
        """初始化配置服务，确保配置目录存在"""
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """确保配置目录和文件存在"""
        self.CLAUDE_DIR.mkdir(parents=True, exist_ok=True)

        if not self.SETTINGS_FILE.exists():
            self._create_default_settings()
            log.info(f"[ClaudeConfig] 创建默认配置文件: {self.SETTINGS_FILE}")

    def _create_default_settings(self) -> None:
        """创建默认配置文件"""
        with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.DEFAULT_SETTINGS, f, indent=2, ensure_ascii=False)

        # 设置文件权限（仅所有者可读写）
        os.chmod(self.SETTINGS_FILE, 0o600)

    def get_settings(self) -> Dict[str, Any]:
        """
        读取 settings.json 配置

        Returns:
            配置字典，包含 env 等字段
        """
        try:
            if not self.SETTINGS_FILE.exists():
                log.warning(f"[ClaudeConfig] 配置文件不存在，使用默认配置")
                return self.DEFAULT_SETTINGS.copy()

            with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            log.info(f"[ClaudeConfig] 读取配置成功: {self.SETTINGS_FILE}")
            return settings

        except json.JSONDecodeError as e:
            log.error(f"[ClaudeConfig] 配置文件 JSON 解析失败: {e}")
            return self.DEFAULT_SETTINGS.copy()
        except Exception as e:
            log.error(f"[ClaudeConfig] 读取配置文件失败: {e}")
            return self.DEFAULT_SETTINGS.copy()

    def get_env_vars(self) -> Dict[str, str]:
        """
        提取环境变量配置，用于执行时注入

        Returns:
            环境变量字典
        """
        settings = self.get_settings()
        env_vars = settings.get("env", {})

        # 转换为字符串类型（确保类型正确）
        return {k: str(v) for k, v in env_vars.items()}

    def get_api_config(self) -> Dict[str, str]:
        """
        获取 API 核心配置（用于显示和验证）

        Returns:
            API 配置字典，包含 base_url, model 等
        """
        env_vars = self.get_env_vars()

        return {
            "base_url": env_vars.get("ANTHROPIC_BASE_URL", ""),
            "model": env_vars.get("ANTHROPIC_MODEL", ""),
            "small_fast_model": env_vars.get("ANTHROPIC_SMALL_FAST_MODEL", ""),
            "timeout_ms": env_vars.get("API_TIMEOUT_MS", "3000000"),
            "has_auth_token": "ANTHROPIC_AUTH_TOKEN" in env_vars
        }

    def update_settings(self, settings: Dict[str, Any]) -> bool:
        """
        更新配置文件

        Args:
            settings: 新的配置字典

        Returns:
            是否更新成功
        """
        try:
            # 备份原配置
            if self.SETTINGS_FILE.exists():
                backup_path = self.SETTINGS_FILE.with_suffix('.json.bak')
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(backup_content)

            # 写入新配置
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)

            # 确保文件权限
            os.chmod(self.SETTINGS_FILE, 0o600)

            log.info(f"[ClaudeConfig] 配置更新成功")
            return True

        except Exception as e:
            log.error(f"[ClaudeConfig] 更新配置失败: {e}")
            return False

    def update_env_var(self, key: str, value: str) -> bool:
        """
        更新单个环境变量

        Args:
            key: 环境变量名
            value: 环境变量值

        Returns:
            是否更新成功
        """
        settings = self.get_settings()
        if "env" not in settings:
            settings["env"] = {}

        settings["env"][key] = value
        return self.update_settings(settings)

    def delete_env_var(self, key: str) -> bool:
        """
        删除单个环境变量

        Args:
            key: 环境变量名

        Returns:
            是否删除成功
        """
        settings = self.get_settings()
        if "env" in settings and key in settings["env"]:
            del settings["env"][key]
            return self.update_settings(settings)
        return True

    async def validate_connection(self) -> Dict[str, Any]:
        """
        验证 API 连接是否有效

        Returns:
            验证结果字典，包含 success, message 等字段
        """
        import httpx

        env_vars = self.get_env_vars()
        base_url = env_vars.get("ANTHROPIC_BASE_URL", "")
        auth_token = env_vars.get("ANTHROPIC_AUTH_TOKEN", "")

        if not base_url:
            return {
                "success": False,
                "message": "未配置 ANTHROPIC_BASE_URL"
            }

        if not auth_token:
            return {
                "success": False,
                "message": "未配置 ANTHROPIC_AUTH_TOKEN"
            }

        try:
            # 发送简单的 API 请求验证连接
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 构建验证请求（使用 models 端点）
                # 注意：不同 API 提供商的端点可能不同
                models_url = base_url.rstrip('/') + '/models'

                response = await client.get(
                    models_url,
                    headers={
                        "x-api-key": auth_token,
                        "anthropic-version": "2023-06-01"
                    }
                )

                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "API 连接验证成功"
                    }
                elif response.status_code == 401:
                    return {
                        "success": False,
                        "message": "API 认证失败，请检查 Auth Token"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"API 返回错误: HTTP {response.status_code}"
                    }

        except httpx.ConnectError:
            return {
                "success": False,
                "message": f"无法连接到 API 端点: {base_url}"
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "API 连接超时"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"验证失败: {str(e)}"
            }

    def get_settings_file_path(self) -> Path:
        """获取配置文件路径"""
        return self.SETTINGS_FILE


# 全局单例
claude_config_service = ClaudeConfigService()