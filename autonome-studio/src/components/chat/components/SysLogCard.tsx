"use client";

/**
 * SysLogCard - 迷你终端日志卡片
 *
 * V2 架构：当后端推送 [SYS_LOG] 标签时，前端渲染科技感迷你终端。
 * 用于展示执行状态、缓解用户等待焦虑。
 *
 * 功能：
 * 1. 渲染科技感迷你终端样式
 * 2. 流式日志追加
 * 3. 可选的重新执行按钮
 */

import React, { useState, useEffect, useRef } from "react";
import { Terminal, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
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
}

/**
 * 将日志级别转换为颜色
 */
function getLogLevelColor(log: string): string {
  if (log.includes("[ERROR]") || log.includes("❌")) {
    return "var(--color-error, #ef4444)";
  }
  if (log.includes("[WARN]") || log.includes("⚠️")) {
    return "var(--color-warning, #f59e0b)";
  }
  if (log.includes("[SUCCESS]") || log.includes("✅")) {
    return "var(--color-success, #22c55e)";
  }
  if (log.includes("[INFO]") || log.includes("ℹ️")) {
    return "var(--color-info, #3b82f6)";
  }
  return "var(--color-muted, #6b7280)";
}

/**
 * 格式化时间戳
 */
function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp);
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const seconds = date.getSeconds().toString().padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

export const SysLogCard: React.FC<SysLogCardProps> = ({
  logs,
  onRetry,
  collapsible = true,
  defaultCollapsed = false,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && logContainerRef.current && !isCollapsed) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll, isCollapsed]);

  // 处理滚动事件，判断是否在底部
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
        </div>
        <div className={styles.headerRight}>
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

      {/* 日志内容 */}
      {!isCollapsed && (
        <div
          className={styles.logContainer}
          ref={logContainerRef}
          onScroll={handleScroll}
        >
          {logs.map((log, index) => (
            <div
              key={index}
              className={styles.logEntry}
              style={{ color: getLogLevelColor(log) }}
            >
              <span className={styles.timestamp}>
                {formatTimestamp(Date.now() - (logs.length - index) * 1000)}
              </span>
              <span className={styles.logContent}>{log}</span>
            </div>
          ))}
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
