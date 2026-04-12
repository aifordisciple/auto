"use client";

/**
 * SysLogCard - 迷你终端日志卡片
 *
 * V2 架构增强：
 * 1. 等宽字体 + ANSI 颜色渲染
 * 2. 自动滚动（可锁定）
 * 3. 默认显示 5 行 / 可展开
 * 4. 搜索过滤
 * 5. 流式日志追加
 * 6. 可选的重新执行按钮
 */

import React, { useState, useEffect, useRef, useMemo } from "react";
import { Terminal, RefreshCw, ChevronDown, ChevronUp, Search, X } from "lucide-react";
import styles from "./SysLogCard.module.css";

export interface SysLogCardProps {
  /** 日志内容数组 */
  logs: string[];
  /** 重新执行回调 */
  onRetry?: () => void;
  /** 是否可折叠 */
  collapsible?: boolean;
  /** 初始折叠状态 */
  defaultCollapsed?: boolean;
  /** V2: 默认显示行数 */
  defaultVisibleLines?: number;
  /** V2: 执行 ID（同执行 ID 日志追加到同一卡片） */
  executionId?: string;
}

// ==========================================
// ANSI 颜色解析
// ==========================================

/** 简化的 ANSI 颜色映射 */
const ANSI_COLORS: Record<number, string> = {
  31: "#ef4444", // red
  32: "#22c55e", // green
  33: "#f59e0b", // yellow
  34: "#3b82f6", // blue
  35: "#8b5cf6", // magenta
  36: "#06b6d4", // cyan
  37: "#e5e7eb", // white
};

/** 解析 ANSI 转义序列并返回 React 节点 */
function renderAnsiText(text: string): React.ReactNode {
  // 简化 ANSI 解析：匹配 \x1b[XXm 格式
  const ansiPattern = /\x1b\[(\d+)m/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let currentColor: string | null = null;
  let match: RegExpExecArray | null;

  while ((match = ansiPattern.exec(text)) !== null) {
    // 添加前面的文本
    if (match.index > lastIndex) {
      const segment = text.slice(lastIndex, match.index);
      parts.push(
        currentColor
          ? <span key={parts.length} style={{ color: currentColor }}>{segment}</span>
          : <span key={parts.length}>{segment}</span>
      );
    }

    const code = parseInt(match[1], 10);
    if (code === 0) {
      currentColor = null; // reset
    } else if (ANSI_COLORS[code]) {
      currentColor = ANSI_COLORS[code];
    }

    lastIndex = match.index + match[0].length;
  }

  // 剩余文本
  if (lastIndex < text.length) {
    const segment = text.slice(lastIndex);
    parts.push(
      currentColor
        ? <span key={parts.length} style={{ color: currentColor }}>{segment}</span>
        : <span key={parts.length}>{segment}</span>
    );
  }

  return parts.length > 0 ? <>{parts}</> : text;
}

/** 日志级别颜色 */
function getLogLevelColor(log: string): string {
  if (log.includes("[ERROR]") || log.includes("❌")) return "var(--color-error, #ef4444)";
  if (log.includes("[WARN]") || log.includes("⚠️")) return "var(--color-warning, #f59e0b)";
  if (log.includes("[SUCCESS]") || log.includes("✅")) return "var(--color-success, #22c55e)";
  if (log.includes("[INFO]") || log.includes("ℹ️")) return "var(--color-info, #3b82f6)";
  return "var(--color-muted, #6b7280)";
}

/** 格式化时间戳 */
function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp);
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const seconds = date.getSeconds().toString().padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

// ==========================================
// 主组件
// ==========================================

export const SysLogCard: React.FC<SysLogCardProps> = ({
  logs,
  onRetry,
  collapsible = true,
  defaultCollapsed = false,
  defaultVisibleLines = 5,
  executionId,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);
  const [isExpanded, setIsExpanded] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // 搜索过滤
  const filteredLogs = useMemo(() => {
    if (!searchQuery) return logs;
    return logs.filter(log =>
      log.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [logs, searchQuery]);

  // 是否截断显示
  const visibleLogs = isExpanded ? filteredLogs : filteredLogs.slice(-defaultVisibleLines);
  const hasMore = filteredLogs.length > defaultVisibleLines && !isExpanded;

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && logContainerRef.current && !isCollapsed) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [filteredLogs, autoScroll, isCollapsed]);

  // 处理滚动事件
  const handleScroll = () => {
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      setAutoScroll(isAtBottom);
    }
  };

  return (
    <div className={styles.container}>
      {/* 头部 */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Terminal className={styles.icon} size={14} />
          <span className={styles.title}>System Log</span>
          <span className={styles.badge}>{logs.length} entries</span>
          {executionId && (
            <span className={styles.execId}>#{executionId.slice(0, 8)}</span>
          )}
        </div>
        <div className={styles.headerRight}>
          <button
            className={styles.searchButton}
            onClick={() => setShowSearch(!showSearch)}
            title="搜索"
          >
            <Search size={12} />
          </button>
          {onRetry && (
            <button
              className={styles.retryButton}
              onClick={onRetry}
              title="重新执行"
            >
              <RefreshCw size={12} />
              <span>重试</span>
            </button>
          )}
          {collapsible && (
            <button
              className={styles.collapseButton}
              onClick={() => setIsCollapsed(!isCollapsed)}
              title={isCollapsed ? "展开" : "折叠"}
            >
              {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            </button>
          )}
        </div>
      </div>

      {/* 搜索栏 */}
      {showSearch && !isCollapsed && (
        <div className={styles.searchBar}>
          <Search size={12} className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索日志..."
            autoFocus
          />
          {searchQuery && (
            <button
              className={styles.searchClear}
              onClick={() => setSearchQuery("")}
            >
              <X size={12} />
            </button>
          )}
        </div>
      )}

      {/* 日志内容 */}
      {!isCollapsed && (
        <div
          className={styles.logContainer}
          ref={logContainerRef}
          onScroll={handleScroll}
        >
          {visibleLogs.map((log, index) => (
            <div
              key={index}
              className={styles.logEntry}
              style={{ color: getLogLevelColor(log) }}
            >
              <span className={styles.timestamp}>
                {formatTimestamp(Date.now() - (filteredLogs.length - index) * 1000)}
              </span>
              <span className={styles.logContent}>
                {renderAnsiText(log)}
              </span>
            </div>
          ))}
          {hasMore && (
            <button
              className={styles.expandButton}
              onClick={() => setIsExpanded(true)}
            >
              显示全部 {filteredLogs.length} 行 ▼
            </button>
          )}
        </div>
      )}

      {/* 底部状态栏 */}
      <div className={styles.footer}>
        <span className={styles.status}>
          {autoScroll ? "Auto-scroll ON" : "Auto-scroll OFF"}
        </span>
        {!autoScroll && (
          <button
            className={styles.scrollToBottom}
            onClick={() => {
              setAutoScroll(true);
              if (logContainerRef.current) {
                logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
              }
            }}
          >
            滚动到底部
          </button>
        )}
      </div>
    </div>
  );
};

export default SysLogCard;
