"""
压缩包解析服务 - 支持从 .zip/.tar.gz/.tgz 压缩包中解析技能素材

功能：
1. 解压压缩包到临时目录
2. 识别文件类型并分类
3. 格式化为 AI 可理解的素材文本
"""

import os
import tempfile
import zipfile
import tarfile
import shutil
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from app.core.logger import log


@dataclass
class ParsedFile:
    """解析后的文件信息"""
    relative_path: str
    file_type: str
    content: str
    size: int
    language: Optional[str] = None


@dataclass
class BundleParseResult:
    """压缩包解析结果"""
    success: bool
    files: List[ParsedFile] = field(default_factory=list)
    raw_material: str = ""
    error: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=dict)


# 文件类型映射
FILE_TYPE_MAP = {
    # 脚本文件
    '.py': ('script', 'python'),
    '.r': ('script', 'r'),
    '.R': ('script', 'r'),
    '.sh': ('script', 'bash'),
    '.bash': ('script', 'bash'),
    '.zsh': ('script', 'bash'),

    # Nextflow
    '.nf': ('script', 'nextflow'),

    # 配置文件
    '.yaml': ('config', 'yaml'),
    '.yml': ('config', 'yaml'),
    '.json': ('config', 'json'),
    '.toml': ('config', 'toml'),
    '.ini': ('config', 'ini'),
    '.conf': ('config', 'ini'),

    # 命令记录/日志
    '.txt': ('log', 'text'),
    '.log': ('log', 'text'),
    '.history': ('log', 'text'),

    # 文档
    '.md': ('doc', 'markdown'),

    # 其他代码
    '.js': ('script', 'javascript'),
    '.ts': ('script', 'typescript'),
    '.java': ('script', 'java'),
    '.c': ('script', 'c'),
    '.cpp': ('script', 'cpp'),
    '.go': ('script', 'go'),
}

# 文件优先级（用于排序显示）
TYPE_PRIORITY = {
    'doc': 1,       # 文档最优先
    'config': 2,    # 配置次之
    'script': 3,    # 脚本
    'log': 4,       # 日志/命令记录
    'unknown': 5,   # 未知类型
}


def get_file_type(filename: str) -> tuple:
    """根据文件扩展名获取文件类型"""
    ext = os.path.splitext(filename)[1].lower()
    return FILE_TYPE_MAP.get(ext, ('unknown', 'text'))


def is_text_file(file_path: str) -> bool:
    """检查文件是否为文本文件（避免读取二进制文件）"""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            # 检查是否包含空字节（二进制文件的特征）
            if b'\x00' in chunk:
                return False
            # 尝试解码为 UTF-8
            try:
                chunk.decode('utf-8')
                return True
            except UnicodeDecodeError:
                # 尝试其他常见编码
                for encoding in ['latin-1', 'gbk', 'gb2312']:
                    try:
                        chunk.decode(encoding)
                        return True
                    except UnicodeDecodeError:
                        continue
                return False
    except Exception:
        return False


def read_file_content(file_path: str, max_size: int = 1024 * 1024) -> str:
    """读取文件内容，限制大小"""
    try:
        file_size = os.path.getsize(file_path)
        if file_size > max_size:
            return f"[文件过大，已跳过读取。大小: {file_size / 1024:.1f} KB]"

        # 尝试多种编码
        encodings = ['utf-8', 'latin-1', 'gbk', 'gb2312']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue

        return "[无法解码文件内容]"
    except Exception as e:
        return f"[读取文件失败: {str(e)}]"


def extract_archive(archive_path: str, extract_dir: str) -> bool:
    """解压压缩包"""
    try:
        lower_path = archive_path.lower()

        if lower_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(extract_dir)
            return True

        elif lower_path.endswith('.tar.gz') or lower_path.endswith('.tgz'):
            with tarfile.open(archive_path, 'r:gz') as tf:
                tf.extractall(extract_dir)
            return True

        elif lower_path.endswith('.tar'):
            with tarfile.open(archive_path, 'r') as tf:
                tf.extractall(extract_dir)
            return True

        else:
            log.error(f"不支持的压缩包格式: {archive_path}")
            return False

    except Exception as e:
        log.error(f"解压失败: {e}")
        return False


def parse_upload_bundle(file_path: str) -> BundleParseResult:
    """
    解析上传的压缩包

    Args:
        file_path: 压缩包文件路径

    Returns:
        BundleParseResult: 解析结果
    """
    result = BundleParseResult(success=False)

    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="skill_bundle_")

    try:
        # 1. 解压
        if not extract_archive(file_path, temp_dir):
            result.error = "解压失败，请检查压缩包格式"
            return result

        # 2. 遍历文件
        all_files = []
        for root, dirs, files in os.walk(temp_dir):
            # 跳过隐藏目录和常见忽略目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', '.git', 'venv', 'env']]

            for filename in files:
                # 跳过隐藏文件
                if filename.startswith('.'):
                    continue

                full_path = os.path.join(root, filename)
                relative_path = os.path.relpath(full_path, temp_dir)

                # 获取文件类型
                file_type, language = get_file_type(filename)

                # 跳过大文件
                file_size = os.path.getsize(full_path)
                if file_size > 5 * 1024 * 1024:  # 5MB 限制
                    log.warning(f"跳过大文件: {relative_path} ({file_size / 1024:.1f} KB)")
                    continue

                # 检查是否为文本文件
                if not is_text_file(full_path):
                    log.info(f"跳过二进制文件: {relative_path}")
                    continue

                # 读取内容
                content = read_file_content(full_path)

                parsed_file = ParsedFile(
                    relative_path=relative_path,
                    file_type=file_type,
                    language=language,
                    content=content,
                    size=file_size
                )
                all_files.append(parsed_file)

        if not all_files:
            result.error = "压缩包中没有找到可解析的文本文件"
            return result

        # 3. 按优先级排序
        all_files.sort(key=lambda f: (TYPE_PRIORITY.get(f.file_type, 5), f.relative_path))

        result.files = all_files
        result.success = True

        # 4. 统计信息
        result.stats = {}
        for f in all_files:
            result.stats[f.file_type] = result.stats.get(f.file_type, 0) + 1

        # 5. 格式化为素材文本
        result.raw_material = format_raw_material(all_files)

        log.info(f"成功解析压缩包: {len(all_files)} 个文件, 统计: {result.stats}")

    except Exception as e:
        log.error(f"解析压缩包失败: {e}")
        result.error = str(e)

    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            log.warning(f"清理临时目录失败: {e}")

    return result


def format_raw_material(files: List[ParsedFile]) -> str:
    """
    将解析后的文件格式化为 AI 可理解的素材文本

    Args:
        files: 解析后的文件列表

    Returns:
        格式化后的文本
    """
    sections = []

    # 添加文件概览
    overview = ["# 压缩包内容概览\n"]
    overview.append(f"共包含 {len(files)} 个文本文件：\n")
    for f in files:
        overview.append(f"- `{f.relative_path}` ({f.file_type}, {f.size} bytes)")
    sections.append("\n".join(overview))

    # 按类型分组
    grouped = {}
    for f in files:
        if f.file_type not in grouped:
            grouped[f.file_type] = []
        grouped[f.file_type].append(f)

    # 添加各类型文件内容
    type_names = {
        'doc': '文档文件',
        'config': '配置文件',
        'script': '脚本文件',
        'log': '日志/命令记录',
        'unknown': '其他文件'
    }

    for file_type in ['doc', 'config', 'script', 'log', 'unknown']:
        if file_type not in grouped:
            continue

        type_files = grouped[file_type]
        section = [f"\n---\n# {type_names.get(file_type, file_type)}\n"]

        for f in type_files:
            section.append(f"\n## 文件: {f.relative_path}\n")

            # 添加语言标识
            if f.language:
                section.append(f"语言: {f.language}\n")

            # 添加内容
            section.append("```" + (f.language or '') + "")
            section.append(f.content)
            section.append("```\n")

        sections.append("\n".join(section))

    return "\n".join(sections)


def get_bundle_preview(files: List[ParsedFile]) -> List[Dict[str, Any]]:
    """
    生成文件预览列表（用于前端展示）

    Args:
        files: 解析后的文件列表

    Returns:
        文件预览列表
    """
    preview = []
    for f in files:
        preview.append({
            "path": f.relative_path,
            "type": f.file_type,
            "language": f.language,
            "size": f.size,
            "preview": f.content[:200] + "..." if len(f.content) > 200 else f.content
        })
    return preview