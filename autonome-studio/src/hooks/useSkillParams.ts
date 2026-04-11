/**
 * useSkillParams Hook - 获取技能参数定义
 *
 * 功能：
 * 1. 根据 skill_id 获取技能的参数定义
 * 2. 返回 StrategyCard 所需的数据格式
 * 3. 支持加载状态和错误处理
 */
import { useState, useEffect, useCallback } from "react";
import { BASE_URL } from "@/lib/api";

export interface SkillParamsResponse {
  tool_id: string;
  title: string;
  description: string;
  parameters: Record<string, unknown>;
  executor_type?: string;
  expert_knowledge?: string;
}

export interface UseSkillParamsReturn {
  data: SkillParamsResponse | null;
  loading: boolean;
  error: string | null;
  fetchParams: (skillId: string) => Promise<void>;
}

export function useSkillParams(): UseSkillParamsReturn {
  const [data, setData] = useState<SkillParamsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchParams = useCallback(async (skillId: string) => {
    if (!skillId || skillId === "live_coding") {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem("autonome_access_token");
      const response = await fetch(`${BASE_URL}/api/skills/params/${skillId}`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (!response.ok) {
        throw new Error(`获取技能参数失败: ${response.status}`);
      }

      const result = await response.json();
      if (result.status === "success" && result.data) {
        setData(result.data);
      } else {
        throw new Error(result.detail || "技能不存在");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "获取技能参数失败";
      setError(message);
      console.error("[useSkillParams] Error:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    data,
    loading,
    error,
    fetchParams,
  };
}

export default useSkillParams;
