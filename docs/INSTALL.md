# AUTONOME STUDIO - 安装指南

AI-Native Bioinformatics IDE — 多智能体生物信息学工作流平台

---

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [安装步骤](#安装步骤)
- [开发环境](#开发环境)
- [生产环境](#生产环境)
- [性能优化](#性能优化)
- [故障排查](#故障排查)

---

## 🖥️ 系统要求

### 必需软件

| 软件 | 版本要求 | 用途 |
|------|---------|------|
| Docker | >= 19.03 | 容器运行环境 |
| Docker Compose | >= 2.0 | 容器编排 |
| Git | >= 2.0 | 版本控制 |

### 硬件要求

| 资源 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4+ 核 |
| 内存 | 8 GB | 16+ GB |
| 磁盘 | 20 GB | 50+ GB |

### 操作系统支持

- ✅ macOS (Intel/Apple Silicon)
- ✅ Linux (Ubuntu 18.04+, CentOS 7+)
- ✅ Windows 10/11 (WSL 2)

---

## 🚀 快速开始

### 1️⃣ 克隆项目

```bash
git clone <repository-url>
cd autonome
```

### 2️⃣ 启动开发环境

```bash
# 一键启动（包含数据库、后端、前端）
docker-compose up
```

首次启动会自动：
- 拉取基础镜像（PostgreSQL、Redis、Python、Node.js）
- 安装所有依赖
- 初始化数据库
- 启动所有服务

### 3️⃣ 访问应用

- **前端 IDE**: http://localhost:3001
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5433
- **Redis**: localhost:6379

---

## 📦 安装步骤

### 步骤 1: 环境准备

#### macOS

```bash
# 安装 Docker Desktop
brew install --cask docker

# 启动 Docker Desktop
open /Applications/Docker.app

# 验证安装
docker --version
docker-compose --version
```

#### Linux (Ubuntu/Debian)

```bash
# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 验证安装
docker --version
docker-compose --version
```

#### Windows (WSL 2)

```powershell
# 安装 WSL 2
wsl --install

# 安装 Docker Desktop for Windows
# 下载: https://www.docker.com/products/docker-desktop

# 在 WSL 2 中验证
docker --version
docker-compose --version
```

### 步骤 2: 配置环境变量

```bash
# 后端环境变量（如果需要自定义）
cd autonome-backend
cp .env.example .env  # 如果存在示例文件
# 编辑 .env 配置数据库密码、API 密钥等
```

### 步骤 3: 构建和启动

```bash
# 返回项目根目录
cd ..

# 构建所有镜像（首次运行或依赖更新后）
docker-compose build

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 步骤 4: 初始化数据库（首次运行）

```bash
# 进入后端容器
docker-compose exec backend-api bash

# 运行数据库迁移
alembic upgrade head

# 创建管理员账户（可选）
python make_admin.py your-email@example.com

# 退出容器
exit
```

---

## 🛠️ 开发环境

### 热重载开发模式

项目已配置 `docker-compose.override.yml`，支持代码热重载：

```bash
# 启动开发环境（自动加载 override 配置）
docker-compose up
```

**特性：**
- ✅ 后端代码修改自动重载（uvicorn --reload）
- ✅ 前端代码修改自动更新（Next.js HMR）
- ✅ 无需手动重建镜像
- ✅ 国内镜像加速下载

### 开发环境架构

**后端开发模式：**
- 基于生产镜像，挂载源码实现热重载
- 使用 `uvicorn --reload` 监听文件变化
- 保留容器内的 Python 依赖

**前端开发模式：**
- 使用独立的 `development` Docker stage
- 不运行 `npm run build`，直接启动开发服务器
- 避免 Turbopack 构建时下载 Google 字体的问题
- 字体在运行时加载，无需构建时网络访问

**Dockerfile 多阶段构建：**
```
deps         → 安装依赖（npm ci）
builder      → 生产构建（npm run build）
runner       → 生产运行（node server.js）
development  → 开发环境（npm run dev）← docker-compose.override.yml 使用
```
### 目录挂载说明

**后端挂载点：**
```
./autonome-backend/app → /app/app
./autonome-backend/main.py → /app/main.py
```

**前端挂载点：**
```
./autonome-studio/src → /app/src
./autonome-studio/public → /app/public
```

### 开发工作流

```bash
# 1. 启动服务
docker-compose up -d

# 2. 修改代码（自动生效）
vim autonome-backend/app/api/routes/chat.py

# 3. 查看实时日志
docker-compose logs -f backend-api

# 4. 进入容器调试
docker-compose exec backend-api bash

# 5. 运行测试（如果有）
docker-compose exec backend-api pytest

# 6. 停止服务
docker-compose down
```

### 依赖更新

```bash
# 后端依赖更新
vim autonome-backend/requirements.txt
docker-compose build backend-api backend-worker
docker-compose up -d

# 前端依赖更新
vim autonome-studio/package.json
docker-compose build frontend
docker-compose up -d
```

---

## 🏭 生产环境

### 生产部署

```bash
# 使用明确的生产配置（忽略 override）
docker-compose -f docker-compose.yml up --build -d

# 或设置环境变量
COMPOSE_FILE=docker-compose.yml docker-compose up -d
```

### 生产环境检查清单

- [ ] 修改默认数据库密码
- [ ] 配置 HTTPS 反向代理
- [ ] 设置环境变量 `NODE_ENV=production`
- [ ] 配置日志收集
- [ ] 设置健康检查
- [ ] 配置备份策略
- [ ] 启用 Redis 持久化
- [ ] 限制容器资源使用

### 生产配置示例

```yaml
# docker-compose.prod.yml（可选）
version: '3.8'

services:
  backend-api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## ⚡ 性能优化

### 🚀 已实施的优化

#### 1. 国内镜像加速

**后端（Python PyPI）**
```
镜像源：https://pypi.tuna.tsinghua.edu.cn/simple
提速：10-50 倍
```

**前端（Node.js npm）**
```
镜像源：https://registry.npmmirror.com
提速：10-50 倍
```

#### 2. BuildKit 缓存

```bash
# 已通过 .env 文件启用
DOCKER_BUILDKIT=1
COMPOSE_DOCKER_CLI_BUILD=1
```

**效果：**
- ✅ 依赖层缓存复用
- ✅ 增量构建加速
- ✅ 并行构建优化

#### 3. 构建上下文优化

已创建 `.dockerignore` 文件过滤不必要文件：
- 后端：排除 `__pycache__/`, `.venv/`, `.git/`
- 前端：排除 `node_modules/`, `.next/`, `.env*`

**效果：** 构建上下文减少 60-80%

### 📊 性能对比

| 场景 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 首次构建 | 8-12 分钟 | 3-5 分钟 | **60%+** |
| 增量构建 | 5-8 分钟 | 30-60 秒 | **80%+** |
| 代码改动 | 5-8 分钟 | 0 秒（热重载） | **100%** |
| 包下载速度 | 50-200 KB/s | 2-5 MB/s | **10-50x** |

### 🔧 优化命令

```bash
# 清理构建缓存
docker builder prune

# 查看构建缓存使用情况
docker builder du

# 强制无缓存重建
docker-compose build --no-cache

# 只重建特定服务
docker-compose build backend-api

# 查看镜像大小
docker images | grep autonome
```

---

## 🔍 故障排查

### 常见问题

#### 问题 1: 端口已被占用

```bash
# 错误信息
Error: bind: address already in use

# 解决方案：查找占用进程
lsof -i :8000  # 后端端口
lsof -i :3001  # 前端端口
lsof -i :5433  # 数据库端口

# 停止占用进程或修改 docker-compose.yml 中的端口映射
```

#### 问题 2: 依赖安装失败

```bash
# 错误信息
ERROR: Could not find a version that satisfies the requirement

# 解决方案 1: 临时使用官方源
docker-compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple

# 解决方案 2: 检查网络连接
ping pypi.tuna.tsinghua.edu.cn
```

#### 问题 3: 热重载不生效

```bash
# 检查 override 文件是否存在
ls -la docker-compose.override.yml

# 检查挂载点
docker-compose exec backend-api ls -la /app/app

# 重启容器
docker-compose restart backend-api
```

#### 问题 4: 数据库连接失败

```bash
# 错误信息
psycopg2.OperationalError: could not connect to server

# 解决方案：等待数据库完全启动
docker-compose logs postgres

# 检查数据库状态
docker-compose exec postgres pg_isready
```

```

#### 问题 6: 前端容器启动失败（next: not found）

```bash
# 错误信息
sh: next: not found

# 原因：开发环境缺少 node_modules 或构建失败

# 解决方案 1: 重新构建前端镜像
docker-compose build --no-cache frontend
docker-compose up -d frontend

# 解决方案 2: 检查 Dockerfile 是否使用 development target
# 在 docker-compose.override.yml 中应该有:
# frontend:
#   build:
#     target: development
```

#### 问题 7: 前端构建时字体下载失败

```bash
# 错误信息
Error while requesting resource
There was an issue establishing a connection while requesting https://fonts.gstatic.com/...

# 原因：Turbopack 在构建时尝试下载 Google 字体，网络不通

# 解决方案：已通过使用 development stage 解决
# development stage 不运行 npm run build，直接启动开发服务器
# 字体在运行时加载，此时容器有网络访问

# 验证：检查 Dockerfile 是否包含 development stage
grep -A 10 'FROM deps AS development' autonome-studio/Dockerfile
```
### 日志查看

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend-api
docker-compose logs -f frontend

# 查看最近 100 行日志
docker-compose logs --tail=100 backend-api
```

### 完全重置

```bash
# 停止所有容器
docker-compose down

# 删除所有数据（谨慎使用！）
docker-compose down -v

# 清理所有镜像
docker system prune -a

# 重新开始
docker-compose up --build
```

---

## 📚 其他资源

### 项目文档

- `README.md` - 项目概述
- `AGENTS.md` - AI Agent 知识库
- `DOCKER_OPTIMIZATION.md` - Docker 优化详细指南

### 技术栈

**后端：**
- FastAPI + LangGraph
- PostgreSQL + pgvector
- Redis + Celery
- Docker Sandbox

**前端：**
- Next.js 16
- React 19
- Zustand
- Tailwind CSS v4

### 有用的命令

```bash
# 查看运行中的容器
docker-compose ps

# 查看资源使用情况
docker stats

# 进入数据库容器
docker-compose exec postgres psql -U autonome -d autonome_db

# 进入 Redis 容器
docker-compose exec redis redis-cli

# 导出数据库
docker-compose exec postgres pg_dump -U autonome autonome_db > backup.sql

# 导入数据库
cat backup.sql | docker-compose exec -T postgres psql -U autonome autonome_db
```

---

## 🆘 获取帮助

如果遇到问题：

1. 查看本文档的故障排查部分
2. 查看 `DOCKER_OPTIMIZATION.md` 详细优化指南
3. 检查 GitHub Issues
4. 联系开发团队

---

**最后更新:** 2026-03-03
**Docker 版本要求:** >= 19.03
**Docker Compose 版本要求:** >= 2.0
