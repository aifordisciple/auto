"""
SKILL API 路由 - 模块化入口

本文件是技能 API 的统一入口，实际实现已拆分到 skills/ 子目录：

模块结构：
- skills/__init__.py: 路由聚合入口
- skills/crud.py: 基础 CRUD 操作
- skills/catalog.py: 目录、分类、标签
- skills/forge.py: 技能锻造
- skills/testing.py: 沙箱测试
- skills/transform.py: Live Coding 转化
- skills/versions.py: 版本管理
- skills/stats.py: 统计与历史
- skills/favorites.py: 收藏功能
- skills/reviews.py: 评价功能
- skills/my.py: 我的技能
- skills/admin.py: 管理员审核

辅助服务：
- services/skill_validator.py: 铁律校验
- schemas/skill.py: Pydantic 模型
"""

# 从子模块导入路由
from app.api.routes.skills import router

__all__ = ["router"]