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
from app.models.domain import Project, ChatSession, ChatMessage, DataFile, User, ProjectUpdate
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


# ✨ 2.3 & 2.5: 更新项目信息与状态 (包括重命名、改图标、软删除归档)
@router.put("/{project_id}")
async def update_project(
    project_id: str,
    project_in: ProjectUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    project = session.exec(select(Project).where(Project.id == project_id, Project.owner_id == current_user.id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 更新传入的非空字段
    project_data = project_in.model_dump(exclude_unset=True)
    for key, value in project_data.items():
        setattr(project, key, value)

    session.add(project)
    session.commit()
    session.refresh(project)

    return {"status": "success", "data": project, "message": "项目已更新"}


# ✨ 2.5: 硬删除 (彻底销毁数据库记录与底层物理硬盘文件)
@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    project = session.exec(select(Project).where(Project.id == project_id, Project.owner_id == current_user.id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 1. 物理层抹除：彻底删除该项目的沙箱工作区及所有数据
    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    if project_dir.exists():
        shutil.rmtree(project_dir, ignore_errors=True)

    # 2. 逻辑层抹除：从数据库中删除记录 (级联的外键会自动处理)
    session.delete(project)
    session.commit()

    return {"status": "success", "message": "项目及其所有物理数据已彻底销毁"}

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
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),
    target_path: str = "raw_data",  # ✨ 新增：目标路径参数，默认 raw_data
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # ✨ 安全检查：防止路径穿越
    if ".." in target_path or target_path.startswith("/"):
        raise HTTPException(status_code=400, detail="非法的目标路径")

    # ✨ 只允许上传到 raw_data 或 results 目录下
    if not (target_path == "raw_data" or target_path == "results" or
            target_path.startswith("raw_data/") or target_path.startswith("results/")):
        raise HTTPException(status_code=403, detail="只能上传到 raw_data 或 results 目录下")

    # ✨ 禁止上传到 references 目录
    if target_path.startswith("references"):
        raise HTTPException(status_code=403, detail="全局参考库只读，禁止上传文件")

    # ✨ 创建项目专属文件夹
    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    target_dir = project_dir / target_path
    target_dir.mkdir(parents=True, exist_ok=True)

    # ✨ 文件保存在目标目录里
    file_path = target_dir / file.filename

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
    """获取项目下的所有文件（递归扫描 raw_data, results 和 references 目录）"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"

    # 1. 顺手把标准物理结构建好
    raw_data_dir = project_dir / "raw_data"
    results_dir = project_dir / "results"
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    # 2. 初始化全局参考目录
    global_ref_dir = Path(settings.UPLOAD_DIR) / "global_references"
    global_ref_dir.mkdir(parents=True, exist_ok=True)

    # 3. 注入防空洞机制：放一个说明文件，确保文件夹非空，从而能被前端树状图识别和渲染
    readme_path = global_ref_dir / "README.txt"
    if not readme_path.exists():
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("系统级全局共享参考库 (Global References)\n存放于此的文件可被所有分析任务共享使用，不占用当前项目的存储空间。")

    # 4. 建立相对软链接
    ref_symlink = project_dir / "references"
    if not ref_symlink.exists() and not ref_symlink.is_symlink():
        try:
            # 建立相对路径软链接 (指向 ../global_references)
            os.symlink("../global_references", str(ref_symlink))
        except OSError:
            pass  # 忽略操作系统不支持或已存在的情况

    files = []
    directories = []  # ✨ 新增：记录目录列表

    # 5. 核心修复：必须加 followlinks=True 才能穿透软链接，读取共享库里的文件
    for root, dirs, filenames in os.walk(project_dir, followlinks=True):
        # 记录当前目录下的所有子目录
        for dir_name in dirs:
            full_dir_path = Path(root) / dir_name
            rel_dir_path = full_dir_path.relative_to(project_dir)

            # 过滤掉隐藏系统目录
            if dir_name.startswith('.'):
                continue

            # 兼容 Windows 系统的路径分隔符
            normalized_dir_path = str(rel_dir_path).replace('\\', '/')
            directories.append({
                "name": dir_name,
                "path": normalized_dir_path,
                "type": "folder"
            })

        for filename in filenames:
            full_path = Path(root) / filename
            rel_path = full_path.relative_to(project_dir)

            # 过滤掉隐藏系统文件
            if filename.startswith('.'):
                continue

            # 兼容 Windows 系统的路径分隔符
            normalized_path = str(rel_path).replace('\\', '/')
            files.append({
                "name": filename,
                "path": normalized_path,
                "type": "file",
                "size": full_path.stat().st_size,
                "url": f"/api/projects/{project_id}/files/{normalized_path}/view"
            })

    # 合并文件和目录，目录在前
    all_items = directories + files

    return {"status": "success", "data": all_items}

@router.delete("/{project_id}/files/{file_path:path}")
async def delete_project_file(
    project_id: str,
    file_path: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """删除项目下的文件或文件夹（通过相对路径）"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    # 1. 防御路径穿越攻击
    if ".." in file_path:
        raise HTTPException(status_code=400, detail="非法的文件路径")

    # 2. 核心防御：绝对禁止修改或删除全局参考库
    if file_path.startswith("references/") or file_path == "references":
        raise HTTPException(status_code=403, detail="全局参考库对所有用户严格只读，禁止删除。")

    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    full_path = project_dir / file_path

    # ✨ 核心修复：增加对目录 (Directory) 的递归删除支持
    if full_path.exists():
        try:
            if full_path.is_dir():
                shutil.rmtree(full_path)  # 递归删除整个文件夹
            else:
                full_path.unlink()  # 删除单个文件
            return {"status": "success", "message": "目标已彻底抹除"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除失败，文件可能被占用: {str(e)}")

    raise HTTPException(status_code=404, detail="文件或文件夹不存在")

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


# ==========================================
# 文件夹管理 API
# ==========================================

class CreateFolderRequest(BaseModel):
    parent_path: str  # 父目录路径，如 "raw_data" 或 "raw_data/subfolder"
    folder_name: str  # 新文件夹名称


class MoveFileRequest(BaseModel):
    source_path: str  # 源文件/文件夹路径
    destination_path: str  # 目标目录路径
    overwrite: bool = False  # 是否覆盖同名文件


def validate_folder_name(name: str) -> str:
    """验证文件夹名称合法性"""
    # 禁止的字符
    forbidden_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\0']
    for char in forbidden_chars:
        if char in name:
            raise HTTPException(status_code=400, detail=f"文件夹名称包含非法字符: {char}")

    # 禁止的保留名
    reserved_names = ['raw_data', 'results', 'references', 'con', 'prn', 'aux', 'nul']
    if name.lower() in reserved_names:
        raise HTTPException(status_code=400, detail="此名称为系统保留，不可使用")

    # 长度限制
    if len(name) == 0:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="文件夹名称过长，最多255个字符")

    # 禁止以点开头
    if name.startswith('.'):
        raise HTTPException(status_code=400, detail="文件夹名称不能以点开头")

    return name


@router.post("/{project_id}/folders")
async def create_folder(
    project_id: str,
    request: CreateFolderRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """创建新文件夹"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 1. 防御路径穿越
    if ".." in request.parent_path or ".." in request.folder_name:
        raise HTTPException(status_code=400, detail="非法的路径")

    # 2. 验证文件夹名称
    folder_name = validate_folder_name(request.folder_name)

    # 3. 检查父目录是否在允许的区域内（只允许在 raw_data 和 results 下创建）
    parent_path = request.parent_path.strip('/')
    if not (parent_path == 'raw_data' or parent_path == 'results' or
            parent_path.startswith('raw_data/') or parent_path.startswith('results/')):
        raise HTTPException(status_code=403, detail="只能在 raw_data 或 results 目录下创建文件夹")

    # 4. 禁止在 references 下创建
    if parent_path.startswith('references'):
        raise HTTPException(status_code=403, detail="全局参考库只读，禁止创建文件夹")

    # 5. 禁止创建根目录
    if parent_path == '' or parent_path == '.':
        raise HTTPException(status_code=400, detail="禁止在项目根目录创建文件夹")

    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    parent_full_path = project_dir / parent_path

    # 6. 检查父目录是否存在
    if not parent_full_path.exists() or not parent_full_path.is_dir():
        raise HTTPException(status_code=404, detail="父目录不存在")

    # 7. 检查是否已存在同名文件夹
    new_folder_path = parent_full_path / folder_name
    if new_folder_path.exists():
        raise HTTPException(status_code=409, detail="同名文件夹已存在")

    # 8. 创建文件夹
    try:
        new_folder_path.mkdir(parents=False, exist_ok=False)
        log.info(f"创建文件夹成功: {new_folder_path}")
        return {
            "status": "success",
            "message": "文件夹创建成功",
            "data": {
                "path": f"{parent_path}/{folder_name}",
                "name": folder_name
            }
        }
    except Exception as e:
        log.error(f"创建文件夹失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建文件夹失败: {str(e)}")


@router.post("/{project_id}/files/move")
async def move_file(
    project_id: str,
    request: MoveFileRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """移动文件或文件夹到目标目录"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 1. 防御路径穿越
    if ".." in request.source_path or ".." in request.destination_path:
        raise HTTPException(status_code=400, detail="非法的路径")

    source_path = request.source_path.strip('/')
    dest_path = request.destination_path.strip('/')

    # 2. 不能移动根目录
    if source_path in ['raw_data', 'results', 'references']:
        raise HTTPException(status_code=403, detail="禁止移动根目录")

    # 3. 不能从/到 references 目录
    if source_path.startswith('references'):
        raise HTTPException(status_code=403, detail="全局参考库只读，禁止移动其中的文件")
    if dest_path.startswith('references'):
        raise HTTPException(status_code=403, detail="全局参考库只读，禁止移动文件到此")

    # 4. 目标目录必须在允许的区域内
    if not (dest_path == 'raw_data' or dest_path == 'results' or
            dest_path.startswith('raw_data/') or dest_path.startswith('results/')):
        raise HTTPException(status_code=403, detail="只能移动到 raw_data 或 results 目录下")

    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"
    source_full = project_dir / source_path
    dest_full = project_dir / dest_path

    # 5. 检查源文件/文件夹是否存在
    if not source_full.exists():
        raise HTTPException(status_code=404, detail="源文件或文件夹不存在")

    # 6. 检查目标目录是否存在
    if not dest_full.exists() or not dest_full.is_dir():
        raise HTTPException(status_code=404, detail="目标目录不存在")

    # 7. 不能移动到自身或子目录
    if source_full == dest_full:
        raise HTTPException(status_code=400, detail="不能移动到自身")

    # 如果源是目录，检查目标是否在源目录内（不能移动到自己的子目录）
    if source_full.is_dir():
        try:
            dest_full.relative_to(source_full)
            raise HTTPException(status_code=400, detail="不能移动到自身的子目录中")
        except ValueError:
            pass  # 目标不在源目录内，正常

    # 8. 处理同名冲突
    source_name = source_full.name
    target_path = dest_full / source_name

    if target_path.exists():
        if not request.overwrite:
            raise HTTPException(status_code=409, detail="目标位置已存在同名文件或文件夹，请选择覆盖或重命名")
        # 覆盖模式：先删除目标
        try:
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除目标文件失败: {str(e)}")

    # 9. 执行移动
    try:
        shutil.move(str(source_full), str(target_path))
        log.info(f"移动成功: {source_full} -> {target_path}")
        return {
            "status": "success",
            "message": "移动成功",
            "data": {
                "old_path": source_path,
                "new_path": f"{dest_path}/{source_name}"
            }
        }
    except Exception as e:
        log.error(f"移动失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"移动失败: {str(e)}")


@router.get("/{project_id}/folders")
async def get_folder_tree(
    project_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取项目的文件夹树结构（用于目标选择器）"""
    project = session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该项目")

    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"

    def build_tree(path: Path, rel_path: str = "") -> dict:
        """递归构建文件夹树"""
        result = {
            "name": path.name,
            "path": rel_path,
            "writable": not rel_path.startswith("references"),
            "children": []
        }

        if path.is_dir():
            try:
                for item in sorted(path.iterdir()):
                    if item.is_dir() and not item.name.startswith('.'):
                        child_rel_path = f"{rel_path}/{item.name}" if rel_path else item.name
                        result["children"].append(build_tree(item, child_rel_path))
            except PermissionError:
                pass  # 忽略无权限的目录

        return result

    # 构建三个根目录的树
    folders = []

    for root_name in ['raw_data', 'results', 'references']:
        root_path = project_dir / root_name
        if root_name == 'references':
            # references 是软链接，检查目标是否存在
            global_ref = Path(settings.UPLOAD_DIR) / "global_references"
            if not global_ref.exists():
                global_ref.mkdir(parents=True, exist_ok=True)
            if not root_path.exists() and not root_path.is_symlink():
                try:
                    os.symlink("../global_references", str(root_path))
                except OSError:
                    pass

        if root_path.exists():
            folders.append(build_tree(root_path, root_name))

    return {
        "status": "success",
        "data": folders
    }