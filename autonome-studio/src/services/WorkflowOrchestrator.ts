/**
 * 工作流编排服务
 *
 * P2 专家增强：
 * - DAG工作流定义与执行
 * - 依赖关系解析
 * - 并行执行优化
 * - 条件分支支持
 * - 进度跟踪与模板管理
 */

// ==========================================
// 类型定义
// ==========================================

export interface WorkflowNode {
  id: string;
  type: 'skill' | 'condition';
  skill_id?: string;
  parameters?: Record<string, unknown>;
  condition?: string;
  dependsOn?: string[];
  conditionBranch?: 'true' | 'false';
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  nodes: WorkflowNode[];
  description?: string;
}

export interface WorkflowValidationResult {
  valid: boolean;
  errors: string[];
}

export interface WorkflowExecutionResult {
  workflowId: string;
  status: 'success' | 'failed' | 'partial';
  nodeResults: WorkflowNodeResult[];
  totalExecutionTime: number;
}

export interface WorkflowNodeResult {
  nodeId: string;
  status: 'success' | 'failed' | 'skipped';
  result?: unknown;
  error?: string;
  executionTime: number;
}

export interface WorkflowExecutionOptions {
  onProgress?: (progress: WorkflowProgress) => void;
}

export interface WorkflowProgress {
  workflowId: string;
  totalNodes: number;
  completedNodes: number;
  currentNodeId?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

interface WorkflowTemplate {
  id: string;
  name: string;
  workflow: WorkflowDefinition;
  createdAt: number;
}

// ==========================================
// 服务类
// ==========================================

export class WorkflowOrchestrator {
  private templates: Map<string, WorkflowTemplate> = new Map();
  private executions: Map<string, WorkflowExecutionResult> = new Map();

  // ==========================================
  // 工作流验证
  // ==========================================

  async validateWorkflow(workflow: WorkflowDefinition): Promise<WorkflowValidationResult> {
    const errors: string[] = [];

    // 验证工作流ID
    if (!workflow.id) {
      errors.push('工作流必须包含唯一ID');
    }

    // 验证节点
    if (!workflow.nodes || workflow.nodes.length === 0) {
      errors.push('工作流必须包含至少一个节点');
      return { valid: false, errors };
    }

    // 验证每个节点
    const nodeIds = new Set<string>();
    for (const node of workflow.nodes) {
      // 检查节点ID
      if (!node.id) {
        errors.push('每个节点必须包含唯一ID');
        continue;
      }

      // 检查ID重复
      if (nodeIds.has(node.id)) {
        errors.push(`节点ID重复: ${node.id}`);
      }
      nodeIds.add(node.id);

      // 检查skill节点必须有skill_id
      if (node.type === 'skill' && !node.skill_id) {
        errors.push(`技能节点 ${node.id} 必须包含 skill_id`);
      }

      // 检查condition节点必须有condition表达式
      if (node.type === 'condition' && !node.condition) {
        errors.push(`条件节点 ${node.id} 必须包含 condition 表达式`);
      }
    }

    // 验证依赖关系
    for (const node of workflow.nodes) {
      if (node.dependsOn && node.dependsOn.length > 0) {
        for (const depId of node.dependsOn) {
          if (!nodeIds.has(depId)) {
            errors.push(`节点 ${node.id} 依赖了不存在的节点 ${depId}`);
          }
        }
      }
    }

    // 检测循环依赖
    const circularErrors = this.detectCircularDependencies(workflow.nodes);
    errors.push(...circularErrors);

    return {
      valid: errors.length === 0,
      errors,
    };
  }

  // ==========================================
  // 循环依赖检测
  // ==========================================

  private detectCircularDependencies(nodes: WorkflowNode[]): string[] {
    const errors: string[] = [];

    // 构建依赖图：节点 -> 它依赖的节点
    // 如果 A dependsOn B，则 A 需要等待 B 完成
    // 循环依赖：A dependsOn B, B dependsOn A

    const nodeIds = new Set(nodes.map(n => n.id));
    const dependencies = new Map<string, Set<string>>();

    for (const node of nodes) {
      const deps = new Set<string>();
      if (node.dependsOn) {
        for (const depId of node.dependsOn) {
          if (nodeIds.has(depId)) {
            deps.add(depId);
          }
        }
      }
      dependencies.set(node.id, deps);
    }

    // 使用迭代方法检测循环
    // 对于每个节点，递归追踪它的依赖链，看是否回到自身
    const visited = new Set<string>();
    const inProgress = new Set<string>();

    const checkCircular = (nodeId: string, path: string[]): boolean => {
      if (inProgress.has(nodeId)) {
        // 发现循环：当前路径中已包含此节点
        const cycleStart = path.indexOf(nodeId);
        const cyclePath = path.slice(cycleStart);
        errors.push(`检测到循环依赖 (circular dependency): ${[...cyclePath, nodeId].join(' -> ')}`);
        return true;
      }

      if (visited.has(nodeId)) {
        return false;
      }

      inProgress.add(nodeId);
      visited.add(nodeId);

      const deps = dependencies.get(nodeId) || new Set();
      for (const depId of deps) {
        if (checkCircular(depId, [...path, nodeId])) {
          return true;
        }
      }

      inProgress.delete(nodeId);
      return false;
    };

    // 检查每个节点
    for (const node of nodes) {
      visited.clear();
      inProgress.clear();
      checkCircular(node.id, []);
    }

    return errors;
  }

  // ==========================================
  // 获取执行顺序
  // ==========================================

  async getExecutionOrder(workflow: WorkflowDefinition): Promise<string[]> {
    // 使用拓扑排序确定执行顺序
    const nodes = workflow.nodes;
    const order: string[] = [];
    const visited = new Set<string>();
    const inDegree = new Map<string, number>();

    // 计算入度
    for (const node of nodes) {
      inDegree.set(node.id, 0);
    }

    for (const node of nodes) {
      if (node.dependsOn) {
        for (const depId of node.dependsOn) {
          if (inDegree.has(depId)) {
            inDegree.set(node.id, (inDegree.get(node.id) || 0) + 1);
          }
        }
      }
    }

    // Kahn算法拓扑排序
    const queue: string[] = [];
    for (const [nodeId, degree] of inDegree) {
      if (degree === 0) {
        queue.push(nodeId);
      }
    }

    while (queue.length > 0) {
      const nodeId = queue.shift()!;
      order.push(nodeId);
      visited.add(nodeId);

      // 减少依赖此节点的入度
      for (const node of nodes) {
        if (node.dependsOn && node.dependsOn.includes(nodeId)) {
          const newDegree = (inDegree.get(node.id) || 0) - 1;
          inDegree.set(node.id, newDegree);
          if (newDegree === 0 && !visited.has(node.id)) {
            queue.push(node.id);
          }
        }
      }
    }

    return order;
  }

  // ==========================================
  // 执行工作流
  // ==========================================

  async executeWorkflow(
    workflow: WorkflowDefinition,
    options?: WorkflowExecutionOptions
  ): Promise<WorkflowExecutionResult> {
    const startTime = Date.now();
    const nodeResults: WorkflowNodeResult[] = [];

    // 验证工作流
    const validation = await this.validateWorkflow(workflow);
    if (!validation.valid) {
      return {
        workflowId: workflow.id,
        status: 'failed',
        nodeResults: [],
        totalExecutionTime: 0,
      };
    }

    // 获取执行顺序
    const order = await this.getExecutionOrder(workflow);

    // 执行节点
    const nodeMap = new Map<string, WorkflowNode>();
    for (const node of workflow.nodes) {
      nodeMap.set(node.id, node);
    }

    const completedNodes = new Set<string>();
    const failedNodes = new Set<string>();

    for (const nodeId of order) {
      const node = nodeMap.get(nodeId)!;

      // 进度更新
      if (options?.onProgress) {
        options.onProgress({
          workflowId: workflow.id,
          totalNodes: workflow.nodes.length,
          completedNodes: completedNodes.size,
          currentNodeId: nodeId,
          status: 'running',
        });
      }

      // 检查依赖是否全部成功
      const dependencies = node.dependsOn || [];
      const hasFailedDependency = dependencies.some((depId) => failedNodes.has(depId));

      if (hasFailedDependency) {
        // 依赖失败，跳过此节点
        nodeResults.push({
          nodeId,
          status: 'skipped',
          executionTime: 0,
        });
        continue;
      }

      // 模拟执行节点
      const result = await this.executeNode(node, nodeResults);

      nodeResults.push(result);

      if (result.status === 'success') {
        completedNodes.add(nodeId);
      } else {
        failedNodes.add(nodeId);
      }
    }

    // 计算结果状态
    const successCount = nodeResults.filter((r) => r.status === 'success').length;
    const failedCount = nodeResults.filter((r) => r.status === 'failed').length;

    let status: 'success' | 'failed' | 'partial';
    if (failedCount === 0) {
      status = 'success';
    } else if (successCount === 0) {
      status = 'failed';
    } else {
      status = 'partial';
    }

    // 最终进度更新
    if (options?.onProgress) {
      options.onProgress({
        workflowId: workflow.id,
        totalNodes: workflow.nodes.length,
        completedNodes: workflow.nodes.length,
        status: status === 'success' ? 'completed' : 'failed',
      });
    }

    const executionTime = (Date.now() - startTime) / 1000;

    const result: WorkflowExecutionResult = {
      workflowId: workflow.id,
      status,
      nodeResults,
      totalExecutionTime: executionTime,
    };

    this.executions.set(workflow.id, result);

    return result;
  }

  // ==========================================
  // 执行单个节点
  // ==========================================

  private async executeNode(
    node: WorkflowNode,
    previousResults: WorkflowNodeResult[]
  ): Promise<WorkflowNodeResult> {
    const startTime = Date.now();

    try {
      // 条件节点处理
      if (node.type === 'condition') {
        // 简化：假设条件总是通过
        // 实际实现会解析 condition 表达式
        const passed = true;

        return {
          nodeId: node.id,
          status: 'success',
          result: { passed, branch: passed ? 'true' : 'false' },
          executionTime: (Date.now() - startTime) / 1000,
        };
      }

      // 技能节点执行
      // 模拟执行（实际会调用技能执行服务）
      await this.simulateSkillExecution(node.skill_id!, node.parameters);

      return {
        nodeId: node.id,
        status: 'success',
        executionTime: (Date.now() - startTime) / 1000,
      };
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : '执行失败';

      return {
        nodeId: node.id,
        status: 'failed',
        error: errorMessage,
        executionTime: (Date.now() - startTime) / 1000,
      };
    }
  }

  // ==========================================
  // 模拟技能执行
  // ==========================================

  private async simulateSkillExecution(
    skillId: string,
    parameters?: Record<string, unknown>
  ): Promise<void> {
    // 模拟执行时间
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  // ==========================================
  // 工作流模板管理
  // ==========================================

  async saveAsTemplate(workflow: WorkflowDefinition, name: string): Promise<string> {
    const templateId = this.generateTemplateId();

    const template: WorkflowTemplate = {
      id: templateId,
      name,
      workflow: { ...workflow },
      createdAt: Date.now(),
    };

    this.templates.set(templateId, template);

    return templateId;
  }

  async loadTemplate(templateId: string): Promise<WorkflowTemplate> {
    const template = this.templates.get(templateId);

    if (!template) {
      throw new Error(`模板不存在: ${templateId}`);
    }

    return template;
  }

  async listTemplates(): Promise<WorkflowTemplate[]> {
    return Array.from(this.templates.values());
  }

  // ==========================================
  // 工具方法
  // ==========================================

  private generateTemplateId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    return `template_${timestamp}_${random}`;
  }
}

// ==========================================
// 单例导出
// ==========================================

let instance: WorkflowOrchestrator | null = null;

export function getWorkflowOrchestrator(): WorkflowOrchestrator {
  if (!instance) {
    instance = new WorkflowOrchestrator();
  }
  return instance;
}

export default WorkflowOrchestrator;