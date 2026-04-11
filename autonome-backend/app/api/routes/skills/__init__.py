"""
技能 API 路由模块

按功能拆分的技能相关 API：

- crud.py: 基础 CRUD 操作
- catalog.py: 目录、分类、标签
- forge.py: 技能锻造
- testing.py: 沙箱测试
- transform.py: Live Coding 转化
- versions.py: 版本管理
- stats.py: 统计与历史
- favorites.py: 收藏功能
- reviews.py: 评价功能
- my.py: 我的技能
- admin.py: 管理员审核
- draft.py: 技能草稿管理（自动转化）
"""

from fastapi import APIRouter
from app.core.logger import log

# 导入各功能模块
from app.api.routes.skills import crud
from app.api.routes.skills import catalog
from app.api.routes.skills import forge
from app.api.routes.skills import testing
from app.api.routes.skills import transform
from app.api.routes.skills import versions
from app.api.routes.skills import stats
from app.api.routes.skills import favorites
from app.api.routes.skills import reviews
from app.api.routes.skills import my
from app.api.routes.skills import admin
from app.api.routes.skills import draft

# 创建主路由
router = APIRouter()

# 注册各模块路由
# 注意：路由顺序很重要，具体的路径必须在参数化路径之前注册

# 1. 目录和分类（无参数路径）
router.include_router(catalog.router, tags=["skills-catalog"])

# 2. 锻造相关（无参数路径）
router.include_router(forge.router, tags=["skills-forge"])

# 3. 测试相关（无参数路径）
router.include_router(testing.router, tags=["skills-testing"])

# 4. 转化相关（无参数路径）
router.include_router(transform.router, tags=["skills-transform"])

# 5. 草稿管理（无参数路径，/drafts/*）
router.include_router(draft.router, prefix="/drafts", tags=["skills-draft"])

# 6. 统计相关（包含 /history 无参数路径）
router.include_router(stats.router, tags=["skills-stats"])

# 7. 收藏相关（包含 /favorites 无参数路径）
router.include_router(favorites.router, tags=["skills-favorites"])

# 8. 我的技能（包含 /my/* 路径）
router.include_router(my.router, tags=["skills-my"])

# 9. 版本管理（包含 /{skill_id}/versions 路径）
router.include_router(versions.router, tags=["skills-versions"])

# 10. 评价相关（包含 /{skill_id}/reviews 路径）
router.include_router(reviews.router, tags=["skills-reviews"])

# 11. 管理员功能（包含 /admin/* 路径）
router.include_router(admin.router, tags=["skills-admin"])

# 12. CRUD 基础操作（最后注册，因为包含 /{skill_id} 参数化路径）
router.include_router(crud.router, tags=["skills-crud"])

# 加载完成日志
log.info("📚 SKILL API 路由已加载")

__all__ = ["router"]