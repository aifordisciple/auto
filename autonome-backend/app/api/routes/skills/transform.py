"""
技能转化 API

包含从 Live Coding 会话转化技能的接口
"""

import json
import re
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.core.content_filter import preprocess_llm_response
from app.api.deps import get_current_user
from app.models.domain import User, SystemConfig, RoleEnum
from app.schemas.skill import TransformFromLiveRequest

router = APIRouter()


def extract_code_blocks(content: str) -> List[Dict[str, str]]:
    """
    从消息内容中提取代码块

    Returns:
        [{"language": "python", "code": "..."}, ...]
    """
    # 预处理：过滤 thinking 标签
    content = preprocess_llm_response(content)

    code_blocks = []

    # 匹配 ```python 或 ```r 代码块
    pattern = r'```(python|r)\s*\n(.*?)\n```'
    matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

    for lang, code in matches:
        code_blocks.append({
            "language": lang.lower(),
            "code": code.strip()
        })

    return code_blocks


def extract_strategy_blocks(content: str) -> List[Dict[str, Any]]:
    """
    从消息内容中提取策略卡片

    Returns:
        [{"title": "...", "tool_id": "...", "parameters": {...}}, ...]
    """
    # 预处理：过滤 thinking 标签
    content = preprocess_llm_response(content)

    strategies = []

    # 匹配 ```json_strategy 代码块
    pattern = r'```json_strategy\s*\n(.*?)\n```'
    matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

    for json_str in matches:
        try:
            strategy = json.loads(json_str.strip())
            strategies.append(strategy)
        except json.JSONDecodeError:
            continue

    return strategies


def detect_executor_type(code_blocks: List[Dict[str, str]]) -> str:
    """
    根据代码块检测执行器类型
    """
    if not code_blocks:
        return "Python_env"

    # 统计语言类型
    languages = [block["language"] for block in code_blocks]
    r_count = languages.count("r")
    python_count = languages.count("python")

    if r_count > python_count:
        return "R_env"
    else:
        return "Python_env"


def build_raw_material_from_session(
    messages: List[Any],
    code_blocks: List[Dict[str, str]],
    strategies: List[Dict[str, Any]]
) -> str:
    """
    构建用于锻造的原始素材
    """
    material_parts = []

    # 添加用户需求描述
    user_messages = [m for m in messages if hasattr(m, 'role') and m.role == RoleEnum.user]
    if user_messages:
        material_parts.append("【用户需求】")
        for msg in user_messages[-3:]:  # 最近3条用户消息
            if msg.content:
                material_parts.append(f"- {msg.content[:500]}")
        material_parts.append("")

    # 添加代码
    if code_blocks:
        material_parts.append("【分析代码】")
        for i, block in enumerate(code_blocks[-3:], 1):  # 最近3个代码块
            material_parts.append(f"### 代码片段 {i} ({block['language']})")
            material_parts.append(block["code"])
            material_parts.append("")

    # 添加策略信息
    if strategies:
        material_parts.append("【执行策略】")
        for strategy in strategies[-2:]:  # 最近2个策略
            material_parts.append(f"- 标题: {strategy.get('title', '未知')}")
            material_parts.append(f"- 描述: {strategy.get('description', '未知')}")
            if strategy.get('parameters'):
                material_parts.append(f"- 参数: {json.dumps(strategy['parameters'], ensure_ascii=False)}")
            material_parts.append("")

    return "\n".join(material_parts)


# ==========================================
# POST /api/skills/transform_from_live - 从聊天会话转化技能
# ==========================================
@router.post("/transform_from_live")
async def transform_from_live(
    req: TransformFromLiveRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    从成功的聊天会话转化为技能

    流程：
    1. 获取会话历史消息
    2. 提取代码块和策略卡片
    3. 调用 Crafter Agent 生成技能草稿
    4. 可选保存为 SkillAsset (DRAFT 状态)
    5. 返回生成的技能草稿供预览

    Args:
        req: 包含 session_id, skill_name(可选), auto_save

    Returns:
        生成的技能草稿信息
    """
    from app.agent.crafter import craft_skill_from_material
    from app.models.domain import generate_skill_id, ChatMessage

    log.info(f"🔄 [Skills API] 用户 {current_user.id} 请求从会话转化技能: {req.session_id}")

    # 1. 获取会话消息
    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == req.session_id)
        .order_by(ChatMessage.created_at)
    ).all()

    if not messages:
        raise HTTPException(status_code=404, detail="会话不存在或无消息")

    # 2. 提取所有 AI 消息中的代码和策略
    all_code_blocks = []
    all_strategies = []

    for msg in messages:
        if hasattr(msg, 'role') and msg.role == RoleEnum.assistant:
            # 提取代码块
            code_blocks = extract_code_blocks(msg.content or "")
            all_code_blocks.extend(code_blocks)

            # 提取策略卡片
            strategies = extract_strategy_blocks(msg.content or "")
            all_strategies.extend(strategies)

    if not all_code_blocks and not all_strategies:
        raise HTTPException(status_code=400, detail="未找到可转化的代码或策略")

    # 3. 检测执行器类型
    executor_type = detect_executor_type(all_code_blocks)

    # 4. 构建原始素材
    raw_material = build_raw_material_from_session(messages, all_code_blocks, all_strategies)

    # 5. 获取 LLM 配置
    config = session.get(SystemConfig, 1)
    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    import os
    env_api_key = os.getenv("OPENAI_API_KEY")
    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    api_key = (db_api_key if db_api_key is not None else "") if is_local_model else (db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key)
    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    # 6. 调用 Crafter Agent
    try:
        crafted_result = await craft_skill_from_material(
            raw_material=raw_material,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            executor_type=executor_type
        )

        # 7. 使用自定义名称（如果有）
        if req.skill_name:
            crafted_result["name"] = req.skill_name

        # 8. 可选：自动保存为草稿
        if req.auto_save:
            from app.models.domain import SkillAsset, SkillStatus

            skill_id = generate_skill_id()

            skill = SkillAsset(
                skill_id=skill_id,
                name=crafted_result.get("name", "未命名技能"),
                description=crafted_result.get("description", ""),
                version="1.0.0",
                executor_type=executor_type,
                parameters_schema=crafted_result.get("parameters_schema", {}),
                expert_knowledge=crafted_result.get("expert_knowledge", ""),
                script_code=crafted_result.get("script_code", ""),
                owner_id=current_user.id,
                status=SkillStatus.DRAFT
            )

            session.add(skill)
            session.commit()
            session.refresh(skill)

            log.info(f"✅ [Skills API] 已保存技能草稿: {skill_id}")

            crafted_result["skill_id"] = skill_id
            crafted_result["saved"] = True

        return {
            "status": "success",
            "data": crafted_result,
            "source_info": {
                "session_id": req.session_id,
                "code_blocks_count": len(all_code_blocks),
                "strategies_count": len(all_strategies),
                "executor_type": executor_type
            }
        }

    except Exception as e:
        log.error(f"从会话转化技能失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# POST /api/skills/consolidate - 蓝图固化接口
# ==========================================
@router.post("/consolidate")
async def consolidate_blueprint(
    project_id: str,
    blueprint_json: str,
    skill_name: str = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    【知识固化】将蓝图 JSON 转化为 SKILL

    Args:
        project_id: 项目 ID
        blueprint_json: 蓝图 JSON 字符串
        skill_name: 可选的技能名称

    Returns:
        生成的技能信息
    """
    try:
        # 解析蓝图 JSON
        blueprint = json.loads(blueprint_json)

        # 构建原始素材
        raw_material = f"【蓝图数据】\n{json.dumps(blueprint, ensure_ascii=False, indent=2)}"

        # 获取 LLM 配置
        config = session.get(SystemConfig, 1)
        db_api_key = config.openai_api_key if config else None
        db_base_url = config.openai_base_url if config else None
        db_model = config.default_model if config else None

        import os
        env_api_key = os.getenv("OPENAI_API_KEY")
        is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

        api_key = (db_api_key if db_api_key is not None else "") if is_local_model else (db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key)
        base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
        model_name = db_model if db_model else "gpt-3.5-turbo"

        # 调用 Crafter Agent
        from app.agent.crafter import craft_skill_from_material

        crafted_result = await craft_skill_from_material(
            raw_material=raw_material,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            executor_type="Logical_Blueprint"
        )

        if skill_name:
            crafted_result["name"] = skill_name

        return {
            "status": "success",
            "data": crafted_result
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="蓝图 JSON 格式错误")
    except Exception as e:
        log.error(f"蓝图固化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# GET /api/skills/bundle/{bundle_name}/scripts - 获取脚本内容
# ==========================================
@router.get("/bundle/{bundle_name}/scripts")
def get_bundle_scripts(
    bundle_name: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取指定 Bundle 的脚本内容

    Args:
        bundle_name: 技能包名称

    Returns:
        脚本文件内容列表
    """
    import os

    bundle_path = f"/app/skills/{bundle_name}"
    scripts_dir = os.path.join(bundle_path, "scripts")

    if not os.path.exists(scripts_dir):
        return {"status": "error", "message": "脚本目录不存在", "scripts": []}

    scripts = []
    for f in os.listdir(scripts_dir):
        if f.endswith('.py') or f.endswith('.r') or f.endswith('.R'):
            file_path = os.path.join(scripts_dir, f)
            try:
                with open(file_path, 'r', encoding='utf-8') as fp:
                    content = fp.read()
                scripts.append({
                    "filename": f,
                    "path": file_path,
                    "content": content,
                    "language": "python" if f.endswith('.py') else "r"
                })
            except Exception as e:
                log.warning(f"无法读取脚本文件 {f}: {e}")

    return {
        "status": "success",
        "bundle_name": bundle_name,
        "scripts": scripts
    }