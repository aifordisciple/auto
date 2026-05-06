# 使用较新的 Python 官方 Slim 镜像 (包含 bash 等基础工具，适合跑沙箱)
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 python 缓冲 stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ✅ 从 Docker 官方镜像复制 Docker CLI（用于容器内执行 docker 命令）
COPY --from=docker:24.0.7-cli /usr/local/bin/docker /usr/local/bin/docker

# ✅ 配置清华 PyPI 镜像加速（国内环境）
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# 复制依赖文件
COPY requirements.txt .

# ✅ 使用 BuildKit 缓存挂载加速 pip 安装
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# 复制整个后端代码库
COPY . .

# 暴露 FastAPI 默认端口
EXPOSE 8000

# 默认启动命令 (如果是 Worker 则在 compose 中覆盖此命令)
# 启动时自动执行 alembic 迁移确保数据库结构最新
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
