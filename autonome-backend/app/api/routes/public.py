from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.core.database import get_session
from app.models.domain import Project, ChatSession, ChatMessage, DataFile

router = APIRouter()


@router.get("/shared/{share_token}")
async def get_shared_workspace(share_token: str, session: Session = Depends(get_session)):
    """
    任何人（无需登录）都可通过此接口获取被公开的项目快照
    """
    # 1. 精准查询被公开的项目
    project = session.exec(
        select(Project).where(Project.share_token == share_token, Project.is_public == True)
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="该分享链接不存在或已被原作者撤销。")

    # 2. 提取聊天记录 (只读)
    chat_session = session.exec(
        select(ChatSession).where(ChatSession.project_id == project.id).order_by(ChatSession.created_at.desc())
    ).first()
    
    messages = []
    if chat_session:
        msg_list = session.exec(
            select(ChatMessage).where(ChatMessage.session_id == chat_session.id).order_by(ChatMessage.created_at.asc())
        ).all()
        # 序列化消息
        messages = [
            {
                "id": m.id,
                "role": m.role.value if hasattr(m.role, 'value') else m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in msg_list
        ]
        
    # 3. 提取文件列表 (只读，屏蔽物理路径以防泄露)
    files = session.exec(select(DataFile).where(DataFile.project_id == project.id)).all()
    safe_files = [{"filename": f.filename, "file_size": f.file_size} for f in files]

    # 注意：绝对不要返回 owner_id 或具体的文件绝对路径
    return {
        "status": "success",
        "data": {
            "project_name": project.name,
            "project_desc": project.description,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "messages": messages,
            "files": safe_files
        }
    }
