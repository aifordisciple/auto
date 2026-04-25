# 意图标签设计文档

**日期**: 2026-04-25
**状态**: 已批准

## 概述

在 AI 回复消息的左上角（头像右侧）添加一个小巧的渐变胶囊标签，显示当前意图的精简短名。标签使用语义分组配色，让用户一眼感知意图类别。

## 视觉规格

- **位置**: AI 头像右侧，消息内容上方
- **样式**: 渐变色胶囊，`border-radius: 12px`，`font-size: 11px`，`padding: 2px 10px`
- **投影**: 同色系微投影 `box-shadow: 0 1px 3px rgba(color, 0.3)`
- **字重**: `font-weight: 500`

## 语义分组配色

| 分组 | 渐变色 | 意图标签 |
|------|--------|----------|
| 分析类 | `#6366f1 → #818cf8` (靛蓝) | 探查、可视化、即席、文献 |
| 执行类 | `#10b981 → #34d399` (翠绿) | 执行、锻造、工作流、版本 |
| 交互类 | `#f59e0b → #fbbf24` (琥珀) | 问答、协作、指令 |
| 异常类 | `#ef4444 → #f87171` (玫红) | 诊断、运维 |

## 意图 → 标签映射

| IntentType | 标签文案 | 分组 |
|------------|----------|------|
| DATA_PROBE | 探查 | 分析 |
| VISUAL_TWEAK | 可视化 | 分析 |
| ADHOC_ANALYSIS | 即席 | 分析 |
| LITERATURE | 文献 | 分析 |
| EXPLICIT_EXEC | 执行 | 执行 |
| SKILL_FORGE | 锻造 | 执行 |
| WORKFLOW | 工作流 | 执行 |
| VERSION_CTRL | 版本 | 执行 |
| GENERAL_CHAT | 问答 | 交互 |
| COLLABORATION | 协作 | 交互 |
| SYSTEM_MACRO | 指令 | 交互 |
| DIAGNOSTIC | 诊断 | 异常 |
| SYSTEM_ASSET | 运维 | 异常 |

## 数据流

```
后端 SSE intent 事件
  → useChatSync 捕获 intent_data
  → 提取首个节点的 intent 类型
  → 映射为 { label, group } 存入 Message.intentLabel
  → MemoizedMessageItem 渲染胶囊标签
```

## 涉及文件

### 前端

1. **新增**: `autonome-studio/src/components/chat/IntentTag.tsx`
   - 纯展示组件，接收 `intentType: string`，渲染胶囊标签
   - 包含映射表 `INTENT_CONFIG`：intentType → { label, gradient, shadow }

2. **修改**: `autonome-studio/src/store/useChatStore.ts`
   - `Message` 类型新增 `intentLabel?: { type: string; label: string; group: string }`

3. **修改**: `autonome-studio/src/hooks/useChatSync.ts`
   - 在处理 `intent` 事件时，提取意图类型并存入最近 assistant 消息的 `intentLabel`

4. **修改**: `autonome-studio/src/components/chat/MemoizedMessageItem.tsx`
   - assistant 消息渲染时，在头像右侧插入 `<IntentTag />`

### 后端

无需修改。后端已通过 SSE 推送 `intent` 事件，包含完整的 DAG 数据（含 intent 类型）。

## 边界情况

- **无意图数据**: 不渲染标签（旧消息、非路由消息）
- **未知意图类型**: 渲染为灰色胶囊 + 原始 intent 字符串
- **流式消息**: intent 事件在 assistant 消息之前到达，需在消息创建后回填
