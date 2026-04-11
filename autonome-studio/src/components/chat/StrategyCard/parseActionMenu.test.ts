/**
 * parseActionMenu 测试
 *
 * 测试 parseActionMenu 函数对 actions (PLAN 格式) 和 options (旧格式) 的支持
 */
import { describe, it, expect } from 'vitest';
import { parseActionMenu } from './parseUtils';

describe('parseActionMenu', () => {
  // ==========================================
  // actions 格式测试 (PLAN 格式)
  // ==========================================

  describe('actions 格式 (PLAN 格式)', () => {
    it('应正确解析 actions 格式的基本结构', () => {
      // 使用紧邻格式: ```json_action_menu{...} 让 preprocessCodeBlocks 处理
      const content = '```json_action_menu{"title":"🎯 推荐分析方案","message":"系统检测到您的数据非常适合进行...","actions":[{"id":"skill_cd22f007","action_type":"configure_skill","label":"配置并执行该分析","style":"primary"}]}```';

      const result = parseActionMenu(content);

      expect(result).not.toBeNull();
      expect(result?.title).toBe('🎯 推荐分析方案');
      expect(result?.message).toBe('系统检测到您的数据非常适合进行...');
      expect(result?.options).toHaveLength(1);
      expect(result?.options[0].skill_id).toBe('skill_cd22f007');
      expect(result?.options[0].name).toBe('配置并执行该分析');
      expect(result?.options[0].match_score).toBe(0.5); // 默认值
    });

    it('应正确解析多个 actions', () => {
      const content = '```json_action_menu{"title":"选择操作","actions":[{"id":"skill_001","label":"操作一"},{"id":"skill_002","label":"操作二"},{"id":"skill_003","label":"操作三"}]}```';

      const result = parseActionMenu(content);

      expect(result).not.toBeNull();
      expect(result?.options).toHaveLength(3);
      expect(result?.options[0].skill_id).toBe('skill_001');
      expect(result?.options[1].skill_id).toBe('skill_002');
      expect(result?.options[2].skill_id).toBe('skill_003');
    });

    it('当 actions 为空数组时应返回 null', () => {
      const content = '```json_action_menu{"title":"测试","actions":[]}```';

      const result = parseActionMenu(content);
      expect(result).toBeNull();
    });

    it('当 actions 缺失且 options 也缺失时应返回 null', () => {
      const content = '```json_action_menu{"title":"测试"}```';

      const result = parseActionMenu(content);
      expect(result).toBeNull();
    });
  });

  // ==========================================
  // options 格式测试 (旧格式)
  // ==========================================

  describe('options 格式 (旧格式)', () => {
    it('应正确解析 options 格式的基本结构', () => {
      const content = '```json_action_menu{"title":"请选择操作","message":"选择一个选项","options":[{"skill_id":"skill_abc123","name":"质量控制分析","match_score":0.95,"match_reason":"数据格式符合 QC 要求"}]}```';

      const result = parseActionMenu(content);

      expect(result).not.toBeNull();
      expect(result?.title).toBe('请选择操作');
      expect(result?.options).toHaveLength(1);
      expect(result?.options[0].skill_id).toBe('skill_abc123');
      expect(result?.options[0].name).toBe('质量控制分析');
      expect(result?.options[0].match_score).toBe(0.95);
      expect(result?.options[0].match_reason).toBe('数据格式符合 QC 要求');
    });

    it('当 options 为空数组时应返回 null', () => {
      const content = '```json_action_menu{"title":"测试","options":[]}```';

      const result = parseActionMenu(content);
      expect(result).toBeNull();
    });

    it('应正确处理缺少可选字段的 options 项', () => {
      const content = '```json_action_menu{"title":"测试","options":[{"skill_id":"skill_minimal"}]}```';

      const result = parseActionMenu(content);

      expect(result).not.toBeNull();
      expect(result?.options[0].skill_id).toBe('skill_minimal');
      expect(result?.options[0].name).toBe('skill_minimal'); // 使用 skill_id 作为默认值
      expect(result?.options[0].match_score).toBe(0.5); // 默认值
    });
  });

  // ==========================================
  // 边缘情况测试
  // ==========================================

  describe('边缘情况', () => {
    it('当 content 为空时应返回 null', () => {
      expect(parseActionMenu('')).toBeNull();
    });

    it('当 content 为 undefined 时应返回 null', () => {
      // @ts-ignore - 测试边缘情况
      expect(parseActionMenu(undefined)).toBeNull();
    });

    it('当没有 json_action_menu 代码块时应返回 null', () => {
      const content = '这是一个普通文本，不包含操作菜单';
      expect(parseActionMenu(content)).toBeNull();
    });

    it('当 title 缺失时应使用默认标题', () => {
      const content = '```json_action_menu{"actions":[{"id":"skill_test","label":"测试操作"}]}```';

      const result = parseActionMenu(content);
      expect(result?.title).toBe('请选择操作');
    });

    it('当 message 缺失时应该 undefined', () => {
      const content = '```json_action_menu{"title":"测试","actions":[{"id":"skill_test","label":"测试操作"}]}```';

      const result = parseActionMenu(content);
      expect(result?.message).toBeUndefined();
    });
  });

  // ==========================================
  // 格式优先级测试：actions > options
  // ==========================================

  describe('格式优先级', () => {
    it('当同时存在 actions 和 options 时应优先使用 actions', () => {
      const content = '```json_action_menu{"title":"优先级测试","actions":[{"id":"action_skill","label":"来自 actions"}],"options":[{"skill_id":"option_skill","name":"来自 options"}]}```';

      const result = parseActionMenu(content);

      expect(result).not.toBeNull();
      expect(result?.options).toHaveLength(1);
      expect(result?.options[0].skill_id).toBe('action_skill');
      expect(result?.options[0].name).toBe('来自 actions');
    });
  });
});
