"""
Blueprint API 路由 - 提供蓝图执行和固化接口

Blueprint 是 Autonome 3.0 的核心概念，用于表示复杂的 DAG 任务流程。
"""

import json
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session

from app.core.database import get_session, engine
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, Project, SystemConfig


router = APIRouter()


# ==========================================
# Request/Response Models
# ==========================================

class BlueprintExecuteRequest(BaseModel):
    """蓝图执行请求"""
    project_id: str
    blueprint_json: dict  # 蓝图数据
    enable_visual_review: bool = True
    max_review_attempts: int = 2


class BlueprintParseRequest(BaseModel):
    """蓝图解析请求（从 AI 输出中提取）"""
    ai_output: str


# ==========================================
# POST /api/blueprint/execute - 执行蓝图
# ==========================================
@router.post("/execute")
async def execute_blueprint(
    request: BlueprintExecuteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    执行 DAG 蓝图

    接收蓝图 JSON，进行拓扑排序后流式执行各个任务节点。
    支持视觉审稿和打回重绘机制。

    Returns:
        SSE 事件流，包含任务执行状态更新
    """
    # 1. 安全校验：越权检查
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截
    if not current_user.billing or current_user.billing.credits_balance <= 0:
        raise HTTPException(
            status_code=402,
            detail="⚠️ 您的算力余额已耗尽，请充值后继续使用。"
        )

    # 3. 验证蓝图格式
    blueprint_data = request.blueprint_json
    if not blueprint_data.get("is_complex_task"):
        raise HTTPException(status_code=400, detail="蓝图格式错误：缺少 is_complex_task 标记")

    if not blueprint_data.get("tasks"):
        raise HTTPException(status_code=400, detail="蓝图格式错误：缺少任务列表")

    # 4. 获取 LLM 配置
    config = session.get(SystemConfig, 1)

    db_api_key = config.openai_api_key if config else None
    db_base_url = config.openai_base_url if config else None
    db_model = config.default_model if config else None

    env_api_key = os.getenv("OPENAI_API_KEY")

    is_local_model = db_base_url and ("host.docker.internal" in db_base_url or "ollama" in db_base_url or "localhost" in db_base_url)

    if is_local_model:
        api_key = db_api_key if db_api_key is not None else ""
    else:
        api_key = db_api_key if db_api_key and db_api_key != "ollama-local" else env_api_key

    base_url = db_base_url if db_base_url else "https://api.openai.com/v1"
    model_name = db_model if db_model else "gpt-3.5-turbo"

    user_id = current_user.id

    async def event_generator():
        from app.services.orchestrator import BlueprintOrchestrator

        cost_credits = 2.0  # 蓝图执行基础费用

        try:
            log.info(f"🚀 [Blueprint] 开始执行蓝图 - project={request.project_id}, tasks={len(blueprint_data.get('tasks', []))}")

            # 推送开始事件
            yield {
                "event": "blueprint_start",
                "data": json.dumps({
                    "project_goal": blueprint_data.get("project_goal", ""),
                    "total_tasks": len(blueprint_data.get("tasks", []))
                })
            }

            # 创建调度器并执行
            orchestrator = BlueprintOrchestrator(blueprint_data)

            async for event in orchestrator.run_dag_stream(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                project_id=request.project_id,
                session_id="blueprint_exec",  # 临时 session ID
                enable_visual_review=request.enable_visual_review,
                max_review_attempts=request.max_review_attempts
            ):
                # 根据事件类型计算费用
                if event.get("event") == "task_complete":
                    cost_credits += 1.0
                elif event.get("event") == "visual_review_pass":
                    cost_credits += 0.5

                yield event

            log.info(f"✅ [Blueprint] 蓝图执行完成")

        except ValueError as e:
            log.error(f"❌ [Blueprint] DAG 错误: {str(e)}")
            yield {
                "event": "blueprint_error",
                "data": json.dumps({"error": str(e), "type": "dag_error"})
            }

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log.error(f"❌ [Blueprint] 执行错误: {str(e)}\n{error_details}")
            yield {
                "event": "blueprint_error",
                "data": json.dumps({"error": str(e), "type": "execution_error"})
            }

        finally:
            # 扣费
            with Session(engine) as final_db_session:
                db_user = final_db_session.get(User, user_id)
                if db_user and db_user.billing:
                    db_user.billing.credits_balance -= cost_credits
                    if db_user.billing.credits_balance < 0:
                        db_user.billing.credits_balance = 0
                    final_db_session.commit()

                    final_balance = db_user.billing.credits_balance
                    yield {"event": "billing", "data": json.dumps({"cost": cost_credits, "balance": final_balance})}

            yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator())


# ==========================================
# POST /api/blueprint/parse - 从 AI 输出解析蓝图
# ==========================================
@router.post("/parse")
async def parse_blueprint(
    request: BlueprintParseRequest,
    current_user: User = Depends(get_current_user)
):
    """
    从 AI 输出中解析蓝图 JSON

    支持两种格式：
    1. ```json_blueprint ... ```
    2. 直接的 JSON 对象

    Returns:
        解析后的蓝图数据
    """
    from app.services.orchestrator import extract_blueprint

    blueprint = extract_blueprint(request.ai_output)

    if not blueprint:
        return {
            "status": "error",
            "message": "未找到有效的蓝图数据"
        }

    return {
        "status": "success",
        "data": blueprint
    }


# ==========================================
# POST /api/blueprint/validate - 验证蓝图格式
# ==========================================
@router.post("/validate")
async def validate_blueprint(
    request: BlueprintExecuteRequest,
    current_user: User = Depends(get_current_user)
):
    """
    验证蓝图格式和依赖关系

    检查：
    1. 必要字段是否存在
    2. 任务 ID 是否唯一
    3. 依赖关系是否有效
    4. 是否存在循环依赖

    Returns:
        验证结果和拓扑排序后的执行顺序
    """
    from app.services.orchestrator import BlueprintOrchestrator

    blueprint_data = request.blueprint_json

    errors = []
    warnings = []

    # 1. 检查必要字段
    if not blueprint_data.get("project_goal"):
        errors.append("缺少 project_goal 字段")

    if not blueprint_data.get("is_complex_task"):
        warnings.append("is_complex_task 未设置为 true")

    tasks = blueprint_data.get("tasks", [])
    if not tasks:
        errors.append("任务列表为空")

    # 2. 检查任务 ID 唯一性
    task_ids = [t.get("task_id") for t in tasks]
    if len(task_ids) != len(set(task_ids)):
        errors.append("存在重复的任务 ID")

    # 3. 尝试拓扑排序（检查依赖关系）
    execution_order = []
    try:
        orchestrator = BlueprintOrchestrator(blueprint_data)
        execution_order = orchestrator.topological_sort()
    except ValueError as e:
        errors.append(str(e))

    if errors:
        return {
            "status": "error",
            "valid": False,
            "errors": errors,
            "warnings": warnings
        }

    return {
        "status": "success",
        "valid": True,
        "execution_order": execution_order,
        "task_count": len(tasks),
        "warnings": warnings
    }


log.info("📐 Blueprint API 路由已加载")