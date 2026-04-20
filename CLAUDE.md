# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# AUTONOME STUDIO

AI-Native Bioinformatics IDE — FastAPI/LangGraph 后端 + Next.js 16 前端。多 Agent 系统 + Docker 沙箱代码执行。

详细架构: `docs/LANTU.md`

---

## 强制注释铁律

- **绝不允许删除或精简原有注释**，修改代码时必须同步更新注释
- 核心业务逻辑必须有详尽的中文注释，说明"为什么"而非仅"做什么"
- 违规判定：注释被替换为 `//... existing code...` 则提交无效
- 代码超过 1000 行必须按功能模块拆分

---

## 常用命令

```bash
# Docker 服务
docker-compose up -d                                    # 启动
docker-compose down && docker-compose up -d              # 重启（代码修改后）
docker logs autonome-api | tail -30                      # 后端日志
docker logs autonome-web | tail -30                      # 前端日志
docker-compose exec postgres psql -U autonome autonome_db # 数据库

# 后端本地开发
cd autonome-backend
uvicorn main:app --reload --port 8000                   # 开发服务器
celery -A app.services.celery_app worker --loglevel=info # Celery worker
alembic upgrade head                                     # 数据库迁移
alembic revision --autogenerate -m "描述"                # 创建迁移
python make_admin.py <email>                             # 提升管理员

# 前端本地开发
cd autonome-studio
npm run dev                                              # 开发服务器 (port 3000)
npm run build                                            # 生产构建
npm run lint                                             # ESLint

# 根目录 monorepo
pnpm dev                                                 # 启动前端
pnpm build                                               # 构建前端
pnpm lint                                                # Lint 所有包
```

**添加前端依赖后必须重建镜像：** `docker-compose build --no-cache frontend && docker-compose up -d`

---

## Docker 服务

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| backend-api | autonome-api | 8000 | FastAPI 后端 |
| frontend | autonome-web | 3001 | Next.js 前端 |
| postgres | autonome-postgres | 5433 | PostgreSQL + pgvector |
| redis | autonome-redis | 6379 | Cache + Celery broker |
| backend-worker | autonome-worker | — | Celery async tasks |

Access: Frontend http://localhost:3001 | API http://localhost:8000/docs

---


### 核心开发与部署工作流规范

<rule>

你当前运行在一个由 Git 进行版本控制，并使用 Docker Compose 进行服务编排的 Mac 服务器项目中。对于收到的任何开发任务，你必须严格遵循以下步骤：

1. **执行开发**：完成用户要求的代码编写或编辑任务。
2. **状态验证**：每次代码修改完成后，你必须先执行`docker-compose down && docker-compose up -d`重启docker服务，如有报错则返回进行修复。
3. **自动部署**：上一步状态验证通过后，你必须调用项目根目录下的 `./auto_deploy.sh` 脚本来完成后续动作。
   - 必须使用 `-s` 参数传递简要的修改总结（如 "feat: 增加用户登录接口"）。
   - 必须使用 `-d` 参数传递详细的修改说明（Comments），解释修改了哪些逻辑及原因。
   - 示例命令：`./auto_deploy.sh -s "fix: 修复数据库连接超时" -d "调整了 db_config.js 中的 timeout 参数，从 3000ms 增加到 5000ms，以适应当前网络环境。"`，注意：该脚本已内置 `git add .`、`git commit`的完整逻辑，你只需调用该脚本并传入准确的参数即可。

</rule>
