# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# AUTONOME STUDIO

AI-Native Bioinformatics IDE — FastAPI/LangGraph 后端 + Next.js 16 前端。多 Agent 系统 + Docker 沙箱代码执行。

<file-ref path="docs/ARCHITECTURE.md">
详细架构文档请参阅 docs/ARCHITECTURE.md
</file-ref>

---

## Docker 服务

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| backend-api | autonome-api | 8000 | FastAPI 后端 |
| frontend | autonome-web | 3001 | Next.js 前端 |
| postgres | autonome-postgres | 5433 | PostgreSQL + pgvector |
| redis | autonome-redis | 6379 | Cache + Celery broker |
| backend-worker | autonome-worker | - | Celery async tasks |

**Access:** Frontend http://localhost:3001 | API http://localhost:8000/docs

---


### <critical> 强制注释铁律

**最不可侵犯的底线**：AI 助手绝不允许删除或精简原有注释！

- 每段核心业务逻辑必须有详尽的中文注释
- 修改代码时必须同步更新注释
- 违规判定：注释被替换为 `//... existing code...` 则提交无效

**非常重要：代码超过1000行，要按照功能模块进行拆分，避免过度庞大的代码。

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

---

## Probe Tools 模式

<rule>
处理任何数据文件前，Agent **必须**调用探针工具，**禁止**猜测列名或路径。
</rule>

| 工具 | 用途 |
|------|------|
| `peek_tabular_data` | 预览表格（CSV/TSV）表头和维度 |
| `scan_workspace` | 扫描目录结构 |

---

## SKILL 系统

- Skills 位于 `autonome-backend/app/skills/`
- 每个 SKILL 包含 `SKILL.md` (YAML 元数据 + 参数定义 + 专家知识)
- Agent 优先使用 SKILL，无法匹配时才 Live Coding

**Available Skills:**

| skill_id | Name | Executor |
|----------|------|----------|
| `fastqc_multiqc_pipeline_01` | 原始测序数据质量控制 | Logical_Blueprint |
| `meta_nextflow_generator_01` | Nextflow 流水线生成引擎 | Python_env |
| `singlecell_seurat_pipeline_01` | 单细胞RNA-seq分析 | Python_env |

---

## 规范速查

<pattern>
**后端**: Loguru 日志 (`log.info()`)，SQLModel ORM，JWT HS256/7天
**前端**: `@/*` 路径别名，Zustand 状态管理，深色模式默认
</pattern>

<anti-pattern>
| 禁止 | 正确做法 |
|------|----------|
| `any` 类型 | 定义明确接口 |
| `console.log()` | 使用 logger |
| `print()` | `log.info()` |
| 硬编码中文到 matplotlib | 英文或变量 |
| 猜测列名/路径 | 先调用探针工具 |
</anti-pattern>

<rule>
**React Resizable Panels v4**: `defaultSize="15%"` (字符串)，**禁止** `defaultSize={15}` (数字)
</rule>

<file-ref path="docs/CONVENTIONS.md">
完整开发规范请参阅 docs/CONVENTIONS.md
</file-ref>

---

## 常用命令

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker logs autonome-api | tail -30

# 重启服务
docker-compose down && docker-compose up -d
```

<file-ref path="docs/COMMANDS.md">
完整命令参考请参阅 docs/COMMANDS.md
</file-ref>

---

## Docker 注意事项

<important>
修改 `package.json` 添加新依赖后，必须重建前端镜像：

```bash
docker-compose build --no-cache frontend
docker-compose up -d
```

否则容器内不会安装新依赖，导致 Module not found 错误。
</important>

---

## 重要文件索引

| Task | Location |
|------|----------|
| Agent 主逻辑 | `autonome-backend/app/agent/bot.py` |
| Docker 沙箱执行 | `autonome-backend/app/tools/bio_tools.py` |
| Probe Tools | `autonome-backend/app/tools/probe_tools.py` |
| API 路由 | `autonome-backend/app/api/routes/` |
| 数据模型 | `autonome-backend/app/models/domain.py` |
| SKILL 解析器 | `autonome-backend/app/core/skill_parser.py` |
| Zustand Stores | `autonome-studio/src/store/` |
| 主 IDE 页面 | `autonome-studio/src/app/page.tsx` |
| API 客户端 | `autonome-studio/src/lib/api.ts` |

---

## Known Issues

| Issue | Location |
|-------|----------|
| Hardcoded IP 113.44.66.210 | docker-compose.override.yml, frontend API calls |
| Docker socket mounted | docker-compose.yml (security risk) |

---

<file-ref path="docs/BESALTPIPE.md">
BesaltPipe 生信流程框架请参阅 docs/BESALTPIPE.md
</file-ref>
