"use client";

/**
 * InlineActionMenu - 内联操作菜单组件
 *
 * V2 架构：当后端置信度 < 0.90 时，在聊天气泡中渲染技能选项列表。
 * 用户点击选项后，原地平滑展开为 Strategy Card。
 *
 * 功能：
 * 1. 渲染技能选项列表（带匹配度徽章）
 * 2. 包含 Live Coding 兜底选项
 * 3. 点击后静默调用后端 API 获取预填参数
 * 4. 视觉上平滑切换到 Strategy Card
 */

import React, { useState, useCallback } from "react";
import { Loader2, Zap, ChevronRight } from "lucide-react";
import styles from "./InlineActionMenu.module.css";

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

interface InlineActionMenuProps {
  data: ActionMenuData;
  onSelect: (skillId: string) => void;
  onExpandToStrategyCard?: (skillId: string, strategyData: unknown) => void;
}

/**
 * 将匹配分数转换为徽章颜色
 */
function getMatchBadgeColor(score: number): string {
  if (score >= 0.85) return "var(--color-success, #22c55e)";
  if (score >= 0.7) return "var(--color-warning, #f59e0b)";
  return "var(--color-muted, #6b7280)";
}

/**
 * 将匹配分数转换为徽章文字
 */
function getMatchBadgeText(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export default function InlineActionMenu({
  data,
  onSelect,
}: InlineActionMenuProps) {
  const [loadingSkillId, setLoadingSkillId] = useState<string | null>(null);

  const handleOptionClick = useCallback(
    async (option: ActionMenuOption) => {
      if (option.skill_id === "live_coding") {
        // Live Coding 直接触发
        onSelect("live_coding");
        return;
      }

      setLoadingSkillId(option.skill_id);

      try {
        // 静默调用后端 API 获取预填参数
        // 注意：这里不需要等待完成，状态由父组件管理
        onSelect(option.skill_id);
      } catch (error) {
        console.error("[InlineActionMenu] 获取技能参数失败:", error);
      } finally {
        setLoadingSkillId(null);
      }
    },
    [onSelect]
  );

  const { options = [], title = "请选择操作", message } = data;

  return (
    <div className={styles.container}>
      {/* 标题 */}
      <div className={styles.header}>
        <span className={styles.title}>{title}</span>
        {message && <p className={styles.message}>{message}</p>}
      </div>

      {/* 选项列表 */}
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

      {/* 底部提示 */}
      <div className={styles.footer}>
        <span className={styles.hint}>
          选择一个选项后，AI 将自动填入参数
        </span>
      </div>
    </div>
  );
}
