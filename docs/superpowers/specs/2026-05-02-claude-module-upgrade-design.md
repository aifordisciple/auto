# Claude Code Agent 模式 — 升级方案设计文档

> 基于 `docs/claude_module.md` 设计文档进行功能审计后，制定的分阶段升级方案。
> 创建时间: 2026-05-02

---

## 审计结论

设计文档 Phase 1-5 的 22 个文件全部存在且有实质实现代码。但存在 7 个关键问题导致系统无法正常运行。

### 审计发现的问题

| # | 问题 | 文件 | 严重度 |
|---|------|------|--------|
| 1 | Alembic 迁移文件未部署到 Docker 容器 | `alembic/versions/claude_agent_tables.py` | CRITICAL |
| 2 | Sandbox Docker 镜像未构建 | `autonome-backend/Dockerfile.sandbox` | CRITICAL |
| 3 | ClaudeEvent 缺少 index signature，6 个 TS2345 错误 | `useClaudeStore.ts` | HIGH |
| 4 | refreshSessions 对已解析对象调用 .json()，运行时 TypeError | `ClaudeChatStage.tsx:42` | HIGH |
| 5 | PlanData 前后端命名不一致 (snake_case vs camelCase) | `event_types.py` + `useClaudeStore.ts` | MEDIUM |
| 6 | 预热容器 session_id 为 "pool"，分配时未更新 | `claude_container_pool.py` | MEDIUM |
| 7 | @anthropic-ai/claude-code 未锁定版本 | `Dockerfile.sandbox` | LOW |

---

## Stage 1 — 紧急止血

**目标**: 修复所有崩溃问题，让 Claude 模式可运行。

### 1.1 构建 Sandbox Docker 镜像

- **文件**: `autonome-backend/Dockerfile.sandbox`
- **变更**: 锁定 `@anthropic-ai/claude-code@1.0.0` 版本
- **执行**: `docker build -f autonome-backend/Dockerfile.sandbox -t autonome-claude-sandbox:latest .`
- **验证**: `docker images | grep autonome-claude-sandbox` 镜像存在

### 1.2 部署迁移文件

- **问题**: `claude_agent_tables.py` 存在于源码但未复制到 Docker 容器
- **修复方式**: 在 Dockerfile 中确保 `alembic/versions/` 目录被 COPY；运行 `alembic upgrade head`
- **验证**: `alembic current` 显示 `claude_agent_001`

### 1.3 修复 ClaudeEvent 类型定义

- **文件**: `autonome-studio/src/store/useClaudeStore.ts`
- **变更**: 为 `ClaudeEvent` 接口添加 `[key: string]: unknown` index signature
- **影响**: 解决 6 个 TS2345 编译错误

### 1.4 修复 refreshSessions 双重 JSON 解析

- **文件**: `autonome-studio/src/components/chat/ClaudeChatStage.tsx`（约第 42 行）
- **变更**: 移除 `.then(res => res.json())`，直接使用 `fetchAPI` 返回值
- **同时修复**: 将 `refreshSessions` 从 `.then()` 链改为 async/await，确保错误处理完整

### 1.5 修复容器池 session_id

- **文件**: `autonome-backend/app/services/claude_container_pool.py`
- **变更**: `allocate()` 方法中，复用预热容器时通过 `docker exec` 更新 `CLAUDE_SESSION_ID` 环境变量
- **备选方案**: `pre_warm()` 创建时不传 session_id，分配时首次设置

### 1.6 修复 PlanData 命名不一致

- **后端文件**: `autonome-backend/app/sandbox/agent_service/event_types.py`
- **变更**: `PlanEvent.to_json()` 输出字段从 snake_case 改为 camelCase:
  - `code_snapshot` → `codeSnapshot`
  - `estimated_cost` → `estimatedCost`
- **前端无需变更**（PlanData 接口已使用 camelCase）

### 1.7 前端 API 端点验证

- **检查**: `fetchAPI` 的 `normalizeEndpoint` 是否正确处理 `/api/claude/*` 路径
- **验证**: 在浏览器 Network 面板确认请求打到 `http://host:8000/api/claude/sessions` 而非 `http://host:8000/api/api/claude/sessions`

### Stage 1 验证标准

- [ ] Claude 模式页面正常渲染，无白屏/崩溃
- [ ] 三栏布局可见（左栏会话列表、中间对话区、右栏预览区）
- [ ] 可成功创建 Claude 会话
- [ ] 后端日志无 "Unable to find image" 错误
- [ ] `alembic current` 显示正确的迁移版本

---

## Stage 2 — 韧性加固

**目标**: 防止未来再次出现白屏崩溃，提升用户体验。

### 2.1 React Error Boundary

- **新增文件**: `autonome-studio/src/components/chat/ClaudeErrorBoundary.tsx`
- **功能**:
  - 捕获子组件树中所有未处理的渲染错误
  - 显示友好回退 UI（错误图标 + 描述 + "重试"按钮 + "返回常规模式"按钮）
  - `onReset` 回调支持恢复到常规模式
- **集成位置**: `ChatStage.tsx` 中包裹 `<ClaudeChatStage />`

```tsx
// ChatStage.tsx 中的集成方式
if (chatMode === 'claude') {
  return (
    <ClaudeErrorBoundary onReset={() => setChatMode('normal')}>
      <ClaudeChatStage />
    </ClaudeErrorBoundary>
  );
}
```

### 2.2 SSE 断线重连

- **文件**: `autonome-studio/src/hooks/useClaudeChat.ts`
- **变更**:
  - `sendMessage` 中的 SSE reader 循环增加指数退避重连（1s→2s→4s→8s→16s，最多 5 次）
  - 发送前通过 `GET /api/claude/containers/stats` 检查 Agent 存活状态
  - 新增 `reconnect_attempt` 事件类型通知 UI 层

### 2.3 优雅降级状态

- **文件**: `autonome-studio/src/components/chat/ClaudeChatStage.tsx`
- **新增状态**:

| 状态 | 触发条件 | UI |
|------|---------|-----|
| `loading` | 正在获取会话列表 | 骨架屏 + "正在连接 Claude Agent..." |
| `empty` | 无任何会话 | 居中引导："创建新会话开始分析" + 创建按钮 |
| `error` | API 调用失败 | 错误提示 + "重试"按钮 |

### 2.4 handleSend 前置检查

- **文件**: `autonome-studio/src/components/chat/ClaudeChatStage.tsx`
- **变更**:
  - 无 activeSession 时自动调用 `POST /api/claude/sessions` 创建
  - 无 activeConversation 时自动调用 `POST /api/claude/sessions/{sid}/conversations` 创建
  - 两者就绪后再发送消息

### Stage 2 验证标准

- [ ] 后端不可用时切换到 Claude 模式显示加载态而非白屏
- [ ] API 调用失败后显示错误回退 UI，可点击重试
- [ ] 容器启动期间显示连接中状态
- [ ] SSE 断开后自动展示重连提示

---

## Stage 3 — 测试覆盖

**目标**: 建立回归保护，目标覆盖率 ≥80%。

### 3.1 后端测试

#### 单元测试 — `autonome-backend/tests/test_claude_models.py`

| 测试用例 | 覆盖内容 |
|---------|---------|
| `test_create_claude_session_defaults` | ClaudeSession 默认值（title="新会话", status="active"） |
| `test_create_claude_message_events_serialization` | ClaudeMessage.events_json JSONB 序列化/反序列化 |
| `test_claude_task_status_lifecycle` | ClaudeTask 状态机：pending→running→completed/failed |
| `test_claude_container_idle_detection` | ClaudeContainer 空闲判定（updated_at 超过 30min） |
| `test_plan_data_serialization_camelcase` | PlanEvent.to_json() 输出字段为 camelCase |
| `test_event_types_all_to_json` | 10 种事件类型 to_json() 不抛异常 |

#### 集成测试 — `autonome-backend/tests/test_claude_api.py`

| 测试用例 | 覆盖内容 |
|---------|---------|
| `test_create_session_requires_auth` | POST /sessions 未认证返回 401 |
| `test_create_and_list_sessions` | 创建会话→列表包含新会话 |
| `test_delete_session` | 删除会话→列表不再包含 |
| `test_search_skills_with_keyword` | GET /skills/search?q=fastqc 返回匹配结果 |
| `test_search_skills_no_results` | 无匹配关键词返回空列表 |
| `test_workspace_files_no_container` | 无活跃容器时优雅返回空列表 |
| `test_submit_task_no_container` | 无容器时提交任务返回适当错误 |
| `test_container_pool_stats` | GET /containers/stats 返回正确统计 |
| `test_sse_message_stream_content_type` | POST .../messages 返回 Content-Type: text/event-stream |

### 3.2 前端测试

#### Store 测试 — `useClaudeStore.test.ts`

| 测试用例 | 覆盖内容 |
|---------|---------|
| `test_initial_state` | sessions=[], activeSessionId=null, isStreaming=false |
| `test_add_session` | addSession 后 sessions 包含新会话 |
| `test_remove_session` | removeSession 后 sessions 不包含已删除会话 |
| `test_remove_active_session` | 删除活跃会话→activeSessionId 置空 |
| `test_append_stream_content` | 多次调用→streamEvents 按序累积 |
| `test_reset_stream` | resetStream 清空 streamEvents + isStreaming=false |

#### Hook 测试 — `useClaudeChat.test.ts`

| 测试用例 | 覆盖内容 |
|---------|---------|
| `test_send_message_blocked_when_no_session` | activeSessionId=null 时不发送 |
| `test_send_message_blocked_when_streaming` | isStreaming=true 时不重复发送 |
| `test_cancel_stream_aborts_fetch` | cancelStream 触发 AbortController.abort() |
| `test_load_messages_populates_store` | loadMessages 正确设置消息到 store |

#### 组件测试

| 文件 | 测试用例 | 覆盖类型 |
|------|---------|---------|
| `ThinkingBlock.test.tsx` | 渲染思考内容、折叠/展开切换、空内容不渲染 | 正常+边界 |
| `PlanCard.test.tsx` | 步骤列表渲染、确认按钮回调、disabled 下按钮不可点击 | 正常+交互 |
| `TaskCard.test.tsx` | 四种状态渲染颜色正确、pending/running 触发轮询、completed/failed 停止轮询 | 正常+异步 |
| `ToolUseBlock.test.tsx` | tool_use 展开显示输入、tool_result 成功/失败颜色区分 | 正常+边界 |
| `ClaudeErrorBoundary.test.tsx` | 子组件抛错→回退 UI→点击重试→重新渲染 | 错误路径 |

#### E2E 冒烟测试 — Playwright

| 测试用例 | 覆盖内容 |
|---------|---------|
| `test_switch_claude_mode_shows_layout` | 点击"Claude模式"→三栏布局可见 |
| `test_create_session_updates_sidebar` | 点击"新建会话"→侧边栏出现新会话 |
| `test_api_error_shows_fallback` | 模拟 API 500→错误回退 UI 显示 |

### 覆盖率目标

| 模块 | 目标 | 指标 |
|------|------|------|
| `claude.py` models | ≥85% | 行覆盖率 |
| `claude_session_manager.py` | ≥80% | 行覆盖率 |
| `event_types.py` | ≥90% | 行覆盖率 |
| `useClaudeStore.ts` | 100% | 函数覆盖 |
| `useClaudeChat.ts` | ≥80% | 分支覆盖 |
| 前端组件 | ≥75% | 核心逻辑覆盖 |

---

## Stage 4 — 架构优化

**目标**: 代码质量提升，长期可维护。

### 4.1 前端组件拆分

`ClaudeChatStage.tsx`（当前 319 行）拆分为 4 个子组件：

```
components/chat/claude/
├── ClaudeChatStage.tsx          # 主容器 ~80行
├── ClaudeSessionSidebar.tsx     # 左栏会话列表 ~100行 (新增)
├── ClaudeMessageList.tsx        # 中间消息时间线 ~80行 (新增)
├── ClaudeInputArea.tsx          # 底部输入区 ~50行 (新增)
├── ClaudeErrorBoundary.tsx      # 错误边界 (Stage 2 新增)
├── ClaudePreview.tsx            # 右栏预览 (不变)
├── ThinkingBlock.tsx            # (不变)
├── PlanCard.tsx                 # (不变)
├── TaskCard.tsx                 # (不变)
└── ToolUseBlock.tsx             # (不变)
```

### 4.2 类型体系统一

- 新增 `autonome-studio/src/types/claude.ts` 集中管理所有 Claude 类型
- 后端 `event_types.py` 所有 `to_json()` 输出统一 camelCase
- 前端类型与后端 JSON 输出完全对齐，消除所有 as 强制类型转换

### 4.3 API 响应格式统一

所有 Claude API 端点统一使用项目标准 `ApiResponse<T>` 信封：

```typescript
interface ClaudeSessionListResponse {
  success: true
  data: { sessions: ClaudeSession[] }
  meta?: { total: number }
}
```

### 4.4 后端微小重构

- `claude_container_pool.py`: `pre_warm()` 创建容器时不设 session_id；`allocate()` 中首次设置
- `claude_manager.py`: CLI `--model` 参数可从环境变量 `CLAUDE_MODEL` 配置（默认 sonnet）

### Stage 4 验证标准

- [ ] 每个文件 ≤200 行
- [ ] 前后端类型对齐，零 snake_case/camelCase 不一致
- [ ] Claude API 响应格式与项目其他模块一致

---

## 实施顺序与依赖

```
Stage 1 (止血) ──→ Stage 2 (加固) ──→ Stage 3 (测试) ──→ Stage 4 (优化)
     │                   │                   │                   │
     │ 依赖: 无          │ 依赖: S1 完成     │ 依赖: S2 完成     │ 依赖: S3 完成
     │ 预估: 4-6h        │ 预估: 3-4h        │ 预估: 6-8h        │ 预估: 3-4h
```

每个阶段独立可验收，前一阶段完成后才能开始下一阶段。

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| Sandbox 镜像构建失败（网络/依赖） | 使用 npm registry mirror；Dockerfile 中预先锁定版本 |
| 数据库迁移冲突 | 先在 staging 环境验证 `alembic upgrade head` |
| TypeScript 类型修复引入新错误 | Stage 1 仅添加 index signature，不改变现有类型结构 |
| 组件拆分破坏现有功能 | Stage 4 仅在测试覆盖到位后进行；纯机械提取，不改逻辑 |
| SSE 重连导致消息重复 | 后端去重基于 message_id；前端幂等合并 |
