"""
Docker 沙箱配置 - 统一管理环境路径和挂载模式

核心设计：官方只读层 + 用户沙箱层

架构说明：
┌────────────────────────────────────────────────────────────────┐
│                    Docker 容器视图                              │
├────────────────────────────────────────────────────────────────┤
│  /opt/conda/                    [只读] 官方 Conda 环境          │
│    ├── bin/                     (python, R, conda...)         │
│    ├── lib/python3.10/site-packages/  (预装 Python 包)         │
│    └── lib/R/library/           (预装 R 包)                    │
├────────────────────────────────────────────────────────────────┤
│  /app/user_packages/user_{id}/  [读写] 用户沙箱层              │
│    ├── python/                  (pip install --target)        │
│    ├── r/                       (install.packages)            │
│    ├── conda_envs/              用户 Conda 环境                │
│    └── conda_pkgs/              用户 Conda 包缓存              │
└────────────────────────────────────────────────────────────────┘
"""

import os
from typing import Dict, Optional

# ==========================================
# ✨ Docker Socket 配置
# ==========================================

# Docker 守护进程 Unix Socket 路径
DOCKER_SOCKET = "/var/run/docker.sock"

# ==========================================
# ✨ Conda 环境配置
# ==========================================

# Conda 宿主机路径
CONDA_HOST_PATH = "/opt/data1/public/software/systools/autonome/autonome_conda"

# Conda 容器内路径
CONDA_CONTAINER_PATH = "/opt/conda"

# ✨ Conda 挂载模式：只读，保护官方环境
CONDA_MOUNT_MODE = "ro"

# ==========================================
# ✨ 用户包目录配置
# ==========================================

# 用户包宿主机路径
USER_PACKAGES_HOST_PATH = "/opt/data1/public/software/systools/autonome/uploads/user_packages"

# 用户包容器内路径
USER_PACKAGES_CONTAINER_PATH = "/app/user_packages"

# 用户级目录名
USER_PYTHON_DIRNAME = "python"
USER_R_DIRNAME = "r"
USER_CONDA_ENVS_DIRNAME = "conda_envs"
USER_CONDA_PKGS_DIRNAME = "conda_pkgs"

# ==========================================
# ✨ 其他挂载路径
# ==========================================

# SKILL 技能包目录
SKILLS_HOST_PATH = "/opt/data1/public/software/systools/autonome/autonome-backend/app/skills"
SKILLS_CONTAINER_PATH = "/app/skills"

# Biosource 生信脚本库
BIOSOURCE_HOST_PATH = "/opt/data1/public/software/systools/autonome/biosource"
BIOSOURCE_CONTAINER_PATH = "/app/biosource"

# 上传目录（容器侧路径已改为 /workspace）
UPLOAD_HOST_PATH = os.environ.get("HOST_UPLOAD_DIR", "/opt/data1/public/software/systools/autonome/uploads")
UPLOAD_CONTAINER_PATH = "/workspace"

# ==========================================
# ✨ 配额限制
# ==========================================

# 用户包最大数量
MAX_PACKAGES_PER_USER = 100

# 用户包最大空间（字节）
MAX_SIZE_PER_USER = 2 * 1024 * 1024 * 1024  # 2GB

# 用户 Conda 环境最大空间（字节）
MAX_CONDA_ENV_SIZE = 5 * 1024 * 1024 * 1024  # 5GB

# ==========================================
# ✨ 执行超时配置
# ==========================================

# 默认执行超时时间（秒）
DEFAULT_EXECUTION_TIMEOUT = 3600  # 1 小时


# ==========================================
# ✨ 便捷函数
# ==========================================

def get_user_package_paths(user_id: int) -> Dict[str, str]:
    """
    获取用户级包路径配置

    Args:
        user_id: 用户 ID

    Returns:
        包含所有用户级路径的字典
    """
    user_dir = f"{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"
    host_user_dir = f"{USER_PACKAGES_HOST_PATH}/user_{user_id}"

    return {
        # 容器内路径
        "user_dir": user_dir,
        "python_dir": f"{user_dir}/{USER_PYTHON_DIRNAME}",
        "r_dir": f"{user_dir}/{USER_R_DIRNAME}",
        "conda_envs_dir": f"{user_dir}/{USER_CONDA_ENVS_DIRNAME}",
        "conda_pkgs_dir": f"{user_dir}/{USER_CONDA_PKGS_DIRNAME}",

        # 宿主机路径
        "host_user_dir": host_user_dir,
        "host_python_dir": f"{host_user_dir}/{USER_PYTHON_DIRNAME}",
        "host_r_dir": f"{host_user_dir}/{USER_R_DIRNAME}",
        "host_conda_envs_dir": f"{host_user_dir}/{USER_CONDA_ENVS_DIRNAME}",
        "host_conda_pkgs_dir": f"{host_user_dir}/{USER_CONDA_PKGS_DIRNAME}",
    }


def get_container_mount_config(user_id: Optional[int] = None) -> Dict:
    """
    获取容器挂载配置

    Args:
        user_id: 用户 ID（可选）

    Returns:
        挂载配置字典
    """
    binds = [
        f"{UPLOAD_HOST_PATH}:{UPLOAD_CONTAINER_PATH}:rw",
        f"{CONDA_HOST_PATH}:{CONDA_CONTAINER_PATH}:{CONDA_MOUNT_MODE}",
        f"{SKILLS_HOST_PATH}:{SKILLS_CONTAINER_PATH}:ro",
        f"{BIOSOURCE_HOST_PATH}:{BIOSOURCE_CONTAINER_PATH}:ro",
    ]

    volumes = {
        UPLOAD_CONTAINER_PATH: {},
        CONDA_CONTAINER_PATH: {},
        SKILLS_CONTAINER_PATH: {},
        BIOSOURCE_CONTAINER_PATH: {},
    }

    if user_id:
        user_paths = get_user_package_paths(user_id)
        binds.append(f"{user_paths['host_user_dir']}:{user_paths['user_dir']}:rw")
        volumes[user_paths['user_dir']] = {}

    return {
        "binds": binds,
        "volumes": volumes,
    }


def get_environment_variables(user_id: Optional[int] = None) -> Dict[str, str]:
    """
    获取容器环境变量配置

    Args:
        user_id: 用户 ID（可选）

    Returns:
        环境变量字典
    """
    env = {
        "PATH": f"{CONDA_CONTAINER_PATH}/bin:/usr/local/bin:/usr/bin:/bin",
        "CONDA_PREFIX": CONDA_CONTAINER_PATH,
    }

    if user_id:
        user_paths = get_user_package_paths(user_id)

        # Python 用户包路径（优先级最高）
        env["PYTHONPATH"] = f"{user_paths['python_dir']}:{CONDA_CONTAINER_PATH}/lib/python3.10/site-packages"

        # R 用户包路径
        env["R_LIBS_USER"] = user_paths['r_dir']
        env["R_LIBS"] = f"{user_paths['r_dir']}:{CONDA_CONTAINER_PATH}/lib/R/library"

        # Conda 用户级环境
        env["CONDA_ENVS_PATH"] = user_paths['conda_envs_dir']
        env["CONDA_PKGS_DIRS"] = user_paths['conda_pkgs_dir']

    return env


def ensure_user_directories(user_id: int) -> None:
    """
    确保用户级目录存在

    Args:
        user_id: 用户 ID
    """
    import os

    user_paths = get_user_package_paths(user_id)

    # 创建宿主机上的用户目录
    for dir_key in ['host_python_dir', 'host_r_dir', 'host_conda_envs_dir', 'host_conda_pkgs_dir']:
        os.makedirs(user_paths[dir_key], exist_ok=True)