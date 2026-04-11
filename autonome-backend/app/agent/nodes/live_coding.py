"""
兜底编码节点 (Live Coding Node)

当没有匹配到任何 SKILL 时，由这个节点处理编码请求。
专注于生成高质量代码，附带 json_strategy 策略卡片。
"""

import json
from typing import Optional
from app.core.logger import log


# 编码标准常量
CODING_STANDARDS = """
【代码编写强制规范】
1. **强制参数化**：所有代码必须包含 argparse (Python) 或 optparse (R)
2. **强制注释**：每个函数必须有程序说明，关键步骤有行内注释
3. **强制错误处理**：关键操作必须有 try-except 或 tryCatch
4. **强制路径规范**：
   - 读：原始数据使用 `/workspace/project_{project_id}/raw_data/文件名`
   - 写：必须存入 `TASK_OUT_DIR` 环境变量目录
5. **强制表格格式**：表格数据优先使用 `sep='\\t'` 输出 TSV
6. **出版级图形规范**：
   - 纯英文标签（禁止中文）
   - 300 DPI 或 600 DPI
   - 色盲友好配色 (viridis, ColorBrewer)
   - 必须同时输出 PDF 和 PNG
"""


def build_live_coding_prompt(
    user_message: str,
    project_id: int,
    relevant_skills_md: str = ""
) -> str:
    """
    构建 Live Coding 提示

    Args:
        user_message: 用户消息
        project_id: 项目 ID
        relevant_skills_md: 相关的 Skill 目录（可选）

    Returns:
        格式化的提示字符串
    """
    skills_section = f"\n【相关 SKILL 参考】\n{relevant_skills_md}\n" if relevant_skills_md else ""

    return f"""你是 Autonome 生信分析专家，精通 Python 和 R。

【用户请求】
{user_message}

【项目信息】
当前项目 ID: {project_id}
数据目录: `/workspace/project_{project_id}/raw_data/`
输出目录: `TASK_OUT_DIR` 环境变量（默认 `/workspace/project_{project_id}/results/default_task`）
{skills_section}

{CODING_STANDARDS}

【输出格式】
1. 先用自然语言简要说明分析思路
2. 输出代码块（```python 或 ```r）
3. 输出 json_strategy 策略卡片

```json_strategy
{{
  "title": "任务名称",
  "description": "简要描述",
  "task_summary": "任务总结",
  "tool_id": "execute-python" 或 "execute-r",
  "parameters": {{"参数名": "参数值"}},
  "steps": ["步骤1", "步骤2"],
  "estimated_time": "约 X 分钟"
}}
```
"""


def build_interactive_mode_prompt(
    user_message: str,
    project_id: int
) -> str:
    """
    构建交互式可视化模式提示

    Args:
        user_message: 用户消息
        project_id: 项目 ID

    Returns:
        格式化的提示字符串
    """
    return f"""你是生信可视化专家。

【用户请求】
{user_message}

【项目信息】
当前项目 ID: {project_id}
数据目录: `/workspace/project_{project_id}/raw_data/`

【交互式可视化模式】
1. 输出数据处理代码（Python/R）
2. 代码必须：
   - 保存结果到 `results.tsv`
   - 输出列名信息供图表配置使用
3. 不输出 json_interactive_plot（由系统自动生成）

【数据处理代码模板】
```python
import os
import pandas as pd

out_dir = os.environ.get('TASK_OUT_DIR', '/workspace/project_{project_id}/results/default_task')
os.makedirs(out_dir, exist_ok=True)

df = pd.read_csv('数据路径', sep='\\t')
# 处理逻辑...

result_df.to_csv(f'{{out_dir}}/results.tsv', sep='\\t', index=False)
print(f'列名: {{list(result_df.columns)}}')
print(f'结果已保存到 {{out_dir}}/results.tsv')
```

【策略卡片输出】
```json_strategy
{{
  "title": "数据处理任务",
  "description": "处理数据并生成可视化",
  "tool_id": "execute-python",
  "task_mode": "interactive_visualization",
  "visualization_config": {{
    "plot_type": "bar",
    "title": "图表标题",
    "data_source": "results.tsv",
    "parameters": {{}},
    "export_formats": ["pdf", "png_300dpi", "tsv"]
  }},
  "parameters": {{"code": "上述代码"}},
  "steps": ["处理数据", "生成图表"],
  "estimated_time": "约 1 分钟"
}}
```
"""


async def handle_live_coding(
    user_message: str,
    project_id: int,
    llm=None,
    task_mode: Optional[str] = None,
    relevant_skills_md: str = ""
) -> dict:
    """
    处理 Live Coding 请求

    Args:
        user_message: 用户消息
        project_id: 项目 ID
        llm: LLM 实例
        task_mode: 任务模式（None, 'interactive'）
        relevant_skills_md: 相关的 Skill 目录

    Returns:
        包含 code 和 strategy_card 的字典
    """
    log.info(f"🛠️ [LiveCoding] 处理请求: {user_message[:50]}...")

    if llm is None:
        return {
            "code": "# 请提供有效的 LLM 配置",
            "strategy_card": {
                "title": "编码任务",
                "description": "无法生成代码",
                "tool_id": "execute-python",
                "parameters": {},
                "steps": ["错误"],
                "estimated_time": "约 1 分钟"
            }
        }

    # 根据模式选择提示
    if task_mode == "interactive":
        prompt = build_interactive_mode_prompt(user_message, project_id)
    else:
        prompt = build_live_coding_prompt(user_message, project_id, relevant_skills_md)

    try:
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # 解析代码
        code = ""
        strategy_card = None

        import re
        code_blocks = re.findall(r'```(?:python|r)\s*\n(.*?)```', content, re.DOTALL)
        if code_blocks:
            code = code_blocks[0].strip()

        json_blocks = re.findall(r'```json_strategy\s*\n(.*?)```', content, re.DOTALL)
        if json_blocks:
            try:
                strategy_card = json.loads(json_blocks[0])
            except json.JSONDecodeError:
                pass

        if not strategy_card:
            strategy_card = {
                "title": "数据处理任务",
                "description": "处理数据",
                "tool_id": "execute-python",
                "parameters": {},
                "steps": ["处理数据"],
                "estimated_time": "约 1 分钟"
            }

        return {
            "code": code,
            "strategy_card": strategy_card
        }

    except Exception as e:
        log.error(f"❌ [LiveCoding] 生成失败: {e}")
        return {
            "code": f"# 错误: {e}",
            "strategy_card": {
                "title": "编码任务",
                "description": f"错误: {e}",
                "tool_id": "execute-python",
                "parameters": {},
                "steps": ["错误"],
                "estimated_time": "约 1 分钟"
            }
        }


log.info("🛠️ [LiveCoding] 兜底编码节点已加载")
