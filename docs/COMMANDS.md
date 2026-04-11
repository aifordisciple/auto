# AUTONOME STUDIO 命令参考与工作流

> **文档版本**: 1.0.0
> **更新日期**: 2026-03-21
> **适用范围**: 开发、测试、部署全流程

---

## 目录

1. [Docker 服务命令](#1-docker-服务命令)
2. [开发环境命令](#2-开发环境命令)
3. [数据库迁移命令](#3-数据库迁移命令)
4. [部署工作流详解](#4-部署工作流详解)
5. [auto_deploy.sh 使用说明](#5-auto_deploysh-使用说明)

---

## 1. Docker 服务命令

### 1.1 服务启动与停止

<command>
```bash
# 启动所有服务 (推荐方式)
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启所有服务
docker-compose down && docker-compose up -d
```
</command>

### 1.2 服务概览

| 服务名 | 容器名 | 端口 | 功能 |
|--------|--------|------|------|
| `backend-api` | `autonome-api` | 8000 | FastAPI 后端 |
| `frontend` | `autonome-web` | 3001 | Next.js 前端 |
| `postgres` | `autonome-postgres` | 5433 | PostgreSQL + pgvector |
| `redis` | `autonome-redis` | 6379 | Redis 缓存 |
| `backend-worker` | `autonome-worker` | - | Celery 异步任务 |

**访问地址**:
- 前端: http://localhost:3001
- API 文档: http://localhost:8000/docs

### 1.3 查看日志

<command>
```bash
# 查看后端日志 (最近 30 行)
docker logs autonome-api | tail -30

# 查看前端日志 (最近 30 行)
docker logs autonome-web | tail -30

# 实时跟踪日志
docker logs -f autonome-api

# 查看所有服务状态
docker-compose ps
```
</command>

### 1.4 进入容器调试

<command>
```bash
# 进入后端容器
docker-compose exec backend-api bash

# 进入数据库容器
docker-compose exec postgres psql -U autonome autonome_db

# 进入 Redis 容器
docker-compose exec redis redis-cli
```
</command>

---

## 2. 开发环境命令

### 2.1 后端本地开发

<command>
```bash
# 进入后端目录
cd autonome-backend

# 启动开发服务器 (热重载)
uvicorn main:app --reload --port 8000

# 启动开发服务器 (指定主机)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
</command>

### 2.2 前端本地开发

<command>
```bash
# 进入前端目录
cd autonome-studio

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 启动生产服务器
npm run start
```
</command>

### 2.3 环境变量配置

后端 `.env` 文件示例：

```env
DATABASE_URL=postgresql://autonome:password@localhost:5433/autonome_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-here
OPENAI_API_KEY=your-openai-api-key
```

前端 `.env.local` 文件示例：

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 3. 数据库迁移命令

### 3.1 Alembic 迁移流程

<command>
```bash
# 进入后端目录
cd autonome-backend

# 自动生成迁移文件 (检测模型变更)
alembic revision --autogenerate -m "描述变更内容"

# 执行迁移 (升级到最新版本)
alembic upgrade head

# 回滚上一个版本
alembic downgrade -1

# 查看迁移历史
alembic history

# 查看当前版本
alembic current
```
</command>

### 3.2 数据库管理

<command>
```bash
# 连接数据库
docker-compose exec postgres psql -U autonome autonome_db

# 列出所有表
\dt

# 查看表结构
\d table_name

# 退出
\q
```
</command>

---

## 4. 部署工作流详解

<critical>
**每次代码修改后必须遵循的工作流**

1. 执行开发任务
2. 状态验证和测试
3. 自动部署
</critical>

### 4.1 状态验证流程

<rule>
**每次代码修改完成后，必须执行**:

```bash
# 1. 重启 Docker 服务
docker-compose down && docker-compose up -d

# 2. 检查日志是否有错误
docker logs autonome-api | tail -30
docker logs autonome-web | tail -30

# 3. 设计和实施测试用例
# (根据修改内容编写测试)

# 4. 验证功能正常后，执行部署
./auto_deploy.sh -s "summary" -d "detailed description"
```
</rule>

### 4.2 验证检查清单

- [ ] Docker 服务启动无错误
- [ ] 后端 API 可访问 (http://localhost:8000/docs)
- [ ] 前端页面可访问 (http://localhost:3001)
- [ ] 数据库连接正常
- [ ] 修改的功能正常工作

---

## 5. auto_deploy.sh 使用说明

### 5.1 基本用法

<command>
```bash
# 基本格式
./auto_deploy.sh -s "简要总结" -d "详细描述"

# 示例
./auto_deploy.sh -s "feat: 增加用户登录接口" -d "实现了 JWT 认证的用户登录接口，包括 Token 刷新机制和过期处理。"

./auto_deploy.sh -s "fix: 修复数据库连接超时" -d "调整了 db_config.js 中的 timeout 参数，从 3000ms 增加到 5000ms，以适应当前网络环境。"
```
</command>

### 5.2 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `-s` | 是 | 简要修改总结（commit message 标题） |
| `-d` | 是 | 详细修改说明（commit message 正文） |

### 5.3 提交消息格式建议

推荐使用 Conventional Commits 格式：

| 前缀 | 说明 | 示例 |
|------|------|------|
| `feat:` | 新功能 | `feat: 增加技能推荐系统` |
| `fix:` | Bug 修复 | `fix: 修复登录超时问题` |
| `refactor:` | 重构 | `refactor: 优化 API 响应结构` |
| `docs:` | 文档更新 | `docs: 更新部署文档` |
| `style:` | 代码格式 | `style: 统一代码缩进` |
| `test:` | 测试 | `test: 添加用户服务单元测试` |
| `chore:` | 杂项 | `chore: 更新依赖版本` |

### 5.4 脚本内部逻辑

该脚本已内置完整的 Git 操作流程：

```
auto_deploy.sh 执行流程:
    │
    ├── 1. git add . (暂存所有变更)
    │
    ├── 2. git commit (使用 -s 和 -d 参数构建消息)
    │
    └── 3. git push (推送到远程仓库)
```

**注意**: 该脚本**不执行** Docker 重建，代码变更会在下次 `docker-compose up -d` 时生效。

---

## 常见问题排查

### Q1: 服务启动失败

```bash
# 检查端口占用
lsof -i :8000
lsof -i :3001
lsof -i :5433

# 检查 Docker 状态
docker info

# 查看详细错误日志
docker-compose logs
```

### Q2: 数据库连接失败

```bash
# 检查数据库容器状态
docker-compose ps postgres

# 检查数据库日志
docker logs autonome-postgres

# 重启数据库
docker-compose restart postgres
```

### Q3: 前端构建失败

```bash
# 清除 node_modules 重新安装
cd autonome-studio
rm -rf node_modules package-lock.json
npm install

# 清除 Next.js 缓存
rm -rf .next
npm run build
```

---

*文档生成时间: 2026-03-21*
*维护者: Autonome Team*