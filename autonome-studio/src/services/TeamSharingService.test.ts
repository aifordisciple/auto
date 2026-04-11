/**
 * 团队分享服务测试
 *
 * User Journey:
 * As a team lead, I want to share my parameter templates and workflows,
 * so that my team members can reuse proven configurations.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  TeamSharingService,
  SharedResource,
  ShareRequest,
  TeamLibrary,
} from './TeamSharingService';

// ==========================================
// 测试数据
// ==========================================

const mockTemplateShare: ShareRequest = {
  resourceType: 'template',
  resourceId: 'template_001',
  resourceName: 'RNA-seq标准参数',
  ownerId: 1,
  teamId: 100,
  isPublic: false,
  description: '适用于常规RNA-seq分析的参数配置',
};

const mockWorkflowShare: ShareRequest = {
  resourceType: 'workflow',
  resourceId: 'workflow_001',
  resourceName: '质控-比对-定量流程',
  ownerId: 1,
  teamId: 100,
  isPublic: true,
  description: '标准RNA-seq分析流程',
};

const mockSkillShare: ShareRequest = {
  resourceType: 'skill',
  resourceId: 'skill_custom_001',
  resourceName: '自定义质控脚本',
  ownerId: 1,
  teamId: 100,
  isPublic: false,
  description: '团队自定义的质控脚本',
};

// ==========================================
// Mock fetch
// ==========================================

const mockFetch = vi.fn();
(global as any).fetch = mockFetch;

// ==========================================
// Test Suite: 团队分享服务
// ==========================================

describe('TeamSharingService', () => {
  let service: TeamSharingService;

  beforeEach(() => {
    vi.clearAllMocks();
    service = new TeamSharingService();
    mockFetch.mockReset();
  });

  // ==========================================
  // Test Case 1: 创建分享
  // ==========================================

  describe('Create Share', () => {
    it('should create a share for parameter template', async () => {
      const shareId = await service.createShare(mockTemplateShare);

      expect(shareId).toBeDefined();
      expect(shareId).toMatch(/^share_/);
    });

    it('should create a share for workflow', async () => {
      const shareId = await service.createShare(mockWorkflowShare);

      expect(shareId).toBeDefined();
    });

    it('should create a share for custom skill', async () => {
      const shareId = await service.createShare(mockSkillShare);

      expect(shareId).toBeDefined();
    });

    it('should generate share link for public share', async () => {
      const shareId = await service.createShare(mockWorkflowShare);
      const share = await service.getShare(shareId);

      expect(share.shareLink).toBeDefined();
      expect(share.shareLink).toContain('share/');
    });

    it('should not generate share link for private share', async () => {
      const shareId = await service.createShare(mockTemplateShare);
      const share = await service.getShare(shareId);

      expect(share.shareLink).toBeUndefined();
    });
  });

  // ==========================================
  // Test Case 2: 获取分享
  // ==========================================

  describe('Get Share', () => {
    it('should get share by ID', async () => {
      const shareId = await service.createShare(mockTemplateShare);
      const share = await service.getShare(shareId);

      expect(share).toBeDefined();
      expect(share.id).toBe(shareId);
      expect(share.resourceType).toBe('template');
      expect(share.resourceName).toBe('RNA-seq标准参数');
    });

    it('should throw error for non-existent share', async () => {
      await expect(service.getShare('share_nonexistent')).rejects.toThrow();
    });

    it('should get share by share link', async () => {
      const shareId = await service.createShare(mockWorkflowShare);
      const share = await service.getShare(shareId);
      const linkShare = await service.getShareByLink(share.shareLink!);

      expect(linkShare).toBeDefined();
      expect(linkShare.id).toBe(shareId);
    });
  });

  // ==========================================
  // Test Case 3: 团队库管理
  // ==========================================

  describe('Team Library', () => {
    it('should add resource to team library', async () => {
      const shareId = await service.createShare(mockTemplateShare);
      await service.addToTeamLibrary(100, shareId);

      const library = await service.getTeamLibrary(100);

      expect(library.templates.length).toBe(1);
      expect(library.templates[0].resourceName).toBe('RNA-seq标准参数');
    });

    it('should list all resources in team library', async () => {
      const shareId1 = await service.createShare(mockTemplateShare);
      const shareId2 = await service.createShare(mockWorkflowShare);

      await service.addToTeamLibrary(100, shareId1);
      await service.addToTeamLibrary(100, shareId2);

      const library = await service.getTeamLibrary(100);

      expect(library.templates.length).toBe(1);
      expect(library.workflows.length).toBe(1);
    });

    it('should remove resource from team library', async () => {
      const shareId = await service.createShare(mockTemplateShare);
      await service.addToTeamLibrary(100, shareId);

      await service.removeFromTeamLibrary(100, shareId);
      const library = await service.getTeamLibrary(100);

      expect(library.templates.length).toBe(0);
    });
  });

  // ==========================================
  // Test Case 4: 权限管理
  // ==========================================

  describe('Permission Management', () => {
    it('should check if user can access share', async () => {
      const shareId = await service.createShare(mockTemplateShare);

      // 团队成员可以访问
      const canAccess = await service.checkAccess(shareId, 2, 100);
      expect(canAccess).toBe(true);
    });

    it('should allow access to public share', async () => {
      const shareId = await service.createShare(mockWorkflowShare);

      // 任何人都可以访问公开分享
      const canAccess = await service.checkAccess(shareId, 999, 999);
      expect(canAccess).toBe(true);
    });

    it('should deny access to private share from other team', async () => {
      const shareId = await service.createShare(mockTemplateShare);

      // 其他团队成员不能访问
      const canAccess = await service.checkAccess(shareId, 999, 999);
      expect(canAccess).toBe(false);
    });

    it('should allow owner to access their share', async () => {
      const shareId = await service.createShare(mockTemplateShare);

      // 创建者始终可以访问
      const canAccess = await service.checkAccess(shareId, 1, 999);
      expect(canAccess).toBe(true);
    });
  });

  // ==========================================
  // Test Case 5: 复制分享内容
  // ==========================================

  describe('Copy Shared Content', () => {
    it('should copy template to user library', async () => {
      const shareId = await service.createShare(mockTemplateShare);

      const copyId = await service.copyToUserLibrary(shareId, 2);

      expect(copyId).toBeDefined();
      expect(copyId).not.toBe(shareId);
    });

    it('should copy workflow to user library', async () => {
      const shareId = await service.createShare(mockWorkflowShare);

      const copyId = await service.copyToUserLibrary(shareId, 2);

      expect(copyId).toBeDefined();
    });
  });

  // ==========================================
  // Test Case 6: 分享统计
  // ==========================================

  describe('Share Statistics', () => {
    it('should track share view count', async () => {
      const shareId = await service.createShare(mockTemplateShare);

      await service.recordView(shareId);
      await service.recordView(shareId);
      await service.recordView(shareId);

      const stats = await service.getShareStats(shareId);

      expect(stats.viewCount).toBe(3);
    });

    it('should track share copy count', async () => {
      const shareId = await service.createShare(mockTemplateShare);

      await service.copyToUserLibrary(shareId, 2);
      await service.copyToUserLibrary(shareId, 3);

      const stats = await service.getShareStats(shareId);

      expect(stats.copyCount).toBe(2);
    });
  });

  // ==========================================
  // Test Case 7: 列出分享
  // ==========================================

  describe('List Shares', () => {
    it('should list shares by owner', async () => {
      await service.createShare(mockTemplateShare);
      await service.createShare(mockWorkflowShare);

      const shares = await service.listSharesByOwner(1);

      expect(shares.length).toBe(2);
    });

    it('should list shares by team', async () => {
      await service.createShare(mockTemplateShare);

      const shares = await service.listSharesByTeam(100);

      expect(shares.length).toBe(1);
    });

    it('should list public shares', async () => {
      await service.createShare(mockTemplateShare); // private
      await service.createShare(mockWorkflowShare); // public

      const shares = await service.listPublicShares();

      expect(shares.length).toBe(1);
      expect(shares[0].isPublic).toBe(true);
    });
  });
});