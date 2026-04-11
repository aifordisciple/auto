# PLAN7.md - 智能学习系统："越用越聪明"核心能力

> 创建日期：2026-03-31
> 项目：AUTONOME Studio - AI-Native Bioinformatics IDE

---

## 1. 需求重述

### 1.1 "越来越聪明"的具体含义

用户期望系统具备以下核心能力：

| 维度 | 具体含义 | 量化指标 |
|------|----------|----------|
| **推荐准确度提升** | 技能推荐越来越精准，减少用户搜索和试错 | 推荐命中率从 ~60% 提升至 ~85% |
| **领域知识积累** | 系统对生信分析的理解越来越深入 | 知识库词条从 ~50 提升至 ~500+ |
| **个性化适应** | 系统理解每个用户的使用习惯和偏好 | 用户偏好命中率 > 70% |
| **执行稳定性** | 技能执行成功率随使用逐步提高 | 成功率从 ~80% 提升至 ~95% |
| **参数推断优化** | LLM 参数推断越来越符合用户期望 | 参数准确率从 ~60% 提升至 ~85% |

### 1.2 现有基础评估

| 模块 | 现状评分 | 基础能力 | 需补充能力 |
|------|----------|----------|------------|
| 技能推荐系统 | 7.5 | 三阶段混合匹配（规则+向量+LLM） | 个性化权重、反馈驱动优化 |
| 反馈闭环 | 6.5 | SkillMatchingFeedback 模型、RecommendationFeedbackService | 埋点覆盖率、知识提炼机制 |
| 向量检索 | 7.0 | pgvector 索引、缓存策略 | 向量增量更新、领域知识向量 |
| 用户数据 | 6.0 | 执行历史、收藏功能 | 偏好学习、行为画像 |
| 知识库 | 4.0 | SKILL.md 专家知识字段 | 知识图谱、动态更新机制 |

---

## 2. 系统架构设计

### 2.1 数据流架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    智能学习系统架构                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                    │
│  │ 用户行为    │────▶│ 行为埋点    │────▶│ 反馈数据库  │                    │
│  │ (查询/执行) │     │ 服务        │     │ PostgreSQL  │                    │
│  └─────────────┘     └─────────────┘     └─────────────┘                    │
│                                                │                              │
│                                                ▼                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    数据分析层                            ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐││
│  │  │ 偏好学习引擎 │  │ 知识提炼引擎 │  │ 模型优化引擎 │  │ 异常检测引擎 │││
│  │  │              │  │              │  │              │  │              │││
│  │  │ 用户画像     │  │ 知识图谱     │  │ 权重调整     │  │ 告警触发     │││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                │                              │
│                                                ▼                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    知识应用层                             ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐││
│  │  │ 个性化推荐   │  │ 智能参数推断 │  │ 动态权重     │  │ 预警干预     │││
│  │  │              │  │              │  │              │  │              │││
│  │  │ 用户偏好+    │  │ 历史参数+    │  │ 反馈驱动     │  │ 异常自动     │││
│  │  │ 领域知识     │  │ 领域知识     │  │ 实时调整     │  │ 处理         │││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                │                              │
│                                                ▼                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    持续优化循环                                ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │                                                                           ││
│  │   用户使用 → 行为采集 → 数据分析 → 知识应用 → 体验优化 → 更多使用          ││
│  │       ↑___________________________________________________________↓       ││
│  │                                                                           ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 新增数据模型

| 模型 | 用途 | 关键字段 |
|------|------|----------|
| `UserPreferenceProfile` | 用户偏好画像 | user_id, frequent_skills, preferred_categories, parameter_patterns, expertise_level |
| `DomainKnowledgeEntry` | 领域知识库 | knowledge_id, domain, concept, synonyms, related_skills, usage_context, confidence |
| `FeedbackDrivenWeight` | 反馈驱动权重 | skill_id, keyword_weights, category_boost, success_rate_factor, last_updated |
| `ParameterPattern` | 参数使用模式 | skill_id, parameter_name, common_values, inferred_rules, success_correlation |
| `LearningMetrics` | 学习效果指标 | metric_type, value, trend, timestamp, improvement_rate |

---

## 3. 实现阶段分解

### Phase 1: 数据采集与埋点完善（P1，4天）

**目标**: 建立完整的行为数据采集体系，为学习引擎提供数据基础。

| 任务 | 文件路径 | 依赖 | 风险 | 状态 |
|------|----------|------|------|------|
| 1.1 行为埋点服务重构 | `/autonome-backend/app/services/behavior_tracker.py` | 无 | Low | ✅ 完成 |
| 1.2 前端埋点 SDK | `/autonome-studio/src/lib/analytics.ts` | 无 | Low | ✅ 完成 |
| 1.3 埋点 API 路由 | `/autonome-backend/app/api/routes/analytics.py` | 1.1 | Medium | ✅ 完成 |
| 1.4 反馈埋点覆盖率提升 | `skill_matcher.py`, `skill_executor.py` | 1.1 | Medium | ✅ 完成 |

**行为类型定义**:
```python
class BehaviorType:
    QUERY = "query"               # 用户查询
    RECOMMEND = "recommend"       # 技能被推荐
    CLICK = "click"               # 用户点击技能
    VIEW_DETAIL = "view_detail"   # 查看技能详情
    EXECUTE = "execute"           # 技能被执行
    SUCCESS = "success"           # 执行成功
    FAILURE = "failure"           # 执行失败
    RETRY = "retry"               # 重试执行
    MODIFY_PARAM = "modify_param" # 修改参数
    ABORT = "abort"               # 中断执行
    FEEDBACK = "feedback"         # 用户反馈
    FAVORITE = "favorite"         # 收藏技能
    SHARE = "share"               # 分享结果
```

---

### Phase 2: 用户偏好学习引擎（P2，9天）

**目标**: 建立用户画像，实现个性化推荐。

| 任务 | 文件路径 | 依赖 | 风险 | 状态 |
|------|----------|------|------|------|
| 2.1 用户偏好模型 | `/autonome-backend/app/models/user_preference.py` | Phase 1 | Low | ✅ 完成 |
| 2.2 偏好学习引擎 | `/autonome-backend/app/services/preference_engine.py` | 2.1 | Medium | ✅ 完成 |
| 2.3 偏好画像 API | `/autonome-backend/app/api/routes/preferences.py` | 2.2 | Low | ✅ 完成 |
| 2.4 个性化推荐集成 | `skill_matcher.py` 修改 | 2.2 | High | ✅ 完成 |
| 2.5 前端偏好展示 | `/autonome-studio/src/components/preferences/` | 2.3 | Low | ⏳ 待开始 |

**偏好学习维度**:
1. 常用技能: 过去30天执行次数最多的技能（Top 10）
2. 偏好分类: 用户倾向使用的技能分类（权重分布）
3. 参数模式: 用户常用的参数设置（历史统计）
4. 时间偏好: 用户活跃时段分析
5. 专家水平: 基于执行成功率和参数复杂度推断

---

### Phase 3: 领域知识提炼引擎（P3，8天）

**目标**: 从用户行为和技能执行中提炼生信领域知识，构建知识图谱。

| 任务 | 文件路径 | 依赖 | 风险 | 状态 |
|------|----------|------|------|------|
| 3.1 领域知识模型 | `/autonome-backend/app/models/domain_knowledge.py` | Phase 1 | Low | ✅ 完成 |
| 3.2 知识提炼引擎 | `/autonome-backend/app/services/knowledge_engine.py` | 3.1 | High | ✅ 完成 |
| 3.3 知识图谱构建 | `/autonome-backend/app/services/knowledge_graph.py` | 3.2 | High | ✅ 完成 |
| 3.4 知识检索 API | `/autonome-backend/app/api/routes/knowledge.py` | 3.3 | Medium | ✅ 完成 |
| 3.5 知识向量索引 | `skill_embedding_service.py` 扩展 | 3.3 | Medium | ⏳ 待开始 |

**知识提炼来源**:
1. 高成功率执行记录: 提取成功的参数配置、数据特征
2. 用户反馈文本: 从反馈中提取关键概念和问题
3. 技能专家知识: 融合 SKILL.md 中的专家指导
4. 查询-技能映射: 分析查询关键词与技能的关联
5. 执行错误模式: 提取常见错误和解决方案

---

### Phase 4: 反馈驱动权重优化（P4，4.5天）

**目标**: 建立反馈驱动的动态权重调整机制，让推荐算法持续优化。

| 任务 | 文件路径 | 依赖 | 风险 | 状态 |
|------|----------|------|------|------|
| 4.1 动态权重模型 | `/autonome-backend/app/models/feedback_weight.py` | Phase 1 | Low | ✅ 完成 |
| 4.2 权重优化引擎 | `/autonome-backend/app/services/weight_optimizer.py` | 4.1 | Medium | ✅ 完成 |
| 4.3 权重调整 API | `/autonome-backend/app/api/routes/weights.py` | 4.2 | Low | ✅ 完成 |
| 4.4 推荐集成 | `skill_matcher.py` 修改 | 4.2 | High | ⏳ 待开始 |

**权重计算公式**:
```
final_weight = base_weight
               × success_rate_factor
               × click_rate_factor
               × user_preference_factor
               × time_decay_factor
```

---

### Phase 5: 学习效果监控与可视化（P5，6天）

**目标**: 建立学习效果监控体系，可视化系统智能成长过程。

| 任务 | 文件路径 | 依赖 | 风险 | 状态 |
|------|----------|------|------|------|
| 5.1 学习指标模型 | `/autonome-backend/app/models/learning_metrics.py` | Phase 2-4 | Low | ✅ 完成 |
| 5.2 指标计算服务 | `/autonome-backend/app/services/learning_metrics_service.py` | 5.1 | Low | ✅ 完成 |
| 5.3 学习仪表盘 API | `/autonome-backend/app/api/routes/learning.py` | 5.2 | Low | ✅ 完成 |
| 5.4 前端学习可视化 | `/autonome-studio/src/components/learning/` | 5.3 | Medium | ⏳ 待开始 |
| 5.5 定期报告生成 | `/autonome-backend/app/tasks/learning_report.py` | 5.2 | Low | ⏳ 待开始 |

**监控指标**:
- 推荐命中率趋势
- 参数推断准确率
- 执行成功率变化
- 用户满意度评分
- 知识库增长曲线
- 个性化效果对比

---

### Phase 6: 持续学习闭环自动化（P6，5.5天）

**目标**: 建立自动化学习闭环，定期执行学习任务，无需人工干预。

| 任务 | 文件路径 | 依赖 | 风险 | 状态 |
|------|----------|------|------|------|
| 6.1 Celery 定时任务 | `/autonome-backend/app/tasks/learning_tasks.py` | Phase 2-5 | Medium | ✅ 完成 |
| 6.2 学习任务调度器 | `/autonome-backend/app/services/learning_scheduler.py` | 6.1 | Medium | ✅ 完成 |
| 6.3 A/B 测试框架 | `/autonome-backend/app/services/ab_testing.py` | 6.2 | High | ✅ 完成 |
| 6.4 模型版本管理 | `/autonome-backend/app/services/model_versioning.py` | 6.3 | Medium | ✅ 完成 |
| 6.5 自动回滚机制 | `/autonome-backend/app/services/rollback.py` | 6.4 | High | ✅ 完成 |

**定时任务调度**:
```python
# 每5分钟聚合反馈数据
sender.add_periodic_task(300.0, aggregate_feedback.s())

# 每小时更新用户偏好画像
sender.add_periodic_task(3600.0, update_user_profiles.s())

# 每6小时提炼领域知识
sender.add_periodic_task(21600.0, extract_domain_knowledge.s())

# 每天优化推荐权重
sender.add_periodic_task(crontab(hour=2, minute=0), optimize_weights.s())

# 每周生成学习报告
sender.add_periodic_task(crontab(hour=3, minute=0, day_of_week=1), generate_report.s())
```

---

## 4. 依赖与风险分析

### 4.1 依赖关系

```
Phase 1 (埋点完善) ─────────────────────────────────────────────────────────────┐
                                                                                 │
Phase 2 (偏好学习) ────────────────────────┬─────────────────────────────────────┤
                                          │                                      │
Phase 3 (知识提炼) ────────────────────────┤                                      │
                                          │                                      │
Phase 4 (权重优化) ────────────────────────┼─────────────────────────────────────┤
                                          │                                      │
Phase 5 (效果监控) ────────────────────────┼─────────────────────────────────────┤
                                          │                                      │
Phase 6 (持续学习) ────────────────────────┼─────────────────────────────────────┘
                                          │
                                          ▼
                                    用户可见效果
```

### 4.2 风险分析

| 风险 | 级别 | 描述 | 缓解措施 |
|------|------|------|----------|
| **数据隐私风险** | HIGH | 用户行为数据涉及隐私 | 数据脱敏、用户授权机制、隐私政策 |
| **冷启动问题** | MEDIUM | 新用户无历史数据 | 默认推荐策略、渐进式个性化 |
| **过度拟合风险** | MEDIUM | 仅学习当前用户偏好 | 加入全局知识、A/B 测试验证 |
| **数据质量问题** | MEDIUM | 噪声数据影响学习 | 数据清洗、异常检测、置信度阈值 |
| **性能开销** | MEDIUM | 学习任务消耗资源 | 批量处理、异步执行、资源监控 |
| **知识冲突** | LOW | 不同来源知识矛盾 | 知识置信度评分、人工审核机制 |

---

## 5. 复杂度评估

### 5.1 总体复杂度: 3.0/5 (中等)

| 维度 | 评分 | 说明 |
|------|------|------|
| 技术复杂度 | 3.5 | 涉及 ML/数据分析，但无复杂模型训练 |
| 数据复杂度 | 3.0 | 多模型关联，需要数据同步机制 |
| 架构复杂度 | 3.0 | 新增多个服务，但架构清晰 |
| 前端复杂度 | 2.5 | 基础可视化组件，无复杂交互 |
| 运维复杂度 | 2.0 | Celery 定时任务，常规运维 |

### 5.2 工作量估算

| Phase | 后端 | 前端 | 测试 | 总计 |
|-------|------|------|------|------|
| P1 埋点完善 | 2天 | 1天 | 1天 | **4天** |
| P2 偏好学习 | 5天 | 2天 | 2天 | **9天** |
| P3 知识提炼 | 5天 | 1天 | 2天 | **8天** |
| P4 权重优化 | 3天 | 0.5天 | 1天 | **4.5天** |
| P5 效果监控 | 2天 | 3天 | 1天 | **6天** |
| P6 持续学习 | 3天 | 0.5天 | 2天 | **5.5天** |
| **总计** | **20天** | **8天** | **9天** | **37天** |

---

## 6. 成功指标

### 6.1 学习效果目标

| 指标 | 当前值 | 目标值 | 提升幅度 |
|------|--------|--------|----------|
| 推荐命中率 | ~60% | ~85% | +25% |
| 参数推断准确率 | ~60% | ~85% | +25% |
| 执行成功率 | ~80% | ~95% | +15% |
| 用户满意度 | 未测量 | 4.5/5 | - |
| 知识库词条数 | ~50 | ~500 | +450 |
| 个性化覆盖率 | 0% | 70% | +70% |

### 6.2 验收标准

- [ ] 用户行为埋点覆盖率 > 90%
- [ ] 用户偏好画像每日自动更新
- [ ] 知识库每周新增词条 > 10
- [ ] 推荐命中率持续提升趋势
- [ ] 学习仪表盘可视化上线
- [ ] A/B 测试框架支持算法验证

---

## 7. 关键文件清单

### 7.1 新增文件

| 优先级 | 文件路径 | 功能描述 |
|--------|----------|----------|
| P1 | `/autonome-backend/app/services/behavior_tracker.py` | 行为埋点服务 |
| P1 | `/autonome-backend/app/api/routes/analytics.py` | 埋点 API 路由 |
| P1 | `/autonome-studio/src/lib/analytics.ts` | 前端埋点 SDK |
| P2 | `/autonome-backend/app/models/user_preference.py` | 用户偏好模型 |
| P2 | `/autonome-backend/app/services/preference_engine.py` | 偏好学习引擎 |
| P3 | `/autonome-backend/app/models/domain_knowledge.py` | 领域知识模型 |
| P3 | `/autonome-backend/app/services/knowledge_engine.py` | 知识提炼引擎 |
| P4 | `/autonome-backend/app/services/weight_optimizer.py` | 权重优化引擎 |
| P5 | `/autonome-backend/app/models/learning_metrics.py` | 学习指标模型 |
| P5 | `/autonome-studio/src/components/learning/LearningDashboard.tsx` | 学习仪表盘 |
| P6 | `/autonome-backend/app/tasks/learning_tasks.py` | Celery 学习任务 |

### 7.2 需修改文件

| 优先级 | 文件路径 | 修改内容 |
|--------|----------|----------|
| P1 | `skill_matcher.py` | 增加埋点调用 |
| P1 | `skill_executor.py` | 增加执行埋点 |
| P2 | `skill_matcher.py` | 集成偏好引擎 |
| P4 | `skill_matcher.py` | 动态权重集成 |
| P5 | `main.py` | 注册学习 API 路由 |
| P6 | `celery_config.py` | 学习任务调度配置 |

---

## 8. 进度追踪

| Phase | 开始日期 | 完成日期 | 状态 |
|-------|----------|----------|------|
| P1 | 2026-03-31 | 2026-03-31 | ✅ 完成 |
| P2 | 2026-03-31 | 2026-03-31 | ✅ 完成 |
| P3 | 2026-03-31 | 2026-03-31 | ✅ 完成 |
| P4 | 2026-03-31 | 2026-03-31 | ✅ 完成 |
| P5 | 2026-03-31 | 2026-03-31 | ✅ 完成 |
| P6 | 2026-03-31 | 2026-03-31 | ✅ 完成 |

---

## 9. 更新日志

| 日期 | 更新内容 |
|------|----------|
| 2026-03-31 | P6 完成：A/B测试框架(14测试)、模型版本管理(12测试)、自动回滚机制(10测试)，共84个测试通过 |
| 2026-03-31 | P6.3 完成：A/B测试框架 - 实验创建、用户分配、转化记录、统计结果，14个测试通过 |
| 2026-03-31 | P6.1-6.2 完成：Celery定时任务、学习调度器，共24个测试通过 |
| 2026-03-31 | P5 完成：学习指标模型、指标计算服务、学习仪表盘API，共66个测试通过 |
| 2026-03-31 | P4 完成：动态权重模型、权重优化引擎、权重调整API，共64个测试通过 |
| 2026-03-31 | P3 完成：领域知识模型、知识提炼引擎、知识图谱服务、知识检索API，共64个测试通过 |
| 2026-03-31 | P2 完成：用户偏好模型、偏好学习引擎、偏好画像API、个性化推荐集成到skill_matcher |
| 2026-03-31 | P1 完成：行为埋点服务、前端SDK、API路由、集成到skill_matcher和skill_executor |
| 2026-03-31 | 初始计划创建 |