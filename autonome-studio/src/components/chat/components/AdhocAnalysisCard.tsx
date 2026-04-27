'use client'

import { useState, useRef, useEffect } from 'react'
import { ChevronDown, ChevronRight, Play, Star, Loader2, FileText, Eye } from 'lucide-react'

/**
 * JSON Schema 属性定义（与 ParameterProbingCard 一致）
 */
interface SchemaProperty {
  type: 'string' | 'number' | 'boolean'
  title?: string
  description?: string
  enum?: string[]
  default?: string | number | boolean
  minimum?: number
  maximum?: number
  step?: number
}

/**
 * 输出文件信息
 */
interface OutputFile {
  path: string
  name: string
  ext: string
  size: number
  preview: boolean
}

/**
 * 执行结果载荷
 */
interface ExecutionResult {
  status: 'success' | 'failed'
  output?: string | null
  error?: string | null
  exit_code: number
  language: string
  output_files?: OutputFile[]
}

/**
 * 即席分析卡片 Props
 */
export interface AdhocAnalysisCardProps {
  /** 策略描述 */
  strategy: string
  /** 生成的代码 */
  code: string
  /** 代码语言 */
  code_language: 'python' | 'r'
  /** 参数 Schema */
  parameter_schema: {
    type: string
    properties: Record<string, SchemaProperty>
    required?: string[]
  }
  /** 输入文件映射 */
  input_mapping: Record<string, string>
  /** 后端存储策略包的 message_id，执行时回传用于 Redis 查找 */
  message_id: string
  /** Vercel AI SDK addToolResult 回调 */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addToolResult: any
  /** ToolCall ID */
  toolCallId: string
}

/**
 * AdhocAnalysisCard — 即席交互式分析策略卡片。
 *
 * 当 adhoc_analysis_node 生成策略包后，通过 render_adhoc_card ToolCall
 * 触发前端渲染此卡片。用户可以在卡片上修改参数、查看代码、执行分析。
 *
 * 四个区域：
 * 1. 策略说明区（顶部，靛蓝色背景）
 * 2. 参数面板（中部，网格布局，动态表单）
 * 3. 代码预览区（折叠）
 * 4. 实时日志窗口（点击执行后展开）
 * 5. 操作区（底部，执行按钮 + 固化技能按钮）
 */
export function AdhocAnalysisCard({
  strategy,
  code,
  code_language,
  parameter_schema,
  input_mapping,
  message_id,
  addToolResult,
  toolCallId,
}: AdhocAnalysisCardProps) {
  // 从 Schema 默认值初始化表单状态
  const [formData, setFormData] = useState<Record<string, unknown>>(() => {
    const defaults: Record<string, unknown> = {}
    for (const [key, prop] of Object.entries(parameter_schema?.properties || {})) {
      if (prop.default !== undefined) {
        defaults[key] = prop.default
      }
    }
    return defaults
  })

  const [isExecuting, setIsExecuting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)
  const [showCode, setShowCode] = useState(false)
  const [editableCode, setEditableCode] = useState(code)
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null)
  // 实时日志流状态
  const [logLines, setLogLines] = useState<string[]>([])
  const [showLogWindow, setShowLogWindow] = useState(false)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // 日志窗口自动滚动到底部
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logLines])

  // 处理参数变化
  const handleParamChange = (key: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [key]: value }))
  }

  // 核心：点击执行，通过 SSE 流式接收 Docker 沙箱实时日志
  const handleExecute = async () => {
    if (isExecuting) return
    setIsExecuting(true)
    setExecutionResult(null)
    setLogLines([])
    setShowLogWindow(true)

    // 合并用户填写的参数和底层文件映射
    const finalPayload = {
      parameters: formData,
      inputs: input_mapping,
      code_snapshot: editableCode,
    }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null

    // 创建 AbortController 用于取消请求
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    try {
      const res = await fetch(`${apiUrl}/api/chat/adhoc/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message_id,
          payload: finalPayload,
        }),
        signal: abortController.signal,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        throw new Error(errData.detail || `请求失败 (${res.status})`)
      }

      // 读取 SSE 流
      const reader = res.body?.getReader()
      if (!reader) {
        throw new Error('浏览器不支持流式读取')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        // 保留最后一个可能不完整的行
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))
              handleSSEEvent(event)
            } catch {
              // 跳过解析失败的行
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setLogLines(prev => [...prev, '⏹️ 用户取消了执行'])
      } else {
        const message = err instanceof Error ? err.message : '执行失败'
        setLogLines(prev => [...prev, `❌ ${message}`])
        const failedResult: ExecutionResult = {
          status: 'failed',
          error: message,
          exit_code: -1,
          language: code_language,
        }
        setExecutionResult(failedResult)
        addToolResult({
          toolCallId,
          output: {
            action: 'execute',
            payload: finalPayload,
            execution_result: failedResult,
          },
        })
      }
    } finally {
      setIsExecuting(false)
      abortControllerRef.current = null
    }
  }

  // 处理 SSE 事件
  const handleSSEEvent = (event: Record<string, unknown>) => {
    switch (event.type) {
      case 'init':
        setLogLines(prev => [...prev, `🚀 ${event.message || '沙箱启动中...'}`])
        break
      case 'log':
        setLogLines(prev => [...prev, event.line as string])
        break
      case 'result': {
        const result: ExecutionResult = {
          status: (event.status as 'success' | 'failed') || 'failed',
          output: event.output as string | null,
          error: event.error as string | null,
          exit_code: event.exit_code as number,
          language: code_language,
          output_files: event.output_files as OutputFile[],
        }
        setExecutionResult(result)

        // 回传给 Vercel AI SDK
        addToolResult({
          toolCallId,
          output: {
            action: 'execute',
            payload: { parameters: formData, inputs: input_mapping, code_snapshot: editableCode },
            execution_result: result,
          },
        })

        // 推送日志行
        if (result.status === 'success') {
          setLogLines(prev => [...prev, `✅ 分析完成 (exit_code=${result.exit_code})`])
          if (result.output_files && result.output_files.length > 0) {
            setLogLines(prev => [
              ...prev,
              `📁 输出文件 (${result.output_files!.length} 个):`,
              ...result.output_files!.map(f => `   ${f.name} (${f.ext}, ${formatFileSize(f.size)})`),
            ])
          }
        } else {
          setLogLines(prev => [...prev, `❌ 执行失败 (exit_code=${result.exit_code})`])
        }
        break
      }
      case 'done':
        // 流结束
        break
    }
  }

  // 取消执行
  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }

  // 固化技能到资产库：调用后端 API 将策略包写入文件系统
  const handleSaveSkill = async () => {
    if (isSaving) return
    setIsSaving(true)
    setSaveResult(null)
    try {
      const skillName = prompt('请输入技能名称：', strategy.slice(0, 30))
      if (!skillName) {
        setIsSaving(false)
        return
      }
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null
      const res = await fetch(`${apiUrl}/api/chat/adhoc/save-skill`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
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

  return (
    <div className="my-3 rounded-xl border border-indigo-500/40 bg-white dark:bg-[#1a1a1c] shadow-sm overflow-hidden">
      {/* 1. 策略说明区（顶部，靛蓝色背景） */}
      <div className="bg-indigo-50/50 dark:bg-indigo-900/20 p-4 border-b border-indigo-100 dark:border-indigo-500/20">
        <h3 className="font-bold text-indigo-900 dark:text-indigo-300 flex items-center gap-2 text-sm">
          <span>⚡ 即席分析就绪</span>
        </h3>
        <p className="text-gray-600 dark:text-zinc-300 text-sm mt-2">{strategy}</p>
      </div>

      {/* 2. 参数面板（中部，网格布局，动态表单） */}
      {Object.keys(parameter_schema?.properties || {}).length > 0 && (
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {Object.entries(parameter_schema.properties).map(([key, field]) => (
            <div key={key} className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700 dark:text-zinc-300">
                {field.title || key}
                {parameter_schema.required?.includes(key) && <span className="ml-1 text-red-400">*</span>}
              </label>

              {/* enum → 下拉选择框 */}
              {field.enum ? (
                <select
                  value={String(formData[key] ?? field.default ?? '')}
                  onChange={(e) => handleParamChange(key, e.target.value)}
                  className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
                >
                  {field.enum.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              ) : field.type === 'boolean' ? (
                /* boolean → 开关 */
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={Boolean(formData[key] ?? field.default ?? false)}
                    onChange={(e) => handleParamChange(key, e.target.checked)}
                    className="h-4 w-4 rounded border-zinc-600 text-indigo-500 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-zinc-400">{field.description || '启用'}</span>
                </label>
              ) : field.type === 'number' ? (
                /* number → 数字输入框 */
                <input
                  type="number"
                  value={Number(formData[key] ?? field.default ?? 0)}
                  onChange={(e) => handleParamChange(key, Number(e.target.value))}
                  min={field.minimum}
                  max={field.maximum}
                  step={field.step ?? 1}
                  className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
                />
              ) : (
                /* string → 文本输入框 */
                <input
                  type="text"
                  value={String(formData[key] ?? field.default ?? '')}
                  onChange={(e) => handleParamChange(key, e.target.value)}
                  placeholder={field.description || `请输入 ${field.title || key}`}
                  className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* 3. 代码预览区（折叠） */}
      <div className="px-4">
        <button
          onClick={() => setShowCode(!showCode)}
          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline mb-2 flex items-center gap-1"
        >
          {showCode ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {showCode ? '隐藏底层代码' : '查看底层代码'}
        </button>
        {showCode && (
          <textarea
            value={editableCode}
            onChange={(e) => setEditableCode(e.target.value)}
            className="w-full text-xs bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto mb-4 font-mono resize-y min-h-[120px] max-h-96"
            spellCheck={false}
          />
        )}
      </div>

      {/* 4. 实时日志窗口（点击执行后展开，始终可见直到手动关闭） */}
      {showLogWindow && (
        <div className="mx-4 mb-4 border border-gray-700 rounded-md overflow-hidden">
          {/* 日志窗口标题栏 */}
          <div className="flex items-center justify-between bg-gray-800 px-3 py-2">
            <span className="text-xs font-medium text-gray-300 flex items-center gap-2">
              {isExecuting ? (
                <Loader2 size={12} className="animate-spin text-blue-400" />
              ) : executionResult ? (
                executionResult.status === 'success' ? (
                  <span className="text-green-400">✅ 执行日志</span>
                ) : (
                  <span className="text-red-400">❌ 执行日志</span>
                )
              ) : (
                <span className="text-gray-400">📋 执行日志</span>
              )}
            </span>
            <button
              onClick={() => setShowLogWindow(false)}
              className="text-gray-500 hover:text-gray-300 text-xs"
            >
              关闭
            </button>
          </div>
          {/* 日志内容区 */}
          <div
            ref={logContainerRef}
            className="bg-gray-900 text-gray-100 p-3 text-xs font-mono max-h-64 overflow-y-auto"
          >
            {logLines.length === 0 && isExecuting ? (
              <span className="text-gray-500">等待日志输出...</span>
            ) : (
              logLines.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))
            )}
          </div>
          {/* 取消按钮（仅在执行中显示） */}
          {isExecuting && (
            <div className="bg-gray-800 px-3 py-2 flex justify-end">
              <button
                onClick={handleCancel}
                className="text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded px-3 py-1 hover:bg-red-500/10 transition-colors"
              >
                ⏹️ 取消执行
              </button>
            </div>
          )}
        </div>
      )}

      {/* 5. 结果区（执行完成后显示在日志窗口下方） */}
      {executionResult && (
        <div
          className={`mx-4 mb-4 p-4 rounded-md ${
            executionResult.status === 'success'
              ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-500/20'
              : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-500/20'
          }`}
        >
          <h4
            className={`font-semibold mb-2 text-sm ${
              executionResult.status === 'success'
                ? 'text-green-800 dark:text-green-300'
                : 'text-red-800 dark:text-red-300'
            }`}
          >
            {executionResult.status === 'success' ? '✅ 分析完成' : '❌ 执行失败'}
          </h4>
          {executionResult.output && (
            <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto max-h-48">
              <code>{executionResult.output}</code>
            </pre>
          )}
          {executionResult.error && (
            <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto max-h-48 mt-2">
              <code>{executionResult.error}</code>
            </pre>
          )}
          {!executionResult.output && !executionResult.error && (
            <p className="text-xs text-gray-500 dark:text-zinc-400">
              exit_code={executionResult.exit_code}，详见上方日志窗口
            </p>
          )}
          {executionResult.output_files && executionResult.output_files.length > 0 && (
            <div className="mt-3">
              <h5 className="text-xs font-semibold text-gray-600 dark:text-zinc-400 mb-2">输出文件</h5>
              <div className="space-y-1">
                {executionResult.output_files.map((file, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 text-xs text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-800 rounded px-2 py-1"
                  >
                    <FileText size={12} />
                    <span className="flex-1 truncate">{file.name}</span>
                    <span className="text-zinc-400">{file.ext}</span>
                    {file.preview && <Eye size={12} className="text-blue-500" />}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 6. 操作区（底部） */}
      <div className="p-4 bg-gray-50 dark:bg-[#1e1e20] flex justify-between items-center border-t border-gray-200 dark:border-zinc-800">
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
        <button
          onClick={handleExecute}
          disabled={isExecuting}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-600/50 disabled:cursor-not-allowed rounded-md transition-colors"
        >
          {isExecuting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Play size={14} />
          )}
          {isExecuting ? '沙箱执行中...' : '执行分析'}
        </button>
      </div>
    </div>
  )
}

/** 格式化文件大小 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}
