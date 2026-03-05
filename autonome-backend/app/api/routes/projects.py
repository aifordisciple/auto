import os
import shutil
import secrets
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from pydantic import BaseModel
import shutil
import secrets
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.core.database import get_session
from app.core.config import settings
from app.models.domain import Project, ChatSession, ChatMessage, DataFile, User
from app.api.deps import get_current_user
from app.core.logger import log

router = APIRouter()

class ProjectCreate(BaseModel):
    name: str
    description: str = ""

@router.get("")
async def get_projects(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # ✨ 绝对隔离：只返回属于当前用户的项目
    projects = session.exec(select(Project).where(Project.owner_id == current_user.id)).all()
    return {"status": "success", "data": projects}

@router.post("")
async def create_project(project: ProjectCreate, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # ✨ 创建项目时，强制绑定 owner_id
    new_proj = Project(name=project.name, description=project.description, owner_id=current_user.id)
    session.add(new_proj)
    session.commit()
    session.refresh(new_proj)
    return {"status": "success", "data": new_proj}

@router.delete("/{project_id}")
async def delete_project(project_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除该项目")
    session.delete(project)
    session.commit()
    return {"status": "success", "message": "Project deleted"}

@router.get("/{project_id}/sessions")
async def get_project_sessions(project_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    sessions = session.exec(
        select(ChatSession).where(ChatSession.project_id == project_id).order_by(ChatSession.created_at.desc())
    ).all()
    return {"status": "success", "data": sessions}

@router.post("/{project_id}/sessions")
async def create_session(project_id: int, title: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    new_session = ChatSession(title=title, project_id=project_id)
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    return {"status": "success", "data": new_session}


@router.get("/{project_id}/current-session")
async def get_current_session(project_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    """获取或创建当前项目的最新会话"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    
    chat_session = session.exec(
        select(ChatSession).where(ChatSession.project_id == project_id).order_by(ChatSession.created_at.desc())
    ).first()
    
    if not chat_session:
        chat_session = ChatSession(project_id=project_id, title="默认分析会话")
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)
    
    return {"status": "success", "session_id": chat_session.id}


@router.get("/{project_id}/chat-history")
async def get_chat_history(project_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # ✨ 安全校验：越权检查
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
         raise HTTPException(status_code=403, detail="无权访问该项目或项目不存在")

    chat_session = session.exec(
        select(ChatSession).where(ChatSession.project_id == project_id).order_by(ChatSession.created_at.desc())
    ).first()
    
    if not chat_session:
        return {"status": "success", "data": []}
        
    messages = session.exec(
        select(ChatMessage).where(ChatMessage.session_id == chat_session.id).order_by(ChatMessage.created_at.asc())
    ).all()
    return {"status": "success", "data": messages}

@router.post("/{project_id}/files")
async def upload_file(project_id: int, file: UploadFile = File(...), session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # ✨ 创建项目专属文件夹: /app/uploads/project_{project_id}
    project_dir = os.path.join(settings.UPLOAD_DIR, f"project_{project_id}")
    os.makedirs(project_dir, exist_ok=True)
    
    # ✨ 文件保存在专属文件夹里，使用干净的文件名
    file_path = os.path.join(project_dir, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Determine file type
    file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    file_type_map = {
        'fastq': 'fastq', 'fq': 'fastq', 'gz': 'fastq',
        'bam': 'bam', 'sam': 'bam',
        'csv': 'csv', 'tsv': 'csv', 'xlsx': 'csv',
        'vcf': 'vcf', 'h5ad': 'h5ad'
    }
    file_type = file_type_map.get(file_ext, 'other')

    new_file = DataFile(
        filename=file.filename,
        file_path=file_path,
        file_size=os.path.getsize(file_path),
        file_type=file_type,
        project_id=project_id
    )
    session.add(new_file)
    session.commit()
    session.refresh(new_file)
    return {"status": "success", "data": new_file}

@router.get("/{project_id}/files")
async def get_project_files(project_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
        
    files = session.exec(select(DataFile).where(DataFile.project_id == project_id)).all()
    return {"status": "success", "data": files}

@router.delete("/{project_id}/files/{file_id}")
async def delete_project_file(
    project_id: int,
    file_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    彻底删除文件：清理物理硬盘 + 清理数据库记录
    """
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    
    # 查找文件记录
    db_file = session.get(DataFile, file_id)
    if not db_file or db_file.project_id != project_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 1. 尝试删除物理文件（容错处理）
    try:
        if db_file.file_path and os.path.exists(db_file.file_path):
            os.remove(db_file.file_path)
            log.info(f"🗑️ 物理文件已删除: {db_file.file_path}")
        else:
            log.info(f"👻 物理文件本就不存在，跳过: {db_file.file_path}")
    except Exception as e:
        log.warning(f"⚠️ 删除物理文件时出错: {e}")
    
    # 2. 删除数据库记录
    session.delete(db_file)
    session.commit()
    
    return {"status": "success", "message": "文件已彻底删除"}

@router.post("/{project_id}/share")
async def toggle_project_share(
    project_id: int, 
    session: Session = Depends(get_session), 
    current_user: User = Depends(get_current_user)
):
    """切换项目的公开分享状态"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
        
    if project.is_public:
        # 关闭分享
        project.is_public = False
        project.share_token = None
    else:
        # 开启分享，生成一个极其安全的随机 URL 友好 Token (24字符)
        project.is_public = True
        project.share_token = secrets.token_urlsafe(24)
        
    session.add(project)
    session.commit()
    session.refresh(project)
    
    return {
        "status": "success", 
        "is_public": project.is_public,
        "share_token": project.share_token
    }



@router.get("/{project_id}/files/{filename:path}/view")
async def view_project_file(
    project_id: int,
    filename: str,
    token: str = None,
):
    """
    提供给前端 Markdown 渲染图片的直链读取接口
    """
    if not token:
        raise HTTPException(status_code=401, detail="未授权的访问")
    
    project_dir = os.path.join(settings.UPLOAD_DIR, f"project_{project_id}")
    file_path = os.path.join(project_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图片或文件不存在")
    
    return FileResponse(file_path)