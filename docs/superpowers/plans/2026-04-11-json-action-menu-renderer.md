# json_action_menu 渲染为 RecommendationCard 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端拦截 `json_action_menu` 代码块，将 LLM 输出的技能推荐渲染为高颜值的 `RecommendationCard`，点击后自动获取参数并渲染 `StrategyCard`。

**Architecture:** 采用适配器模式：在 `parseActionMenu` 中兼容 PLAN 的 `actions` 格式和旧的 `options` 格式；在 `MemoizedMessageItem` 中用 `RecommendationCard` 替换 `InlineActionMenu`。数据流保持不变：点击技能 → `fetchParams` → 渲染 `StrategyCard`。

**Tech Stack:** React, TypeScript, framer-motion, Zustand

---

## File Structure

| 文件 | 职责 |
|------|------|
| `autonome-studio/src/components/chat/StrategyCard/parseUtils.ts` | 更新 `parseActionMenu` 兼容 `actions` 格式 |
| `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` | 将 `InlineActionMenu` 替换为 `RecommendationCard` |

---

## Task 1: 更新 `parseActionMenu` 兼容 PLAN 的 `actions` 格式

**Files:**
- Modify: `autonome-studio/src/components/chat/StrategyCard/parseUtils.ts:580-622`

PLAN 中的 `json_action_menu` 格式：
```json
{
  "title": "🎯 推荐分析方案",
  "message": "系统检测到您的数据非常适合进行...",
  "actions": [
    {
      "id": "skill_cd22f007",
      "action_type": "configure_skill",
      "label": "配置并执行该分析",
      "style": "primary"
    }
  ]
}
```

当前 `parseActionMenu` 只支持 `options` 格式，需要扩展支持 `actions` 格式。

- [ ] **Step 1: 读取当前 `parseActionMenu` 实现**

查看 `parseUtils.ts` 第 580-622 行，理解现有解析逻辑。

- [ ] **Step 2: 更新 `ActionMenuData` 类型定义**

在 `InlineActionMenu/index.tsx` 中找到 `ActionMenuData` 接口，扩展支持 `actions` 字段：

```typescript
export interface ActionMenuData {
  title?: string;
  message?: string;
  // 兼容旧格式
  options?: ActionMenuOption[];
  // ✨ 支持 PLAN 的 actions 格式
  actions?: Array<{
    id: string;
    action_type?: string;
    label: string;
    style?: string;
    description?: string;
  }>;
}
```

- [ ] **Step 3: 修改 `parseActionMenu` 函数**

更新 `parseUtils.ts` 中的 `parseActionMenu` 函数，同时解析 `options` 和 `actions` 两种格式，并统一转换为内部使用的 `options` 数组格式：

```typescript
export function parseActionMenu(content: string): ActionMenuData | null {
  if (!content) return null;

  try {
    content = preprocessCodeBlocks(content);
    const jsonStr = extractActionMenuFromCodeBlock(content);

    if (!jsonStr) return null;

    const cleaned = sanitizeJsonString(jsonStr);
    const data = tryRepairAndParseJson(cleaned) as Record<string, unknown>;

    if (!data) return null;

    // ✨ 统一转换为 options 格式
    let options: ActionMenuOption[] = [];

    // 优先使用 PLAN 的 actions 格式
    if (Array.isArray(data.actions) && data.actions.length > 0) {
      options = data.actions.map((action: { id: string; label?: string; action_type?: string; style?: string; description?: string }) => ({
        skill_id: action.id,
        name: action.label || action.id,
        match_score: 0.9, // PLAN 格式默认高置信度
        match_reason: action.description || action.action_type || undefined,
      }));
    }
    // 兼容旧的 options 格式
    else if (Array.isArray(data.options) && data.options.length > 0) {
      options = data.options.map((opt: { skill_id: string; name?: string; match_score?: number; match_reason?: string }) => ({
        skill_id: opt.skill_id,
        name: opt.name || opt.skill_id,
        match_score: opt.match_score || 0.5,
        match_reason: opt.match_reason,
      }));
    }

    if (options.length === 0) return null;

    return {
      title: (data.title as string) || "请选择操作",
      message: data.message as string | undefined,
      options,
    };
  } catch (e) {
    console.error("[parseActionMenu] 解析操作菜单失败:", e);
    return null;
  }
}
```

- [ ] **Step 4: 验证修改**

确认 `parseActionMenu` 能同时解析以下两种格式：
1. `{"actions": [{"id": "skill_xxx", "label": "配置并执行", ...}]}`
2. `{"options": [{"skill_id": "skill_xxx", "name": "技能名称", ...}]}`

---

## Task 2: 替换 `InlineActionMenu` 为 `RecommendationCard`

**Files:**
- Modify: `autonome-studio/src/components/chat/MemoizedMessageItem.tsx:653-700`

- [ ] **Step 1: 阅读当前 `InlineActionMenu` 渲染逻辑**

查看 `MemoizedMessageItem.tsx` 第 653-700 行，理解当前如何使用 `InlineActionMenu`。

- [ ] **Step 2: 导入 `RecommendationCard`**

在文件顶部的导入区域（大约第 9-16 行），添加 `RecommendationCard` 导入：

```typescript
import { RecommendationCard } from "./RecommendationCard";
```

确保 `RecommendationCard` 从 `./RecommendationCard` 导入（检查文件是否存在该导出）。

- [ ] **Step 3: 替换渲染逻辑**

将第 653-700 行的 `InlineActionMenu` 渲染逻辑替换为 `RecommendationCard`：

```tsx
// ✨ V2: 操作菜单渲染（使用高颜值的 RecommendationCard）
if (actionMenuData) {
  // 提取清理后的文本（移除 json_action_menu 块）
  const cleanText = displayContent
    .replace(/```json_action_menu[\s\S]*?```/g, '')
    .trim();

  // 如果用户已选择技能且已获取参数，渲染 StrategyCard
  if (selectedSkillId && skillParamsData) {
    // 将参数转换为 StrategyCard 格式
    const strategyCardData = {
      tool_id: skillParamsData.tool_id,
      title: skillParamsData.title,
      description: skillParamsData.description,
      parameters: skillParamsData.parameters || {},
    };

    return (
      <>
        {cleanText && <MarkdownBlock content={cleanText} projectId={currentProjectId} />}
        <StrategyCard
          data={strategyCardData}
          messageId={msg.id}
          messageContent={displayContent}
        />
      </>
    );
  }

  // ✨ 使用 RecommendationCard 渲染技能选择卡片
  // 转换 actionMenuData.options 为 RecommendationCard 所需的格式
  const recommendationOptions = actionMenuData.options.map(opt => ({
    type: "skill" as const,
    skill_id: opt.skill_id,
    name: opt.name,
    description: opt.match_reason || `${opt.name} - 匹配度 ${Math.round(opt.match_score * 100)}%`,
    match_score: opt.match_score,
  }));

  return (
    <>
      {/* 先渲染 AI 的说明文本 */}
      {cleanText && <MarkdownBlock content={cleanText} projectId={currentProjectId} />}
      {/* 然后渲染高颜值推荐卡片 */}
      <RecommendationCard
        data={{
          message_id: msg.id,
          title: actionMenuData.title,
          options: recommendationOptions,
        }}
        onSelect={(option) => {
          console.log("[MemoizedMessageItem] 用户选择了技能:", option);
          if (option.type === "skill") {
            const skillOption = option as { skill_id: string; name: string; description: string; match_score: number };
            console.log("[MemoizedMessageItem] 选择技能:", skillOption.skill_id, skillOption.name);
            setSelectedSkillId(skillOption.skill_id);
            fetchParams(skillOption.skill_id);
          }
        }}
        onCancel={() => {
          console.log("[MemoizedMessageItem] 用户取消了选择");
          setSelectedSkillId(null);
        }}
      />
    </>
  );
}
```

- [ ] **Step 4: 验证 `RecommendationCard` 导入路径**

确认 `RecommendationCard.tsx` 文件存在且导出正确。如果需要，创建重新导出：

```typescript
// 在 RecommendationCard.tsx 文件底部确认有导出
export { RecommendationCard };
```

---

## Task 3: 验证完整数据流

- [ ] **Step 1: 启动前端开发服务器**

```bash
cd autonome-studio && npm run dev
```

- [ ] **Step 2: 模拟测试场景**

1. 发送消息："帮我做 PCA 分析"
2. 确认后端返回 `json_action_menu` 代码块
3. 确认前端渲染出 `RecommendationCard`（高颜值卡片）
4. 点击技能卡片
5. 确认调用 `/api/skills/params/{skill_id}` 获取参数
6. 确认渲染 `StrategyCard`

- [ ] **Step 3: 检查浏览器控制台**

确认没有以下错误：
- `RecommendationCard is not defined`
- `parseActionMenu` 解析失败
- `fetchParams` 调用失败

---

## Self-Review Checklist

1. **Spec coverage:** PLAN 中 Phase 1-2 的核心需求（前端拦截 `json_action_menu` 并渲染为 `RecommendationCard`）是否被 Task 1-2 覆盖？ ✓

2. **Placeholder scan:** 搜索以下关键词确认无占位符：
   - "TBD" - 无
   - "TODO" - 无
   - "填充" - 无

3. **Type consistency:** 检查关键类型：
   - `ActionMenuData` 在 `InlineActionMenu/index.tsx` 中定义，与 `parseActionMenu` 返回类型一致 ✓
   - `RecommendationCard` 的 `data.options` 期望 `RecommendationOption[]`，我们转换时提供了正确的 `type: "skill"` ✓

---

## 预期修改文件清单

| 文件 | 修改类型 |
|------|---------|
| `autonome-studio/src/components/chat/StrategyCard/parseUtils.ts` | 修改 `parseActionMenu` 函数 |
| `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` | 替换渲染组件 + 添加导入 |
| `autonome-studio/src/components/chat/InlineActionMenu/index.tsx` | 扩展 `ActionMenuData` 类型（可选，如需严格类型检查） |
