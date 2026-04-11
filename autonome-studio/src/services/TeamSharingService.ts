/**
 * 团队分享服务
 *
 * P3 团队协作：
 * - 分享参数模板
 * - 分享工作流
 * - 团队技能库
 * - 执行记录分享
 */

// ==========================================
// 类型定义
// ==========================================

export type ResourceType = 'template' | 'workflow' | 'skill';

export interface ShareRequest {
  resourceType: ResourceType;
  resourceId: string;
  resourceName: string;
  ownerId: number;
  teamId?: number;
  isPublic: boolean;
  description?: string;
}

export interface SharedResource {
  id: string;
  resourceType: ResourceType;
  resourceId: string;
  resourceName: string;
  ownerId: number;
  teamId?: number;
  isPublic: boolean;
  description?: string;
  shareLink?: string;
  createdAt: number;
  viewCount: number;
  copyCount: number;
}

export interface TeamLibrary {
  teamId: number;
  templates: SharedResource[];
  workflows: SharedResource[];
  skills: SharedResource[];
  updatedAt: number;
}

export interface ShareStats {
  viewCount: number;
  copyCount: number;
  lastViewedAt?: number;
  lastCopiedAt?: number;
}

// ==========================================
// 服务类
// ==========================================

export class TeamSharingService {
  private shares: Map<string, SharedResource> = new Map();
  private teamLibraries: Map<number, TeamLibrary> = new Map();
  private userShares: Map<number, string[]> = new Map(); // userId -> shareIds

  // ==========================================
  // 创建分享
  // ==========================================

  async createShare(request: ShareRequest): Promise<string> {
    const shareId = this.generateId();

    // 生成分享链接（仅公开分享）
    let shareLink: string | undefined;
    if (request.isPublic) {
      shareLink = `share/${shareId}`;
    }

    const resource: SharedResource = {
      id: shareId,
      resourceType: request.resourceType,
      resourceId: request.resourceId,
      resourceName: request.resourceName,
      ownerId: request.ownerId,
      teamId: request.teamId,
      isPublic: request.isPublic,
      description: request.description,
      shareLink,
      createdAt: Date.now(),
      viewCount: 0,
      copyCount: 0,
    };

    this.shares.set(shareId, resource);

    // 记录用户分享
    if (!this.userShares.has(request.ownerId)) {
      this.userShares.set(request.ownerId, []);
    }
    this.userShares.get(request.ownerId)!.push(shareId);

    return shareId;
  }

  // ==========================================
  // 获取分享
  // ==========================================

  async getShare(shareId: string): Promise<SharedResource> {
    const share = this.shares.get(shareId);

    if (!share) {
      throw new Error(`分享不存在: ${shareId}`);
    }

    return share;
  }

  async getShareByLink(shareLink: string): Promise<SharedResource> {
    const shareId = shareLink.replace('share/', '');
    return this.getShare(shareId);
  }

  // ==========================================
  // 团队库管理
  // ==========================================

  async addToTeamLibrary(teamId: number, shareId: string): Promise<void> {
    const share = await this.getShare(shareId);

    if (!this.teamLibraries.has(teamId)) {
      this.teamLibraries.set(teamId, {
        teamId,
        templates: [],
        workflows: [],
        skills: [],
        updatedAt: Date.now(),
      });
    }

    const library = this.teamLibraries.get(teamId)!;

    // 根据类型添加到对应数组
    switch (share.resourceType) {
      case 'template':
        library.templates.push(share);
        break;
      case 'workflow':
        library.workflows.push(share);
        break;
      case 'skill':
        library.skills.push(share);
        break;
    }

    library.updatedAt = Date.now();
  }

  async removeFromTeamLibrary(teamId: number, shareId: string): Promise<void> {
    const library = this.teamLibraries.get(teamId);

    if (!library) {
      return;
    }

    // 从所有数组中移除
    library.templates = library.templates.filter((s) => s.id !== shareId);
    library.workflows = library.workflows.filter((s) => s.id !== shareId);
    library.skills = library.skills.filter((s) => s.id !== shareId);

    library.updatedAt = Date.now();
  }

  async getTeamLibrary(teamId: number): Promise<TeamLibrary> {
    if (!this.teamLibraries.has(teamId)) {
      return {
        teamId,
        templates: [],
        workflows: [],
        skills: [],
        updatedAt: Date.now(),
      };
    }

    return this.teamLibraries.get(teamId)!;
  }

  // ==========================================
  // 权限检查
  // ==========================================

  async checkAccess(
    shareId: string,
    userId: number,
    userTeamId: number
  ): Promise<boolean> {
    const share = await this.getShare(shareId);

    // 公开分享 - 任何人可访问
    if (share.isPublic) {
      return true;
    }

    // 创建者始终可访问
    if (share.ownerId === userId) {
      return true;
    }

    // 同团队成员可访问
    if (share.teamId && share.teamId === userTeamId) {
      return true;
    }

    return false;
  }

  // ==========================================
  // 复制到用户库
  // ==========================================

  async copyToUserLibrary(shareId: string, userId: number): Promise<string> {
    const share = await this.getShare(shareId);

    // 记录复制
    share.copyCount++;

    // 生成新的资源ID（模拟复制）
    const newResourceId = `${share.resourceId}_copy_${Date.now()}`;

    return newResourceId;
  }

  // ==========================================
  // 统计
  // ==========================================

  async recordView(shareId: string): Promise<void> {
    const share = this.shares.get(shareId);

    if (share) {
      share.viewCount++;
    }
  }

  async getShareStats(shareId: string): Promise<ShareStats> {
    const share = await this.getShare(shareId);

    return {
      viewCount: share.viewCount,
      copyCount: share.copyCount,
    };
  }

  // ==========================================
  // 列出分享
  // ==========================================

  async listSharesByOwner(ownerId: number): Promise<SharedResource[]> {
    const shareIds = this.userShares.get(ownerId) || [];
    const shares: SharedResource[] = [];

    for (const id of shareIds) {
      const share = this.shares.get(id);
      if (share) {
        shares.push(share);
      }
    }

    return shares;
  }

  async listSharesByTeam(teamId: number): Promise<SharedResource[]> {
    const shares: SharedResource[] = [];

    for (const share of this.shares.values()) {
      if (share.teamId === teamId) {
        shares.push(share);
      }
    }

    return shares;
  }

  async listPublicShares(): Promise<SharedResource[]> {
    const shares: SharedResource[] = [];

    for (const share of this.shares.values()) {
      if (share.isPublic) {
        shares.push(share);
      }
    }

    return shares;
  }

  // ==========================================
  // 工具方法
  // ==========================================

  private generateId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    return `share_${timestamp}_${random}`;
  }
}

// ==========================================
// 单例导出
// ==========================================

let instance: TeamSharingService | null = null;

export function getTeamSharingService(): TeamSharingService {
  if (!instance) {
    instance = new TeamSharingService();
  }
  return instance;
}

export default TeamSharingService;