/**
 * 多入口创建对话框
 *
 * 提供多种技能创建方式：
 * 1. 对话锻造 - AI 对话式创建
 * 2. 代码导入 - 粘贴代码，AI 推断参数
 * 3. 模板实例化 - 从模板库选择
 * 4. 文件包上传 - 上传 .zip 技能包
 */

'use client';

import React, { useState, useRef } from 'react';
import { X, MessageSquare, Code, FileBox, Upload, Loader2, Check, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { templateApi, skillForgeApi, forgeSessionApi, SkillTemplate, ExecutorType } from '@/lib/api';
import { useForgeStore } from '@/store/useForgeStore';

type EntryType = 'chat' | 'code' | 'template' | 'bundle';

interface CreateEntryDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function CreateEntryDialog({ isOpen, onClose, onSuccess }: CreateEntryDialogProps) {
  const [selectedEntry, setSelectedEntry] = useState<EntryType | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 代码导入状态
  const [codeInput, setCodeInput] = useState('');
  const [codeLanguage, setCodeLanguage] = useState<'python' | 'r'>('python');

  // 模板选择状态
  const [templates, setTemplates] = useState<SkillTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<SkillTemplate | null>(null);
  const [templateCustomName, setTemplateCustomName] = useState('');

  // 文件上传状态
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { createSession, setSkillDraft, sessionId } = useForgeStore();

  // 入口选项配置
  const entryOptions: Array<{
    type: EntryType;
    icon: React.ReactNode;
    title: string;
    description: string;
    color: string;
  }> = [
    {
      type: 'chat',
      icon: <MessageSquare size={24} />,
      title: '对话锻造',
      description: '通过 AI 对话描述需求，逐步完善技能',
      color: 'text-blue-400 bg-blue-500/20'
    },
    {
      type: 'code',
      icon: <Code size={24} />,
      title: '代码导入',
      description: '粘贴已有代码，AI 自动推断参数定义',
      color: 'text-green-400 bg-green-500/20'
    },
    {
      type: 'template',
      icon: <FileBox size={24} />,
      title: '模板实例化',
      description: '从预置模板快速创建技能实例',
      color: 'text-purple-400 bg-purple-500/20'
    },
    {
      type: 'bundle',
      icon: <Upload size={24} />,
      title: '文件包上传',
      description: '上传 .zip 技能包（含 SKILL.md + scripts/）',
      color: 'text-orange-400 bg-orange-500/20'
    }
  ];

  // 重置状态
  const resetState = () => {
    setSelectedEntry(null);
    setCodeInput('');
    setCodeLanguage('python');
    setSelectedTemplate(null);
    setTemplateCustomName('');
    setUploadedFile(null);
    setUploadProgress(0);
    setError(null);
  };

  // 关闭对话框
  const handleClose = () => {
    resetState();
    onClose();
  };

  // 加载模板列表
  const loadTemplates = async () => {
    try {
      const result = await templateApi.listTemplates();
      setTemplates(result || []);
    } catch (err) {
      console.error('加载模板失败:', err);
      setTemplates([]);
    }
  };

  // 选择入口类型
  const handleSelectEntry = async (type: EntryType) => {
    setSelectedEntry(type);
    setError(null);

    if (type === 'template') {
      await loadTemplates();
    }
  };

  // 对话锻造 - 创建新会话
  const handleChatCreate = async () => {
    setIsLoading(true);
    try {
      await createSession();
      onSuccess?.();
      handleClose();
    } catch (err: any) {
      setError(err.message || '创建会话失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 代码导入 - AI 推断参数
  const handleCodeImport = async () => {
    if (!codeInput.trim()) {
      setError('请输入代码');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // 先创建会话
      const newSessionId = await createSession();

      // 调用 AI 推断接口
      const response = await skillForgeApi.craftFromMaterial({
        raw_material: codeInput,
        executor_type: codeLanguage === 'python' ? 'Python_env' : 'R_env',
        generate_full_bundle: false
      });

      // 设置技能草稿
      if (response.data) {
        setSkillDraft({
          name: response.data.name || '未命名技能',
          description: response.data.description || '',
          executor_type: response.data.executor_type as ExecutorType,
          script_code: response.data.script_code || '',
          parameters_schema: response.data.parameters_schema || {},
          expert_knowledge: response.data.expert_knowledge || '',
          dependencies: response.data.dependencies || []
        });
      }

      onSuccess?.();
      handleClose();
    } catch (err: any) {
      setError(err.message || '代码导入失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 模板实例化
  const handleTemplateInstantiate = async () => {
    if (!selectedTemplate) {
      setError('请选择模板');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // 先创建会话
      await createSession();

      // 实例化模板
      const result = await templateApi.instantiateTemplate(selectedTemplate.template_id, {
        skill_name: templateCustomName || undefined
      });

      // 设置技能草稿
      setSkillDraft({
        name: result.name || templateCustomName || selectedTemplate.name,
        description: result.description || selectedTemplate.description || '',
        executor_type: result.executor_type as ExecutorType,
        script_code: result.script_code || '',
        parameters_schema: result.parameters_schema || {},
        expert_knowledge: result.expert_knowledge || '',
        dependencies: result.dependencies || []
      });

      onSuccess?.();
      handleClose();
    } catch (err: any) {
      setError(err.message || '模板实例化失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 文件包上传
  const handleBundleUpload = async () => {
    if (!uploadedFile) {
      setError('请选择文件');
      return;
    }

    setIsLoading(true);
    setError(null);
    setUploadProgress(10);

    try {
      // 先创建会话
      await createSession();
      setUploadProgress(30);

      // 上传并解析
      const response = await skillForgeApi.craftFromBundle({
        file: uploadedFile,
        executorType: 'Logical_Blueprint',
        generateFullBundle: false
      });

      setUploadProgress(80);

      // 设置技能草稿
      if (response.data) {
        setSkillDraft({
          name: response.data.name || uploadedFile.name.replace(/\.(zip|tar\.gz|tgz)$/, ''),
          description: response.data.description || '',
          executor_type: response.data.executor_type as ExecutorType,
          script_code: response.data.script_code || '',
          nextflow_code: response.data.nextflow_code || '',
          parameters_schema: response.data.parameters_schema || {},
          expert_knowledge: response.data.expert_knowledge || '',
          dependencies: response.data.dependencies || []
        });
      }

      setUploadProgress(100);
      onSuccess?.();
      handleClose();
    } catch (err: any) {
      setError(err.message || '文件解析失败');
      setUploadProgress(0);
    } finally {
      setIsLoading(false);
    }
  };

  // 处理文件选择
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const validExtensions = ['.zip', '.tar.gz', '.tgz'];
      const isValid = validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
      if (!isValid) {
        setError('请上传 .zip, .tar.gz 或 .tgz 文件');
        return;
      }
      setUploadedFile(file);
      setError(null);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          className="bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden"
          onClick={e => e.stopPropagation()}
        >
          {/* 标题栏 */}
          <div className="flex items-center justify-between p-4 border-b border-neutral-800">
            <h2 className="text-lg font-semibold text-white">创建新技能</h2>
            <button
              onClick={handleClose}
              className="p-1 text-neutral-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* 内容区 */}
          <div className="p-6">
            {/* 入口选择 */}
            {!selectedEntry && (
              <div className="grid grid-cols-2 gap-4">
                {entryOptions.map(option => (
                  <button
                    key={option.type}
                    onClick={() => handleSelectEntry(option.type)}
                    className="flex flex-col items-start p-4 rounded-lg border border-neutral-700 hover:border-neutral-500 hover:bg-neutral-800/50 transition-all text-left group"
                  >
                    <div className={`p-2 rounded-lg mb-3 ${option.color}`}>
                      {option.icon}
                    </div>
                    <h3 className="text-sm font-medium text-white group-hover:text-blue-400 transition-colors">
                      {option.title}
                    </h3>
                    <p className="text-xs text-neutral-500 mt-1">
                      {option.description}
                    </p>
                  </button>
                ))}
              </div>
            )}

            {/* 代码导入 */}
            {selectedEntry === 'code' && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 mb-2">
                  <button
                    onClick={() => setCodeLanguage('python')}
                    className={`px-3 py-1 rounded-md text-sm ${
                      codeLanguage === 'python'
                        ? 'bg-blue-500 text-white'
                        : 'bg-neutral-800 text-neutral-400 hover:text-white'
                    }`}
                  >
                    Python
                  </button>
                  <button
                    onClick={() => setCodeLanguage('r')}
                    className={`px-3 py-1 rounded-md text-sm ${
                      codeLanguage === 'r'
                        ? 'bg-blue-500 text-white'
                        : 'bg-neutral-800 text-neutral-400 hover:text-white'
                    }`}
                  >
                    R
                  </button>
                </div>
                <textarea
                  value={codeInput}
                  onChange={(e) => setCodeInput(e.target.value)}
                  placeholder={`粘贴 ${codeLanguage === 'python' ? 'Python' : 'R'} 代码，AI 将自动推断参数定义...`}
                  className="w-full h-64 bg-neutral-800 border border-neutral-700 rounded-lg p-4 text-sm text-white font-mono focus:border-blue-500 focus:outline-none resize-none"
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setSelectedEntry(null)}
                    className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
                  >
                    返回
                  </button>
                  <button
                    onClick={handleCodeImport}
                    disabled={isLoading || !codeInput.trim()}
                    className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-neutral-700 text-white text-sm rounded-lg transition-colors"
                  >
                    {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Code size={16} />}
                    导入并推断参数
                  </button>
                </div>
              </div>
            )}

            {/* 模板实例化 */}
            {selectedEntry === 'template' && (
              <div className="space-y-4">
                {templates.length === 0 ? (
                  <div className="text-center py-8 text-neutral-500">
                    <FileBox size={32} className="mx-auto mb-2 opacity-50" />
                    <p>暂无可用模板</p>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-2">
                      {templates.map(template => (
                        <button
                          key={template.template_id}
                          onClick={() => setSelectedTemplate(template)}
                          className={`p-3 rounded-lg border text-left transition-all ${
                            selectedTemplate?.template_id === template.template_id
                              ? 'border-purple-500 bg-purple-500/20'
                              : 'border-neutral-700 hover:border-neutral-500'
                          }`}
                        >
                          <div className="text-sm font-medium text-white truncate">{template.name}</div>
                          <div className="text-xs text-neutral-500 truncate">{template.description}</div>
                        </button>
                      ))}
                    </div>
                    {selectedTemplate && (
                      <div className="mt-4">
                        <label className="text-xs text-neutral-500 mb-1 block">自定义名称（可选）</label>
                        <input
                          type="text"
                          value={templateCustomName}
                          onChange={(e) => setTemplateCustomName(e.target.value)}
                          placeholder={selectedTemplate.name}
                          className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white focus:border-purple-500 focus:outline-none"
                        />
                      </div>
                    )}
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setSelectedEntry(null)}
                        className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
                      >
                        返回
                      </button>
                      <button
                        onClick={handleTemplateInstantiate}
                        disabled={isLoading || !selectedTemplate}
                        className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-neutral-700 text-white text-sm rounded-lg transition-colors"
                      >
                        {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
                        实例化模板
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* 文件包上传 */}
            {selectedEntry === 'bundle' && (
              <div className="space-y-4">
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-neutral-700 rounded-lg p-8 text-center cursor-pointer hover:border-orange-500/50 transition-colors"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".zip,.tar.gz,.tgz"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  {uploadedFile ? (
                    <div className="text-orange-400">
                      <Check size={32} className="mx-auto mb-2" />
                      <p className="text-sm">{uploadedFile.name}</p>
                      <p className="text-xs text-neutral-500">{(uploadedFile.size / 1024).toFixed(1)} KB</p>
                    </div>
                  ) : (
                    <div className="text-neutral-500">
                      <Upload size={32} className="mx-auto mb-2" />
                      <p className="text-sm">点击或拖拽上传技能包</p>
                      <p className="text-xs">支持 .zip, .tar.gz, .tgz 格式</p>
                    </div>
                  )}
                </div>

                {uploadProgress > 0 && uploadProgress < 100 && (
                  <div className="w-full bg-neutral-800 rounded-full h-2">
                    <div
                      className="bg-orange-500 h-2 rounded-full transition-all"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setSelectedEntry(null)}
                    className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
                  >
                    返回
                  </button>
                  <button
                    onClick={handleBundleUpload}
                    disabled={isLoading || !uploadedFile}
                    className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-500 disabled:bg-neutral-700 text-white text-sm rounded-lg transition-colors"
                  >
                    {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                    解析并创建
                  </button>
                </div>
              </div>
            )}

            {/* 错误提示 */}
            {error && (
              <div className="mt-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400 text-sm">
                <AlertCircle size={16} />
                {error}
              </div>
            )}
          </div>

          {/* 对话锻造快捷入口 */}
          {selectedEntry === null && (
            <div className="px-6 pb-6">
              <button
                onClick={handleChatCreate}
                disabled={isLoading}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-sm rounded-lg transition-colors"
              >
                {isLoading ? <Loader2 size={16} className="animate-spin" /> : <MessageSquare size={16} />}
                开始对话锻造
              </button>
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}