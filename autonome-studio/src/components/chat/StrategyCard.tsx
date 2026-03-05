"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Play, Clock, CheckCircle, Loader2, XCircle } from "lucide-react";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { BASE_URL } from "@/lib/api";

export interface StrategyCardData {
  title: string;
  description: string;
  tool_id: string;
  code?: string;
  parameters?: Record<string, unknown>;
  steps?: string[];
  estimated_time?: string;
  risk_level?: "low" | "medium" | "high";
}

interface StrategyCardProps {
  data: StrategyCardData;
  onExecute?: (taskId: string) => void;
  onCancel?: () => void;
}

export function StrategyCard({ data, onExecute, onCancel }: StrategyCardProps) {
  const { currentProjectId, currentSessionId } = useWorkspaceStore();
  const [isExecuting, setIsExecuting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Generate unique key for localStorage based on card data
  const cacheKey = `strategy_status_${currentProjectId}_${data.title}_${data.description?.slice(0, 20)}`;

  // Load cached status on mount
  useEffect(() => {
    const cached = localStorage.getItem(cacheKey);
    if (cached) {
      try {
        const cachedData = JSON.parse(cached);
        if (cachedData.taskStatus === 'SUCCESS') {
          setTaskId(cachedData.taskId);
          setTaskStatus(cachedData.taskStatus);
        }
      } catch (e) {
        // Invalid cache, ignore
      }
    }
  }, [cacheKey]);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectWebSocket = (id: string) => {
    const token = localStorage.getItem('autonome_access_token');
    const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/tasks/${id}/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected for task:', id);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        if (message.type === 'status') {
          setTaskStatus(message.status);
          setProgress(message.progress);
          
          if (message.status === 'SUCCESS' || message.status === 'FAILURE') {
            setIsExecuting(false);
            if (message.status === 'SUCCESS') {
              // Save to localStorage for persistence across re-renders
              localStorage.setItem(cacheKey, JSON.stringify({
                taskId: id,
                taskStatus: message.status
              }));
              window.dispatchEvent(new CustomEvent('refresh-chat'));
            }
            ws.close();
          }
        } else if (message.type === 'error') {
          setError(message.error);
          setIsExecuting(false);
          ws.close();
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('WebSocket connection error');
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected for task:', id);
    };

    wsRef.current = ws;
  };

  const handleExecute = async () => {
    if (!data.tool_id) {
      setError("No tool selected");
      return;
    }

    setIsExecuting(true);
    setError(null);

    const safeSessionId = currentSessionId || 1;

    try {
      const token = localStorage.getItem('autonome_access_token');
      
      let payload: Record<string, unknown>;
      
      // Support both execute-python and execute-r
      if ((data.tool_id === 'execute-python' || data.tool_id === 'execute-r') && data.code) {
        payload = {
          tool_id: data.tool_id,
          parameters: {
            code: data.code,
            session_id: safeSessionId,
            project_id: currentProjectId
          },
          project_id: currentProjectId
        };
      } else {
        payload = {
          tool_id: data.tool_id,
          parameters: data.parameters || {},
          project_id: currentProjectId
        };
      }

      const response = await fetch(`${BASE_URL}/api/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json();

      if (result.status === 'submitted') {
        setTaskId(result.task_id);
        onExecute?.(result.task_id);
        
        // Connect to WebSocket for real-time updates
        connectWebSocket(result.task_id);
      } else {
        setError(result.message || 'Failed to submit task');
        setIsExecuting(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setIsExecuting(false);
    }
  };

  const getStatusIcon = () => {
    if (isExecuting) return <Loader2 className="w-4 h-4 animate-spin text-blue-400" />;
    if (taskStatus === 'SUCCESS') return <CheckCircle className="w-4 h-4 text-green-400" />;
    if (taskStatus === 'FAILURE') return <XCircle className="w-4 h-4 text-red-400" />;
    return <Clock className="w-4 h-4 text-yellow-400" />;
  };

  const getRiskColor = (risk?: string) => {
    switch (risk) {
      case 'low': return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'high': return 'bg-red-500/20 text-red-400 border-red-500/30';
      default: return 'bg-neutral-700/50 text-neutral-400 border-neutral-600';
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-neutral-900 to-neutral-800 border border-neutral-700 rounded-xl p-5 shadow-xl my-4 max-w-2xl"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-white mb-1">{data.title}</h3>
          <div className="flex items-center gap-2">
            {data.estimated_time && (
              <span className="flex items-center gap-1 text-xs text-neutral-400">
                <Clock className="w-3 h-3" />
                {data.estimated_time}
              </span>
            )}
            {data.risk_level && (
              <span className={`text-xs px-2 py-0.5 rounded-full border ${getRiskColor(data.risk_level)}`}>
                {data.risk_level.toUpperCase()} RISK
              </span>
            )}
          </div>
        </div>
        <div className="px-3 py-1.5 bg-blue-600/20 border border-blue-500/30 rounded-lg">
          <span className="text-xs font-mono text-blue-400">{data.tool_id}</span>
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-neutral-300 mb-4">{data.description}</p>

      {/* Steps Preview */}
      {data.steps && data.steps.length > 0 && (
        <div className="bg-neutral-950/50 rounded-lg p-3 mb-4">
          <p className="text-xs text-neutral-500 mb-2">执行步骤</p>
          <ul className="space-y-1">
            {data.steps.map((step, i) => (
              <li key={i} className="text-xs text-neutral-400 flex items-start gap-2">
                <span className="text-indigo-500 mt-0.5">•</span>
                {step}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Parameters Preview */}
      {data.parameters && Object.keys(data.parameters).length > 0 && (
        <div className="bg-neutral-950/50 rounded-lg p-3 mb-4">
          <p className="text-xs text-neutral-500 mb-2">Parameters</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.parameters).map(([key, value]) => (
              <span key={key} className="text-xs bg-neutral-800 px-2 py-1 rounded text-neutral-300">
                <span className="text-neutral-500">{key}:</span> {String(value)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Status */}
      {(isExecuting || taskStatus) && (
        <div className="flex items-center gap-2 text-sm mb-4">
          {getStatusIcon()}
          <span className="text-neutral-300">
            {isExecuting 
              ? progress !== null 
                ? `Executing... ${progress}%` 
                : 'Executing...' 
              : `Status: ${taskStatus}`
            }
          </span>
          {progress !== null && (
            <div className="flex-1 h-1.5 bg-neutral-700 rounded-full overflow-hidden ml-2">
              <div 
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-950/30 border border-red-500/30 rounded-lg p-3 mb-4">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        {!taskId ? (
          <>
            <button
              onClick={handleExecute}
              disabled={isExecuting}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {isExecuting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Execute
            </button>
            {onCancel && (
              <button
                onClick={onCancel}
                className="px-4 py-2 bg-neutral-700 hover:bg-neutral-600 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Cancel
              </button>
            )}
          </>
        ) : (
          <div className="text-sm text-neutral-400">
            Task ID: <code className="bg-neutral-800 px-2 py-0.5 rounded text-blue-400">{taskId.slice(0, 8)}...</code>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// Helper to parse strategy card from AI response
export function parseStrategyCard(content: string): StrategyCardData | null {
  // Extract code from content - supports python and r blocks with more flexible regex
  const codeMatch = content.match(/```(?:python|r)[^\n]*\n([\s\S]*?)(?:```|$)/i);
  const scriptCode = codeMatch ? codeMatch[1].trim() : "";

  // Look for JSON block marked with json_strategy type - more flexible
  const jsonMatch = content.match(/```(?:json_strategy|json)[^\n]*\n?([\s\S]*?)\n?```/i);
  
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[1]);
      if (parsed.tool_id && parsed.title) {
        // Combine JSON metadata with extracted code
        return {
          ...parsed,
          code: scriptCode,
        } as StrategyCardData;
      }
    } catch (e) {
      console.error("Strategy card parse error:", e);
    }
  }

  // Also try to find raw JSON object anywhere in content
  const rawMatch = content.match(/\{[\s\S]*?"tool_id"[\s\S]*?\}/);
  if (rawMatch) {
    try {
      const parsed = JSON.parse(rawMatch[0]);
      if (parsed.tool_id && parsed.title) {
        return {
          ...parsed,
          code: scriptCode,
        } as StrategyCardData;
      }
    } catch (e) {
      console.error("Strategy card parse error (raw):", e);
    }
  }

  return null;
}
