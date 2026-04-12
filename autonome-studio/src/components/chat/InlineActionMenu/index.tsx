"use client";

/**
 * InlineActionMenu - 内联操作菜单组件
 *
 * V2 架构：4 阶段工作流
 * 1. select  - 渲染技能选项列表（带匹配度徽章）
 * 2. params  - 参数配置表单（预填 + 可编辑）
 * 3. execute - 执行中状态（进度 + 日志）
 * 4. result  - 执行结果（平滑转换为 StrategyCard）
 *
 * 阶段 4→StrategyCard 使用 framer-motion 平滑过渡动画
 */

import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Zap, ChevronRight, Play, CheckCircle, XCircle, ArrowLeft, Settings2 } from "lucide-react";
import styles from "./InlineActionMenu.module.css";

// ==========================================
// 类型定义
// ==========================================

export interface ActionMenuOption {
  skill_id: string;
  name: string;
  match_score: number;
  match_reason?: string;
}

export interface ActionMenuData {
  title?: string;
  message?: string;
  options: ActionMenuOption[];
}

/** V2: 工作流阶段 */
type WorkflowStage = "select" | "params" | "execute" | "result";

/** V2: 参数字段定义 */
interface ParamField {
  key: string;
  label: string;
  type: "string" | "number" | "boolean" | "select";
  value: unknown;
  default?: unknown;
  options?: string[];
  required?: boolean;
  /** V2: 参数来源标记（M4 智能参数系统） */
  source?: "explicit" | "extracted" | "workspace" | "default" | "null";
}

interface InlineActionMenuProps {
  data: ActionMenuData;
  onSelect: (skillId: string) => void;
  onExpandToStrategyCard?: (skillId: string, strategyData: unknown) => void;
  /** V2: 预填参数（由父组件从 API 获取后传入） */
  paramsData?: ParamField[];
  /** V2: 执行状态 */
  isExecuting?: boolean;
  /** V2: 执行结果 */
  executeResult?: { success: boolean; output?: string; error?: string };
  /** V2: 当前阶段（由父组件控制） */
  stage?: WorkflowStage;
  /** V2: 阶段变更回调 */
  onStageChange?: (stage: WorkflowStage) => void;
  /** V2: 参数提交回调 */
  onParamsSubmit?: (params: Record<string, unknown>) => void;
}

// ==========================================
// 辅助函数
// ==========================================

function getMatchBadgeColor(score: number): string {
  if (score >= 0.85) return "var(--color-success, #22c55e)";
  if (score >= 0.7) return "var(--color-warning, #f59e0b)";
  return "var(--color-muted, #6b7280)";
}

function getMatchBadgeText(score: number): string {
  return `${Math.round(score * 100)}%`;
}

/** V2: 参数来源对应的边框颜色 */
function getSourceBorderColor(source?: string): string {
  switch (source) {
    case "explicit": return "var(--color-success, #22c55e)";
    case "extracted": return "var(--color-warning, #f59e0b)";
    case "workspace": return "var(--color-info, #3b82f6)";
    case "default": return "var(--color-muted, #6b7280)";
    case "null": return "var(--color-error, #ef4444)";
    default: return "transparent";
  }
}

// ==========================================
// 阶段动画配置
// ==========================================

const stageVariants = {
  enter: { opacity: 0, x: 20 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -20 },
};

// ==========================================
// 主组件
// ==========================================

export default function InlineActionMenu({
  data,
  onSelect,
  onExpandToStrategyCard,
  paramsData,
  isExecuting = false,
  executeResult,
  stage: controlledStage,
  onStageChange,
  onParamsSubmit,
}: InlineActionMenuProps) {
  // V2: 阶段状态（支持受控和非受控模式）
  const [internalStage, setInternalStage] = useState<WorkflowStage>("select");
  const stage = controlledStage ?? internalStage;

  const setStage = useCallback((newStage: WorkflowStage) => {
    if (onStageChange) {
      onStageChange(newStage);
    } else {
      setInternalStage(newStage);
    }
  }, [onStageChange]);

  const [loadingSkillId, setLoadingSkillId] = useState<string | null>(null);
  const [selectedOption, setSelectedOption] = useState<ActionMenuOption | null>(null);
  const [editedParams, setEditedParams] = useState<Record<string, unknown>>({});

  // ==========================================
  // 阶段 1: 选择技能
  // ==========================================
  const handleOptionClick = useCallback(
    async (option: ActionMenuOption) => {
      if (option.skill_id === "live_coding") {
        onSelect("live_coding");
        return;
      }

      setLoadingSkillId(option.skill_id);
      setSelectedOption(option);

      try {
        onSelect(option.skill_id);
        // V2: 选择后进入参数阶段
        setStage("params");
      } catch (error) {
        console.error("[InlineActionMenu] 获取技能参数失败:", error);
      } finally {
        setLoadingSkillId(null);
      }
    },
    [onSelect, setStage]
  );

  // ==========================================
  // 阶段 2: 参数提交
  // ==========================================
  const handleParamsSubmit = useCallback(() => {
    if (onParamsSubmit) {
      onParamsSubmit(editedParams);
    }
    setStage("execute");
  }, [editedParams, onParamsSubmit, setStage]);

  const handleParamChange = useCallback((key: string, value: unknown) => {
    setEditedParams(prev => ({ ...prev, [key]: value }));
  }, []);

  // ==========================================
  // 阶段 4: 结果确认
  // ==========================================
  const handleResultConfirm = useCallback(() => {
    if (onExpandToStrategyCard && selectedOption && executeResult) {
      onExpandToStrategyCard(selectedOption.skill_id, executeResult);
    }
  }, [onExpandToStrategyCard, selectedOption, executeResult]);

  const { options = [], title = "请选择操作", message } = data;

  return (
    <div className={styles.container}>
      <AnimatePresence mode="wait">
        {/* ==========================================
            阶段 1: 选择技能
            ========================================== */}
        {stage === "select" && (
          <motion.div
            key="select"
            variants={stageVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2 }}
          >
            <div className={styles.header}>
              <span className={styles.title}>{title}</span>
              {message && <p className={styles.message}>{message}</p>}
            </div>

            <div className={styles.options}>
              {options.map((option) => {
                const isLiveCoding = option.skill_id === "live_coding";
                const isLoading = loadingSkillId === option.skill_id;

                return (
                  <button
                    key={option.skill_id}
                    className={`${styles.option} ${isLiveCoding ? styles.liveCoding : ""}`}
                    onClick={() => handleOptionClick(option)}
                    disabled={isLoading}
                  >
                    <div className={styles.optionContent}>
                      <span className={styles.optionName}>
                        {isLiveCoding && <Zap className={styles.liveIcon} size={14} />}
                        {option.name}
                      </span>
                      {option.match_reason && (
                        <span className={styles.matchReason}>{option.match_reason}</span>
                      )}
                    </div>

                    <div className={styles.optionRight}>
                      {!isLiveCoding && (
                        <span
                          className={styles.matchBadge}
                          style={{ color: getMatchBadgeColor(option.match_score) }}
                        >
                          {getMatchBadgeText(option.match_score)}
                        </span>
                      )}
                      {isLoading ? (
                        <Loader2 className={styles.loader} size={14} />
                      ) : (
                        <ChevronRight className={styles.chevron} size={14} />
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            <div className={styles.footer}>
              <span className={styles.hint}>
                选择一个选项后，AI 将自动填入参数
              </span>
            </div>
          </motion.div>
        )}

        {/* ==========================================
            阶段 2: 参数配置
            ========================================== */}
        {stage === "params" && (
          <motion.div
            key="params"
            variants={stageVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2 }}
          >
            <div className={styles.headerRow}>
              <button
                className={styles.backButton}
                onClick={() => setStage("select")}
              >
                <ArrowLeft size={14} />
              </button>
              <Settings2 size={16} className={styles.stageIcon} />
              <span className={styles.title}>
                {selectedOption?.name || "参数配置"}
              </span>
            </div>

            {paramsData && paramsData.length > 0 ? (
              <div className={styles.paramsForm}>
                {paramsData.map((field) => (
                  <div key={field.key} className={styles.paramField}>
                    <label className={styles.paramLabel}>
                      {field.label}
                      {field.required && <span className={styles.required}>*</span>}
                    </label>
                    <input
                      className={styles.paramInput}
                      type={field.type === "number" ? "number" : "text"}
                      value={String(editedParams[field.key] ?? field.value ?? field.default ?? "")}
                      onChange={(e) => handleParamChange(
                        field.key,
                        field.type === "number" ? Number(e.target.value) : e.target.value
                      )}
                      style={{ borderColor: getSourceBorderColor(field.source) }}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <div className={styles.paramsLoading}>
                <Loader2 className={styles.loader} size={16} />
                <span>正在获取参数配置...</span>
              </div>
            )}

            <div className={styles.footer}>
              <button
                className={styles.executeButton}
                onClick={handleParamsSubmit}
                disabled={!paramsData || paramsData.length === 0}
              >
                <Play size={14} />
                <span>执行</span>
              </button>
            </div>
          </motion.div>
        )}

        {/* ==========================================
            阶段 3: 执行中
            ========================================== */}
        {stage === "execute" && (
          <motion.div
            key="execute"
            variants={stageVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2 }}
          >
            <div className={styles.header}>
              <span className={styles.title}>
                {selectedOption?.name || "执行中"}
              </span>
            </div>

            <div className={styles.executingState}>
              <Loader2 className={styles.executingSpinner} size={24} />
              <span className={styles.executingText}>
                正在执行 {selectedOption?.name}...
              </span>
            </div>
          </motion.div>
        )}

        {/* ==========================================
            阶段 4: 执行结果
            ========================================== */}
        {stage === "result" && (
          <motion.div
            key="result"
            variants={stageVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2 }}
          >
            <div className={styles.header}>
              <span className={styles.title}>
                {selectedOption?.name || "执行结果"}
              </span>
            </div>

            <div className={styles.resultState}>
              {executeResult?.success ? (
                <>
                  <CheckCircle size={20} className={styles.resultSuccess} />
                  <span className={styles.resultText}>执行成功</span>
                </>
              ) : (
                <>
                  <XCircle size={20} className={styles.resultError} />
                  <span className={styles.resultText}>
                    执行失败: {executeResult?.error || "未知错误"}
                  </span>
                </>
              )}
            </div>

            <div className={styles.footer}>
              {executeResult?.success && onExpandToStrategyCard && (
                <button
                  className={styles.executeButton}
                  onClick={handleResultConfirm}
                >
                  <span>查看详情</span>
                  <ChevronRight size={14} />
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
