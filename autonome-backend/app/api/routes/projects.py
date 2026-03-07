import os
import shutil
import secrets
from pathlib import Path
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
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

@router.get("/{project_id}")
async def get_project(project_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # ✨ 获取单个项目详情
    project = session.exec(select(Project).where(Project.id == project_id, Project.owner_id == current_user.id)).first()
    if not project:
        return {"status": "error", "message": "Project not found"}
    return {"status": "success", "data": project}

@router.post("")
async def create_project(project: ProjectCreate, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # ✨ 创建项目时，强制绑定 owner_id
    new_proj = Project(name=project.name, description=project.description, owner_id=current_user.id)
    session.add(new_proj)
    session.commit()
    session.refresh(new_proj)

    # ✨ 1. 基础物理目录划分
    project_dir = Path(settings.UPLOAD_DIR) / f"project_{new_proj.id}"
    (project_dir / "raw_data").mkdir(parents=True, exist_ok=True)
    (project_dir / "results").mkdir(parents=True, exist_ok=True)

    # ✨ 2. 初始化系统级全局参考数据库目录
    # 放在 UPLOAD_DIR 下，确保 Docker 沙箱能一并挂载
    global_ref_dir = Path(settings.UPLOAD_DIR) / "global_references"
    global_ref_dir.mkdir(parents=True, exist_ok=True)

    # ✨ 3. 为当前项目创建相对路径的软链接
    ref_symlink = project_dir / "references"
    if not ref_symlink.exists():
        # 相当于在 Linux 中执行 ln -s ../global_references references
        os.symlink("../global_references", str(ref_symlink))

    return {"status": "success", "data": new_proj}

@router.delete("/{project_id}")
async def delete_project(project_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除该项目")
    session.delete(project)
    session.commit()
    return {"status": "success", "message": "Project deleted"}

@router.get("/{project_id}/sessions")
async def get_project_sessions(project_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    sessions = session.exec(
        select(ChatSession).where(ChatSession.project_id == project_id).order_by(ChatSession.created_at.desc())
    ).all()
    return {"status": "success", "data": sessions}

@router.post("/{project_id}/sessions")
async def create_session(project_id: str, title: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    new_session = ChatSession(title=title, project_id=project_id)
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    return {"status": "success", "data": new_session}


@router.get("/{project_id}/current-session")
async def get_current_session(project_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
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
async def get_chat_history(project_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
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
async def upload_file(project_id: str, file: UploadFile = File(...), session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # ✨ 创建项目专属文件夹: /app/uploads/project_{project_id}/raw_data
    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    raw_data_dir = project_dir / "raw_data"  # ✨ 目标存入原始数据区
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    
    # ✨ 文件保存在 raw_data 目录里
    file_path = raw_data_dir / file.filename
    
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
        file_path=str(file_path),
        file_size=os.path.getsize(file_path),
        file_type=file_type,
        project_id=project_id
    )
    session.add(new_file)
    session.commit()
    session.refresh(new_file)
    return {"status": "success", "data": new_file}

@router.get("/{project_id}/files")
async def get_project_files(project_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    """获取项目下的所有文件（递归扫描 raw_data 和 results 目录）"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    
    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    
    # 如果目录不存在，顺手把标准结构建好
    raw_data_dir = project_dir / "raw_data"
    results_dir = project_dir / "results"
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    files = []
    # 递归遍历整个 project 目录
    for root, _, filenames in os.walk(project_dir):
        for filename in filenames:
            full_path = Path(root) / filename
            # 获取相对于项目根目录的相对路径，例如：raw_data/ras.tsv
            rel_path = full_path.relative_to(project_dir)
            
            # 过滤掉隐藏系统文件
            if filename.startswith('.'):
                continue
                
            files.append({
                "name": filename,
                "path": str(rel_path),
                "size": full_path.stat().st_size,
                "url": f"/api/projects/{project_id}/files/{str(rel_path)}/view"
            })
            
    return {"status": "success", "data": files}

@router.delete("/{project_id}/files/{file_path:path}")
async def delete_project_file(
    project_id: str,
    file_path: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """删除项目下的文件（通过相对路径）"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    
    # 安全检查：防止路径穿越攻击
    if ".." in file_path:
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    full_path = project_dir / file_path

    if full_path.exists():
        full_path.unlink()
        return {"status": "success", "message": "File deleted"}
    
    raise HTTPException(status_code=404, detail="File not found")
    
    # 2. 删除数据库记录
    session.delete(db_file)
    session.commit()
    
    return {"status": "success", "message": "文件已彻底删除"}

@router.post("/{project_id}/share")
async def toggle_project_share(
    project_id: str, 
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



@router.get("/{project_id}/files/{file_path:path}/view")
async def view_project_file(
    project_id: str,
    file_path: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    提供给前端 Markdown 渲染图片的直链读取接口
    """
    # 安全检查：防止路径穿越攻击
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path")

    # 验证用户是否有权访问该项目
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该项目")

    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    full_path = project_dir / file_path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(full_path)