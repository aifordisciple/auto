/**
 * 技能工厂面板 - 整合到技能中心的锻造功能
 *
 * Gemini 风格对话式创建：
 * - 进入时直接创建新会话，无弹窗
 * - 双栏布局：左栏对话，右栏技能编辑
 * - 底部工具栏支持 Tool 选择器（对话/代码导入/技能包导入）
 * - 支持从"我的"标签页编辑现有技能
 * - 离开标签页时自动保存草稿
 */

'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useForgeStore, ExecutorType } from '@/store/useForgeStore';
import { SkillDraftEditor } from '@/app/skill-forge/components/SkillDraftEditor';
import { skillForgeApi, forgeSessionApi, fetchAPI, BASE_URL, getToken } from '@/lib/api';
import { toast } from 'sonner';
import { PendingDraftsList } from './PendingDraftsList';

interface ForgePanelProps {
  // 从聊天转化的草稿
  transformDraft?: {
    skill_id?: string;
    name?: string;
    description?: string;
    script_code?: string;
    parameters_schema?: Record<string, any>;
    expert_knowledge?: string;
    dependencies?: string[];
    executor_type?: string;  // 添加执行器类型字段
    nextflow_code?: string;  // 添加 Nextflow 代码字段
  } | null;
  // 待编辑的技能 ID（从 SkillCenter 传递）
  editSkillId?: string | null;
  // 编辑完成后回调
  onEditComplete?: () => void;
  // 转化草稿处理完成回调
  onTransformComplete?: () => void;
}

export function ForgePanel({ transformDraft, editSkillId, onEditComplete, onTransformComplete }: ForgePanelProps) {
  const {
    sessionId,
    createSession,
    loadSession,
    updateSkillDraft,
    setSkillId,
    setSkillDraft,
    setExecutorType,
    initSkillFiles,
    skillDraft
  } = useForgeStore();

  // 标记是否已完成初始化，防止重复执行
  const initRef = useRef(false);
  // 追踪上一次保存的草稿内容，判断是否有变化
  const lastSavedDraftRef = useRef<string>('');
  // 追踪上一次的 editSkillId，判断是否变化
  const lastEditSkillIdRef = useRef<string | null | undefined>(null);
  // 追踪上一次的 transformDraft，判断是否变化
  const lastTransformDraftRef = useRef<string | null>(null);

  // ==========================================
  // 离开标签页时自动保存草稿
  // ==========================================
  const saveDraftIfNeeded = useCallback(async () => {
    if (!sessionId) return;

    // 检查草稿是否有实际内容且发生变化
    const hasContent = skillDraft.name || skillDraft.description || skillDraft.script_code || skillDraft.nextflow_code;
    const currentDraftStr = JSON.stringify(skillDraft);

    if (hasContent && currentDraftStr !== lastSavedDraftRef.current) {
      try {
        await forgeSessionApi.updateDraft(sessionId, {
          name: skillDraft.name,
          description: skillDraft.description,
          executor_type: skillDraft.executor_type,
          script_code: skillDraft.script_code,
          nextflow_code: skillDraft.nextflow_code,
          parameters_schema: skillDraft.parameters_schema,
          expert_knowledge: skillDraft.expert_knowledge,
          dependencies: skillDraft.dependencies
        });
        lastSavedDraftRef.current = currentDraftStr;
      } catch (error) {
        console.error('[ForgePanel] 自动保存草稿失败:', error);
      }
    }
  }, [sessionId, skillDraft]);

  // 组件卸载时保存
  useEffect(() => {
    return () => {
      // 组件卸载时触发保存（使用同步方式确保保存完成）
      if (sessionId && skillDraft) {
        const hasContent = skillDraft.name || skillDraft.description || skillDraft.script_code || skillDraft.nextflow_code;
        if (hasContent) {
          const payload = JSON.stringify({
            name: skillDraft.name,
            description: skillDraft.description,
            executor_type: skillDraft.executor_type,
            script_code: skillDraft.script_code,
            nextflow_code: skillDraft.nextflow_code,
            parameters_schema: skillDraft.parameters_schema,
            expert_knowledge: skillDraft.expert_knowledge,
            dependencies: skillDraft.dependencies
          });

          // 使用 navigator.sendBeacon 确保请求在页面卸载时也能发送
          // sendBeacon 是专门为此场景设计的，比 fetch + keepalive 更可靠
          const url = `${BASE_URL}/api/skills/forge/session/${sessionId}/draft`;
          const blob = new Blob([payload], { type: 'application/json' });

          // 注意：sendBeacon 不支持自定义 Headers，后端需要支持其他认证方式
          // 这里先尝试 fetch keepalive，失败则静默处理（因为这是预期的）
          fetch(url, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${getToken()}`
            },
            body: payload,
            keepalive: true
          }).catch(() => {
            // 静默处理：页面卸载时 fetch 失败是预期行为，无需输出错误
            // 实际的草稿会在 visibilitychange 事件中保存
          });
        }
      }
    };
  }, [sessionId, skillDraft]);

  // 监听页面可见性变化（切换标签页时触发）
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        saveDraftIfNeeded();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [saveDraftIfNeeded]);

  // ==========================================
  // 初始化 - 进入工厂时检查是否有草稿会话或待编辑的技能
  // ==========================================
  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    const init = async () => {
      // 记录当前的 editSkillId
      lastEditSkillIdRef.current = editSkillId;

      // ==========================================
      // 场景1：编辑现有技能（优先级最高）
      // ==========================================
      if (editSkillId) {
        try {
          // 获取技能详情
          const skill = await skillForgeApi.getSkill(editSkillId);

          // 创建新会话
          const newSessionId = await createSession();

          // 填充技能草稿
          const skillDraftData = {
            name: skill.name || '',
            description: skill.description || '',
            executor_type: skill.executor_type || 'Python_env',
            script_code: skill.script_code || '',
            nextflow_code: skill.nextflow_code || '',
            parameters_schema: skill.parameters_schema || {},
            expert_knowledge: skill.expert_knowledge || '',
            dependencies: skill.dependencies || [],
            category: skill.category,
            subcategory: skill.subcategory,
            tags: skill.tags || []
          };

          // 关键修复：传入完整的草稿数据到 setExecutorType
          // 这样 initVirtualFileSystem 就能使用正确的 script_code/nextflow_code 初始化文件系统
          setExecutorType(skill.executor_type || 'Python_env', skillDraftData);

          // 设置 skillId 表示这是编辑现有技能
          setSkillId(editSkillId);

          // 持久化到后端会话
          if (newSessionId) {
            try {
              await forgeSessionApi.updateDraft(newSessionId, skillDraftData);
            } catch (persistErr) {
              console.error('[ForgePanel] 持久化编辑草稿失败:', persistErr);
            }
          }

          // 通知父组件编辑已完成
          onEditComplete?.();

          return; // 编辑模式结束，不再执行后续逻辑
        } catch (error) {
          console.error('[ForgePanel] 加载技能详情失败:', error);
          toast.error?.('加载技能详情失败');
          // 加载失败，继续执行正常的初始化流程
        }
      }

      // ==========================================
      // 场景2：从聊天转化的草稿
      // ==========================================
      if (transformDraft) {
        try {
          // 创建新会话
          const newSessionId = await createSession();

          // 确定执行器类型（显式类型断言以满足 ExecutorType 类型要求）
          const executorType: ExecutorType = (transformDraft.executor_type as ExecutorType) || 'Python_env';

          // 构建完整草稿数据
          const skillDraftData = {
            name: transformDraft.name || '',
            description: transformDraft.description || '',
            executor_type: executorType,
            script_code: transformDraft.script_code || '',
            nextflow_code: transformDraft.nextflow_code || '',
            parameters_schema: transformDraft.parameters_schema || {},
            expert_knowledge: transformDraft.expert_knowledge || '',
            dependencies: transformDraft.dependencies || []
          };

          // 关键修复：调用 setExecutorType 初始化文件系统
          setExecutorType(executorType, skillDraftData);

          // 设置 skillId（如果有）
          if (transformDraft.skill_id) {
            setSkillId(transformDraft.skill_id);
          }

          // 持久化到后端会话
          if (newSessionId) {
            try {
              await forgeSessionApi.updateDraft(newSessionId, skillDraftData);
            } catch (persistErr) {
              console.error('[ForgePanel] 持久化转化草稿失败:', persistErr);
            }
          }

          // 通知父组件转化已完成
          onTransformComplete?.();

          return; // 转化模式结束，不再执行后续逻辑
        } catch (error) {
          console.error('[ForgePanel] 处理转化草稿失败:', error);
          // 失败时继续执行正常的初始化流程
        }
      }

      // ==========================================
      // 场景3：检查是否有草稿会话
      // ==========================================
      try {
        const data = await fetchAPI('/api/skills/forge/sessions');
        const sessions = data.sessions || [];

        // 查找最近的草稿会话（status 为 drafting 且有 skill_draft 内容）
        const draftSession = sessions.find((s: any) =>
          s.status === 'drafting' && s.has_draft
        );

        if (draftSession) {
          await loadSession(draftSession.id);
        } else {
          await createSession();
          initSkillFiles();
        }
      } catch (error) {
        console.error('[ForgePanel] 初始化失败:', error);
        await createSession();
        initSkillFiles();
      }
    };

    init();
  }, [createSession, loadSession, initSkillFiles, editSkillId, onEditComplete, transformDraft, onTransformComplete, setExecutorType, setSkillId]);

  // ==========================================
  // 处理 editSkillId 变化（用户在工厂 Tab 时点击编辑另一个技能）
  // ==========================================
  useEffect(() => {
    // 检查 editSkillId 是否变化（且不是初始化时的设置）
    if (initRef.current && editSkillId !== lastEditSkillIdRef.current && editSkillId) {
      const loadSkillForEdit = async () => {
        try {
          // 获取技能详情
          const skill = await skillForgeApi.getSkill(editSkillId);

          // 创建新会话
          const newSessionId = await createSession();

          // 填充技能草稿
          const skillDraftData = {
            name: skill.name || '',
            description: skill.description || '',
            executor_type: skill.executor_type || 'Python_env',
            script_code: skill.script_code || '',
            nextflow_code: skill.nextflow_code || '',
            parameters_schema: skill.parameters_schema || {},
            expert_knowledge: skill.expert_knowledge || '',
            dependencies: skill.dependencies || [],
            category: skill.category,
            subcategory: skill.subcategory,
            tags: skill.tags || []
          };

          // 设置执行器类型和草稿数据
          setExecutorType(skill.executor_type || 'Python_env', skillDraftData);

          // 关键：设置 skillId 表示这是编辑现有技能
          setSkillId(editSkillId);

          // 更新记录
          lastEditSkillIdRef.current = editSkillId;

          // 持久化到后端
          if (newSessionId) {
            await forgeSessionApi.updateDraft(newSessionId, skillDraftData);
          }

          // 通知父组件
          onEditComplete?.();
        } catch (error) {
          console.error('[ForgePanel] 重新加载技能失败:', error);
          toast.error?.('加载技能详情失败');
        }
      };

      loadSkillForEdit();
    }
  }, [editSkillId, createSession, setExecutorType, setSkillId, onEditComplete]);

  // ==========================================
  // 处理 transformDraft 变化（用户在工厂 Tab 时再次点击"固化"）
  // ==========================================
  useEffect(() => {
    // 检查 transformDraft 是否变化（且不是初始化时的设置）
    if (initRef.current && transformDraft) {
      const currentDraftStr = JSON.stringify(transformDraft);
      if (currentDraftStr !== lastTransformDraftRef.current) {
        const loadTransformDraft = async () => {
          try {
            // 创建新会话
            const newSessionId = await createSession();

            // 确定执行器类型（显式类型断言以满足 ExecutorType 类型要求）
            const executorType: ExecutorType = (transformDraft.executor_type as ExecutorType) || 'Python_env';

            // 构建完整草稿数据
            const skillDraftData = {
              name: transformDraft.name || '',
              description: transformDraft.description || '',
              executor_type: executorType,
              script_code: transformDraft.script_code || '',
              nextflow_code: transformDraft.nextflow_code || '',
              parameters_schema: transformDraft.parameters_schema || {},
              expert_knowledge: transformDraft.expert_knowledge || '',
              dependencies: transformDraft.dependencies || []
            };

            // 设置执行器类型和草稿数据（初始化文件系统）
            setExecutorType(executorType, skillDraftData);

            // 设置 skillId（如果有）
            if (transformDraft.skill_id) {
              setSkillId(transformDraft.skill_id);
            }

            // 更新记录
            lastTransformDraftRef.current = currentDraftStr;

            // 持久化到后端
            if (newSessionId) {
              await forgeSessionApi.updateDraft(newSessionId, skillDraftData);
            }

            // 通知父组件
            onTransformComplete?.();
          } catch (error) {
            console.error('[ForgePanel] 重新加载 transformDraft 失败:', error);
          }
        };

        loadTransformDraft();
      }
    }
  }, [transformDraft, createSession, setExecutorType, setSkillId, onTransformComplete]);

  return (
    <div className="flex-1 flex flex-col min-h-0 h-full overflow-hidden">
      {/* 待发布草稿列表 */}
      <PendingDraftsList
        onSelectDraft={(draft) => {
          // 将草稿加载到编辑器
          const skillDraftData = {
            name: draft.draft_name || '',
            description: draft.draft_description || '',
            executor_type: (draft.executor_type || 'Python_env') as ExecutorType,
            script_code: draft.script_code || '',
            parameters_schema: draft.parameters_schema || {},
            expert_knowledge: draft.expert_knowledge || '',
            dependencies: draft.dependencies || []
          };
          setExecutorType(skillDraftData.executor_type, skillDraftData);
        }}
      />

      {/* 技能编辑/预览区 */}
      <div className="flex-1 min-h-0 h-full overflow-y-auto">
        <SkillDraftEditor />
      </div>
    </div>
  );
}
