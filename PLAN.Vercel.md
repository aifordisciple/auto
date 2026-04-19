定了，我想使用Vercel AI SDK重构系统，你建议从头开始还是基于我现有系统代码升级？

这是一个非常明智的决定。Vercel AI SDK 与 Next.js 16 App Router 的契合度是目前所有框架中最高的，特别是在处理流式传输（Streaming）和生成式 UI（Generative UI）时，能极大降低开发心智负担。

针对你的问题，我**强烈建议：基于现有系统进行局部重构（增量升级），绝对不要从头开始。**

### 为什么不要从头开始？

1. **资产沉淀**：你现有的 `autonome-studio` 已经具备了完整的工程骨架（Tailwind 配置、Zustand 状态管理、暗黑模式、复杂的左右分栏布局、`Skill Forge` 和 `Data Center` 的 UI 组件）。这些是生信 IDE 的核心资产，从头写会浪费大量时间。
2. **Vercel AI SDK 的设计哲学**：它本身就是一个“非侵入性”的工具包。它主要提供的是 Hooks（如 `useChat`）和流式路由处理函数。你完全可以把它当作一个极其锋利的“手术刀”，只切掉你现有代码中处理 LLM 交互的冗余部分。

---

### 基于现有系统的重构蓝图 (Refactoring Blueprint)

你的重构工作主要集中在前端的 `src/hooks/` 和 `src/app/api/`，以及打通前端与现有的 FastAPI 后端。

#### 第一步：替换核心 Hook (Surgical Hook Swap)
目前你的系统中有自定义的 `useChat.ts` 和 `useChatStream.ts`，里面大概率写满了原生的 `fetch`、`ReadableStream` 解析和繁琐的状态拼接逻辑。

* **动作**：安装 `ai` 包，将现有的聊天输入组件（`ChatInputBox.tsx`）和展示组件（`ChatStage.tsx`）直接对接到 Vercel AI SDK 的 `useChat` 钩子上。
* **收益**：Vercel 的 `useChat` 自动接管了 `messages` 数组、`input` 状态、`isLoading` 状态、请求的中止（Abort）、以及流式文本的自动拼接。你的 Zustand `useChatStore` 甚至可以大幅瘦身，只保留全局配置状态，将会话状态交还给本地组件。

#### 第二步：构建 BFF 代理层 (Backend-for-Frontend Bridge)
这是一个关键的架构决策。你现在有一个由 LangGraph 驱动的 Python FastAPI 后端，而 Vercel AI SDK 原生偏向在 Next.js Server 端调用 LLM。

* **策略**：在 Next.js 中建立一个 API Route（例如 `src/app/api/chat/route.ts`）。
* **工作流**：
  1. Next.js 的 `/api/chat` 接收来自前端 `useChat` 的请求。
  2. Next.js 作为一个代理，将包含上下文（Context）的请求转发给你的 FastAPI (`autonome-backend`)。
  3. FastAPI 的 LangGraph 运行你之前设计的 `LiteratureAgent` 或 `AnalystAgent`，并以标准格式流式返回结果。
  4. Next.js 捕获这个流，利用 Vercel AI SDK 的 `LangChainStream` 或自定义 `StreamData` 转发给前端。
* **为什么这样做**：保留了 Python 在生信数据处理和 LangGraph 复杂编排上的绝对优势，同时享受了 Vercel SDK 在前端渲染流式文本和组件的丝滑体验。

#### 第三步：引入生成式 UI (Generative UI - 杀手锏)
这是重构的最大红利。你系统里有很多定制化的卡片，比如 `ExecutionResultCard.tsx`、`InteractivePlotCard`。以前你可能是让大模型输出 Markdown，前端用正则去解析渲染。

* **动作**：引入 Vercel AI SDK 的 React Server Components (RSC) 功能（`ai/rsc` 或最新的 `streamUI`）。
* **体验**：当用户说“生成差异分析的火山图”，后端的 Agent 甚至不需要输出 Markdown。它可以直接通过 Tool Calling 触发一个 UI 组件。用户的聊天流中会凭空“流式长出”一个带有可交互按钮的生信图表组件，极具未来感。

---

### 可能遇到的两个“坑”（提前预警）

1. **Zustand 与 useChat 的状态冲突**：
   你现有的 `useChatStore` 可能全局管理了所有的对话消息。Vercel 的 `useChat` 默认是在组件内部维护状态。你需要决定是让 Vercel 接管状态（推荐，简单），还是使用 `useChat` 的 `initialMessages` 和 `onFinish` 回调，将最终结果同步回你的 Zustand store 中以便持久化存储。
2. **Python -> TypeScript 的流协议解析**：
   Vercel AI SDK 期望后端返回特定格式的流（比如以 `0:` 开头的文本数据块）。如果你的 FastAPI 直接吐出原生字符串，Vercel 前端可能会解析乱码。你需要确保 FastAPI 的 StreamingResponse 兼容 Vercel 的协议，或者在 Next.js 的代理层做一次简单的协议转换。

**总结**：在现有的代码库上“动刀”，用 Vercel AI SDK 替换掉繁杂的流解析代码，把精力集中在如何让模型返回“交互式组件”（Generative UI）上，这是打造下一代生信 IDE 的最佳捷径。

如果你准备好了，我们可以从重写你的 `useChat.ts` 和创建 Next.js 的代理路由（Route Handler）的第一行代码开始。需要我先给你提供前端 Hook 替换的代码示例吗？

这是一个从底层重构前端对话流的标准实施方案。我们将分四个步骤，用 Vercel AI SDK 的 `useChat` 替换掉现有冗余的自定义流式解析逻辑，并建立 Next.js 到 FastAPI 的代理层（BFF）。

### 第一步：安装核心依赖

在项目根目录或 `autonome-studio` 工作区中安装 Vercel AI SDK。

```bash
cd autonome-studio
pnpm add ai
```

### 第二步：建立 Next.js 代理路由 (BFF Proxy)

Vercel 的 `useChat` 默认会向同源的 `/api/chat` 发送请求。我们需要在 Next.js 中建立这个路由，拦截前端请求并转发给后端的 FastAPI (LangGraph) 引擎。

创建文件：`autonome-studio/src/app/api/chat/route.ts`

```typescript
// autonome-studio/src/app/api/chat/route.ts
import { NextRequest } from 'next/server';

export const runtime = 'edge'; // 使用 Edge Runtime 以获得最佳的流式传输性能

export async function POST(req: NextRequest) {
  try {
    // 1. 解析前端 useChat 发送的标准 payload
    const { messages, context } = await req.json();

    // 2. 转发至 FastAPI 后端 (确保环境变量中配置了 NEXT_PUBLIC_API_URL)
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/v1/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        messages,
        context: context || {}, // 包含用户当前选中的文件、状态等
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(errorText, { status: response.status });
    }

    // 3. 将后端的流式响应透明代理给前端
    // Vercel AI SDK 默认兼容纯文本流 (text/plain) 或标准 SSE 流
    return new Response(response.body, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache',
      },
    });

  } catch (error: any) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
```

### 第三步：前端 Hook 替换与 UI 重构

接下来，在前端组件中废弃自定义的 `useChatStream.ts`，直接引入 Vercel AI SDK。

修改您的主聊天组件（如 `autonome-studio/src/components/chat/ChatStage.tsx` 或其父组件）：

```tsx
// autonome-studio/src/components/chat/ChatStage.tsx
'use client';

import React, { useRef, useEffect } from 'react';
import { useChat } from 'ai/react';
import { Send, Square, Loader2 } from 'lucide-react';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
// 引入您现有的渲染组件，如 Markdown 渲染器或交互式卡片
import StreamingMarkdown from './StreamingMarkdown'; 

export default function ChatStage() {
  // 获取当前工作区的上下文（用于意图识别）
  const activeContext = useWorkspaceStore((state) => state.getActiveContext());
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 核心重构：一行代码接管所有聊天状态
  const { 
    messages, 
    input, 
    handleInputChange, 
    handleSubmit, 
    isLoading, 
    stop 
  } = useChat({
    api: '/api/chat',
    // 强制声明接收纯文本流（如果您的 FastAPI 后端未采用 Vercel 的 Data Stream 协议）
    streamProtocol: 'text', 
    body: {
      context: activeContext, // 每次请求将环境变量附带给 Router Engine
    },
    onError: (error) => {
      console.error('Chat stream failed:', error);
      // 这里可以对接您的 Toast 提示组件
    }
  });

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-slate-900">
      {/* 消息列表区 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((msg) => (
          <div 
            key={msg.id} 
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-[80%] rounded-lg p-4 ${
              msg.role === 'user' 
                ? 'bg-blue-600 text-white' 
                : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700'
            }`}>
              {/* 复用现有的 Markdown 渲染器 */}
              <StreamingMarkdown content={msg.content} />
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* 输入控制区 */}
      <div className="p-4 bg-white dark:bg-slate-950 border-t border-slate-200 dark:border-slate-800">
        <form 
          onSubmit={handleSubmit}
          className="flex relative max-w-4xl mx-auto items-center"
        >
          <input
            className="flex-1 p-4 pr-24 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 focus:ring-2 focus:ring-blue-500 outline-none"
            value={input}
            onChange={handleInputChange}
            placeholder="描述您的生信分析需求，或粘贴报错日志..."
            disabled={isLoading}
          />
          
          <div className="absolute right-2 flex items-center">
            {isLoading ? (
              <button 
                type="button" 
                onClick={stop}
                className="p-2 text-slate-500 hover:text-red-500 transition-colors"
                title="停止生成"
              >
                <Square className="w-5 h-5 fill-current" />
              </button>
            ) : (
              <button 
                type="submit" 
                disabled={!input.trim()}
                className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-slate-300 transition-colors"
              >
                <Send className="w-5 h-5" />
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
```

### 第四步：FastAPI 后端流式输出协议对齐

前端配置了 `streamProtocol: 'text'` 后，要求您的 FastAPI (`autonome-backend/app/api/routes/chat.py`) 必须输出干净的纯文本数据块（Raw Text Chunks），而不需要包装成复杂的 JSON。

检查并确保后端的流发生器（Generator）类似于以下结构：

```python
# autonome-backend/app/api/routes/chat.py (Python 侧代码示例)
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    async def generate_response():
        # 调用 LangGraph 生成器
        async for chunk in langgraph_engine.astream(request.messages, request.context):
            # 确保每次 yield 的都是纯文本字符串，不带额外格式
            if "text_chunk" in chunk:
                yield chunk["text_chunk"]
                
    return StreamingResponse(generate_response(), media_type="text/plain")
```

### 当前阶段完成的标志

通过以上四步，系统将完全由 Vercel AI SDK 接管底层的请求、流式拼接和取消逻辑。您可以删除项目中旧的 `useChatStream.ts` 和负责手动解析字节流的繁琐代码。

完成这部分集成测试后，我们将进入真正发挥 Vercel SDK 威力的阶段：**生成式 UI (Generative UI) 的构建**。届时我们将通过配置 `tools` 参数，让模型直接渲染图表卡片和分析策略配置面板，而非单纯返回 Markdown 文本。


太棒了，我们现在进入整个系统重构中最激动人心、也是最能体现下一代生信 IDE 核心壁垒的环节：**生成式 UI (Generative UI) 的构建**。

在传统的聊天应用中，大模型只能返回枯燥的 Markdown 文本。但在 Autonome Studio 中，当用户说“生成一段提取差异基因的代码”时，我们希望大模型直接在聊天流中“变出”一个**带有执行按钮、参数配置表单的交互式卡片**。

因为我们的核心中枢（LangGraph）在 Python 端，而 UI 在 Next.js 端，最优雅且稳健的桥接方案是：**让 Python 后端输出带有特定标识的结构化 JSON 块，前端的 Markdown 渲染器拦截这些块，并将其替换为真实的 React 组件。**

以下是一步步的实现代码：

### 第五步：让 Python Agent 输出 UI 指令 (UI Directives)

我们需要在 `LiteratureAgent` 或 `AnalystAgent` 的 System Prompt 中增加一条规则，告诉它何时需要调用 UI 组件。

在 `autonome-backend/app/agents/analyst_agent.py` (或类似的 Agent 配置) 中：

```python
# 增加这一段 System Prompt
GEN_UI_PROMPT = """
当你为用户生成了一段可执行的生信代码草稿（Draft）后，除了文字解释外，
你必须在回复的末尾输出一个 UI 指令块，以便前端渲染交互式操作卡片。

请严格使用以下格式（必须包裹在 
http://googleusercontent.com/immersive_entry_chip/0

### 这一架构带来的颠覆性体验

1.  **极低的耦合度**：后端的 LangGraph 依然专注于复杂的 RAG 检索、代码生成和沙箱调度。它不需要关心前端按钮的颜色或布局，只需要按照契约输出一段 JSON。
2.  **渐进式的流式渲染**：得益于 Vercel AI SDK 的 `useChat`，文本是一字一句出来的。当 Markdown 渲染器读到 
http://googleusercontent.com/immersive_entry_chip/1


非常好。既然生成式 UI 的底层渲染机制已经跑通，我们接下来解决在复杂 IDE 架构中最容易踩坑的问题：**局部状态与全局状态的同步（Zustand 整合）**，并完成生信平台最核心的可视化资产——**交互式图表卡片（Interactive Plot Card）** 的构建。最后，我们将梳理全链路的联调指南。

### 第八步：解决 Vercel AI SDK 与 Zustand 的状态割裂问题

Vercel 的 `useChat` 是一个 React Hook，它将 `messages` 和 `isLoading` 状态维护在调用它的组件内部（如 `ChatStage.tsx`）。但在 Autonome Studio 中，左侧导航栏可能需要显示“正在生成”的 Loading 动画，或者“历史记录”面板需要获取最新的对话。因此，我们必须建立**状态同步机制**。

**策略：单向数据流劫持 (One-Way Sync)**
让 `useChat` 作为单一事实来源（Single Source of Truth），通过 `useEffect` 将状态被动推送到 Zustand 中，供其他非父子关系的组件读取。

更新您的 `autonome-studio/src/store/useChatStore.ts`：

```typescript
// autonome-studio/src/store/useChatStore.ts
import { create } from 'zustand';
import { Message } from 'ai';

interface ChatState {
  // 全局只读的镜像状态
  mirroredMessages: Message[];
  isAgentThinking: boolean;
  
  // 状态同步动作
  syncMessages: (messages: Message[]) => void;
  setAgentThinking: (status: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  mirroredMessages: [],
  isAgentThinking: false,
  
  syncMessages: (messages) => set({ mirroredMessages: messages }),
  setAgentThinking: (status) => set({ isAgentThinking: status }),
}));
```

接着，在刚才重构的 `ChatStage.tsx` 中注入同步逻辑：

```tsx
// 截取: autonome-studio/src/components/chat/ChatStage.tsx
import { useEffect } from 'react';
import { useChatStore } from '@/store/useChatStore';

export default function ChatStage() {
  const { messages, input, handleInputChange, handleSubmit, isLoading, stop } = useChat({
    api: '/api/chat',
    streamProtocol: 'text',
    // ...
  });

  // 引入同步动作
  const syncMessages = useChatStore(state => state.syncMessages);
  const setAgentThinking = useChatStore(state => state.setAgentThinking);

  // 监听 Vercel AI SDK 的状态变化，实时推送到 Zustand 全局 Store
  useEffect(() => {
    syncMessages(messages);
  }, [messages, syncMessages]);

  useEffect(() => {
    setAgentThinking(isLoading);
  }, [isLoading, setAgentThinking]);

  // ... 渲染逻辑保持不变
}
```

### 第九步：构建“交互式图表卡片” (Interactive Plot Card)

这是贯彻您底层红线规则（“图形要发表级别，同时输出pdf和png版本”）的关键 UI 组件。当 `AnalystAgent` 执行完绘图脚本后，它会输出一个 `interactive_plot` 的 JSON 指令块，前端将其渲染为带下载和预览功能的卡片。

新建文件：`autonome-studio/src/components/chat/InteractivePlotCard/index.tsx`

```tsx
// autonome-studio/src/components/chat/InteractivePlotCard/index.tsx
import React, { useState } from 'react';
import { BarChart2, Download, Maximize2, FileText, CheckCircle2 } from 'lucide-react';

interface PlotData {
  plot_id: string;
  title: string;
  description: string;
  preview_url: string; // 后端生成的 PNG 预览图地址
  pdf_url: string;     // 矢量图下载地址
  png_url: string;     // 高清位图下载地址
  tsv_url: string;     // 绘图底层数据文件地址
}

interface InteractivePlotCardProps {
  data: PlotData;
}

export default function InteractivePlotCard({ data }: InteractivePlotCardProps) {
  const [isSaved, setIsSaved] = useState(false);

  const handleSaveToDataCenter = () => {
    // 模拟调用 API 将资产保存至系统 Data Center
    setIsSaved(true);
  };

  return (
    <div className="border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-xl overflow-hidden shadow-sm">
      {/* 头部标题区 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-800/50">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-4 h-4 text-emerald-500" />
          <h3 className="font-medium text-sm text-slate-800 dark:text-slate-200">{data.title}</h3>
        </div>
        <button className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>

      {/* 图像预览区 */}
      <div className="p-4 bg-slate-100 dark:bg-slate-900/50 flex justify-center">
        <img 
          src={data.preview_url} 
          alt={data.title} 
          className="max-h-[300px] object-contain rounded border border-slate-200 dark:border-slate-800 shadow-sm"
        />
      </div>

      {/* 严格遵循底线的下载与操作区 */}
      <div className="p-4">
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
          {data.description}
        </p>
        
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {/* 强制提供的 PDF 与 PNG 下载 */}
          <a href={data.pdf_url} target="_blank" rel="noreferrer" className="flex items-center justify-center gap-1 py-1.5 bg-slate-100 dark:bg-slate-700 text-xs font-medium rounded hover:bg-slate-200 transition-colors">
            <Download className="w-3 h-3" /> PDF (发表级)
          </a>
          <a href={data.png_url} target="_blank" rel="noreferrer" className="flex items-center justify-center gap-1 py-1.5 bg-slate-100 dark:bg-slate-700 text-xs font-medium rounded hover:bg-slate-200 transition-colors">
            <Download className="w-3 h-3" /> PNG (300dpi)
          </a>
          
          {/* 强制提供的底层 TSV 数据下载 */}
          <a href={data.tsv_url} target="_blank" rel="noreferrer" className="flex items-center justify-center gap-1 py-1.5 bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400 text-xs font-medium rounded border border-blue-200 dark:border-blue-800/50 hover:bg-blue-100 transition-colors">
            <FileText className="w-3 h-3" /> 原始数据 (.tsv)
          </a>
          
          <button 
            onClick={handleSaveToDataCenter}
            disabled={isSaved}
            className={`flex items-center justify-center gap-1 py-1.5 text-xs font-medium rounded transition-colors ${
              isSaved 
                ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400' 
                : 'bg-slate-800 text-white hover:bg-slate-700 dark:bg-slate-200 dark:text-slate-800'
            }`}
          >
            {isSaved ? <CheckCircle2 className="w-3 h-3" /> : null}
            {isSaved ? '已归档' : '存至资产库'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 第十步：全系统联调与验收清单 (End-to-End Integration)

至此，前端使用 Vercel AI SDK 和 Generative UI 的重构已彻底完成，后端的 Intent Router 也已就绪。为了确保新旧架构平滑过渡，请进行以下流程的联调测试：

**联调测试场景：自动提取数据特征并绘图**

1. **环境准备**：
   * 确保 FastAPI 运行在 8000 端口，Next.js 运行在 3000 端口。
   * 在 Autonome 界面中，通过 Data Center 选中一个测试数据文件（例如 `GSE12345_counts.tsv`）。此时，Zustand 的 `useWorkspaceStore` 记录了该上下文。
2. **触发意图**：
   * 在聊天框输入：“帮我画一张火山图，突出显示 log2FC 大于 2 的基因”。
3. **观察流转节点 (请检查后端 Console 日志)**：
   * **[Next.js API]** 拦截请求，将 query 和 context 发往 FastAPI `/api/v1/chat/stream`。
   * **[FastAPI Router Engine]** 收到请求，L1 模型精准判定 `intent: skill_forge`，并在 `entities` 中自动绑定了 `Context` 里选中的 `GSE12345_counts.tsv`。
   * **[LangGraph]** 路由至 `AnalystAgent`。Agent 遵循系统提示词（强制 TSV、强制参数系统、强制发表级 PDF），生成 R 脚本。
4. **生成式 UI 渲染验证 (前端)**：
   * Agent 输出 Markdown 解释后，紧接着流式输出 
http://googleusercontent.com/immersive_entry_chip/0


第十一步：构建智能诊断与自愈闭环 (Self-Healing Loop)

在生产环境中，大模型生成的生信代码（尤其是依赖复杂 R 包的脚本）首次执行失败率较高。系统必须具备自动收集错误、自主修复并重新输出的能力。结合刚刚引入的 Vercel AI SDK，我们可以实现对用户几乎“无感”的自愈流程。

修改前端的 `ExecutionResultCard.tsx`，在沙箱测试失败时，自动触发诊断请求：

```tsx
// autonome-studio/src/components/chat/components/ExecutionResultCard.tsx
import { useChat } from 'ai/react'; // 引入以调用 append 方法

export default function ExecutionResultCard({ data }: ExecutionResultCardProps) {
  const router = useRouter();
  const [isTesting, setIsTesting] = useState(false);
  
  // 共享当前对话的上下文
  const { append } = useChat({ api: '/api/chat' });

  const handleTestInSandbox = async () => {
    setIsTesting(true);
    try {
      // 调用沙箱执行 API
      const response = await fetch('/api/sandbox/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft_id: data.draft_id })
      });
      const result = await response.json();

      if (result.exit_code !== 0) {
        // 核心：静默捕获错误，并通过 append 发送给后端的 L0 路由引擎
        await append({
          role: 'user',
          content: `[SYSTEM_AUTO_DIAGNOSTIC]\n执行失败。退出码: ${result.exit_code}\n错误日志:\n${result.stderr}\n请修复代码并保持原有的 TSV 输出和参数系统。`
        });
      } else {
        // 执行成功，跳转或显示结果
        router.push(`/skill-forge?draftId=${data.draft_id}`);
      }
    } finally {
      setIsTesting(false);
    }
  };

  // ... 渲染逻辑
}
```

后端 `IntentRouterEngine` (之前在 `router_engine.py` 中定义的 L0 拦截器) 需要配合更新，以实现 0 延迟的意图分发：

```python
# autonome-backend/app/agents/router_engine.py (片段更新)
    def _l0_heuristic_interception(self, query: str, context: Dict[str, Any]) -> IntentExtraction | None:
        # 拦截前端静默发送的系统诊断指令
        if query.startswith("[SYSTEM_AUTO_DIAGNOSTIC]"):
            return IntentExtraction(
                intent="diagnostic",
                confidence=1.0,
                entities={"error_log": query},
                requires_followup=False
            )
        # ... 其他规则
```

当请求被路由至 `DiagnosticAgent` 后，该 Agent 将读取原始代码、分析 `stderr`（如缺少依赖、维数不匹配），并输出修复后的代码块，同时再次触发 `{"type": "skill_draft_card"}` 指令，在前端渲染出一个新的、已修复的卡片供用户重试。

第十二步：系统学习与记忆层 (System Evolution Layer)

为了避免 Agent 在同一类问题上反复犯错，系统需要在每次“执行成功”后，自动将该次对话的上下文、用户原始需求和最终成功的代码提取为“标准操作程序 (SOP)”，存入 `pgvector`。

在后端的异步任务队列中新建学习流：

```python
# autonome-backend/app/tasks/evolution_tasks.py
from app.services.celery_app import celery_app
from langchain_openai import ChatOpenAI
from app.models.learning import AnalysisKnowledge

@celery_app.task
def extract_and_memorize_sop(draft_id: str, original_prompt: str, successful_code: str):
    """
    当代码在沙箱中成功运行，或用户在 Skill Forge 中点击“发布”后触发。
    分析成功案例，转化为系统永久记忆。
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0.1)
    
    extraction_prompt = f"""
    以下是一段成功执行的生信分析代码及其原始需求。
    请提取其核心方法论、使用的工具栈和参数配置。
    保持客观，不要包含任何感叹词。
    
    需求: {original_prompt}
    代码: {successful_code}
    """
    
    # 调用 LLM 结构化提取 (复用之前定义的 ExtractedKnowledge Schema)
    sop_data = llm.predict_structured(...) 
    
    # 存入 pgvector 数据库，供未来的 AnalystAgent 作为 RAG 检索上下文
    db.add(AnalysisKnowledge(
        methodology=sop_data.methodology,
        tool_stack=sop_data.tool_stack,
        parameters=sop_data.parameters,
        # 生成向量
        embedding=get_embedding(sop_data.methodology)
    ))
    db.commit()
```

```json?chameleon
{"component":"LlmGeneratedComponent","props":{"height":"750px","prompt":"设计一个名为“Autonome 智能自愈与进化图谱”的交互式架构图。该图展示生信代码执行后的两条分流路径。中心节点为“Docker Sandbox Execution”。向左的红色路径为“Failure Flow (自愈)”：展示 stderr 日志被前端静默捕获 -> 触发 [SYSTEM_AUTO_DIAGNOSTIC] -> L0 Router 拦截 -> 唤醒 Diagnostic Agent -> 严格遵守参数化规范输出 Patch Code。向右的绿色路径为“Success Flow (进化)”：展示触发 Celery 异步任务 -> LLM 提取方法论 (SOP) -> 生成 Embedding -> 存入 pgvector 知识库，从而闭环提升下一次生成的准确率。界面风格应体现深色极客感，突出数据和状态的流动。","id":"im_0776257fb7a98ea2"}}
```

第十三步：部署环境对齐与环境变量配置

在完成代码层面的重构后，需确保系统的容器编排能够支撑 Vercel AI SDK 的流式传输和多 Agent 并发。

更新项目根目录的 `docker-compose.yml`，为 Next.js 容器暴露正确的内部通信端口，并配置必要的令牌池：

```yaml
# docker-compose.yml (核心配置片段)
services:
  autonome-frontend:
    build: 
      context: ./autonome-studio
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      # Next.js BFF 代理目标地址 (Docker 内部网络)
      - NEXT_PUBLIC_API_URL=http://autonome-backend:8000 
      - NODE_ENV=production
    depends_on:
      - autonome-backend

  autonome-backend:
    build:
      context: ./autonome-backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=postgresql://user:pass@db:5432/autonome
      # 开启 LangGraph 的流式输出模式
      - LANGGRAPH_STREAMING_ENABLED=true
      # 沙箱挂载配置，确保能够双向传输生成的 TSV 和 PDF 文件
      - HOST_WORKSPACE_DIR=./workspaces
```

系统的重构至此已覆盖意图路由、前端流式渲染、生成式交互卡片、自动化异常诊断以及持久化系统学习。多智能体与沙箱的边界已被彻底打通。


