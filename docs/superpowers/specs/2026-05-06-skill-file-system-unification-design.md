# 技能文件系统统一化升级设计

> 日期：2026-05-06
> 类型：架构升级
> 目标：所有技能（官方+工厂创建）统一为文件系统存储，消除 DB/Filesystem 双源矛盾

---

## 1. 背景与动机

### 1.1 当前架构问题

```
Forge ──→ SkillAsset(DB) ──→ DBSkillParser          ✗ 两套数据源
Skills/ ──→ SkillBundleParser(fs)                    ✗ 格式不统一
     ↓                    ↓
get_combined_skills() 合并 → API 层使用              ✗ 脆弱的合并逻辑
SkillExecutor → get_skill_parser() → 只读文件         ✗ DB技能无法执行
```

**核心矛盾**：工厂创建的技能只存数据库（`SkillAsset` 表 JSONB 字段），不写文件系统。执行器 (`SkillExecutor`) 的初始化逻辑只读文件系统，导致用户创建的技能无法通过正常执行路径运行。

### 1.2 五个官方技能已经文件化

`/app/skills/` 下已有 5 个官方预置技能，每个都是完整文件夹结构（SKILL.md + scripts/ + config/ 等），证明文件化是可行的模式。

### 1.3 升级目标

- **唯一真相源**：文件系统是技能的权威存储
- **消除双源**：删除 `DBSkillParser` 和 `get_combined_skills()` 合并逻辑
- **统一执行路径**：`SkillExecutor` 无差别对待官方和用户技能
- **DB 降级为索引**：`SkillAsset` 仅存元数据索引（状态、评分、权限、统计）

---

## 2. 目标架构

```
Forge ──→ SkillFileWriter ──→ /app/skills/{skill_id}/
                                   │
                                   ├── SKILL.md              (YAML + 专家知识)
                                   ├── scripts/main.py       (入口脚本)
                                   └── (其他资源文件)
                                   ↓
SkillIndexer (启动/变更时) ──→ SkillAsset(DB, 仅元数据索引)
                                   ↓
SkillParser(fs only) ←── API 层取元数据 ←── SkillAsset(DB)
SkillExecutor ←── SkillParser(fs)
```

**核心变更模块**：

| 模块 | 类型 | 职责 |
|------|------|------|
| `SkillFileWriter` | 新增 | Forge commit 时将草稿序列化为文件系统目录 |
| `SkillIndexer` | 新增 | 启动时/变更时从文件系统重建 DB 索引 |
| `SkillParser` | 精简 | 只读文件系统，删除 DBSkillParser 和合并逻辑 |
| `skills_forge.py` | 修改 | commit/submit 端点增加文件写入和增量索引 |
| `SkillAsset` 表 | 精简 | 删除冗余字段（script_code 等），新增索引字段 |

---

## 3. 数据模型变更

### 3.1 SkillAsset 表字段精简

移除以下字段（内容已迁移到文件系统）：

- `parameters_schema` (JSONB)
- `expert_knowledge` (TEXT)
- `script_code` (TEXT)
- `nextflow_code` (TEXT)
- `dependencies` (JSONB)

保留字段：

- `skill_id` — 唯一标识，对应文件夹名
- `name`, `description` — 显示用索引
- `version`, `executor_type` — 索引
- `category`, `category_name`, `subcategory`, `subcategory_name`, `tags` — 分类索引
- `status` (SkillStatus) — 审核状态（DRAFT / PENDING_REVIEW / PUBLISHED / DEPRECATED）
- `visibility`, `license` — 发布信息
- `usage_count`, `avg_rating`, `favorite_count` — 统计信息
- `execution_mode` — docker/native

新增字段：

```python
bundle_path: str          # 相对路径，如 "skills/user_skill_001"
is_official: bool         # 官方预置(true) vs 用户创建(false)
file_hash: str            # SKILL.md 内容哈希，用于检测文件变更
indexed_at: datetime      # 最后索引时间
```

### 3.2 工厂生成的 SKILL.md 模板

```yaml
---
skill_id: "gen_abc123"
name: "用户创建的技能"
version: "1.0.0"
executor_type: "Python_env"
entry_point: "scripts/main.py"
timeout_seconds: 3600
category: "custom"
category_name: "自定义"
tags: ["custom"]
visibility: "private"
license: "MIT"
---

## 1. 技能意图与功能边界
{description 内容}

## 2. 动态参数定义规范
| 参数键名 | 数据类型 | 必填 | 默认值 | 详细描述说明 |
|---|---|---|---|---|
| ... (从 parameters_schema JSON 转换为表格) |

## 3. 操作指令与专家级知识库
{expert_knowledge 内容}
```

### 3.3 用户技能文件夹结构

与官方技能完全一致：

```
/app/skills/{skill_id}/
├── SKILL.md                    # YAML frontmatter + 完整技能文档
└── scripts/
    └── main.py                 # 入口脚本（script_code 内容写入）
```

对于 `Logical_Blueprint` 类型，增加：

```
/app/skills/{skill_id}/
├── SKILL.md
├── scripts/
│   └── main.py                 # Python 入口（如有）
└── nextflow/
    └── main.nf                 # Nextflow DSL2 工作流
```

---

## 4. 核心模块设计

### 4.1 SkillFileWriter (`app/services/skill_file_writer.py`)

```python
class SkillFileWriter:
    """技能文件写入器 — 将 Forge 草稿序列化为文件系统目录"""

    def __init__(self, skills_dir: str = "/app/app/skills"):
        self.skills_dir = skills_dir

    def write_skill_from_draft(
        self, draft: dict, skill_id: str | None = None
    ) -> str:
        """
        从草稿创建技能文件夹：
        1. 生成或使用已有 skill_id
        2. 创建 /app/skills/{skill_id}/ 和 scripts/ 目录
        3. 渲染 SKILL.md（YAML frontmatter + markdown 内容）
        4. 写入 scripts/main.py（或 nextflow/main.nf）
        5. 返回 skill_id
        """

    def update_skill(self, skill_id: str, draft: dict) -> None:
        """覆写已有技能的 SKILL.md + 脚本文件"""

    def delete_skill(self, skill_id: str) -> None:
        """删除技能文件夹（仅限用户技能，官方技能受保护）"""
```

### 4.2 SkillIndexer (`app/services/skill_indexer.py`)

```python
class SkillIndexer:
    """技能索引器 — 从文件系统重建 DB 元数据索引"""

    def __init__(self, skills_dir: str = "/app/app/skills"):
        self.skills_dir = skills_dir
        self.parser = SkillBundleParser(skills_dir)

    def index_all(self) -> int:
        """
        全量索引：
        1. 扫描所有技能文件夹
        2. 解析 SKILL.md 获取元数据
        3. 计算 file_hash
        4. 与 DB 中现有记录对比，有变化才 upsert
        5. 删除 DB 中对应文件已不存在的记录
        返回索引数量
        """

    def index_one(self, skill_id: str) -> None:
        """增量索引单个技能（Forge commit 后调用）"""

    def remove_index(self, skill_id: str) -> None:
        """技能文件夹被删除后，从 DB 移除索引"""
```

### 4.3 SkillParser 精简 (`app/core/skill_parser.py`)

删除的代码：

- `DBSkillParser` 类（约 170 行）
- `get_db_skill_parser()` 函数
- `get_combined_skills_cached()` 函数
- `get_combined_skills()` 函数
- `get_combined_skill_by_id()` 函数

保留的代码：

- `SkillBundleParser` 类
- `get_skill_parser()` 单例
- Sample Sheet 配置提取函数

> `SkillParser` 的唯一数据源变为文件系统，不再需要区分 DB/FS。

### 4.4 skills_forge.py 修改 (`app/api/routes/skills_forge.py`)

commit 端点（`POST /session/{id}/commit`）变更：

```python
# 原有逻辑：创建/更新 SkillAsset DB 记录
# ✨ 新增：
# 1. SkillFileWriter.write_skill_from_draft(draft, skill_id)
# 2. SkillIndexer.index_one(skill_id)
# 3. 更新 SkillAsset 的 bundle_path 和 file_hash
```

submit 端点（`POST /session/{id}/submit`）同样增加文件写入。

### 4.5 API 路由层适配

`get_all_skills()` 调用的变更模式：

```python
# BEFORE:
skills = get_combined_skills(user_id)

# AFTER:
db_skills = SkillAsset 表查询（获取元数据索引）
# 详情需要时再从 SkillParser 读文件获取 parameters_schema / expert_knowledge
```

---

## 5. 调用时序

### 5.1 启动时

```
1. 等待 PostgreSQL 就绪
2. 运行一次性迁移脚本（如未执行过）：migrate_db_skills_to_files.py
3. SkillIndexer.index_all() → 扫描文件系统，重建 DB 索引
4. 启动 FastAPI 服务
```

### 5.2 Forge commit 时

```
1. 前端点击"确认保存"
2. POST /skills-forge/session/{id}/commit
3. SkillFileWriter.write_skill_from_draft(draft, skill_id)
   → 创建 /app/skills/{skill_id}/ 目录
   → 写入 SKILL.md
   → 写入 scripts/main.py
4. SkillIndexer.index_one(skill_id)
   → 解析 SKILL.md → upsert SkillAsset 记录
5. 返回 {skill_id, name, ...}
```

### 5.3 执行时（无变化）

```
1. Agent DAG → l3_executor_node
2. SkillExecutor(skill_id, ...)
3. get_skill_parser().get_skill_by_id(skill_id) → 读文件系统
4. 从 bundle_path 找到入口脚本，Docker 沙箱执行
```

---

## 6. 迁移策略

### 6.1 迁移脚本

`autonome-backend/scripts/migrate_db_skills_to_files.py`：

```python
"""
一次性迁移脚本：将 SkillAsset 表中的用户技能导出为文件系统结构
"""
for skill in SkillAsset 表中有 script_code 的记录:
    1. 从 DB JSONB 还原 draft（script_code, parameters_schema, expert_knowledge...）
    2. 构建 SKILL.md YAML frontmatter
    3. SkillFileWriter.write_skill_from_draft(draft, skill.skill_id)
    4. 更新 SkillAsset：清除冗余字段，设置 bundle_path / is_official / file_hash
    5. log 记录迁移结果
```

### 6.2 执行机制

- 在 `docker-compose` 启动脚本中，API 启动前执行
- 通过环境变量 `SKILL_MIGRATION_DONE` 标记避免重复执行
- 迁移前自动 `pg_dump` 备份

### 6.3 兼容期处理

- 迁移后 1 周内，SkillAsset 表保留 `script_code` 字段（`nullable=True`）作为回退
- `SkillParser` 增加 fallback 逻辑：文件读取失败 → 查 DB script_code
- 1 周稳定后，删除 DB 冗余字段和 fallback 逻辑

---

## 7. 错误处理

| 场景 | 处理方式 |
|------|----------|
| Forge commit 时文件写入失败（磁盘满/权限） | 事务回滚，DB 不更新，返回 500 给前端 |
| 文件已存在但 DB 索引缺失 | `index_all()` 自动补齐 |
| DB 有索引但 SKILL.md 被误删 | `index_all()` 标记为 MISSING，API 不返回该技能 |
| SKILL.md YAML 解析失败 | 跳过该技能，log 警告，不影响其他技能索引 |
| Docker 容器路径映射 | FileWriter 写宿主机路径，容器内通过 volume 映射访问 |
| 并发 Forge commit 同一个 skill_id | `update_skill` 覆写是幂等的，DB upsert 也是幂等的 |
| 删除官方技能（误操作） | `delete_skill` 检查 `is_official=True` 时拒绝删除 |

---

## 8. 测试计划

### 8.1 单元测试

| 测试对象 | 测试内容 |
|----------|----------|
| `SkillFileWriter` | write/update/delete 操作的正确性 |
| `SkillFileWriter` | SKILL.md 模板渲染结果正确 |
| `SkillFileWriter` | 目录不存在时自动创建 |
| `SkillIndexer` | index_all 正确扫描和 upsert |
| `SkillIndexer` | index_one 增量索引 |
| `SkillIndexer` | remove_index 正确删除 |
| `SkillIndexer` | file_hash 变化检测 |
| `SkillParser` | 从文件系统正确解析 SKILL.md |
| `SkillParser` | 不存在的 skill_id 返回 None |

### 8.2 集成测试

| 测试场景 | 验证点 |
|----------|--------|
| Forge commit → 文件写入 → 索引 → API 查询 | 端到端链路 |
| 官方技能解析 + 执行 | 回归：现有 5 个技能仍可正常执行 |
| 用户技能执行 | 通过 Forge 创建的技能可通过 Executor 执行 |
| 启动时迁移 | DB 技能正确导出为文件 |
| 文件变更后重索引 | index_all 正确更新变更的技能 |

### 8.3 回归检查

- 现有 5 个官方技能解析 100% 通过
- 现有技能执行流程不受影响
- 前端技能列表显示正常
- ForgePanel 创建/编辑/保存流程正常

---

## 9. 实施步骤

| 步骤 | 内容 | 预估工时 |
|------|------|----------|
| 1 | 创建 `SkillFileWriter` 服务 + 单元测试 | 0.5 天 |
| 2 | 创建 `SkillIndexer` 服务 + 单元测试 | 0.5 天 |
| 3 | 精简 `SkillParser`，删除 DBSkillParser | 0.5 天 |
| 4 | 修改 `skills_forge.py` commit/submit 端点 | 0.5 天 |
| 5 | 修改 `SkillAsset` 模型，创建 migration | 0.5 天 |
| 6 | API 路由层适配（替换 get_combined_skills 调用） | 0.5 天 |
| 7 | 编写数据迁移脚本 | 0.5 天 |
| 8 | 集成测试 + 回归测试 | 0.5 天 |
| 9 | Docker 启动时序调整 | 0.5 天 |
| 10 | 文档更新 | 0.5 天 |

**总计**：约 5 天
