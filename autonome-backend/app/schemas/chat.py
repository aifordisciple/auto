"""
聊天模块 Pydantic 模型集中管理

将原本散落在 chat.py 中的请求/响应模型集中定义，
提高代码可维护性和复用性。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ==========================================
# 聊天请求模型
# ==========================================

class ChatRequest(BaseModel):
    """聊天流请求"""
    project_id: str
    message: str
    context_files: list[str] = []
    session_id: Optional[str] = None
    skill_id: Optional[str] = None  # 用户预选技能ID
    images: list[str] = []  # 粘贴上传的图片路径列表
    task_mode: Optional[str] = None  # 任务模式：'complex' 强制蓝图，None 自动判断
    enable_think: bool = False  # ✨ 深度思考模式开关（用户手动切换，默认关闭）


# ==========================================
# 会话管理模型
# ==========================================

class SessionUpdate(BaseModel):
    """会话更新请求"""
    title: str


# ==========================================
# 深度解读模型
# ==========================================

class InterpretRequest(BaseModel):
    """深度解读请求"""
    project_id: str
    session_id: str
    user_message: str  # 用户的原始需求
    code: str  # 执行的代码
    files: list[str]  # 结果文件相对路径列表


# ==========================================
# 搜索模型
# ==========================================

class SearchRequest(BaseModel):
    """对话搜索请求"""
    query: str
    project_id: Optional[str] = None
    limit: int = 20


class SearchResultMessage(BaseModel):
    """搜索结果消息"""
    message_id: str
    content: str
    role: str
    created_at: datetime
    highlight: str


class SearchResult(BaseModel):
    """搜索结果"""
    session_id: str
    session_title: str
    matched_messages: list[SearchResultMessage]


# ==========================================
# 收藏模型
# ==========================================

class BookmarkCreate(BaseModel):
    """创建收藏请求"""
    note: Optional[str] = None


class BookmarkUpdate(BaseModel):
    """更新收藏请求"""
    note: Optional[str] = None


# ==========================================
# 标签模型
# ==========================================

class TagCreate(BaseModel):
    """创建标签请求"""
    name: str
    color: Optional[str] = "#3B82F6"


# ==========================================
# 经验提取模型
# ==========================================

class CloseSessionRequest(BaseModel):
    """关闭会话请求"""
    extract_experience: bool = True  # 是否尝试提取经验