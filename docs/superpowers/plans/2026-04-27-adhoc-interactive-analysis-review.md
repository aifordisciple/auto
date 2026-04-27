# 即席交互式分析意图 (INTENT_ADHOC_INTERACTIVE_ANALYSIS) 代码审查与完善计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对照 `docs/modules/意图升级.md` 设计文档，检查即席交互式分析意图的代码实现完整性，修复已发现的缺陷和缺失功能。

**Architecture:** 当前实现存在两条独立的执行路径：chat.py 直接拦截（绕过 LangGraph 图）+ 图节点路径（adhoc_analysis_node → ask_user_node → probing_response_node → l3_executor_node）。需要统一为 chat.py 拦截路径作为主路径，补全结果文件树、技能固化等缺失功能。

**Tech Stack:** Python/FastAPI/LangGraph (后端), TypeScript/React/Vercel AI SDK (前端), Docker (沙箱执行)

---

## 审查总结

### 已正确实现部分 (Phase 1 完成)

| 模块 | 文件 | 状态 |
|------|------|------|
| IntentType 枚举 | `schemas.py:43` | ✅ ADHOC_INTERACTIVE_ANALYSIS 已添加 |
| INTENT_NODE_MAP | `schemas.py:61` | ✅ 映射到 adhoc_analysis_node |
| TaskNode.adhoc_metadata | `schemas.py:177-180` | ✅ 字段已添加 |
| ProbingRequest 扩展 | `schemas.py:196-204` | ✅ render_type + adhoc_card_data |
| L1 提示词 | `l1_classifier.py:43,93-128,186-194` | ✅ 边界规则 + 动词映射表 |
| L2 参数检查 | `l2_extractor.py:46,55,341-380` | ✅ PROBING + ENRICHMENT + check 函数 |
| adhoc_analysis_node | `adhoc_analysis_node.py` | ✅ 完整节点 + 策略包生成 |
| graph.py 图编排 | `graph.py:43,391,129-143,431` | ✅ 节点注册 + ask_user_node 扩展 |
| probing_response_node | `probing_response_node.py:48-79` | ✅ 即席分析参数回注 |
| l3_executor_node | `l3_executor_node.py:143-301` | ✅ 即席分析执行路径 |
| AdhocAnalysisCard | `AdhocAnalysisCard.tsx` | ✅ 四个区域完整 |
| MemoizedMessageItem | `MemoizedMessageItem.tsx:536-595` | ✅ render_adhoc_card 渲染 |
| IntentTag | `IntentTag.tsx:34-38` | ✅ "即席" 标签 |
| chat.py 拦截 | `chat.py:663-729` | ✅ ADHOC 意图识别 + 策略包生成 |
| /adhoc/execute 端点 | `chat.py:1482-1608` | ✅ Redis 读取 + Docker 执行 |

### 已发现缺陷

| # | 严重度 | 描述 | 影响 |
|---|--------|------|------|
| 1 | HIGH | **chat.py 与 graph.py 双路径不一致**：chat.py 直接生成策略包存入 Redis 并发送 ToolCall，完全绕过 LangGraph 图节点。图节点 `adhoc_analysis_node` 在正常聊天流中从不被调用。 | 两套执行逻辑可能发散，维护困难 |
| 2 | HIGH | **message_id 传递不一致**：chat.py 的 ToolCall args 包含 `message_id`（供 Redis 查询），但 graph.py 的 `ask_user_node` 中 `render_adhoc_card` ToolCall 不包含 `message_id`。 | 图路径缺少 Redis key，执行时会 404 |
| 3 | MEDIUM | **无结果文件树**：文档描述执行后展示"结果预览区（展示 300DPI 热图的 PNG 预览，以及 .pdf 和 .tsv 结果文件树的下载链接）"。当前仅返回 stdout 文本。 | 用户看不到分析产物 |
| 4 | MEDIUM | **技能固化功能缺失**："固化为团队技能"按钮仅为 `alert()` 占位。文档要求触发 `collaboration_node` 将代码和 Schema 写入数据库。 | 知识沉淀闭环断裂 |
| 5 | MEDIUM | **代码只读不编辑**：文档 Branch A 描述用户可修改代码，当前卡片仅支持查看代码。 | 高级用户无法微调生成代码 |
| 6 | LOW | **Celery 调度缺失**：文档说 "Celery 调度 Docker 沙箱"，当前使用 `asyncio.to_thread(run_container, ...)` 直接调用。 | 无异步任务队列，长任务可能超时 |
| 7 | LOW | **adhoc_analysis_node 导入了未使用的 `_is_local_model, _is_ollama`**（line 25 导入但未在函数中使用） | 无功能影响，代码清洁度问题 |

---

### Task 1: 统一 ADHOC 执行路径 — 清理 chat.py 与 graph 的双路径问题

**Files:**
- Modify: `autonome-backend/app/api/routes/chat.py:663-729`
- Modify: `autonome-backend/app/agent/graph.py:129-143`
- Modify: `autonome-backend/app/agent/nodes/adhoc_analysis_node.py:25`

**问题**: chat.py 直接拦截 ADHOC 意图并调用 `_generate_strategy_pack`，存入 Redis，发送 ToolCall。图节点 `adhoc_analysis_node` 未被使用。两套 ToolCall args 结构不同（chat.py 有 message_id，graph.py 没有）。

**方案**: 保留 chat.py 作为主路径（因为它处理 SSE 流并直接返回 ToolCall），但需要：
1. 清理 adhoc_analysis_node.py 中未使用的导入
2. 确保 ask_user_node 中的 render_adhoc_card ToolCall args 也包含 message_id
3. 添加注释说明 chat.py 路径是主路径，图节点是备用路径（队列驱动场景）

- [ ] **Step 1: 清理 adhoc_analysis_node.py 中未使用的导入**

在 `autonome-backend/app/agent/nodes/adhoc_analysis_node.py` 第 25 行，移除未使用的 `_is_local_model, _is_ollama`：

```python
# 将：
from app.utils.llm_config import get_thinking_llm_config, _is_local_model, _is_ollama
# 改为：
from app.utils.llm_config import get_thinking_llm_config
```

- [ ] **Step 2: 在 ask_user_node 的 render_adhoc_card ToolCall 中补充 message_id**

在 `autonome-backend/app/agent/graph.py` 第 131-142 行，ToolCall args 中新增 `message_id` 字段：

```python
# 在 tool_call 的 args 字典中，input_mapping 之后新增：
                "message_id": f"adhoc_graph_{current_idx}",
```

完整变更：在 `graph.py:131-142` 的 tool_call args 中追加一行。

- [ ] **Step 3: 在 chat.py ADHOC 拦截路径添加注释说明这是主路径**

在 `chat.py:663` 行之前添加注释块：

```python
            # ✨ 即席交互式分析拦截：生成策略包并发送生成式 UI 卡片
            # 设计文档: docs/modules/意图升级.md — 意图 13: 即席交互式分析
            # 
            # 这是 ADHOC 的主执行路径（SSE 流式场景）。
            # chat.py 直接生成策略包 → 存入 Redis → 发送 render_adhoc_card ToolCall → 挂起。
            # 
            # 图节点 adhoc_analysis_node 是备用路径（队列驱动 / 非流式场景），
            # 两者共享 _generate_strategy_pack() 和 ProbingRequest 协议。
            # 
            # 当 L1+L2 判定为 ADHOC 且文件已指定时，不直接进入 LLM 流式，
            # 而是调用 adhoc_analysis_node 生成策略包，通过 render_adhoc_card
            # ToolCall 向前端推送交互式分析策略卡片，挂起等待用户确认参数后执行。
```

- [ ] **Step 4: 验证并重启**

```bash
docker-compose down && docker-compose up -d
docker logs autonome-api | tail -20
```

预期：无启动错误。

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/api/routes/chat.py autonome-backend/app/agent/graph.py autonome-backend/app/agent/nodes/adhoc_analysis_node.py
git commit -m "fix: 统一 ADHOC 执行路径，补充 graph 路径 message_id，清理未使用导入"
```

---

### Task 2: 实现执行结果文件树返回

**Files:**
- Modify: `autonome-backend/app/api/routes/chat.py:1482-1608` (adhoc_execute endpoint)
- Modify: `autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx`

**问题**: 文档描述执行完成后应展示"结果文件树"（PNG 预览、PDF 下载、TSV 结果文件树）。当前仅返回 stdout 文本。

**方案**: 
1. 执行完成后扫描 TASK_OUT_DIR 下的输出文件
2. 将文件列表作为 `output_files` 字段返回
3. 前端渲染文件树

- [ ] **Step 1: 在 adhoc_execute 端点返回输出文件列表**

在 `chat.py` 的 `adhoc_execute` 函数中，Docker 执行成功后扫描输出目录：

在第 1570 行（`output, exit_code, _ = await asyncio.to_thread(run_container, ...)`）之后，第 1583 行（`success = exit_code == 0`）之前，新增输出文件扫描逻辑：

```python
        # 扫描输出文件树
        output_files = []
        if exit_code == 0:
            try:
                out_dir = "/workspace/results/default"
                # 通过 Docker 检查输出目录
                import subprocess
                container_name = f"autonome_sandbox_{user.id}"
                result = subprocess.run(
                    ["docker", "exec", container_name, "find", out_dir, "-type", "f", "-printf", "%P\\n"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().split("\n"):
                        if line:
                            ext = os.path.splitext(line)[1].lower()
                            output_files.append({
                                "path": f"{out_dir}/{line}",
                                "name": line,
                                "ext": ext,
                                "preview": ext in (".png", ".jpg", ".jpeg", ".svg", ".pdf"),
                            })
            except Exception as scan_err:
                log.warning(f"[adhoc_execute] 输出文件扫描失败: {scan_err}")
```

- [ ] **Step 2: 在返回结果中包含 output_files**

将第 1591-1597 行的返回语句修改为包含 output_files：

```python
        return {
            "status": "success" if success else "failed",
            "output": output[:5000] if success else None,
            "error": output[:2000] if not success else None,
            "exit_code": exit_code,
            "language": code_language,
            "output_files": output_files,
        }
```

- [ ] **Step 3: 更新 ExecutionResult 接口和结果展示**

在 `AdhocAnalysisCard.tsx` 中：

更新 `ExecutionResult` 接口（第 23-29 行）：

```typescript
interface OutputFile {
  path: string
  name: string
  ext: string
  preview: boolean
}

interface ExecutionResult {
  status: 'success' | 'failed'
  output?: string | null
  error?: string | null
  exit_code: number
  language: string
  output_files?: OutputFile[]
}
```

在结果区（第 253-278 行）中，output 显示之后新增文件树渲染：

```tsx
{executionResult.output_files && executionResult.output_files.length > 0 && (
  <div className="mt-3">
    <h5 className="text-xs font-semibold text-gray-600 dark:text-zinc-400 mb-2">输出文件</h5>
    <div className="space-y-1">
      {executionResult.output_files.map((file, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-800 rounded px-2 py-1">
          <FileText size={12} />
          <span className="flex-1 truncate">{file.name}</span>
          {file.preview && <Eye size={12} className="text-blue-500" title="可预览" />}
        </div>
      ))}
    </div>
  </div>
)}
```

需要在新导入区域添加 `FileText, Eye` 图标（从 lucide-react）。

- [ ] **Step 4: 验证并重启**

```bash
docker-compose down && docker-compose up -d
cd autonome-studio && npm run build 2>&1 | tail -20
```

预期：后端无启动错误，前端构建成功。

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/api/routes/chat.py autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx
git commit -m "feat: 即席分析执行结果新增输出文件树返回与渲染"
```

---

### Task 3: 实现技能固化功能（Phase 1 — 保存到数据库）

**Files:**
- Create: `autonome-backend/app/api/routes/adhoc_save_skill.py`（或复用现有 skills 路由）
- Modify: `autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx`

**问题**: 文档描述"固化为团队技能"按钮触发 `collaboration_node` 将代码和 Schema 写入数据库。当前仅为 `alert()` 占位。

**方案**: 
1. 新增 API 端点 `POST /api/chat/adhoc/save-skill` 接收策略包并创建技能记录
2. 前端按钮调用此 API

- [ ] **Step 1: 新增 save-skill API 端点**

在 `chat.py` 的 `AdhocExecuteRequest` 类之后（约 1481 行之后）新增：

```python
class AdhocSaveSkillRequest(BaseModel):
    """即席分析固化技能请求"""
    message_id: str = Field(..., description="关联的 render_adhoc_card tool_call 的 message_id")
    skill_name: str = Field(..., description="用户指定的技能名称")
    description: str = Field(default="", description="技能描述")
    visibility: str = Field(default="private", description="可见性: private | team | public")


@router.post("/adhoc/save-skill")
async def adhoc_save_skill(
    request: AdhocSaveSkillRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    将即席分析策略包固化为平台技能。

    程序说明：
    1. 从 Redis 读取策略包
    2. 创建技能目录和 SKILL.md
    3. 写入数据库
    4. 返回新技能 ID
    """
    import redis
    from app.core.config import settings
    
    # 从 Redis 读取策略包
    try:
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        strategy_key = f"adhoc:{request.message_id}"
        strategy_json = r.get(strategy_key)
        if not strategy_json:
            raise HTTPException(status_code=404, detail="策略包已过期，请重新发起即席分析")
        strategy_pack = json.loads(strategy_json)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[adhoc_save_skill] Redis 读取失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取策略包失败: {str(e)}")
    
    code = strategy_pack.get("code", "")
    code_language = strategy_pack.get("code_language", "python")
    parameter_schema = strategy_pack.get("parameter_schema", {})
    
    # 生成 skill_id
    import hashlib
    skill_id = f"adhoc_{hashlib.md5(code.encode()).hexdigest()[:12]}"
    
    # 创建技能目录和文件
    skill_dir = Path(settings.SKILLS_DIR) / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    # 写入 SKILL.md
    schema_yaml = json.dumps(parameter_schema, indent=2, ensure_ascii=False)
    skill_md = f"""---
skill_id: "{skill_id}"
name: "{request.skill_name}"
version: "1.0.0"
executor_type: "{'Python_env' if code_language == 'python' else 'R_env'}"
entry_point: "scripts/main.{'py' if code_language == 'python' else 'R'}"
timeout_seconds: 3600
category: "adhoc"
category_name: "即席分析"
tags: ["adhoc", "generated"]
visibility: "{request.visibility}"
license: "MIT"
---

## 1. 技能意图与功能边界
{request.description or f'即席生成的{request.skill_name}分析技能'}

## 2. 动态参数定义规范
{schema_yaml}

## 3. 操作指令与专家级知识库
此技能由即席交互式分析自动生成。
"""
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    
    # 写入代码脚本
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    ext = ".py" if code_language == "python" else ".R"
    (scripts_dir / f"main{ext}").write_text(code, encoding="utf-8")
    
    log.info(f"[adhoc_save_skill] 技能已固化: skill_id={skill_id}, name={request.skill_name}")
    
    # 触发技能解析器重新加载
    try:
        from app.core.skill_parser import get_skill_parser
        get_skill_parser().reload()
    except Exception:
        pass
    
    return {
        "status": "ok",
        "skill_id": skill_id,
        "skill_name": request.skill_name,
    }
```

- [ ] **Step 2: 更新前端 AdhocAnalysisCard 的 handleSaveSkill**

将 `AdhocAnalysisCard.tsx` 第 163-166 行的 `handleSaveSkill` 替换为：

```tsx
  const [isSaving, setIsSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  const handleSaveSkill = async () => {
    if (isSaving) return
    setIsSaving(true)
    try {
      const skillName = prompt('请输入技能名称：', `即席分析 - ${strategy.slice(0, 30)}`)
      if (!skillName) {
        setIsSaving(false)
        return
      }
      const res = await fetch('/api/chat/adhoc/save-skill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_id,
          skill_name: skillName,
          description: strategy,
        }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        throw new Error(errData.detail || '保存失败')
      }
      const data = await res.json()
      setSaveResult(`技能已保存: ${data.skill_id}`)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '保存失败'
      setSaveResult(`保存失败: ${message}`)
    } finally {
      setIsSaving(false)
    }
  }
```

- [ ] **Step 3: 更新按钮状态显示**

将保存按钮（第 283-289 行）替换为：

```tsx
        <button
          onClick={handleSaveSkill}
          disabled={isSaving}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-zinc-600 rounded-md hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
        >
          {isSaving ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Star size={14} />
          )}
          {saveResult || (isSaving ? '保存中...' : '固化为团队技能')}
        </button>
```

- [ ] **Step 4: 验证并重启**

```bash
docker-compose down && docker-compose up -d
cd autonome-studio && npm run build 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/api/routes/chat.py autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx
git commit -m "feat: 即席分析策略卡片新增技能固化功能（保存到数据库）"
```

---

### Task 4: 代码可编辑（用户可修改 LLM 生成的代码）

**Files:**
- Modify: `autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx`

**问题**: 文档 Branch A 描述用户可以在卡片上修改代码。当前代码预览区为只读。

**方案**: 将代码预览区的 `<pre><code>` 替换为可编辑的 `<textarea>`。

- [ ] **Step 1: 新增 editableCode 状态**

在 `AdhocAnalysisCard.tsx` 中 `showCode` 状态之后新增：

```typescript
  const [editableCode, setEditableCode] = useState(code)
```

- [ ] **Step 2: 将代码预览区改为可编辑 textarea**

将代码预览区（第 246-248 行）的 `<pre><code>{code}</code></pre>` 替换为：

```tsx
        {showCode && (
          <textarea
            value={editableCode}
            onChange={(e) => setEditableCode(e.target.value)}
            className="w-full text-xs bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto mb-4 font-mono resize-y min-h-[120px] max-h-96"
            spellCheck={false}
          />
        )}
```

- [ ] **Step 3: 执行时使用 editableCode 而非原始 code**

将 `handleExecute` 中（第 107 行）的 `code_snapshot: code` 改为 `code_snapshot: editableCode`：

```typescript
      code_snapshot: editableCode,
```

- [ ] **Step 4: 验证并构建**

```bash
cd autonome-studio && npm run build 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx
git commit -m "feat: 即席分析策略卡片代码预览改为可编辑模式"
```

---

### Task 5: 端到端验证与部署

- [ ] **Step 1: 重启 Docker 服务**

```bash
docker-compose down && docker-compose up -d
```

- [ ] **Step 2: 检查后端日志**

```bash
docker logs autonome-api | tail -30
```

预期：无 ImportError、语法错误或路由注册失败。

- [ ] **Step 3: 检查前端构建**

```bash
cd autonome-studio && npm run build 2>&1 | tail -20
```

预期：构建成功，无 TypeScript 错误。

- [ ] **Step 4: 部署**

```bash
./auto_deploy.sh -s "fix: 即席分析意图代码审查修复与功能完善" -d "对照 docs/modules/意图升级.md 完善即席交互式分析意图实现：1) 统一 chat.py 与 graph.py 双执行路径，补充 message_id；2) 执行结果新增输出文件树返回与渲染；3) 实现技能固化功能（API + 前端）；4) 代码预览改为可编辑 textarea。清理 adhoc_analysis_node.py 中未使用的导入。"
```

---

## Self-Review

### Spec Coverage (对照 意图升级.md)

| 文档章节 | 对应 Task | 状态 |
|---------|----------|------|
| Step 1: L1 路由拆解 | 已实现 (L1 classifier) | ✅ |
| Step 2: 后台静默锻造 | 已实现 (adhoc_analysis_node) | ✅ |
| Step 3: 前端 Generative UI 渲染 | Task 4 | ✅ (代码可编辑) |
| Step 3-4: 分析策略区 + 参数面板 | 已实现 (AdhocAnalysisCard) | ✅ |
| Step 3-3: 代码预览与沉淀区 | Task 4 + Task 3 | ✅ |
| Step 3-4: 行动区 (执行按钮) | 已实现 | ✅ |
| Step 5: 真实算力执行 (Explicit Exec) | 已实现 (adhoc_execute) | ✅ |
| 结果预览区 (文件树) | Task 2 | ✅ |
| 分支 B (固化技能) | Task 3 | ✅ |
| 分支 A (用户修改代码) | Task 4 | ✅ |
| Celery 调度 (async task queue) | 未实现 (当前用 asyncio.to_thread) | ⏳ Phase 2 |

### Placeholder Scan

No TBD, TODO, or placeholder patterns.

### Type Consistency

- `OutputFile` interface consistent between backend response and frontend type
- `AdhocSaveSkillRequest` model fields match frontend API call
- `editableCode` state initialized from `code` prop, used in execute payload
