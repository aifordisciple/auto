/**
 * 批量执行服务
 *
 * P2 专家增强：
 * - 批量提交多个技能执行
 * - 并行度控制
 * - 错误处理策略
 * - 进度跟踪
 */

// ==========================================
// 类型定义
// ==========================================

export interface BatchExecution {
  executions: BatchExecutionItem[];
}

export interface BatchExecutionItem {
  skill_id: string;
  parameters: Record<string, unknown>;
}

export interface BatchExecutionOptions {
  parallelism: number;          // 并行度 (0 = 无限制)
  stopOnError: boolean;         // 遇错停止
  notification: 'all' | 'errors' | 'none';
  onProgress?: (progress: BatchProgress) => void;
  onComplete?: (result: BatchExecutionResult) => void;
}

export interface BatchProgress {
  batchId: string;
  total: number;
  completed: number;
  failed: number;
  running: number;
  status: 'pending' | 'running' | 'completed' | 'cancelled';
}

export interface BatchExecutionResult {
  batchId: string;
  total: number;
  completed: number;
  failed: number;
  status: 'completed' | 'cancelled' | 'partial';
  results: BatchTaskResult[];
  totalExecutionTime: number;
}

export interface BatchTaskResult {
  index: number;
  skill_id: string;
  status: 'success' | 'failed' | 'skipped';
  result?: any;
  error?: string;
  execution_time: number;
}

interface BatchRecord {
  id: string;
  executions: BatchExecutionItem[];
  options: BatchExecutionOptions;
  status: 'pending' | 'running' | 'completed' | 'cancelled';
  results: BatchTaskResult[];
  startTime?: number;
  endTime?: number;
}

// ==========================================
// 服务类
// ==========================================

export class BatchExecutionService {
  private batches: Map<string, BatchRecord> = new Map();
  private abortControllers: Map<string, AbortController> = new Map();

  // ==========================================
  // 创建批量任务
  // ==========================================

  async createBatch(
    executions: BatchExecutionItem[],
    options: BatchExecutionOptions
  ): Promise<string> {
    // 验证
    if (!executions || executions.length === 0) {
      throw new Error('执行列表不能为空');
    }

    for (const exec of executions) {
      if (!exec.skill_id) {
        throw new Error('每个执行项必须包含 skill_id');
      }
    }

    // 生成 ID
    const batchId = this.generateId();

    // 创建记录
    const record: BatchRecord = {
      id: batchId,
      executions: [...executions],
      options: { ...options },
      status: 'pending',
      results: [],
    };

    this.batches.set(batchId, record);

    return batchId;
  }

  // ==========================================
  // 获取批量任务状态
  // ==========================================

  async getBatchStatus(batchId: string): Promise<BatchProgress> {
    const record = this.batches.get(batchId);

    if (!record) {
      throw new Error(`批量任务不存在: ${batchId}`);
    }

    const completed = record.results.filter(
      (r) => r.status === 'success' || r.status === 'failed'
    ).length;
    const failed = record.results.filter((r) => r.status === 'failed').length;

    return {
      batchId,
      total: record.executions.length,
      completed,
      failed,
      running: record.status === 'running' ? record.executions.length - completed : 0,
      status: record.status,
    };
  }

  // ==========================================
  // 开始执行
  // ==========================================

  async startBatch(batchId: string): Promise<BatchExecutionResult> {
    const record = this.batches.get(batchId);

    if (!record) {
      throw new Error(`批量任务不存在: ${batchId}`);
    }

    // 更新状态
    record.status = 'running';
    record.startTime = Date.now();

    // 创建中断控制器
    const abortController = new AbortController();
    this.abortControllers.set(batchId, abortController);

    const results: BatchTaskResult[] = [];
    const parallelism = record.options.parallelism || 0; // 0 = 无限制
    let wasCancelled = false;

    // 分批执行
    const chunks = this.chunkArray(record.executions, parallelism || record.executions.length);

    for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
      // 检查是否被取消（通过 AbortController）
      if (abortController.signal.aborted) {
        wasCancelled = true;
        break;
      }

      const chunk = chunks[chunkIndex];

      // 并行执行当前批次
      const chunkResults = await Promise.all(
        chunk.map((exec, i) =>
          this.executeTask(
            record.executions.indexOf(exec),
            exec,
            abortController.signal
          )
        )
      );

      results.push(...chunkResults);

      // 检查是否有失败且需要停止
      if (record.options.stopOnError) {
        const hasFailure = chunkResults.some((r) => r.status === 'failed');
        if (hasFailure) {
          // 跳过剩余任务
          const remaining = record.executions.length - results.length;
          for (let i = 0; i < remaining; i++) {
            results.push({
              index: results.length,
              skill_id: record.executions[results.length]?.skill_id || '',
              status: 'skipped',
              execution_time: 0,
            });
          }
          break;
        }
      }

      // 更新进度
      if (record.options.onProgress) {
        record.options.onProgress({
          batchId,
          total: record.executions.length,
          completed: results.length,
          failed: results.filter((r) => r.status === 'failed').length,
          running: 0,
          status: 'running',
        });
      }
    }

    // 更新记录
    record.results = results;
    record.endTime = Date.now();
    record.status = wasCancelled ? 'cancelled' : 'completed';

    // 计算结果
    const result: BatchExecutionResult = {
      batchId,
      total: record.executions.length,
      completed: results.filter((r) => r.status === 'success').length,
      failed: results.filter((r) => r.status === 'failed').length,
      status: wasCancelled ? 'cancelled' : 'completed',
      results,
      totalExecutionTime: (record.endTime - (record.startTime || 0)) / 1000,
    };

    // 完成回调
    if (record.options.onComplete) {
      record.options.onComplete(result);
    }

    return result;
  }

  // ==========================================
  // 取消批量任务
  // ==========================================

  async cancelBatch(batchId: string): Promise<void> {
    const record = this.batches.get(batchId);

    if (!record) {
      throw new Error(`批量任务不存在: ${batchId}`);
    }

    // 中断执行
    const controller = this.abortControllers.get(batchId);
    if (controller) {
      controller.abort();
    }

    // 更新状态
    record.status = 'cancelled';
  }

  // ==========================================
  // 私有方法
  // ==========================================

  private generateId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    return `batch_${timestamp}_${random}`;
  }

  private chunkArray<T>(array: T[], size: number): T[][] {
    if (size <= 0 || size >= array.length) {
      return [array];
    }

    const chunks: T[][] = [];
    for (let i = 0; i < array.length; i += size) {
      chunks.push(array.slice(i, i + size));
    }
    return chunks;
  }

  private async executeTask(
    index: number,
    execution: BatchExecutionItem,
    signal: AbortSignal
  ): Promise<BatchTaskResult> {
    const startTime = Date.now();

    try {
      // 模拟执行（实际项目中会调用 API）
      await this.simulateExecution(execution, signal);

      return {
        index,
        skill_id: execution.skill_id,
        status: 'success',
        execution_time: (Date.now() - startTime) / 1000,
      };
    } catch (error: any) {
      return {
        index,
        skill_id: execution.skill_id,
        status: 'failed',
        error: error.message || '执行失败',
        execution_time: (Date.now() - startTime) / 1000,
      };
    }
  }

  private async simulateExecution(
    execution: BatchExecutionItem,
    signal: AbortSignal
  ): Promise<void> {
    // 模拟执行时间
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(resolve, 100);

      signal.addEventListener('abort', () => {
        clearTimeout(timeout);
        reject(new Error('任务已取消'));
      });
    });
  }
}

// ==========================================
// 单例导出
// ==========================================

let instance: BatchExecutionService | null = null;

export function getBatchExecutionService(): BatchExecutionService {
  if (!instance) {
    instance = new BatchExecutionService();
  }
  return instance;
}

export default BatchExecutionService;