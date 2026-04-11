/**
 * 技能工厂对话舞台
 *
 * Gemini 风格对话式创建：
 * - 集成 ForgeToolbar（底部工具栏 + Tool 选择器）
 * - 集成 ForgeFileUploader（增强版文件上传）
 * - 支持 toolMode 切换：
 *   - chat: 正常对话，SSE 实时更新 skillDraft
 *   - code_import: 调用 craftFromMaterial() 分析代码
 *   - skill_import: 调用 craftFromBundle() 解析 SKILL 包
 */

"use client";

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Bot, User, Sparkles, Paperclip, Loader2, Hammer, Check, AlertCircle, Code, Settings2, FileCode } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchEventSource } from '@microsoft/fetch-event-source';

import { useForgeStore, ToolMode } from '@/store/useForgeStore';
import { MarkdownBlock } from '@/components/MarkdownBlock';
import { BASE_URL, skillForgeApi, forgeSessionApi } from '@/lib/api';
import { ForgeToolbar } from './ForgeToolbar';
import { ForgeFileUploader, UploadedFile } from './ForgeFileUploader';

// ==========================================
// 代码语言检测
// ==========================================

type DetectedLanguage = 'python' | 'r' | 'perl' | 'bash' | 'unknown';

/**
 * 根据代码特征检测语言类型
 *
 * 检测逻辑：
 * - R 语言特征：library(), require(), <-, %>% , function(), data.frame, tibble 等
 * - Python 特征：import, from ... import, def, class, if __name__, print( 等
 * - Perl 特征：use strict, use warnings, my $, sub, print 等
 * - Bash 特征：#!/bin/bash, echo, export, $变量 等
 */
function detectCodeLanguage(code: string): DetectedLanguage {
  const codeLower = code.toLowerCase();
  const firstLines = code.split('\n').slice(0, 20).join('\n').toLowerCase();

  // R 语言特征检测
  const rPatterns = [
    /\blibrary\s*\(/,
    /\brequire\s*\(/,
    /\bfunction\s*\([^)]*\)\s*\{/,
    /\bdata\.frame\s*\(/,
    /\btibble\s*\(/,
    /\breadr::/,
    /\bdplyr::/,
    /\bggplot2::/,
    /\btidyr::/,
    /<-\s*[^=]/,
    /\%>\%/,
    /\bsapply\s*\(/,
    /\blapply\s*\(/,
    /\bapply\s*\(/,
    /\bmapply\s*\(/,
    /\bvapply\s*\(/,
    /\bplot\s*\(/,
    /\bhist\s*\(/,
    /\bsummary\s*\(/,
    /\bhead\s*\(/,
    /\btail\s*\(/,
    /\bstr\s*\(/,
    /\bnrow\s*\(/,
    /\bncol\s*\(/,
    /\blength\s*\(/,
    /\bnames\s*\(/,
    /\bcolnames\s*\(/,
    /\brownames\s*\(/,
    /\bcbind\s*\(/,
    /\brbind\s*\(/,
    /\bmerge\s*\(/,
    /\bsubset\s*\(/,
    /\btransform\s*\(/,
    /\bwithin\s*\(/,
    /\bwith\s*\(/,
    /\baggregate\s*\(/,
    /\btable\s*\(/,
    /\bprop\.table\s*\(/,
    /\bxtabs\s*\(/,
    /\bftable\s*\(/,
    /\bas\.data\.frame\s*\(/,
    /\bas\.matrix\s*\(/,
    /\bas\.list\s*\(/,
    /\blist\s*\(/,
    /\bc\s*\(/,
    /\bseq\s*\(/,
    /\brep\s*\(/,
    /\bsample\s*\(/,
    /\brnorm\s*\(/,
    /\brunif\s*\(/,
    /\brpois\s*\(/,
    /\bdnorm\s*\(/,
    /\bpnorm\s*\(/,
    /\bqnorm\s*\(/,
    /\bsetwd\s*\(/,
    /\bgetwd\s*\(/,
    /\blist\.files\s*\(/,
    /\bread\.csv\s*\(/,
    /\bread\.table\s*\(/,
    /\bread\.delim\s*\(/,
    /\breadLines\s*\(/,
    /\bread\.rds\s*\(/,
    /\breadRDS\s*\(/,
    /\bsave\.rds\s*\(/,
    /\bsaveRDS\s*\(/,
    /\bwrite\.csv\s*\(/,
    /\bwrite\.table\s*\(/,
    /\bwriteLines\s*\(/,
    /\bload\s*\(/,
    /\bsave\s*\(/,
    /\bsave\.image\s*\(/,
    /\battach\s*\(/,
    /\bdetach\s*\(/,
    /\brm\s*\(/,
    /\bls\s*\(/,
    /\bobjects\s*\(/,
    /\bclass\s*\(/,
    /\btypeof\s*\(/,
    /\bmode\s*\(/,
    /\bexists\s*\(/,
    /\bget\s*\(/,
    /\bassign\s*\(/,
    /\bcat\s*\(/,
    /\bprint\s*\([^)]*\)/,
    /\bpaste\s*\(/,
    /\bpaste0\s*\(/,
    /\bsprintf\s*\(/,
    /\bsubstr\s*\(/,
    /\bgsub\s*\(/,
    /\bsub\s*\(/,
    /\bgrep\s*\(/,
    /\bregexpr\s*\(/,
    /\bgregexpr\s*\(/,
    /\bregexec\s*\(/,
    /\bregmatches\s*\(/,
    /\bnchar\s*\(/,
    /\btolower\s*\(/,
    /\btoupper\s*\(/,
    /\bchartr\s*\(/,
    /\btrimws\s*\(/,
    /\bzoo::/,
    /\blubridate::/,
    /\bstringr::/,
    /\bpurrr::/,
    /\bstringi::/,
    /\breshape2::/,
    /\bplyr::/,
    /\bdata\.table::/,
    /\bmatrixStats::/,
    /\bfutile\.logger::/,
  ];

  // Python 特征检测
  const pythonPatterns = [
    /^import\s+\w+/m,
    /^from\s+\w+\s+import/m,
    /\bdef\s+\w+\s*\(/,
    /\bclass\s+\w+.*:/,
    /\bif\s+__name__\s*==\s*['"]__main__['"]/,
    /\bprint\s*\(/,
    /\blen\s*\(/,
    /\brange\s*\(/,
    /\benumerate\s*\(/,
    /\bzip\s*\(/,
    /\bmap\s*\(/,
    /\bfilter\s*\(/,
    /\bsorted\s*\(/,
    /\blist\s*\(/,
    /\bdict\s*\(/,
    /\bset\s*\(/,
    /\btuple\s*\(/,
    /\bstr\s*\(/,
    /\bint\s*\(/,
    /\bfloat\s*\(/,
    /\bbool\s*\(/,
    /\btype\s*\(/,
    /\bisinstance\s*\(/,
    /\bhasattr\s*\(/,
    /\bgetattr\s*\(/,
    /\bsetattr\s*\(/,
    /\bopen\s*\([^)]*,\s*['"][rwa]['"]/,
    /\bwith\s+open\s*\(/,
    /\bfor\s+\w+\s+in\s+/,
    /\bwhile\s+\w+\s*:/,
    /\btry\s*:/,
    /\bexcept\s+\w*\s*:/,
    /\bfinally\s*:/,
    /\braise\s+\w+/,
    /\bassert\s+/,
    /\blambda\s+/,
    /\breturn\s+/,
    /\byield\s+/,
    /\basync\s+def/,
    /\bawait\s+/,
    /\bself\s*\./,
    /\bNone\b/,
    /\bTrue\b/,
    /\bFalse\b/,
    /\bimport\s+pandas\b/,
    /\bimport\s+numpy\b/,
    /\bimport\s+matplotlib\b/,
    /\bimport\s+seaborn\b/,
    /\bimport\s+scipy\b/,
    /\bimport\s+sklearn\b/,
    /\bimport\s+tensorflow\b/,
    /\bimport\s+torch\b/,
    /\bimport\s+keras\b/,
    /\bpd\.\w+/,
    /\bnp\.\w+/,
    /\bplt\.\w+/,
    /\bsns\.\w+/,
    /\bsklearn\.\w+/,
    /\btf\.\w+/,
  ];

  // Perl 特征检测
  const perlPatterns = [
    /^use\s+strict/m,
    /^use\s+warnings/m,
    /\bmy\s+\$\w+/,
    /\bour\s+\$\w+/,
    /\blocal\s+\$\w+/,
    /\bsub\s+\w+\s*\{/,
    /\bprint\s+"/,
    /\bprint\s+'\w/,
    /\bsay\s+/,
    /\bchomp\s*\(/,
    /\bchop\s*\(/,
    /\bsplit\s*\(/,
    /\bjoin\s*\(/,
    /\bpush\s*\(@/,
    /\bpop\s*\(@/,
    /\bshift\s*\(@/,
    /\bunshift\s*\(@/,
    /\bmap\s*\{/,
    /\bgrep\s*\{/,
    /\bsort\s*\{/,
    /\bforeach\s+\$\w+/,
    /\bwhile\s*\(.*<.*>\)/,
    /\bopen\s*\(\$\w+,/,
    /\bclose\s*\(\$\w+\)/,
    /\bdie\s+/,
    /\bwarn\s+/,
    /\bif\s*\([^)]*\)\s*\{/,
    /\bunless\s+/,
    /\belif\s+/,
    /\belsif\s+/,
    /\bdefined\s*\(/,
    /\bexists\s+\$/,
    /\bdelete\s+\$[\w{]+/,
    /\bkeys\s+\%/,
    /\bvalues\s+\%/,
    /\beach\s+\%/,
    /\bscalar\s*\(@/,
    /\blength\s*\(/,
    /\bsubstr\s*\(/,
    /\bindex\s*\(/,
    /\brindex\s*\(/,
    /\bsprintf\s*\(/,
    /\bprintf\s*\(/,
    /\bsystem\s*\(/,
    /\bexec\s*\(/,
    /\bqx\{/,
    /\b`\w/,
    /\$ARGV\[/,
    /\$ENV\{/,
    /\@ARGV/,
    /\@INC/,
    /\%INC/,
    /\brequire\s+\w+/,
    /\bpackage\s+\w+/,
    /\buse\s+File::/,
    /\buse\s+Getopt::/,
    /\buse\s+Data::Dumper/,
    /\buse\s+Bio::/,
    /\b->\w+\(/,
  ];

  // Bash 特征检测
  const bashPatterns = [
    /^#!\/bin\/bash/,
    /^#!\/bin\/sh/,
    /^#!\/usr\/bin\/env\s+bash/,
    /\becho\s+/,
    /\bexport\s+\w+=/,
    /\bif\s+\[\[/,
    /\bif\s+\[/,
    /\bthen\s*$/,
    /\bfi\s*$/,
    /\bfor\s+\w+\s+in\s+/,
    /\bdo\s*$/,
    /\bdone\s*$/,
    /\bwhile\s+\[\[/,
    /\bwhile\s+\[/,
    /\bcase\s+\$\w+\s+in/,
    /\besac\s*$/,
    /\bfunction\s+\w+\s*\(\)/,
    /\b\$\{\w+\}/,
    /\b\$\(\w+\)/,
    /\b\$\(\([^)]+\)\)/,
    /\blocal\s+\w+=/,
    /\bread\s+\w+/,
    /\bprintf\s+/,
    /\bcat\s+<</,
    /\bcat\s+[^>]/,
    /\bgrep\s+/,
    /\bsed\s+/,
    /\bawk\s+/,
    /\bcut\s+/,
    /\bsort\s+/,
    /\buniq\s+/,
    /\bwc\s+/,
    /\bhead\s+/,
    /\btail\s+/,
    /\bfind\s+/,
    /\bxargs\s+/,
    /\bmkdir\s+/,
    /\brm\s+/,
    /\bcp\s+/,
    /\bmv\s+/,
    /\bchmod\s+/,
    /\bchown\s+/,
    /\bls\s+/,
    /\bcd\s+/,
    /\bpwd\s*$/,
    /\bexit\s+\d+/,
    /\breturn\s+\d+/,
    /\btrap\s+/,
    /\bsource\s+/,
    /\b\.\s+\//,
    /\bnohup\s+/,
    /\b&\s*$/,
    /\b\|\s*\w+/,
    /\b>\s*\//,
    /\b>>\s*\//,
  ];

  // 计算各语言特征匹配数
  let rScore = 0;
  let pythonScore = 0;
  let perlScore = 0;
  let bashScore = 0;

  for (const pattern of rPatterns) {
    if (pattern.test(code) || pattern.test(firstLines)) {
      rScore++;
    }
  }

  for (const pattern of pythonPatterns) {
    if (pattern.test(code) || pattern.test(firstLines)) {
      pythonScore++;
    }
  }

  for (const pattern of perlPatterns) {
    if (pattern.test(code) || pattern.test(firstLines)) {
      perlScore++;
    }
  }

  for (const pattern of bashPatterns) {
    if (pattern.test(code) || pattern.test(firstLines)) {
      bashScore++;
    }
  }

  console.log('[detectCodeLanguage] Scores:', { rScore, pythonScore, perlScore, bashScore });

  // 找出最高分
  const maxScore = Math.max(rScore, pythonScore, perlScore, bashScore);

  if (maxScore === 0) {
    return 'unknown';
  }

  // 需要有明显优势才判定
  const threshold = 3;  // 至少匹配3个特征

  if (rScore >= threshold && rScore > pythonScore * 1.2) {
    return 'r';
  }

  if (pythonScore >= threshold && pythonScore > rScore * 1.2) {
    return 'python';
  }

  if (perlScore >= threshold && perlScore > Math.max(rScore, pythonScore) * 1.2) {
    return 'perl';
  }

  if (bashScore >= threshold && bashScore > Math.max(rScore, pythonScore, perlScore) * 1.2) {
    return 'bash';
  }

  // 默认返回得分最高的
  if (rScore >= pythonScore && rScore >= perlScore && rScore >= bashScore) {
    return 'r';
  }

  if (pythonScore >= perlScore && pythonScore >= bashScore) {
    return 'python';
  }

  if (perlScore >= bashScore) {
    return 'perl';
  }

  return 'bash';
}

/**
 * 根据检测到的语言返回执行器类型
 */
function getExecutorTypeFromLanguage(language: DetectedLanguage): string {
  switch (language) {
    case 'python':
      return 'Python_env';
    case 'r':
      return 'R_env';
    case 'perl':
    case 'bash':
      return 'Python_env'; // Perl/Bash 暂时用 Python_env 包装
    default:
      return 'Python_env';
  }
}

// ==========================================
// 代码导入进度阶段
// ==========================================

type CodeImportStage = 'idle' | 'creating_session' | 'analyzing_code' | 'inferring_params' | 'generating_draft' | 'complete' | 'error';

const CODE_IMPORT_STAGES: Record<CodeImportStage, { label: string; progress: number; icon: React.ReactNode }> = {
  idle: { label: '准备开始', progress: 0, icon: <Code size={16} /> },
  creating_session: { label: '创建会话...', progress: 15, icon: <Loader2 size={16} className="animate-spin" /> },
  analyzing_code: { label: '分析代码结构...', progress: 30, icon: <FileCode size={16} className="animate-pulse" /> },
  inferring_params: { label: 'AI 推断参数定义...', progress: 55, icon: <Sparkles size={16} className="animate-pulse" /> },
  generating_draft: { label: '生成技能草稿...', progress: 80, icon: <Settings2 size={16} className="animate-pulse" /> },
  complete: { label: '导入完成！', progress: 100, icon: <Check size={16} /> },
  error: { label: '导入失败', progress: 0, icon: <AlertCircle size={16} /> },
};

// ==========================================
// 进度卡片组件
// ==========================================

interface ProgressCardProps {
  stage: CodeImportStage;
  skillName?: string;
  paramCount?: number;
  errorMessage?: string;
}

function ProgressCard({ stage, skillName, paramCount, errorMessage }: ProgressCardProps) {
  const config = CODE_IMPORT_STAGES[stage];
  const isComplete = stage === 'complete';
  const isError = stage === 'error';

  return (
    <div className="bg-neutral-800 rounded-2xl p-4 min-w-[280px] max-w-[360px]">
      {/* 进度条 */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-2">
          <span className={`text-sm font-medium ${
            isComplete ? 'text-emerald-400' : isError ? 'text-red-400' : 'text-blue-400'
          }`}>
            {config.icon}
          </span>
          <span className="text-xs text-neutral-500">{config.progress}%</span>
        </div>
        <div className="w-full bg-neutral-700 rounded-full h-2 overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${config.progress}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            className={`h-2 rounded-full ${
              isComplete ? 'bg-emerald-500' : isError ? 'bg-red-500' : 'bg-blue-500'
            }`}
          />
        </div>
      </div>

      {/* 当前状态 */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`${
          isComplete ? 'text-emerald-400' : isError ? 'text-red-400' : 'text-neutral-300'
        } text-sm`}>
          {config.label}
        </span>
      </div>

      {/* 阶段指示器 */}
      <div className="flex justify-between text-[10px] text-neutral-600">
        <span className={stage !== 'idle' ? 'text-blue-400' : ''}>会话</span>
        <span className={['analyzing_code', 'inferring_params', 'generating_draft', 'complete'].includes(stage) ? 'text-blue-400' : ''}>分析</span>
        <span className={['inferring_params', 'generating_draft', 'complete'].includes(stage) ? 'text-purple-400' : ''}>推断</span>
        <span className={['generating_draft', 'complete'].includes(stage) ? 'text-emerald-400' : ''}>生成</span>
      </div>

      {/* 完成信息 */}
      {isComplete && skillName && (
        <div className="mt-3 pt-3 border-t border-neutral-700">
          <div className="text-sm text-neutral-300">
            <span className="text-emerald-400">✓</span> 技能名称：<span className="font-medium">{skillName}</span>
          </div>
          {paramCount !== undefined && (
            <div className="text-xs text-neutral-500 mt-1">
              已识别 {paramCount} 个参数
            </div>
          )}
        </div>
      )}

      {/* 错误信息 */}
      {isError && errorMessage && (
        <div className="mt-3 pt-3 border-t border-neutral-700">
          <div className="text-sm text-red-400">{errorMessage}</div>
        </div>
      )}
    </div>
  );
}

// ==========================================
// 主组件
// ==========================================

export function ForgeChatStage() {
  const {
    sessionId,
    messages,
    addMessage,
    appendLastMessage,
    skillDraft,
    setSkillDraft,
    isTyping,
    setIsTyping,
    executorType,
    createSession,
    setExecutorType,
    refreshSessionList,
    toolMode,
    initSkillFiles
  } = useForgeStore();

  // 本地状态
  const [isFileUploaderOpen, setIsFileUploaderOpen] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [codeImportStage, setCodeImportStage] = useState<CodeImportStage>('idle');
  const [progressSkillName, setProgressSkillName] = useState<string>();
  const [progressParamCount, setProgressParamCount] = useState<number>();
  const [progressError, setProgressError] = useState<string>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isStreamingRef = useRef(false);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ==========================================
  // 处理发送消息（根据 toolMode 分发）
  // ==========================================

  const handleSendMessage = useCallback(async (message: string, files: File[]) => {
    if (!sessionId) return;

    // 根据 toolMode 处理
    switch (toolMode) {
      case 'chat':
        await handleChatMode(message, files);
        break;
      case 'code_import':
        await handleCodeImportMode(message);
        break;
      case 'skill_import':
        await handleSkillImportMode(files);
        break;
    }
  }, [sessionId, toolMode, executorType]);

  // ==========================================
  // 对话模式 - SSE 流式对话
  // ==========================================

  const handleChatMode = async (message: string, files: File[]) => {
    if (!message.trim() && files.length === 0) return;
    if (!sessionId) return;

    // 添加用户消息
    const attachmentNames = files.map(f => f.name);
    addMessage('user', message, attachmentNames);
    setIsTyping(true);
    isStreamingRef.current = true;

    // 清空待处理文件
    setPendingFiles([]);

    // 添加空的助手消息（用于流式追加）
    addMessage('assistant', '');

    try {
      const token = localStorage.getItem('autonome_access_token');

      // 如果有文件，需要先上传到服务器
      // 这里简化处理：将文件名作为附件路径传递
      // 后端会根据实际需求处理附件
      let uploadedPaths: string[] = [];
      if (files.length > 0) {
        // 使用项目上传接口（需要一个有效的项目 ID）
        // 暂时简化：只传递文件名，让后端知道用户上传了什么文件
        uploadedPaths = files.map(f => `/uploads/forge_temp/${f.name}`);
        appendLastMessage(`📎 已添加 ${files.length} 个附件: ${files.map(f => f.name).join(', ')}\n\n`);
      }

      await fetchEventSource(`${BASE_URL}/api/skills/forge/session/${sessionId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          message,
          attachments: uploadedPaths,
          executor_type: executorType
        }),
        openWhenHidden: true,
        onmessage(event) {
          console.log('[ForgeChatStage] SSE event:', event.event, event.data?.substring(0, 200));
          if (event.event === 'message') {
            try {
              const data = JSON.parse(event.data);
              if (data.type === 'text') {
                appendLastMessage(data.content);
              }
            } catch {}
          } else if (event.event === 'skill_update') {
            try {
              const data = JSON.parse(event.data);
              console.log('[ForgeChatStage] skill_update data:', data);
              if (data.type === 'draft') {
                // 使用 getState() 获取最新状态，避免闭包陷阱
                const latestDraft = useForgeStore.getState().skillDraft;
                const mergedDraft = { ...latestDraft, ...data.data };
                console.log('[ForgeChatStage] 合并后的草稿:', mergedDraft);
                setSkillDraft(mergedDraft);
              }
            } catch (e) {
              console.error('[ForgeChatStage] 解析 skill_update 失败:', e);
            }
          } else if (event.event === 'done') {
            isStreamingRef.current = false;
            setIsTyping(false);
          } else if (event.event === 'error') {
            try {
              const data = JSON.parse(event.data);
              appendLastMessage(`\n\n❌ 错误: ${data.content}`);
            } catch {}
            isStreamingRef.current = false;
            setIsTyping(false);
          }
        },
        onclose() {
          isStreamingRef.current = false;
          setIsTyping(false);
        },
        onerror(err) {
          console.error('Forge chat error:', err);
          isStreamingRef.current = false;
          setIsTyping(false);
          throw err;
        }
      });
    } catch (error) {
      console.error('Forge chat error:', error);
      setIsTyping(false);
    }
  };

  // ==========================================
  // 代码导入模式 - AI 分析推断参数
  // ==========================================

  const handleCodeImportMode = async (code: string) => {
    if (!code.trim()) return;

    // ==========================================
    // 0. 自动检测代码语言类型
    // ==========================================
    const detectedLanguage = detectCodeLanguage(code);
    const detectedExecutorType = getExecutorTypeFromLanguage(detectedLanguage);

    console.log('[handleCodeImportMode] 检测到语言类型:', detectedLanguage, '→ 执行器类型:', detectedExecutorType);

    // 重置进度状态
    setProgressSkillName(undefined);
    setProgressParamCount(undefined);
    setProgressError(undefined);
    setCodeImportStage('idle');

    // ==========================================
    // 1. 添加用户消息（显示代码片段和语言检测结果）
    // ==========================================
    const codePreview = code.length > 500 ? code.slice(0, 500) + '\n...' : code;
    const codeLines = code.split('\n').length;
    const languageDisplay = detectedLanguage === 'r' ? 'R' :
                            detectedLanguage === 'python' ? 'Python' :
                            detectedLanguage === 'perl' ? 'Perl' :
                            detectedLanguage === 'bash' ? 'Bash' : '未知';
    addMessage('user', `📝 **代码导入** (${languageDisplay})\n\n\`\`\`${detectedLanguage === 'r' ? 'r' : detectedLanguage === 'python' ? 'python' : ''}\n${codePreview}\n\`\`\`\n\n共 ${codeLines} 行代码`);

    // 清空待处理文件
    setPendingFiles([]);
    setIsTyping(true);

    try {
      // ==========================================
      // 2. 添加助手消息占位（用于显示进度卡片）
      // ==========================================
      addMessage('assistant', '__PROGRESS_CARD__');

      // 确保有会话
      let currentSessionId = sessionId;

      // ==========================================
      // 阶段1: 创建会话
      // ==========================================
      setCodeImportStage('creating_session');
      if (!currentSessionId) {
        currentSessionId = await createSession();
      }
      await new Promise(resolve => setTimeout(resolve, 200));

      // ==========================================
      // 阶段2: 分析代码结构
      // ==========================================
      setCodeImportStage('analyzing_code');
      await new Promise(resolve => setTimeout(resolve, 300));

      // ==========================================
      // 阶段3: AI 推断参数（使用检测到的执行器类型）
      // ==========================================
      setCodeImportStage('inferring_params');

      // 调用 AI 分析接口 - 使用检测到的执行器类型
      const response = await skillForgeApi.craftFromMaterial({
        raw_material: code,
        executor_type: detectedExecutorType as any,  // 使用检测到的类型
        generate_full_bundle: false
      });

      // ==========================================
      // 阶段4: 生成技能草稿
      // ==========================================
      setCodeImportStage('generating_draft');
      await new Promise(resolve => setTimeout(resolve, 200));

      // 设置技能草稿
      if (response.data) {
        const inferredExecutorType = response.data.executor_type as any;
        const skillDraftData = {
          name: response.data.name || '未命名技能',
          description: response.data.description || '',
          executor_type: inferredExecutorType,
          script_code: response.data.script_code || '',
          nextflow_code: response.data.nextflow_code || '',
          parameters_schema: response.data.parameters_schema || {},
          expert_knowledge: response.data.expert_knowledge || '',
          dependencies: response.data.dependencies || []
        };

        const paramCount = Object.keys(skillDraftData.parameters_schema?.properties || {}).length;

        // 更新进度卡片信息
        setProgressSkillName(skillDraftData.name);
        setProgressParamCount(paramCount);

        // 同步执行器类型
        setExecutorType(inferredExecutorType);

        // 设置前端状态
        setSkillDraft(skillDraftData);

        // 持久化到后端会话
        if (currentSessionId) {
          try {
            await forgeSessionApi.updateDraft(currentSessionId, skillDraftData);
          } catch (persistErr) {
            console.error('持久化草稿失败:', persistErr);
          }
        }

        // 刷新会话列表
        await refreshSessionList();

        // 初始化文件系统
        initSkillFiles();

        // ==========================================
        // 阶段5: 完成
        // ==========================================
        setCodeImportStage('complete');
      }
    } catch (error: any) {
      setCodeImportStage('error');
      setProgressError(error.message || '未知错误');
    } finally {
      setIsTyping(false);
    }
  };

  // ==========================================
  // 技能包导入模式 - 解析 SKILL 包
  // ==========================================

  const handleSkillImportMode = async (files: File[]) => {
    if (files.length === 0) return;

    const skillBundleFile = files[0];
    setIsTyping(true);

    // 添加用户消息
    addMessage('user', `上传技能包: ${skillBundleFile.name}`);

    try {
      // 确保有会话
      let currentSessionId = sessionId;
      if (!currentSessionId) {
        currentSessionId = await createSession();
      }

      // 调用解析接口
      const response = await skillForgeApi.craftFromBundle({
        file: skillBundleFile,
        executorType: executorType,
        generateFullBundle: false
      });

      // 设置技能草稿
      if (response.data) {
        const inferredExecutorType = response.data.executor_type as any;
        const skillDraftData = {
          name: response.data.name || skillBundleFile.name.replace(/\.(zip|tar\.gz|tgz)$/, ''),
          description: response.data.description || '',
          executor_type: inferredExecutorType,
          script_code: response.data.script_code || '',
          nextflow_code: response.data.nextflow_code || '',
          parameters_schema: response.data.parameters_schema || {},
          expert_knowledge: response.data.expert_knowledge || '',
          dependencies: response.data.dependencies || []
        };

        // 同步执行器类型
        setExecutorType(inferredExecutorType);

        // 设置前端状态
        setSkillDraft(skillDraftData);

        // 持久化到后端会话
        if (currentSessionId) {
          try {
            await forgeSessionApi.updateDraft(currentSessionId, skillDraftData);
          } catch (persistErr) {
            console.error('持久化草稿失败:', persistErr);
          }
        }

        // 刷新会话列表
        await refreshSessionList();

        // 初始化文件系统
        initSkillFiles();

        // 添加成功消息
        addMessage('assistant', `✅ 技能包解析成功！\n\n**技能名称**: ${skillDraftData.name}\n\n已在右侧编辑器中加载技能配置，请查看和调整。`);
      }
    } catch (error: any) {
      addMessage('assistant', `❌ 技能包解析失败: ${error.message || '未知错误'}`);
    } finally {
      setIsTyping(false);
      setPendingFiles([]);
    }
  };

  // ==========================================
  // 文件上传回调
  // ==========================================

  const handleFilesUploaded = useCallback((uploadedFiles: UploadedFile[]) => {
    const files = uploadedFiles.map(f => f.file);
    setPendingFiles(prev => [...prev, ...files]);
    setIsFileUploaderOpen(false);
  }, []);

  const handleRemoveFile = useCallback((index: number) => {
    setPendingFiles(prev => prev.filter((_, i) => i !== index));
  }, []);

  // ==========================================
  // 渲染
  // ==========================================

  return (
    <div className="flex-1 flex flex-col min-h-0 h-full">
      {/* 欢迎消息 */}
      {messages.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center py-8 text-neutral-500">
            <Hammer size={32} className="mx-auto mb-3 text-blue-500" />
            <p className="font-medium text-neutral-300">技能锻造工坊</p>
            <p className="text-sm mt-2">描述您的需求，AI 将帮您锻造标准化技能</p>
            <div className="mt-4 text-xs text-neutral-600 space-y-1">
              <p>示例："帮我写一个用 scanpy 过滤单细胞数据的脚本"</p>
              <p>"写一个 FastQC + MultiQC 质控工作流"</p>
            </div>
          </div>
        </div>
      )}

      {/* 消息列表 */}
      {messages.length > 0 && (
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
          <AnimatePresence>
            {messages.map((msg, idx) => (
              <motion.div
                key={msg.id || idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center shrink-0">
                    <Bot size={16} className="text-blue-400" />
                  </div>
                )}
                <div className={`max-w-[85%] ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-neutral-800 text-neutral-200'
                } rounded-2xl px-4 py-3`}>
                  {msg.role === 'assistant' ? (
                    // 检查是否是进度卡片占位消息
                    msg.content === '__PROGRESS_CARD__' ? (
                      <ProgressCard
                        stage={codeImportStage}
                        skillName={progressSkillName}
                        paramCount={progressParamCount}
                        errorMessage={progressError}
                      />
                    ) : (
                      <MarkdownBlock content={msg.content} />
                    )
                  ) : (
                    <MarkdownBlock content={msg.content} />
                  )}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {msg.attachments.map((att, i) => (
                        <span key={i} className="text-xs bg-black/20 px-2 py-0.5 rounded flex items-center gap-1">
                          <Paperclip size={10} />
                          {att}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                    <User size={16} className="text-emerald-400" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* 普通 typing 指示器 */}
          {isTyping && messages[messages.length - 1]?.role !== 'assistant' && toolMode !== 'code_import' && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center">
                <Loader2 size={16} className="text-blue-400 animate-spin" />
              </div>
              <div className="bg-neutral-800 rounded-2xl px-4 py-3">
                <Sparkles size={16} className="text-blue-400 animate-pulse" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* 底部工具栏 */}
      <ForgeToolbar
        onSendMessage={handleSendMessage}
        onOpenFileUploader={() => setIsFileUploaderOpen(true)}
        isTyping={isTyping}
        attachments={pendingFiles}
        onRemoveAttachment={handleRemoveFile}
      />

      {/* 文件上传对话框 */}
      <ForgeFileUploader
        isOpen={isFileUploaderOpen}
        onClose={() => setIsFileUploaderOpen(false)}
        onFilesUploaded={handleFilesUploaded}
      />
    </div>
  );
}