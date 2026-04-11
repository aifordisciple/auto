"""
深度解读 API

专门用于解读分析结果，生成专业的深度解读报告
"""

import os
import json
from http import HTTPStatus
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_session, engine
from app.models.domain import ChatSession, ChatMessage, Project, User, RoleEnum, SystemConfig
from app.api.deps import get_current_user
from app.core.logger import log


router = APIRouter()


class InterpretRequest(BaseModel):
    """深度解读请求"""
    project_id: str
    session_id: str
    user_message: str  # 用户的原始需求
    code: str  # 执行的代码
    files: list[str]  # 结果文件相对路径列表


@router.post("/interpret")
async def interpret_results(
    request: InterpretRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    深度解读分析结果 - 只返回解读，不生成策略卡片
    """
    # 1. 安全校验
    project = session.get(Project, request.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该项目")

    # 2. 计费拦截（使用 BillingService）
    from app.services.billing_service import BillingService
    billing_service = BillingService(session)
    wallet = billing_service.get_user_wallet(current_user.id)

    if not billing_service.check_available(wallet, min_amount=1.0):
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail="⚠️ 您的算力余额已耗尽，请充值后继续使用。"
        )

    user_id = current_user.id

    # 3. 读取结果文件内容
    project_dir = f"/workspace/project_{request.project_id}"
    file_contents = []

    for rel_path in request.files:
        # 安全检查：防止路径遍历
        if ".." in rel_path:
            continue

        full_path = os.path.join(project_dir, rel_path)
        if not os.path.exists(full_path):
            continue

        ext = os.path.splitext(rel_path)[1].lower()

        # 图片文件：只记录文件名和类型
        if ext in ['.png', '.jpg', '.jpeg', '.svg', '.pdf']:
            file_contents.append(f"\n**图片文件**: `{rel_path}`\n（AI 已生成可视化图表，请查看上方展示）\n")

        # 表格/文本文件：读取内容并截取
        elif ext in ['.csv', '.tsv', '.txt', '.xlsx']:
            try:
                if ext == '.xlsx':
                    file_contents.append(f"\n**Excel文件**: `{rel_path}`\n（二进制格式，已在前端渲染）\n")
                else:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                    # 截取前 30 行
                    max_lines = 30
                    if len(lines) > max_lines:
                        content = ''.join(lines[:max_lines])
                        content += f"\n... (共 {len(lines)} 行，已截取前 {max_lines} 行)"
                    else:
                        content = ''.join(lines)

                    file_contents.append(f"\n**数据文件**: `{rel_path}`\n```\n{content}\n```\n")
            except Exception as e:
                file_contents.append(f"\n**文件**: `{rel_path}`\n（读取失败: {str(e)}）\n")

    # 4. 构造深度解读提示词
    files_info = '\n'.join(file_contents) if file_contents else "（无文件信息）"

    interpret_prompt = f"""## 任务：生成专业深度解读报告

请根据以下生物信息学分析结果，生成一份专业的深度解读报告。

---

### 用户原始需求
{request.user_message}

---

### 执行的代码
```{'python' if 'import pandas' in request.code or 'import numpy' in request.code else 'r'}
{request.code}
```

---

### 生成的结果文件
{files_info}

---

## 报告输出要求

请严格按照以下结构输出专业的深度解读报告，使用美观的 Markdown 格式：

### 📋 报告结构

**1. 主要发现（中文）**
- 用清晰的段落总结核心发现
- 列出关键数据指标

**2. Figure Legend / 图注**
```
【中文图注】
专业的图表描述（适合论文投稿格式）

【English Figure Legend】
Professional figure description in publication-ready format
```

**3. Materials and Methods / 材料与方法**
```
【中文材料方法】
简述分析流程和方法，适合论文方法部分引用

【English Materials and Methods】
Brief description of analysis pipeline for manuscript Methods section
```

**4. 生物学意义**
- 解释结果的生物学含义
- 与已知文献或知识的关联

**5. 临床/研究价值**
- 潜在应用场景
- 对后续研究的启示

**6. 局限性与注意事项**
- 分析方法的局限性
- 结果解读需注意的问题

**7. 下一步分析建议**
- 推荐 2-3 个后续分析方向
- 简要说明每个方向的价值

---

## 格式要求
- 使用适当的标题层级（##, ###）
- 关键术语加粗
- 数据用 `代码格式` 标注
- 列表使用 - 或 1. 2. 3.
- 整体风格专业、清晰、易读
- 中英文部分分开标注"""

    # 5. 获取 LLM 配置
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

    # 6. 流式生成解读结果
    async def event_generator():
        ai_full_response = ""
        cost_credits = 1.0  # 解读任务收费

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)

            log.info(f"🔍 [Interpret] 开始深度解读 - model={model_name}")

            # 专业系统提示，确保输出高质量报告
            stream = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一位资深的生物信息学分析报告撰写专家，具有丰富的学术论文写作经验。

你的专长：
- 撰写高质量的中英文图注（Figure Legend）
- 撰写标准的中英文材料方法（Materials and Methods）
- 进行深入的生物学意义解读
- 提供专业的后续分析建议

**重要规则**：
1. 不要输出任何代码
2. 不要生成策略卡片
3. 只输出纯文本的专业报告
4. 必须包含中英文图注和材料方法
5. 格式美观，适合直接用于学术报告或论文草稿"""
                    },
                    {"role": "user", "content": interpret_prompt}
                ],
                stream=True,
                temperature=0.7,
                max_tokens=4000
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    ai_full_response += content
                    yield {"event": "message", "data": json.dumps({"type": "text", "content": content})}

            log.info(f"✅ [Interpret] 解读完成，共 {len(ai_full_response)} 字符")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log.error(f"❌ [Interpret] 错误: {str(e)}\n{error_details}")
            err_msg = f"\n\n❌ **解读服务异常**: {str(e)}"
            ai_full_response += err_msg
            yield {"event": "message", "data": json.dumps({"type": "text", "content": err_msg})}

        finally:
            # 保存消息到数据库
            with Session(engine) as final_db_session:
                # 保存用户消息（简要提示）
                user_msg = ChatMessage(
                    session_id=request.session_id,
                    role=RoleEnum.user,
                    content="🧬 深度解读分析结果"
                )
                final_db_session.add(user_msg)

                # 保存 AI 解读结果
                ai_msg = ChatMessage(
                    session_id=request.session_id,
                    role=RoleEnum.assistant,
                    content=ai_full_response
                )
                final_db_session.add(ai_msg)

                # 扣费（使用 BillingService）
                db_user = final_db_session.get(User, user_id)
                if db_user:
                    try:
                        from app.services.billing_service import BillingService
                        bs = BillingService(final_db_session)
                        bs.deduct_credits(
                            wallet_id=wallet.wallet_id,
                            amount=cost_credits,
                            transaction_type="consume_chat",
                            description=f"深度解读消费",
                        )
                        final_db_session.refresh(wallet)
                        final_balance = wallet.credits_balance
                    except Exception as e:
                        log.warning(f"扣费失败: {e}")
                        if db_user.billing:
                            db_user.billing.credits_balance -= cost_credits
                            if db_user.billing.credits_balance < 0:
                                db_user.billing.credits_balance = 0
                        final_balance = db_user.billing.credits_balance if db_user.billing else 0
                else:
                    final_balance = 0

                final_db_session.commit()

                # 发送 AI 消息的真实 ID 给前端
                yield {"event": "ai_message_id", "data": json.dumps({"message_id": ai_msg.id})}

                yield {"event": "billing", "data": json.dumps({"cost": cost_credits, "balance": final_balance})}

            yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator())