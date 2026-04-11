/**
 * 用户行为埋点库
 *
 * 功能：
 * 1. 记录用户行为事件
 * 2. Session 追踪
 * 3. 自动收集页面信息
 * 4. 支持批量上报
 */

// ==========================================
// 类型定义
// ==========================================

/**
 * 用户行为类型枚举
 *
 * 覆盖完整的用户旅程：
 * 1. 查询阶段: query
 * 2. 推荐阶段: recommend
 * 3. 浏览阶段: click, view_detail
 * 4. 执行阶段: execute, modify_param, retry, abort
 * 5. 结果阶段: success, failure
 * 6. 反馈阶段: feedback, favorite, share
 */
export type EventType =
  // 查询阶段
  | 'query'          // 用户发起查询
  // 推荐阶段
  | 'recommend'      // 系统推荐技能
  // 浏览阶段
  | 'click'          // 用户点击技能
  | 'view_detail'    // 查看技能详情
  // 执行阶段
  | 'execute'        // 技能被执行
  | 'modify_param'   // 用户修改参数
  | 'retry'          // 重试执行
  | 'abort'          // 中断执行
  // 结果阶段
  | 'success'        // 执行成功
  | 'failure'        // 执行失败
  // 反馈阶段
  | 'feedback'       // 用户反馈
  | 'favorite'       // 收藏技能
  | 'share'          // 分享结果
  // 其他
  | 'page_view'      // 页面访问
  | 'error';         // 错误

export interface AnalyticsEvent {
  event_type: EventType;
  session_id: string;
  timestamp: number;
  user_id?: number;
  skill_id?: string;
  skill_name?: string;
  query?: string;
  // 匹配相关
  match_source?: 'rule' | 'vector' | 'llm' | 'hybrid';
  confidence?: number;
  // 执行相关
  parameters?: Record<string, unknown>;
  execution_time?: number;
  error_message?: string;
  // 反馈相关
  feedback_rating?: number;
  feedback_text?: string;
  // 元数据
  metadata?: Record<string, unknown>;
}

export interface AnalyticsConfig {
  enabled: boolean;
  batchSize: number;
  flushInterval: number;  // ms
  endpoint: string;
}

// ==========================================
// 默认配置
// ==========================================

const DEFAULT_CONFIG: AnalyticsConfig = {
  enabled: true,
  batchSize: 10,
  flushInterval: 30000, // 30秒
  endpoint: '/api/analytics/events',
};

// ==========================================
// Analytics 类
// ==========================================

class Analytics {
  private config: AnalyticsConfig;
  private sessionId: string;
  private userId: number | null = null;
  private eventQueue: AnalyticsEvent[] = [];
  private flushTimer: ReturnType<typeof setInterval> | null = null;

  constructor(config: Partial<AnalyticsConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.sessionId = this.generateSessionId();
    this.startFlushTimer();

    // 页面卸载时上报
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => this.flush());
    }
  }

  // ==========================================
  // 公共方法
  // ==========================================

  /**
   * 设置用户ID
   */
  setUserId(userId: number | null): void {
    this.userId = userId;
  }

  /**
   * 获取 Session ID
   */
  getSessionId(): string {
    return this.sessionId;
  }

  /**
   * 记录事件
   */
  track(
    eventType: EventType,
    data: Partial<Omit<AnalyticsEvent, 'event_type' | 'session_id' | 'timestamp'>> = {}
  ): void {
    if (!this.config.enabled) return;

    const event: AnalyticsEvent = {
      event_type: eventType,
      session_id: this.sessionId,
      timestamp: Date.now(),
      user_id: this.userId || undefined,
      ...data,
    };

    this.eventQueue.push(event);

    // 达到批量大小时立即上报
    if (this.eventQueue.length >= this.config.batchSize) {
      this.flush();
    }
  }

  // ==========================================
  // 便捷方法
  // ==========================================

  /**
   * 页面访问
   */
  pageView(pageName: string, metadata?: Record<string, unknown>): void {
    this.track('page_view', {
      metadata: { page_name: pageName, ...metadata },
    });
  }

  /**
   * 用户发起查询
   */
  query(queryText: string, resultCount?: number): void {
    this.track('query', {
      query: queryText,
      metadata: resultCount !== undefined ? { result_count: resultCount } : undefined,
    });
  }

  /**
   * 系统推荐技能
   */
  recommend(
    skillId: string,
    skillName: string,
    queryText: string,
    matchSource: 'rule' | 'vector' | 'llm' | 'hybrid',
    confidence: number
  ): void {
    this.track('recommend', {
      skill_id: skillId,
      skill_name: skillName,
      query: queryText,
      match_source: matchSource,
      confidence,
    });
  }

  /**
   * 用户点击技能
   */
  click(skillId: string, skillName: string): void {
    this.track('click', {
      skill_id: skillId,
      skill_name: skillName,
    });
  }

  /**
   * 查看技能详情
   */
  viewDetail(skillId: string, skillName: string): void {
    this.track('view_detail', {
      skill_id: skillId,
      skill_name: skillName,
    });
  }

  /**
   * 技能执行
   */
  execute(skillId: string, skillName: string, parameters?: Record<string, unknown>): void {
    this.track('execute', {
      skill_id: skillId,
      skill_name: skillName,
      metadata: parameters ? { parameters } : undefined,
    });
  }

  /**
   * 用户修改参数
   */
  modifyParam(skillId: string, skillName: string, paramName: string, paramValue: unknown): void {
    this.track('modify_param', {
      skill_id: skillId,
      skill_name: skillName,
      metadata: { param_name: paramName, param_value: paramValue },
    });
  }

  /**
   * 重试执行
   */
  retry(skillId: string, skillName: string): void {
    this.track('retry', {
      skill_id: skillId,
      skill_name: skillName,
    });
  }

  /**
   * 中断执行
   */
  abort(skillId: string, skillName: string): void {
    this.track('abort', {
      skill_id: skillId,
      skill_name: skillName,
    });
  }

  /**
   * 执行成功
   */
  success(skillId: string, skillName: string, executionTime: number): void {
    this.track('success', {
      skill_id: skillId,
      skill_name: skillName,
      execution_time: executionTime,
    });
  }

  /**
   * 执行失败
   */
  failure(skillId: string, skillName: string, errorMessage: string): void {
    this.track('failure', {
      skill_id: skillId,
      skill_name: skillName,
      error_message: errorMessage,
    });
  }

  /**
   * 用户反馈
   */
  feedback(skillId: string, skillName: string, rating: number, text?: string): void {
    this.track('feedback', {
      skill_id: skillId,
      skill_name: skillName,
      feedback_rating: rating,
      feedback_text: text,
    });
  }

  /**
   * 收藏技能
   */
  favorite(skillId: string, skillName: string): void {
    this.track('favorite', {
      skill_id: skillId,
      skill_name: skillName,
    });
  }

  /**
   * 分享结果
   */
  share(skillId: string, skillName: string): void {
    this.track('share', {
      skill_id: skillId,
      skill_name: skillName,
    });
  }

  /**
   * 错误
   */
  error(errorType: string, errorMessage: string, metadata?: Record<string, unknown>): void {
    this.track('error', {
      error_message: errorMessage,
      metadata: { error_type: errorType, ...metadata },
    });
  }

  // ==========================================
  // 内部方法
  // ==========================================

  /**
   * 生成 Session ID
   */
  private generateSessionId(): string {
    // 使用时间戳 + 随机数
    return `${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
  }

  /**
   * 启动定时上报
   */
  private startFlushTimer(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
    }
    this.flushTimer = setInterval(() => this.flush(), this.config.flushInterval);
  }

  /**
   * 上报事件
   */
  private async flush(): Promise<void> {
    if (this.eventQueue.length === 0) return;

    const events = [...this.eventQueue];
    this.eventQueue = [];

    try {
      // 使用 sendBeacon 优先（页面卸载时更可靠）
      if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify({ events })], {
          type: 'application/json',
        });
        navigator.sendBeacon(this.config.endpoint, blob);
      } else {
        // 降级到 fetch
        await fetch(this.config.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ events }),
          keepalive: true,
        });
      }
    } catch (error) {
      // 上报失败，放回队列
      console.error('[Analytics] Failed to flush events:', error);
      this.eventQueue = [...events, ...this.eventQueue];
    }
  }
}

// ==========================================
// 全局单例
// ==========================================

let analyticsInstance: Analytics | null = null;

export function getAnalytics(): Analytics {
  if (!analyticsInstance) {
    analyticsInstance = new Analytics();
  }
  return analyticsInstance;
}

// ==========================================
// 便捷导出
// ==========================================

export const analytics = {
  // 基础方法
  track: (eventType: EventType, data?: Partial<AnalyticsEvent>) => getAnalytics().track(eventType, data),
  setUserId: (userId: number | null) => getAnalytics().setUserId(userId),
  getSessionId: () => getAnalytics().getSessionId(),

  // 页面访问
  pageView: (pageName: string, metadata?: Record<string, unknown>) => getAnalytics().pageView(pageName, metadata),

  // 查询阶段
  query: (queryText: string, resultCount?: number) => getAnalytics().query(queryText, resultCount),

  // 推荐阶段
  recommend: (
    skillId: string,
    skillName: string,
    queryText: string,
    matchSource: 'rule' | 'vector' | 'llm' | 'hybrid',
    confidence: number
  ) => getAnalytics().recommend(skillId, skillName, queryText, matchSource, confidence),

  // 浏览阶段
  click: (skillId: string, skillName: string) => getAnalytics().click(skillId, skillName),
  viewDetail: (skillId: string, skillName: string) => getAnalytics().viewDetail(skillId, skillName),

  // 执行阶段
  execute: (skillId: string, skillName: string, parameters?: Record<string, unknown>) =>
    getAnalytics().execute(skillId, skillName, parameters),
  modifyParam: (skillId: string, skillName: string, paramName: string, paramValue: unknown) =>
    getAnalytics().modifyParam(skillId, skillName, paramName, paramValue),
  retry: (skillId: string, skillName: string) => getAnalytics().retry(skillId, skillName),
  abort: (skillId: string, skillName: string) => getAnalytics().abort(skillId, skillName),

  // 结果阶段
  success: (skillId: string, skillName: string, executionTime: number) =>
    getAnalytics().success(skillId, skillName, executionTime),
  failure: (skillId: string, skillName: string, errorMessage: string) =>
    getAnalytics().failure(skillId, skillName, errorMessage),

  // 反馈阶段
  feedback: (skillId: string, skillName: string, rating: number, text?: string) =>
    getAnalytics().feedback(skillId, skillName, rating, text),
  favorite: (skillId: string, skillName: string) => getAnalytics().favorite(skillId, skillName),
  share: (skillId: string, skillName: string) => getAnalytics().share(skillId, skillName),

  // 错误
  error: (errorType: string, errorMessage: string, metadata?: Record<string, unknown>) =>
    getAnalytics().error(errorType, errorMessage, metadata),

  // 向后兼容方法
  /** @deprecated 使用 query 代替 */
  skillSearch: (query: string, resultCount: number) => getAnalytics().query(query, resultCount),
  /** @deprecated 使用 viewDetail 代替 */
  skillView: (skillId: string, skillName: string) => getAnalytics().viewDetail(skillId, skillName),
  /** @deprecated 使用 execute 代替 */
  skillExecute: (skillId: string, skillName: string, parameters?: Record<string, unknown>) =>
    getAnalytics().execute(skillId, skillName, parameters),
  /** @deprecated 使用 success 代替 */
  skillSuccess: (skillId: string, skillName: string, executionTime: number) =>
    getAnalytics().success(skillId, skillName, executionTime),
  /** @deprecated 使用 failure 代替 */
  skillFailure: (skillId: string, skillName: string, errorMessage: string) =>
    getAnalytics().failure(skillId, skillName, errorMessage),
  /** @deprecated 使用 favorite 代替 */
  skillBookmark: (skillId: string, skillName: string) => getAnalytics().favorite(skillId, skillName),
};