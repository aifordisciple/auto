# AUTONOME STUDIO 开发规范与约定

> **文档版本**: 1.0.0
> **更新日期**: 2026-03-21
> **适用范围**: 所有代码提交必须遵循本规范

---

## 目录

1. [后端规范 (Python/FastAPI)](#1-后端规范-pythonfastapi)
2. [前端规范 (Next.js/TypeScript)](#2-前端规范-nextjstypescript)
3. [React Resizable Panels 注意事项](#3-react-resizable-panels-注意事项)
4. [环境变量使用规范](#4-环境变量使用规范)
5. [Probe Tools 使用模式](#5-probe-tools-使用模式)
6. [强制注释铁律](#6-强制注释铁律)

---

## 1. 后端规范 (Python/FastAPI)

### 1.1 日志记录

<pattern>
**使用 Loguru 进行日志记录**

```python
from loguru import logger

# 正确示例
log.info("Processing task {task_id}", task_id=task_id)
log.error("Failed to process: {error}", error=str(e))

# 错误示例 - 绝对禁止
print("Processing task")  # 禁止使用 print()
```
</pattern>

<rule>
- **禁止**在生产代码中使用 `print()`
- **必须**使用 `log.info()`, `log.error()`, `log.warning()`, `log.debug()`
- 日志消息应包含足够的上下文信息（如 task_id, user_id）
</rule>

### 1.2 ORM 与数据库

<pattern>
**使用 SQLModel ORM + Alembic 迁移**

```python
from sqlmodel import SQLModel, Field

class Task(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    status: str = Field(default="pending")
```
</pattern>

<command>
```bash
# 创建迁移
cd autonome-backend && alembic revision --autogenerate -m "add task table"

# 执行迁移
alembic upgrade head
```
</command>

### 1.3 认证机制

- **JWT Token**: HS256 算法
- **有效期**: 7 天
- **自动刷新**: 前端检测过期前自动刷新

---

## 2. 前端规范 (Next.js/TypeScript)

### 2.1 路径别名

<pattern>
**使用 `@/*` 路径别名**

```typescript
// 正确示例
import { useAuthStore } from '@/store/useAuthStore';
import { Button } from '@/components/ui/Button';

// 错误示例
import { useAuthStore } from '../../../store/useAuthStore';
```
</pattern>

### 2.2 状态管理

<pattern>
**使用 Zustand 进行全局状态管理**

```typescript
// store/useAuthStore.ts
import { create } from 'zustand';

interface AuthState {
  user: User | null;
  token: string | null;
  login: (user: User, token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  login: (user, token) => set({ user, token }),
  logout: () => set({ user: null, token: null }),
}));
```
</pattern>

<rule>
- **禁止**使用 React Context API 进行全局状态管理
- **必须**使用 Zustand 管理跨组件共享状态
- 局部状态可使用 `useState` 或 `useReducer`
</rule>

### 2.3 深色模式

<pattern>
**默认深色模式**

```html
<!-- layout.tsx -->
<html lang="zh" className="dark">
  <body>{children}</body>
</html>
```
</pattern>

### 2.4 TypeScript 严格模式

<rule>
- **禁止**使用 `any` 类型
- 必须定义明确的类型或使用 `unknown` 配合类型守卫
</rule>

<anti-pattern>
```typescript
// 错误示例
const data: any = fetchData();

// 正确示例
interface DataResponse {
  id: string;
  name: string;
}
const data: DataResponse = fetchData();
```
</anti-pattern>

---

## 3. React Resizable Panels 注意事项

<critical>
**版本 v4 的 breaking change**

面板尺寸必须使用字符串格式，不能使用数字。
</critical>

```typescript
// 错误示例 - 会导致运行时错误
<Panel defaultSize={15} />
<Panel minSize={5} />

// 正确示例
<Panel defaultSize="15%" />
<Panel minSize="5%" />
```

---

## 4. 环境变量使用规范

### 4.1 代码输出目录

<pattern>
**使用 `TASK_OUT_DIR` 环境变量**

在生成写入文件的代码时，必须使用环境变量获取输出目录：

```python
import os

# 正确示例
out_dir = os.environ.get('TASK_OUT_DIR', '/workspace/project_{id}/results/default')
os.makedirs(out_dir, exist_ok=True)

# 错误示例 - 禁止硬编码路径
out_dir = 'results/'  # 禁止！
```
</pattern>

### 4.2 可用环境变量

| 变量名 | 描述 | 示例值 |
|--------|------|--------|
| `PROJECT_ID` | 当前项目 ID | `42` |
| `TASK_ID` | 当前任务 ID | `abc123` |
| `TASK_OUT_DIR` | 输出目录 | `/workspace/project_42/results/task_abc123` |
| `USER_ID` | 当前用户 ID | `user_001` |

---

## 5. Probe Tools 使用模式

<critical>
**处理数据前必须先探测**

在处理任何数据文件之前，Agent **必须**调用探针工具了解数据结构，**禁止**猜测列名或文件路径。
</critical>

### 5.1 可用探针工具

| 工具名 | 功能 | 使用场景 |
|--------|------|----------|
| `peek_tabular_data` | 预览表格文件（CSV/TSV） | 处理表格数据前，了解表头和维度 |
| `scan_workspace` | 扫描目录结构 | 需要找文件但不确定位置 |
| `inspect_h5ad` | 解析 .h5ad 单细胞数据 | 处理单细胞 AnnData 数据前 |
| `inspect_fastq` | 预览 FASTQ 测序文件 | RNA-Seq、单细胞等测序数据预览 |
| `inspect_bam` | 预览 BAM 比对文件 | 比对结果快速预览 |

### 5.2 使用流程

```
用户: "帮我分析这个表格数据"
    │
    ▼
Agent 自动调用 peek_tabular_data
    │
    ▼
获取表头、维度、数据预览
    │
    ▼
根据实际结构制定处理策略
    │
    ▼
输出代码和策略卡片
```

---

## 6. 强制注释铁律

<critical>
**最不可侵犯的底线**

AI 助手在生成、重构或迭代代码时，绝不允许删除或精简原有注释！
</critical>

### 6.1 极其详细的逻辑注释

每一段核心业务逻辑、复杂算法，**必须**在代码内部包含极其详尽的自然语言说明：

- 注释必须深入阐述"**为什么**采用这种架构"
- 说明核心依赖和约束条件
- 不仅仅是描述"代码做了什么"

### 6.2 严禁删除历史注释

<rule>
- 在进行任何代码修改、重构、组件抽取或 Bug 修复时，**绝不允许**删除原有注释
- 如果业务逻辑发生变更，**必须**同步且完整地更新对应的注释说明
- 绝不允许出现"代码更新，文档腐烂"的情况
</rule>

### 6.3 架构级全局说明

<pattern>
**Design Doc First**

对于任何新建的模块或大重构，必须先在文件头部撰写宏观的 Markdown 格式设计规范：

```python
"""
模块名称: xxx_processor.py
设计日期: 2026-03-21
设计者: xxx

## 设计目标
1. ...
2. ...

## 核心算法
- ...

## 依赖关系
- ...
"""
```
</pattern>

### 6.4 违规判定

如果在代码输出中，原有的详细注释被替换为了 `//... existing code...`，或者因为"认为不重要"而被直接抹除，该次代码提交将被视为**无效并被直接驳回**！

---

## 反模式汇总

<anti-pattern>
以下行为**绝对禁止**：

| 反模式 | 正确做法 |
|--------|----------|
| `any` 类型 | 定义明确的接口/类型 |
| `console.log()` | 使用 logger 或移除 |
| `print()` | 使用 `log.info()` |
| 硬编码中文到 matplotlib | 使用英文或变量 |
| 删除原有注释 | 同步更新注释 |
| 猜测列名/文件路径 | 先调用探针工具 |
</anti-pattern>

---

*文档生成时间: 2026-03-21*
*维护者: Autonome Team*