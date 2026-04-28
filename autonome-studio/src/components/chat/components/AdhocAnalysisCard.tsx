'use client'

import { useState, useRef, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { ChevronDown, ChevronRight, Play, Star, Loader2, FileText, Eye, File, RotateCcw, Check, Copy, FolderOpen, User, Zap } from 'lucide-react'
import { TablePreview } from './TablePreview'
import { BASE_URL } from '@/lib/api'
import { useUIStore } from '@/store/useUIStore'
import { useUserProfileStore } from '@/store/useUserProfileStore'

/**
 * 动态导入 Monaco Editor（禁用 SSR，仅专家模式使用）
 */
const MonacoEditor = dynamic(() => import('@monaco-editor/react').then(mod => mod.default), {
  ssr: false,
  loading: () => (
    <div className="w-full bg-gray-900 p-3 rounded-md mb-4 min-h-[120px] flex items-center justify-center">
      <Loader2 size={16} className="animate-spin text-gray-500" />
    </div>
  ),
})

/**
 * JSON Schema 属性定义（与 ParameterProbingCard 一致）
 */
interface SchemaProperty {
  type: 'string' | 'number' | 'boolean' | 'file'
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
  /** 代码校验结果（由后端 code_validator 生成） */
  _validation?: {
    is_valid: boolean
    status_text: string
    status_icon: 'error' | 'warning' | 'success'
    issues: Array<{ severity: string; message: string; suggestion: string }>
  }
  /** LLM Agent 自动修复结果（由后端 auto_fix_generated_code 生成） */
  _auto_fix?: {
    fixed_code: string | null
    changes_description: string
    success: boolean
    re_validation?: {
      is_valid: boolean
      status_text: string
      status_icon: 'error' | 'warning' | 'success'
      issues: Array<{ severity: string; message: string; suggestion: string }>
    }
  }
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
  _validation,
  _auto_fix,
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

  // 表单验证错误状态：key → 错误消息
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({})

  // === 自适应体验：读取用户画像 ===
  const profileMode = useUserProfileStore(s => s.mode)
  const codeExpandedByDefault = useUserProfileStore(s => s.codeExpandedByDefault)
  const defaultLogTab = useUserProfileStore(s => s.defaultLogTab)
  const setMode = useUserProfileStore(s => s.setMode)
  const unlockMode = useUserProfileStore(s => s.unlockMode)
  const recordCodeEdit = useUserProfileStore(s => s.recordCodeEdit)
  const recordRawLogView = useUserProfileStore(s => s.recordRawLogView)

  const [isExecuting, setIsExecuting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)
  // 固化技能模态框状态
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveSkillName, setSaveSkillName] = useState('')
  const [saveCategory, setSaveCategory] = useState('即席分析')
  const [saveVisibility, setSaveVisibility] = useState('private')
  // 代码区：初始状态由用户模式决定（新手隐藏，专家默认展示）
  const [showCode, setShowCode] = useState(codeExpandedByDefault)
  const [editableCode, setEditableCode] = useState(code)
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null)
  // 输出文件预览所需：project_id 和 output_dir_name 从 SSE result 事件中获取
  const [outputProjectId, setOutputProjectId] = useState<string | null>(null)
  const [outputDirName, setOutputDirName] = useState<string | null>(null)
  // 输出文件点击预览状态
  const [previewFileUrl, setPreviewFileUrl] = useState<string | null>(null)
  const [previewFileName, setPreviewFileName] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewTextContent, setPreviewTextContent] = useState<string | null>(null)
  const [previewType, setPreviewType] = useState<'image' | 'csv' | 'text' | 'pdf' | 'other' | null>(null)
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  // 实时日志流状态
  const [logLines, setLogLines] = useState<string[]>([])  // 所有日志（用于复制）
  const [systemLogs, setSystemLogs] = useState<string[]>([])  // 系统日志（pip install等）
  const [analysisLogs, setAnalysisLogs] = useState<string[]>([])  // 分析日志
  const [showLogWindow, setShowLogWindow] = useState(false)
  const [logCollapsed, setLogCollapsed] = useState(false)
  const [logCopied, setLogCopied] = useState(false)
  const [systemLogsCollapsed, setSystemLogsCollapsed] = useState(true)  // 系统日志默认折叠
  // 日志 Tab：初始值由用户模式决定（新手→进度，专家→全部）
  const [activeLogTab, setActiveLogTab] = useState<'analysis' | 'system' | 'all'>(defaultLogTab as 'analysis' | 'system' | 'all')
  // 进度状态
  const [progressData, setProgressData] = useState<{ step: number; total: number; message: string; percent: number } | null>(null)
  // LLM 结果解读
  const [interpretation, setInterpretation] = useState<string | null>(null)
  // 智能错误诊断
  const [diagnosis, setDiagnosis] = useState<{ diagnosis: string; fixed_code: string | null; fix_description: string } | null>(null)
  // LLM Agent 代码修复状态
  const [isFixingCode, setIsFixingCode] = useState(false)
  const [fixCodeResult, setFixCodeResult] = useState<{
    fixed_code: string | null
    changes_description: string
    success: boolean
    re_validation?: { is_valid: boolean; status_text: string; status_icon: string; issues: Array<{ severity: string; message: string; suggestion: string }> }
  } | null>(_auto_fix || null)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  // 执行计时器状态
  const [executionStartTime, setExecutionStartTime] = useState<number | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  // 数据中心联动
  const openDataCenter = useUIStore(s => s.openDataCenter)
  const setDataCenterHighlightPath = useUIStore(s => s.setDataCenterHighlightPath)

  // 日志窗口自动滚动到底部
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logLines])

  // 执行计时器：每秒更新已运行时间
  useEffect(() => {
    if (!executionStartTime) {
      setElapsedSeconds(0)
      return
    }
    const timer = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - executionStartTime) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [executionStartTime])

  // 处理参数变化
  const handleParamChange = (key: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [key]: value }))
    // 清除该字段的验证错误
    if (validationErrors[key]) {
      setValidationErrors(prev => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    }
  }

  // 恢复所有参数为 Schema 默认值
  const handleRestoreDefaults = () => {
    const defaults: Record<string, unknown> = {}
    for (const [key, prop] of Object.entries(parameter_schema?.properties || {})) {
      if (prop.default !== undefined) {
        defaults[key] = prop.default
      }
    }
    setFormData(defaults)
    setValidationErrors({})
  }

  // 表单验证：基于 JSON Schema 校验必填项、类型、枚举、数值范围
  const validateForm = (): boolean => {
    const errors: Record<string, string> = {}
    for (const [key, field] of Object.entries(parameter_schema?.properties || {})) {
      const value = formData[key]
      const isRequired = parameter_schema?.required?.includes(key)
      // 必填项检查
      if (isRequired && (value === undefined || value === null || value === '')) {
        errors[key] = `${field.title || key} 为必填项`
        continue
      }
      // 跳过空值的非必填项
      if (value === undefined || value === null || value === '') continue
      // 类型校验
      if (field.type === 'number') {
        const numVal = Number(value)
        if (isNaN(numVal)) {
          errors[key] = `${field.title || key} 必须为数字`
          continue
        }
        if (field.minimum !== undefined && numVal < field.minimum) {
          errors[key] = `不能小于 ${field.minimum}`
        }
        if (field.maximum !== undefined && numVal > field.maximum) {
          errors[key] = `不能大于 ${field.maximum}`
        }
      }
      // 枚举校验
      if (field.enum && field.enum.length > 0) {
        if (!field.enum.includes(String(value))) {
          errors[key] = `必须为 ${field.enum.join(' / ')}`
        }
      }
    }
    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  // 核心：点击执行，通过 SSE 流式接收 Docker 沙箱实时日志
  const handleExecute = async () => {
    if (isExecuting) return

    // 执行前表单验证
    if (!validateForm()) return

    setIsExecuting(true)
    setExecutionResult(null)
    setLogLines([])
    setSystemLogs([])
    setAnalysisLogs([])
    setProgressData(null)
    setInterpretation(null)
    setDiagnosis(null)
    setSystemLogsCollapsed(true)
    setActiveLogTab('analysis')
    setShowLogWindow(true)
    setLogCollapsed(false)
    setExecutionStartTime(Date.now())
    setElapsedSeconds(0)

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
        credentials: 'include',
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
      setExecutionStartTime(null)
    }
  }

  // 处理 SSE 事件
  const handleSSEEvent = (event: Record<string, unknown>) => {
    switch (event.type) {
      case 'init':
        setLogLines(prev => [...prev, `🚀 ${event.message || '沙箱启动中...'}`])
        setAnalysisLogs(prev => [...prev, `🚀 ${event.message || '沙箱启动中...'}`])
        break
      case 'progress': {
        // 结构化进度事件
        const prog = {
          step: event.step as number,
          total: event.total as number,
          message: event.message as string,
          percent: event.percent as number,
        }
        setProgressData(prog)
        setLogLines(prev => [...prev, `📊 [${prog.step}/${prog.total}] ${prog.message}`])
        setAnalysisLogs(prev => [...prev, `📊 [${prog.step}/${prog.total}] ${prog.message}`])
        break
      }
      case 'log': {
        const line = event.line as string
        const category = (event.category as string) || 'analysis'
        setLogLines(prev => [...prev, line])
        if (category === 'system') {
          setSystemLogs(prev => [...prev, line])
        } else {
          setAnalysisLogs(prev => [...prev, line])
        }
        break
      }
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

        // 保存 project_id 和 output_dir_name 用于输出文件预览
        if (event.project_id) setOutputProjectId(event.project_id as string)
        if (event.output_dir_name) setOutputDirName(event.output_dir_name as string)

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
      case 'interpretation':
        // LLM 结果解读
        setInterpretation(event.text as string)
        break
      case 'diagnosis':
        // 智能错误诊断（含一键修复建议）
        setDiagnosis({
          diagnosis: event.diagnosis as string,
          fixed_code: event.fixed_code as string | null,
          fix_description: event.fix_description as string,
        })
        break
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

  // 判断文件是否过大（>10MB 仅下载）
  const isLargeFile = (file: OutputFile) => file.size > 10 * 1024 * 1024

  // 点击输出文件：通过 /view 端点获取文件内容并预览
  const handleOutputFileClick = async (file: OutputFile) => {
    if (!outputProjectId || !outputDirName) return

    // 大文件仅下载
    if (isLargeFile(file)) {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null
      const fileViewPath = `results/${outputDirName}/${file.path}`
      const downloadUrl = `${apiUrl}/api/projects/${outputProjectId}/files/${fileViewPath}/view`
      // 直接触发下载
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = file.name
      if (token) a.setAttribute('data-token', token)
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      return
    }

    setPreviewLoading(true)
    setPreviewFileName(file.name)
    setPreviewFilePath(file.path)
    setPreviewFileUrl(null)
    setPreviewTextContent(null)

    const ext = (file.ext || '').toLowerCase()
    const isImage = Boolean(ext.match(/\.(png|jpg|jpeg|svg|gif|bmp|webp)$/i))
    const isCsv = Boolean(ext.match(/\.(csv|tsv)$/i))
    const isText = Boolean(ext.match(/\.(txt|log|md|r|py|sh|json|xml|yml|yaml|toml|cfg|ini|R|Rmd)$/i))
    const isPdf = ext === '.pdf'

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null
      const fileViewPath = `results/${outputDirName}/${file.path}`

      if (isImage) {
        const res = await fetch(`${apiUrl}/api/projects/${outputProjectId}/files/${fileViewPath}/view`, {
          headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        })
        if (!res.ok) throw new Error(`获取文件失败 (${res.status})`)
        const blob = await res.blob()
        const blobUrl = URL.createObjectURL(blob)
        setPreviewFileUrl(blobUrl)
        setPreviewType('image')
      } else if (isCsv || isText) {
        const res = await fetch(`${apiUrl}/api/projects/${outputProjectId}/files/${fileViewPath}/view`, {
          headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        })
        if (!res.ok) throw new Error(`获取文件失败 (${res.status})`)
        const text = await res.text()
        setPreviewTextContent(text)
        setPreviewType(isCsv ? 'csv' : 'text')
      } else if (isPdf) {
        // PDF 使用 iframe 内联预览
        setPreviewType('pdf')
      } else {
        setPreviewType('other')
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '加载失败'
      console.error('输出文件预览失败:', message)
      setPreviewFileUrl(null)
      setPreviewTextContent(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  // 关闭文件预览
  const handleClosePreview = () => {
    if (previewFileUrl) {
      URL.revokeObjectURL(previewFileUrl)
    }
    setPreviewFileUrl(null)
    setPreviewFileName(null)
    setPreviewFilePath(null)
    setPreviewTextContent(null)
    setPreviewType(null)
    setLightboxOpen(false)
  }

  // 调用 LLM Agent 修复代码
  const handleFixCode = async () => {
    if (isFixingCode) return
    setIsFixingCode(true)
    setFixCodeResult(null)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null
      const res = await fetch(`${apiUrl}/api/chat/adhoc/fix-code`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          code: editableCode,
          language: code_language,
          instruction: strategy,
          issues: _validation?.issues || [],
        }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        throw new Error(errData.detail || '修复失败')
      }
      const data = await res.json()
      setFixCodeResult(data)
      if (data.success && data.fixed_code) {
        // 自动应用修复后的代码
        setEditableCode(data.fixed_code)
        setShowCode(true)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '修复失败'
      setFixCodeResult({ fixed_code: null, changes_description: message, success: false })
    } finally {
      setIsFixingCode(false)
    }
  }

  // 固化技能到资产库：调用后端 API 将策略包写入文件系统
  // 打开保存模态框
  const handleSaveSkill = () => {
    setSaveSkillName(strategy.slice(0, 30))
    setSaveCategory('即席分析')
    setSaveVisibility('private')
    setShowSaveModal(true)
  }

  // 确认保存
  const handleConfirmSave = async () => {
    if (isSaving || !saveSkillName.trim()) return
    setIsSaving(true)
    setSaveResult(null)
    setShowSaveModal(false)
    try {
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
          skill_name: saveSkillName,
          description: strategy,
          visibility: saveVisibility,
          category_name: saveCategory,
        }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        throw new Error(errData.detail || '保存失败')
      }
      const data = await res.json()
      setSaveResult(`技能已保存: ${data.skill_id}`)
      // 3 秒后自动清除保存结果
      setTimeout(() => setSaveResult(null), 3000)
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
      <div className={`p-4 border-b transition-colors duration-300 ${
        executionResult?.status === 'success'
          ? 'bg-green-50/50 dark:bg-green-900/20 border-green-100 dark:border-green-500/20'
          : executionResult?.status === 'failed'
          ? 'bg-red-50/50 dark:bg-red-900/20 border-red-100 dark:border-red-500/20'
          : isExecuting
          ? 'bg-blue-50/50 dark:bg-blue-900/20 border-blue-100 dark:border-blue-500/20'
          : 'bg-indigo-50/50 dark:bg-indigo-900/20 border-indigo-100 dark:border-indigo-500/20'
      }`}>
        <div className="flex items-start justify-between gap-2">
          <h3 className={`font-bold flex items-center gap-2 text-sm transition-colors duration-300 ${
            executionResult?.status === 'success'
              ? 'text-green-900 dark:text-green-300'
              : executionResult?.status === 'failed'
              ? 'text-red-900 dark:text-red-300'
              : isExecuting
              ? 'text-blue-900 dark:text-blue-300'
              : 'text-indigo-900 dark:text-indigo-300'
          }`}>
            <span>
              {isExecuting
                ? '⏳ 分析执行中...'
                : executionResult?.status === 'success'
                ? `✅ 分析完成 — 共生成 ${executionResult?.output_files?.length || 0} 个文件`
                : executionResult?.status === 'failed'
                ? `❌ 执行失败 — ${executionResult?.error ? executionResult.error.slice(0, 60) + (executionResult.error.length > 60 ? '...' : '') : '未知错误'}`
                : '⚡ 即席分析就绪'
              }
            </span>
          </h3>
          {/* 自适应模式切换（仅非执行状态显示） */}
          {!isExecuting && !executionResult && (
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => profileMode === 'beginner' ? setMode('expert') : unlockMode()}
                className={`flex items-center gap-1 text-[10px] px-2 py-1 rounded-full transition-colors border ${
                  profileMode === 'expert'
                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30'
                    : 'bg-gray-100 dark:bg-zinc-800 text-gray-500 dark:text-zinc-400 border-gray-300 dark:border-zinc-700 hover:border-amber-500/30'
                }`}
                title={profileMode === 'expert' ? '专家模式（点击恢复自动检测）' : '切换到专家模式'}
              >
                {profileMode === 'expert' ? (
                  <>
                    <Zap size={11} />
                    专家
                  </>
                ) : (
                  <>
                    <User size={11} />
                    新手
                  </>
                )}
              </button>
            </div>
          )}
        </div>
        <p className="text-gray-600 dark:text-zinc-300 text-sm mt-2">{strategy}</p>
      </div>

      {/* 2. 输入文件映射区（在参数面板上方） */}
      {Object.keys(input_mapping || {}).length > 0 && (
        <div className="px-4 pt-4">
          <div className="rounded-md bg-blue-50 dark:bg-blue-900/15 border border-blue-200 dark:border-blue-500/20 p-3">
            <h4 className="text-xs font-semibold text-blue-800 dark:text-blue-300 mb-2 flex items-center gap-1.5">
              <File size={13} />
              输入文件映射
            </h4>
            <div className="space-y-1">
              {Object.entries(input_mapping).map(([paramName, filePath]) => {
                const fileName = (filePath || '').split('/').pop() || filePath
                return (
                  <div
                    key={paramName}
                    className="flex items-center gap-2 text-xs text-blue-700 dark:text-blue-400"
                  >
                    <File size={11} className="flex-shrink-0 text-blue-400" />
                    <span className="font-mono truncate flex-1" title={filePath}>
                      {fileName}
                    </span>
                    <span className="text-blue-400 flex-shrink-0">→</span>
                    <span className="font-medium flex-shrink-0">{paramName}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* 3. 参数面板（中部，网格布局，动态表单） */}
      {Object.keys(parameter_schema?.properties || {}).length > 0 && (
        <div className="p-4">
          {/* 参数面板标题栏 + 恢复默认按钮 */}
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold text-gray-500 dark:text-zinc-400 uppercase tracking-wider">
              分析参数
            </h4>
            <button
              onClick={handleRestoreDefaults}
              className="flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline transition-colors"
            >
              <RotateCcw size={11} />
              恢复默认
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {Object.entries(parameter_schema.properties).map(([key, field]) => {
              const isRequired = parameter_schema.required?.includes(key)
              const hasError = !!validationErrors[key]
              const isFileParam = field.type === 'file' || Object.keys(input_mapping || {}).includes(key)
              // 文件参数的默认值从 input_mapping 获取
              const filePath = isFileParam ? (input_mapping?.[key] || '') : ''
              const fileName = filePath ? filePath.split('/').pop() || filePath : ''

              // 通用的输入框样式，错误状态时红色边框
              const inputBaseClass = `w-full rounded-md border bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none ${
                hasError
                  ? 'border-red-400 dark:border-red-500 focus:border-red-500 focus:ring-1 focus:ring-red-300 transition-all'
                  : 'border-zinc-300 dark:border-zinc-600 focus:border-indigo-500'
              }`

              return (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-sm font-medium text-gray-700 dark:text-zinc-300 flex items-center gap-1 flex-wrap">
                    {/* 新手模式：优先显示中文 title；专家模式：显示技术参数名 */}
                    <span>{field.title || key}</span>
                    {/* 专家模式额外显示参数键名 */}
                    {profileMode === 'expert' && field.title && (
                      <span className="text-[10px] text-gray-400 dark:text-zinc-500 font-mono font-normal">
                        ({key})
                      </span>
                    )}
                    {isRequired && <span className="text-red-400 font-bold">*</span>}
                  </label>
                  {/* 新手模式显示自然语言参数描述 */}
                  {profileMode === 'beginner' && field.description && (
                    <span className="text-[11px] text-zinc-500 dark:text-zinc-400 leading-relaxed">
                      💡 {field.description}
                    </span>
                  )}

                  {/* file 类型 → 只读文件路径展示，不可编辑 */}
                  {isFileParam ? (
                    <div className={`${inputBaseClass} flex items-center gap-2 bg-gray-50 dark:bg-zinc-700/50 cursor-default`}>
                      <File size={13} className="text-blue-500 dark:text-blue-400 flex-shrink-0" />
                      <span className="truncate text-gray-600 dark:text-zinc-400 font-mono" title={filePath}>
                        {fileName || filePath || '（未映射）'}
                      </span>
                    </div>
                  ) : field.enum ? (
                    /* enum → 下拉选择框 */
                    <select
                      value={String(formData[key] ?? field.default ?? '')}
                      onChange={(e) => handleParamChange(key, e.target.value)}
                      className={inputBaseClass}
                    >
                      {field.enum.map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  ) : field.type === 'boolean' ? (
                    /* boolean → 开关 */
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={Boolean(formData[key] ?? field.default ?? false)}
                        onChange={(e) => handleParamChange(key, e.target.checked)}
                        className={`h-4 w-4 rounded border-zinc-600 text-indigo-500 focus:ring-indigo-500 ${hasError ? 'border-red-400' : ''}`}
                      />
                      <span className="text-sm text-zinc-500 dark:text-zinc-400">
                        {field.description || '启用'}
                      </span>
                    </label>
                  ) : field.type === 'number' ? (
                    /* number → 数字输入框 */
                    <div className="flex flex-col gap-1">
                      <input
                        type="number"
                        value={Number(formData[key] ?? field.default ?? 0)}
                        onChange={(e) => handleParamChange(key, Number(e.target.value))}
                        min={field.minimum}
                        max={field.maximum}
                        step={field.step ?? 1}
                        className={inputBaseClass}
                      />
                      {/* 专家模式显示技术描述 */}
                      {profileMode === 'expert' && field.description && (
                        <span className="text-[11px] text-zinc-400 dark:text-zinc-500">{field.description}</span>
                      )}
                    </div>
                  ) : (
                    /* string → 文本输入框 */
                    <div className="flex flex-col gap-1">
                      <input
                        type="text"
                        value={String(formData[key] ?? field.default ?? '')}
                        onChange={(e) => handleParamChange(key, e.target.value)}
                        placeholder={`请输入 ${field.title || key}`}
                        className={inputBaseClass}
                      />
                      {/* 专家模式显示技术描述 */}
                      {profileMode === 'expert' && field.description && (
                        <span className="text-[11px] text-zinc-400 dark:text-zinc-500">{field.description}</span>
                      )}
                    </div>
                  )}

                  {/* 验证错误消息 */}
                  {hasError && (
                    <span className="text-[11px] text-red-500 dark:text-red-400 transition-all">
                      {validationErrors[key]}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 4. 代码预览区（折叠） */}
      <div className="px-4">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <button
            onClick={() => setShowCode(!showCode)}
            className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
          >
            {showCode ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {showCode ? '隐藏底层代码' : '查看底层代码'}
          </button>
          {/* 代码校验状态指示器 */}
          {_validation && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex items-center gap-1 ${
              _validation.status_icon === 'success'
                ? 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                : _validation.status_icon === 'warning'
                ? 'bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400'
                : 'bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400'
            }`}>
              {_validation.status_text}
            </span>
          )}
        </div>
        {showCode && (
          <>
            {/* 校验问题列表 */}
            {_validation && _validation.issues.length > 0 && (
              <div className="mb-2 space-y-1">
                {_validation.issues.map((issue, idx) => (
                  <div
                    key={idx}
                    className={`text-[10px] px-2 py-1 rounded flex items-start gap-1 ${
                      issue.severity === 'error'
                        ? 'bg-red-50 dark:bg-red-900/10 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'
                        : issue.severity === 'warning'
                        ? 'bg-yellow-50 dark:bg-yellow-900/10 text-yellow-700 dark:text-yellow-400 border border-yellow-200 dark:border-yellow-800'
                        : 'bg-blue-50 dark:bg-blue-900/10 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800'
                    }`}
                  >
                    <span className="flex-shrink-0 mt-0.5">
                      {issue.severity === 'error' ? '❌' : issue.severity === 'warning' ? '⚠️' : 'ℹ️'}
                    </span>
                    <span>
                      {issue.message}
                      {issue.suggestion && <span className="ml-1 opacity-75">— {issue.suggestion}</span>}
                    </span>
                  </div>
                ))}
                {/* LLM Agent 代码修复按钮 */}
                {_validation.issues.some(i => i.severity === 'error') && (
                  <div className="mt-2">
                    {!fixCodeResult?.success && (
                      <button
                        onClick={handleFixCode}
                        disabled={isFixingCode}
                        className="text-[10px] px-3 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white rounded flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      >
                        {isFixingCode ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <span>🔧</span>
                        )}
                        {isFixingCode ? 'AI 正在修复代码...' : 'AI 自动修复代码'}
                      </button>
                    )}
                  </div>
                )}
                {/* LLM Agent 修复结果 */}
                {fixCodeResult && (
                  <div className={`text-[10px] px-2 py-1.5 rounded flex items-start gap-1.5 ${
                    fixCodeResult.success
                      ? 'bg-green-50 dark:bg-green-900/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
                      : 'bg-amber-50 dark:bg-amber-900/10 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800'
                  }`}>
                    <span className="flex-shrink-0 mt-0.5">
                      {fixCodeResult.success ? '✅' : '⚠️'}
                    </span>
                    <div className="flex-1">
                      <span>{fixCodeResult.changes_description}</span>
                      {fixCodeResult.success && fixCodeResult.re_validation && (
                        <span className="ml-2 opacity-75">
                          → {fixCodeResult.re_validation.status_text}
                        </span>
                      )}
                      {fixCodeResult.success && fixCodeResult.fixed_code && (
                        <button
                          onClick={() => {
                            setEditableCode(fixCodeResult.fixed_code!)
                            setFixCodeResult(null)
                          }}
                          className="ml-2 text-indigo-600 dark:text-indigo-400 hover:underline"
                        >
                          查看/应用修复代码
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            {/* 代码编辑器：专家模式使用 Monaco，新手模式使用 textarea */}
            {profileMode === 'expert' ? (
              <div className="mb-4 border border-gray-700 rounded-md overflow-hidden">
                <MonacoEditor
                  height="300px"
                  language={code_language === 'r' ? 'r' : 'python'}
                  value={editableCode}
                  onChange={(val) => {
                    setEditableCode(val || '')
                    recordCodeEdit()
                  }}
                  theme="vs-dark"
                  options={{
                    fontSize: 12,
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    lineNumbers: 'on',
                    padding: { top: 8 },
                  }}
                />
              </div>
            ) : (
              <textarea
                value={editableCode}
                onChange={(e) => {
                  setEditableCode(e.target.value)
                  recordCodeEdit()
                }}
                className="w-full text-xs bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto mb-4 font-mono resize-y min-h-[120px] max-h-96"
                spellCheck={false}
              />
            )}
          </>
        )}
      </div>

      {/* 5. 实时日志窗口 */}
      {showLogWindow && (
        <div className="mx-4 mb-4 border border-gray-700 rounded-md overflow-hidden">
          {/* 日志窗口标题栏（使用 div 避免嵌套 button 的 hydration 错误） */}
          <div
            onClick={() => setLogCollapsed(!logCollapsed)}
            onKeyDown={(e) => { if (e.key === 'Enter') setLogCollapsed(!logCollapsed) }}
            role="button"
            tabIndex={0}
            className="w-full flex items-center justify-between bg-gray-800 px-3 py-2 hover:bg-gray-750 transition-colors cursor-pointer"
          >
            <span className="text-xs font-medium text-gray-300 flex items-center gap-2">
              {isExecuting ? (
                <>
                  <Loader2 size={12} className="animate-spin text-blue-400" />
                  <span>⏱ {formatElapsed(elapsedSeconds)}</span>
                </>
              ) : executionResult ? (
                executionResult.status === 'success' ? (
                  <span className="text-green-400">✅ 执行日志</span>
                ) : (
                  <span className="text-red-400">❌ 执行日志</span>
                )
              ) : (
                <span className="text-gray-400">📋 执行日志</span>
              )}
              {logLines.length > 0 && (
                <span className="text-[10px] text-gray-500 bg-gray-700 rounded-full px-1.5 py-0.5">
                  {logLines.length} 行
                </span>
              )}
            </span>
            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              {/* 复制日志按钮 */}
              {logLines.length > 0 && (
                <button
                  onClick={() => {
                    copyToClipboard(logLines.join('\n'))
                    setLogCopied(true)
                    setTimeout(() => setLogCopied(false), 2000)
                  }}
                  className="text-gray-500 hover:text-gray-300 text-xs flex items-center gap-1 transition-colors"
                  title="复制日志"
                >
                  {logCopied ? <Check size={11} className="text-green-400" /> : <Copy size={11} />}
                </button>
              )}
              {/* 折叠/展开 + 关闭 */}
              <span className="text-gray-500 text-xs">
                {logCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setShowLogWindow(false)
                }}
                className="text-gray-500 hover:text-gray-300 text-xs ml-1"
                title="关闭日志窗口"
              >
                ✕
              </button>
            </div>
          </div>
          {/* 日志内容区（可折叠） */}
          {!logCollapsed && (
            <>
              {/* 进度条（仅在有进度数据时显示） */}
              {progressData && (
                <div className="bg-gray-800 px-3 py-2 border-b border-gray-700">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] text-gray-300">
                      📊 [{progressData.step}/{progressData.total}] {progressData.message}
                    </span>
                    <span className="text-[10px] text-gray-500">{progressData.percent}%</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-1.5">
                    <div
                      className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${progressData.percent}%` }}
                    />
                  </div>
                </div>
              )}

              {/* 日志 Tab 切换 */}
              <div className="bg-gray-800 px-2 pt-1.5 flex items-center gap-1 border-b border-gray-700">
                <button
                  onClick={() => setActiveLogTab('analysis')}
                  className={`text-[10px] px-2 py-1 rounded-t transition-colors ${
                    activeLogTab === 'analysis'
                      ? 'bg-gray-900 text-gray-100'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  📈 分析日志
                  {analysisLogs.length > 0 && (
                    <span className="ml-1 text-[9px] opacity-60">{analysisLogs.length}</span>
                  )}
                </button>
                <button
                  onClick={() => setActiveLogTab('system')}
                  className={`text-[10px] px-2 py-1 rounded-t transition-colors ${
                    activeLogTab === 'system'
                      ? 'bg-gray-900 text-gray-100'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  ⚙️ 系统日志
                  {systemLogs.length > 0 && (
                    <span className="ml-1 text-[9px] opacity-60">{systemLogs.length}</span>
                  )}
                </button>
                <button
                  onClick={() => {
                    setActiveLogTab('all')
                    recordRawLogView()
                  }}
                  className={`text-[10px] px-2 py-1 rounded-t transition-colors ${
                    activeLogTab === 'all'
                      ? 'bg-gray-900 text-gray-100'
                      : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  📋 全部
                </button>
                {/* 系统日志计数徽章（有系统日志时显示折叠/展开切换） */}
                {systemLogs.length > 0 && (
                  <button
                    onClick={() => setSystemLogsCollapsed(!systemLogsCollapsed)}
                    className="ml-auto text-[10px] text-gray-500 hover:text-gray-300"
                  >
                    {systemLogsCollapsed ? '▶ 展开系统' : '▼ 折叠系统'}
                  </button>
                )}
              </div>

              <div
                ref={logContainerRef}
                className="bg-gray-900 text-gray-100 p-3 text-xs font-mono max-h-64 overflow-y-auto"
              >
                {logLines.length === 0 && isExecuting ? (
                  <span className="text-gray-500">等待日志输出...</span>
                ) : (
                  (() => {
                    // 根据 Tab 选择展示的日志行
                    let displayLines: string[] = logLines
                    if (activeLogTab === 'analysis') {
                      displayLines = analysisLogs
                    } else if (activeLogTab === 'system') {
                      displayLines = systemLogs
                    }
                    // 系统日志折叠：在 analysis 或 all tab 中隐藏系统日志
                    if (systemLogsCollapsed && activeLogTab !== 'system') {
                      // 从 logLines 中过滤掉系统日志来展示
                      if (activeLogTab === 'all') {
                        const systemSet = new Set(systemLogs)
                        displayLines = logLines.filter(l => !systemSet.has(l))
                      }
                    }
                    return displayLines.map((line, i) => {
                      // 进度行高亮
                      const isProgressLine = line.includes('[1/') || line.includes('[2/') || line.includes('[3/') || line.includes('[4/') || line.includes('[5/') || line.includes('[6/')
                      return (
                        <div
                          key={i}
                          className={`whitespace-pre-wrap break-all ${
                            isProgressLine
                              ? 'text-indigo-300 dark:text-indigo-400'
                              : ''
                          }`}
                        >
                          {line}
                        </div>
                      )
                    })
                  })()
                )}
                {/* 长时间无新日志警告 */}
                {isExecuting && logLines.length > 0 && elapsedSeconds > 300 && (
                  <div className="mt-2 text-amber-400 text-[11px] flex items-center gap-1.5">
                    <span>⚠️</span>
                    <span>
                      已运行 {formatElapsed(elapsedSeconds)}，如长时间无新日志输出，可能是进入了长时间计算
                    </span>
                  </div>
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
            </>
          )}
        </div>
      )}

      {/* 6. 结果区（执行完成后显示在日志窗口下方） */}
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
            {executionResult.status === 'success'
              ? `✅ 分析完成 — 共生成 ${executionResult?.output_files?.length || 0} 个文件`
              : '❌ 执行失败'}
          </h4>

          {/* 打包下载按钮（成功时显示） */}
          {executionResult.status === 'success' && outputProjectId && outputDirName && (
            <div className="mb-3">
              <a
                href={`${BASE_URL}/api/chat/adhoc/download/${outputProjectId}/${encodeURIComponent(outputDirName)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-500 hover:bg-indigo-600 text-white rounded-md transition-colors"
              >
                📦 打包下载结果
              </a>
            </div>
          )}

          {/* LLM 结果解读（成功时） */}
          {executionResult.status === 'success' && interpretation && (
            <div className="mb-3 p-3 rounded-md bg-white/60 dark:bg-white/5 border border-gray-200 dark:border-zinc-700">
              <div className="flex items-start gap-2">
                <span className="text-sm mt-0.5">📝</span>
                <div>
                  <span className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-zinc-500 font-medium">AI 解读</span>
                  <p className="text-xs text-gray-700 dark:text-zinc-300 leading-relaxed mt-0.5">
                    {interpretation}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* 智能错误诊断（失败时） */}
          {executionResult.status === 'failed' && diagnosis && (
            <div className="mb-3 p-3 rounded-md bg-white/60 dark:bg-white/5 border border-amber-200 dark:border-amber-700/30">
              <div className="flex items-start gap-2">
                <span className="text-sm mt-0.5">🔧</span>
                <div className="flex-1">
                  <span className="text-[10px] uppercase tracking-wide text-amber-600 dark:text-amber-400 font-medium">AI 诊断</span>
                  <p className="text-xs text-gray-700 dark:text-zinc-300 leading-relaxed mt-0.5">
                    {diagnosis.diagnosis}
                  </p>
                  {diagnosis.fix_description && (
                    <p className="text-[10px] text-gray-500 dark:text-zinc-400 mt-1">
                      💡 {diagnosis.fix_description}
                    </p>
                  )}
                  {diagnosis.fixed_code && (
                    <button
                      onClick={() => {
                        setEditableCode(diagnosis.fixed_code!)
                        setShowCode(true)
                        setDiagnosis(null)
                        // 滚动到代码区
                      }}
                      className="mt-2 text-xs px-3 py-1.5 bg-amber-500 text-white rounded hover:bg-amber-600 transition-colors flex items-center gap-1"
                    >
                      🔧 一键应用修复
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {executionResult.output && (
            <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto max-h-48">
              <code>{executionResult.output}</code>
            </pre>
          )}
          {executionResult.error && (
            <div className="mt-2 space-y-2">
              {/* 解析错误消息中的 [诊断] 和 [建议] 结构化信息 */}
              {(() => {
                const errorText = executionResult.error || ''
                // 按行分割，找出不同部分
                const lines = errorText.split('\n')
                const errorTitle = lines[0] || ''
                const diagnostics: string[] = []
                const suggestions: string[] = []
                const other: string[] = []
                for (const line of lines.slice(1)) {
                  if (line.startsWith('[诊断]')) {
                    diagnostics.push(line.replace('[诊断] ', ''))
                  } else if (line.startsWith('[建议]')) {
                    suggestions.push(line.replace('[建议] ', ''))
                  } else if (line.trim()) {
                    other.push(line)
                  }
                }
                return (
                  <>
                    {/* 错误标题 */}
                    <pre className="text-xs bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 p-3 rounded-md overflow-x-auto font-sans whitespace-pre-wrap">
                      {errorTitle}
                    </pre>
                    {/* 诊断信息 */}
                    {diagnostics.length > 0 && (
                      <div className="text-xs bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-zinc-400 p-3 rounded-md">
                        <span className="font-semibold">诊断：</span>
                        {diagnostics.map((d, i) => <p key={i} className="mt-1">{d}</p>)}
                      </div>
                    )}
                    {/* 建议操作 */}
                    {suggestions.length > 0 && (
                      <div className="text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 p-3 rounded-md">
                        <span className="font-semibold">建议：</span>
                        {suggestions.map((s, i) => <p key={i} className="mt-1">{s}</p>)}
                      </div>
                    )}
                    {/* 其他错误详情（可折叠） */}
                    {other.length > 0 && (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300">
                          展开原始错误详情
                        </summary>
                        <pre className="bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto mt-1 font-mono">
                          <code>{other.join('\n')}</code>
                        </pre>
                      </details>
                    )}
                  </>
                )
              })()}
            </div>
          )}
          {!executionResult.output && !executionResult.error && (
            <p className="text-xs text-gray-500 dark:text-zinc-400">
              exit_code={executionResult.exit_code}，详见上方日志窗口
            </p>
          )}
          {executionResult.output_files && executionResult.output_files.length > 0 && (
            <div className="mt-3">
              <h5 className="text-xs font-semibold text-gray-600 dark:text-zinc-400 mb-2">
                输出文件（点击预览/下载）
              </h5>
              <div className="space-y-1">
                {executionResult.output_files.map((file, i) => (
                  <button
                    key={i}
                    onClick={() => handleOutputFileClick(file)}
                    disabled={previewLoading}
                    className="w-full flex items-center gap-2 text-xs text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-800 hover:bg-gray-100 dark:hover:bg-zinc-700 rounded px-2 py-1.5 transition-colors cursor-pointer disabled:opacity-50 border-0"
                    title={file.path}
                  >
                    {file.ext.match(/\.(png|jpg|jpeg|svg|gif|bmp|webp)$/i) ? (
                      <Eye size={12} className="text-green-500" />
                    ) : file.ext.match(/\.(csv|tsv|txt|pdf|html?)$/i) ? (
                      <Eye size={12} className="text-blue-500" />
                    ) : (
                      <FileText size={12} className="text-zinc-400" />
                    )}
                    <span className="flex-1 truncate text-left">{file.name}</span>
                    <span className="text-zinc-400 flex-shrink-0">{file.ext}</span>
                    <span className="text-zinc-400 flex-shrink-0">{formatFileSize(file.size)}</span>
                  </button>
                ))}
              </div>
              {/* 内联文件预览 */}
              {previewLoading && (
                <div className="mt-3 flex items-center gap-2 text-xs text-zinc-500">
                  <Loader2 size={12} className="animate-spin" />
                  加载中...
                </div>
              )}
              {/* 通用预览容器：当 previewType 存在时按类型渲染 */}
              {previewType && previewFileName && !previewLoading && (
                <div className="mt-3 border border-indigo-200 dark:border-indigo-500/20 rounded-md overflow-hidden">
                  <div className="flex items-center justify-between bg-gray-100 dark:bg-zinc-800 px-3 py-1.5">
                    <span className="text-xs font-medium text-gray-700 dark:text-zinc-300 truncate">
                      {previewFileName}
                    </span>
                    <button
                      onClick={handleClosePreview}
                      className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-xs"
                    >
                      关闭
                    </button>
                  </div>
                  {/* 图片预览 + 点击放大提示 */}
                  {previewType === 'image' && previewFileUrl && (
                    <div className="bg-white dark:bg-[#1a1a1c] flex justify-center p-2 relative group">
                      <img
                        src={previewFileUrl}
                        alt={previewFileName}
                        className="max-w-full max-h-80 object-contain cursor-zoom-in hover:opacity-90 transition-opacity"
                        onClick={() => setLightboxOpen(true)}
                      />
                      <span className="absolute bottom-2 right-2 text-[10px] text-white bg-black/60 rounded px-1.5 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        点击放大
                      </span>
                    </div>
                  )}
                  {/* CSV/TSV 表格预览 */}
                  {previewType === 'csv' && previewTextContent && (
                    <div className="bg-white dark:bg-[#1a1a1c]" style={{ maxHeight: 420 }}>
                      <TablePreview data={previewTextContent} containerHeight={400} />
                    </div>
                  )}
                  {/* 文本文件代码预览 */}
                  {previewType === 'text' && previewTextContent && (
                    <div className="bg-gray-900 text-gray-100 p-3 text-xs font-mono max-h-80 overflow-auto">
                      <pre className="whitespace-pre-wrap break-all"><code>{previewTextContent}</code></pre>
                    </div>
                  )}
                  {/* PDF iframe 内联预览 */}
                  {previewType === 'pdf' && outputProjectId && outputDirName && previewFilePath && (
                    <div className="bg-white dark:bg-[#1a1a1c]">
                      <iframe
                        src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/projects/${outputProjectId}/files/results/${outputDirName}/${previewFilePath}/view`}
                        className="w-full h-80 border-0"
                        title={previewFileName}
                      />
                    </div>
                  )}
                  {/* 其他文件：仅下载 */}
                  {previewType === 'other' && (
                    <div className="p-4 flex flex-col items-center gap-2 bg-white dark:bg-[#1a1a1c]">
                      <FileText size={24} className="text-zinc-400" />
                      <p className="text-xs text-zinc-500">此文件类型不支持在线预览</p>
                      <p className="text-xs text-zinc-500">点击文件名下方的下载按钮即可下载</p>
                    </div>
                  )}
                </div>
              )}
              {/* Lightbox 图片放大遮罩 */}
              {lightboxOpen && previewType === 'image' && previewFileUrl && (
                <div
                  className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center cursor-zoom-out"
                  onClick={() => setLightboxOpen(false)}
                >
                  <button
                    onClick={() => setLightboxOpen(false)}
                    className="absolute top-4 right-4 text-white/70 hover:text-white text-2xl transition-colors"
                    aria-label="关闭放大视图"
                  >
                    ✕
                  </button>
                  <span className="absolute top-4 left-4 text-xs text-white/50">
                    {previewFileName}
                  </span>
                  <img
                    src={previewFileUrl}
                    alt={previewFileName || ''}
                    className="max-w-[90vw] max-h-[90vh] object-contain select-none"
                    onClick={(e) => e.stopPropagation()}
                    draggable={false}
                  />
                </div>
              )}
            </div>
          )}
          {/* 在数据中心查看按钮（仅在成功执行且有输出目录时显示） */}
          {outputProjectId && outputDirName && (
            <div className="mt-3 pt-3 border-t border-gray-200 dark:border-zinc-700">
              <button
                onClick={() => {
                  setDataCenterHighlightPath(`results/${outputDirName}`)
                  openDataCenter()
                }}
                className="flex items-center gap-1.5 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 transition-colors"
              >
                <FolderOpen size={13} />
                在数据中心中查看所有输出文件
              </button>
            </div>
          )}
        </div>
      )}

      {/* 7. 操作区（底部） */}
      <div className="p-4 bg-gray-50 dark:bg-[#1e1e20] flex justify-between items-center border-t border-gray-200 dark:border-zinc-800">
        <button
          onClick={handleSaveSkill}
          disabled={isSaving}
          className={`flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md transition-colors disabled:opacity-50 ${
            saveResult?.startsWith('技能已保存')
              ? 'text-green-600 dark:text-green-400 border-green-300 dark:border-green-600 bg-green-50 dark:bg-green-900/20'
              : saveResult?.startsWith('保存失败')
              ? 'text-red-600 dark:text-red-400 border-red-300 dark:border-red-600 bg-red-50 dark:bg-red-900/20'
              : 'text-gray-600 dark:text-zinc-400 border-gray-300 dark:border-zinc-600 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-zinc-800'
          }`}
        >
          {isSaving ? (
            <Loader2 size={14} className="animate-spin" />
          ) : saveResult?.startsWith('技能已保存') ? (
            <Check size={14} className="text-green-500" />
          ) : (
            <Star size={14} />
          )}
          {isSaving ? '保存中...' : saveResult?.startsWith('技能已保存') ? '✅ 已保存' : saveResult?.startsWith('保存失败') ? '❌ 保存失败' : '固化为团队技能'}
        </button>
        <div className="flex items-center gap-3">
          {/* 失败原因摘要（仅在失败后显示） */}
          {executionResult?.status === 'failed' && !isExecuting && (
            <span className="text-xs text-red-500 dark:text-red-400 max-w-48 truncate" title={executionResult.error || ''}>
              {(executionResult.error || '未知错误').slice(0, 50)}
              {(executionResult.error || '').length > 50 ? '...' : ''}
            </span>
          )}
          <button
            onClick={handleExecute}
            disabled={isExecuting}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:cursor-not-allowed ${
              executionResult?.status === 'failed' && !isExecuting
                ? 'text-red-600 dark:text-red-400 border border-red-400 dark:border-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50'
                : 'text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-600/50'
            }`}
          >
            {isExecuting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : executionResult?.status === 'failed' ? (
              <RotateCcw size={14} />
            ) : (
              <Play size={14} />
            )}
            {isExecuting ? '沙箱执行中...' : executionResult?.status === 'failed' ? '重试分析' : '执行分析'}
          </button>
        </div>
      </div>

      {/* 8. 固化技能模态框 */}
      {showSaveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* 遮罩层 */}
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setShowSaveModal(false)}
          />
          {/* 模态框内容 */}
          <div className="relative bg-white dark:bg-[#1e1e20] rounded-xl border border-zinc-200 dark:border-zinc-700 shadow-2xl w-full max-w-md mx-4 p-6 z-10">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">
              固化为平台技能
            </h3>
            {/* 技能名称 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5">
                技能名称 <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={saveSkillName}
                onChange={(e) => setSaveSkillName(e.target.value)}
                placeholder="输入技能名称"
                className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && saveSkillName.trim()) handleConfirmSave()
                }}
              />
            </div>
            {/* 分类选择 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5">
                分类
              </label>
              <select
                value={saveCategory}
                onChange={(e) => setSaveCategory(e.target.value)}
                className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-indigo-500 focus:outline-none"
              >
                {SKILL_CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            {/* 可见性选择 */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5">
                可见性
              </label>
              <div className="flex gap-2">
                {[
                  { value: 'private', label: '私有', desc: '仅自己可见' },
                  { value: 'team', label: '团队', desc: '团队成员可见' },
                  { value: 'public', label: '公开', desc: '所有人可见' },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setSaveVisibility(opt.value)}
                    className={`flex-1 px-3 py-2 rounded-md text-xs font-medium border transition-colors ${
                      saveVisibility === opt.value
                        ? 'bg-indigo-50 dark:bg-indigo-900/30 border-indigo-400 dark:border-indigo-500 text-indigo-700 dark:text-indigo-300'
                        : 'border-zinc-300 dark:border-zinc-600 text-gray-500 dark:text-zinc-400 hover:bg-gray-50 dark:hover:bg-zinc-800'
                    }`}
                  >
                    <div>{opt.label}</div>
                    <div className="text-[10px] opacity-60">{opt.desc}</div>
                  </button>
                ))}
              </div>
            </div>
            {/* 操作按钮 */}
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowSaveModal(false)}
                className="px-4 py-2 text-sm text-gray-600 dark:text-zinc-400 border border-gray-300 dark:border-zinc-600 rounded-md hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleConfirmSave}
                disabled={!saveSkillName.trim() || isSaving}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-600/50 disabled:cursor-not-allowed rounded-md transition-colors flex items-center gap-1.5"
              >
                {isSaving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Star size={14} />
                )}
                确认保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** 生信技能分类选项 */
const SKILL_CATEGORIES = [
  '即席分析',
  '数据可视化',
  '差异分析',
  '功能富集',
  '序列分析',
  '机器学习',
  '统计检验',
  '质量控制',
  '通用',
]

/** 安全复制到剪贴板，兼容非 HTTPS 环境 */
function copyToClipboard(text: string) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    navigator.clipboard.writeText(text).catch(() => fallbackCopy(text))
  } else {
    fallbackCopy(text)
  }
}

function fallbackCopy(text: string) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.left = '-9999px'
  ta.style.top = '-9999px'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  try { document.execCommand('copy') } catch { /* 忽略 */ }
  document.body.removeChild(ta)
}

/** 格式化文件大小 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

/** 格式化已运行时间 (秒 → mm:ss 或 hh:mm:ss) */
function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const mmss = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  if (h > 0) return `${h}:${mmss}`
  return mmss
}
