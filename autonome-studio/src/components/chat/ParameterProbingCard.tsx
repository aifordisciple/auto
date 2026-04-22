'use client'

import { useState } from 'react'

/**
 * JSON Schema 属性定义（简化版，仅支持 L2 探查所需的类型）
 */
export interface SchemaProperty {
  type: 'string' | 'number' | 'boolean'
  title?: string
  description?: string
  enum?: string[]
  default?: string | number | boolean
  minimum?: number
  maximum?: number
  step?: number
}

export interface ParameterProbingCardProps {
  /** 追问提示语 */
  message: string
  /** JSON Schema 定义（包含 properties 和 required） */
  schema: {
    type: string
    properties: Record<string, SchemaProperty>
    required?: string[]
  }
  /** 提交回调：将用户填写的参数传回 */
  onSubmit: (values: Record<string, unknown>) => void
}

/**
 * 参数探查卡片 — Active Probing 的前端 Generative UI 组件。
 *
 * 当 L2 层检测到参数缺失时，后端通过 ToolCall 发送 JSON Schema，
 * 前端使用此组件动态渲染表单，用户补全后参数合并回 TaskNode。
 *
 * 样式：橙色边框卡片，标题"系统拦截：缺失必要参数"
 */
export function ParameterProbingCard({ message, schema, onSubmit }: ParameterProbingCardProps) {
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    // 预填 default 值
    const defaults: Record<string, unknown> = {}
    for (const [key, prop] of Object.entries(schema.properties)) {
      if (prop.default !== undefined) {
        defaults[key] = prop.default
      }
    }
    return defaults
  })

  const handleChange = (key: string, value: unknown) => {
    setValues(prev => ({ ...prev, [key]: value }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(values)
  }

  return (
    <div className="my-3 rounded-lg border-2 border-orange-500/60 bg-orange-500/5 p-4">
      {/* 标题栏 */}
      <div className="mb-3 flex items-center gap-2 text-orange-400">
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
        <span className="font-semibold">系统拦截：缺失必要参数</span>
      </div>

      {/* 提示语 */}
      {message && (
        <p className="mb-4 text-sm text-zinc-300">{message}</p>
      )}

      {/* 动态表单 */}
      <form onSubmit={handleSubmit} className="space-y-3">
        {Object.entries(schema.properties).map(([key, prop]) => (
          <div key={key}>
            <label className="mb-1 block text-sm font-medium text-zinc-300">
              {prop.title || key}
              {schema.required?.includes(key) && <span className="ml-1 text-red-400">*</span>}
            </label>

            {/* enum → 下拉选择框 */}
            {prop.enum ? (
              <select
                value={String(values[key] ?? prop.default ?? '')}
                onChange={e => handleChange(key, e.target.value)}
                className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-white focus:border-orange-500 focus:outline-none"
              >
                {prop.enum.map(opt => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : prop.type === 'boolean' ? (
              /* boolean → 开关 */
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={Boolean(values[key] ?? prop.default ?? false)}
                  onChange={e => handleChange(key, e.target.checked)}
                  className="h-4 w-4 rounded border-zinc-600 text-orange-500 focus:ring-orange-500"
                />
                <span className="text-sm text-zinc-400">{prop.description || '启用'}</span>
              </label>
            ) : prop.type === 'number' ? (
              /* number → 数字输入框 */
              <input
                type="number"
                value={Number(values[key] ?? prop.default ?? 0)}
                onChange={e => handleChange(key, Number(e.target.value))}
                min={prop.minimum}
                max={prop.maximum}
                step={prop.step ?? 1}
                className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-white focus:border-orange-500 focus:outline-none"
              />
            ) : (
              /* string → 文本输入框 */
              <input
                type="text"
                value={String(values[key] ?? prop.default ?? '')}
                onChange={e => handleChange(key, e.target.value)}
                placeholder={prop.description || `请输入 ${prop.title || key}`}
                className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-white focus:border-orange-500 focus:outline-none"
              />
            )}
          </div>
        ))}

        {/* 提交按钮 */}
        <button
          type="submit"
          className="mt-2 rounded-md bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-zinc-900"
        >
          确认提交
        </button>
      </form>
    </div>
  )
}
