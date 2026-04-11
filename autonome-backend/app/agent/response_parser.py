"""
Claude Code CLI 输出解析器

从 Claude Code 的 stream-json 输出中提取：
- 文本内容
- 代码块
- json_strategy 策略卡片
- json_blueprint 蓝图
- session_id（用于会话恢复）

设计理念：
- 支持流式输出解析
- 多重解析策略（正则后备）
- 结构化事件提取
"""

import re
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logger import log


# ==========================================
# 数据类定义
# ==========================================

@dataclass
class ParsedResponse:
    """解析后的响应结构"""
    # 文本内容（解释、分析等）
    text_content: str = ""

    # 代码块列表 [{language: str, code: str}]
    code_blocks: List[Dict[str, str]] = field(default_factory=list)

    # 策略卡片
    strategy_card: Optional[Dict[str, Any]] = None

    # 蓝图
    blueprint: Optional[Dict[str, Any]] = None

    # 意图识别结果
    intent: Optional[Dict[str, Any]] = None

    # 会话信息（用于恢复）
    session_id: Optional[str] = None

    # 执行战报
    battle_report: Optional[Dict[str, Any]] = None

    # 文件操作记录
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_read: List[str] = field(default_factory=list)

    # 工具调用记录
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # 原始输出预览
    raw_output_preview: str = ""


# ==========================================
# 正则表达式模式
# ==========================================

# 代码块模式
CODE_BLOCK_PATTERN = re.compile(r'```(\w+)?\s*\n(.*?)```', re.DOTALL)

# 特殊 JSON 块模式
JSON_STRATEGY_PATTERN = re.compile(r'```json_strategy\s*\n(.*?)\n```', re.DOTALL)
JSON_BLUEPRINT_PATTERN = re.compile(r'```json_blueprint\s*\n(.*?)\n```', re.DOTALL)
JSON_INTENT_PATTERN = re.compile(r'```json_intent\s*\n(.*?)\n```', re.DOTALL)

# 策略卡片 JSON 模式（不带代码块标记）
STRATEGY_JSON_PATTERN = re.compile(
    r'\{\s*"title"\s*:\s*"[^"]+"\s*,\s*"tool_id"\s*:\s*"[^"]+"[^}]*\}',
    re.DOTALL
)


# ==========================================
# 解析器类
# ==========================================

class ClaudeResponseParser:
    """
    Claude Code CLI 输出解析器

    解析流程：
    1. 尝试解析 stream-json 格式
    2. 从事件中提取结构化信息
    3. 后备：使用正则表达式解析普通文本
    """

    def parse(self, raw_output: str) -> ParsedResponse:
        """
        解析 Claude CLI 输出

        Args:
            raw_output: Claude CLI 的完整输出（stream-json 格式或普通文本）

        Returns:
            ParsedResponse 解析结果
        """
        result = ParsedResponse()

        if not raw_output:
            return result

        # 保存原始输出预览
        result.raw_output_preview = raw_output[:2000] if len(raw_output) > 2000 else raw_output

        # 尝试解析 stream-json 格式
        stream_events = self._parse_stream_json(raw_output)

        if stream_events:
            self._parse_from_stream_events(stream_events, result)
        else:
            # 后备：使用正则表达式解析
            self._parse_with_regex(raw_output, result)

        return result

    def _parse_stream_json(self, output: str) -> List[Dict[str, Any]]:
        """解析 stream-json 格式的输出"""
        events = []
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                continue
        return events

    def _parse_from_stream_events(self, events: List[Dict[str, Any]], result: ParsedResponse):
        """
        从 stream-json 事件中提取信息

        事件类型：
        - system (init): 会话初始化信息，包含 session_id
        - assistant: 助手消息（思考过程）
        - tool_use: 工具调用
        - tool_result: 工具执行结果
        - result: 最终结果
        """
        assistant_messages = []
        result_content = None

        for event in events:
            event_type = event.get("type", "")

            # 会话初始化 - 提取 session_id
            if event_type == "system" and event.get("subtype") == "init":
                result.session_id = event.get("session_id")
                log.debug(f"[Parser] 提取 session_id: {result.session_id}")

            # 助手消息
            elif event_type == "assistant":
                message = event.get("message", {})
                content_blocks = message.get("content", [])
                for block in content_blocks:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        assistant_messages.append(text)

                        # 从文本中提取策略卡片
                        self._extract_special_blocks(text, result)

            # 工具使用
            elif event_type == "tool_use":
                tool_name = event.get("name", "")
                tool_input = event.get("input", {})
                result.tool_calls.append({
                    "name": tool_name,
                    "input": tool_input
                })

                # 提取文件操作
                if tool_name == "Write":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        result.files_created.append(file_path)
                elif tool_name == "Edit":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        result.files_modified.append(file_path)
                elif tool_name == "Read":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        result.files_read.append(file_path)

            # 最终结果
            elif event_type == "result":
                result_content = event.get("result", "")
                assistant_messages.append(result_content)

        # 合并助手消息
        if assistant_messages:
            result.text_content = "\n\n".join(assistant_messages)

        # 生成战报
        result.battle_report = {
            "success": True,
            "files_created": list(set(result.files_created)),
            "files_modified": list(set(result.files_modified)),
            "files_read": list(set(result.files_read)),
            "tool_calls": result.tool_calls,
            "summary": result.text_content[:500] if result.text_content else ""
        }

    def _parse_with_regex(self, output: str, result: ParsedResponse):
        """
        使用正则表达式解析非 stream-json 输出

        这是后备解析策略，用于处理：
        - 非 stream-json 格式的输出
        - 解析失败的情况
        """
        # 提取文本内容
        result.text_content = output

        # 提取代码块
        code_matches = CODE_BLOCK_PATTERN.findall(output)
        for lang, code in code_matches:
            if lang and lang.lower() not in ["json_strategy", "json_blueprint", "json_intent"]:
                result.code_blocks.append({
                    "language": lang or "text",
                    "code": code.strip()
                })

        # 提取特殊 JSON 块
        self._extract_special_blocks(output, result)

        # 生成战报
        result.battle_report = {
            "success": True,
            "files_created": result.files_created,
            "files_modified": result.files_modified,
            "summary": output[:500] if output else ""
        }

    def _extract_special_blocks(self, text: str, result: ParsedResponse):
        """
        从文本中提取特殊 JSON 块

        包括：json_strategy, json_blueprint, json_intent
        """
        # 提取 json_strategy
        if not result.strategy_card:
            match = JSON_STRATEGY_PATTERN.search(text)
            if match:
                try:
                    result.strategy_card = json.loads(match.group(1))
                    log.debug(f"[Parser] 提取 json_strategy: {result.strategy_card.get('title', 'N/A')}")
                except json.JSONDecodeError as e:
                    log.warning(f"[Parser] json_strategy 解析失败: {e}")

        # 提取 json_blueprint
        if not result.blueprint:
            match = JSON_BLUEPRINT_PATTERN.search(text)
            if match:
                try:
                    result.blueprint = json.loads(match.group(1))
                    log.debug(f"[Parser] 提取 json_blueprint")
                except json.JSONDecodeError as e:
                    log.warning(f"[Parser] json_blueprint 解析失败: {e}")

        # 提取 json_intent
        if not result.intent:
            match = JSON_INTENT_PATTERN.search(text)
            if match:
                try:
                    result.intent = json.loads(match.group(1))
                    log.debug(f"[Parser] 提取 json_intent")
                except json.JSONDecodeError as e:
                    log.warning(f"[Parser] json_intent 解析失败: {e}")

    def extract_strategy_card(self, content: str) -> Optional[Dict[str, Any]]:
        """
        仅提取策略卡片（便捷方法）

        Args:
            content: 文本内容

        Returns:
            策略卡片字典或 None
        """
        match = JSON_STRATEGY_PATTERN.search(content)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试匹配裸 JSON
        match = STRATEGY_JSON_PATTERN.search(content)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def extract_blueprint(self, content: str) -> Optional[Dict[str, Any]]:
        """
        仅提取蓝图（便捷方法）

        Args:
            content: 文本内容

        Returns:
            蓝图字典或 None
        """
        match = JSON_BLUEPRINT_PATTERN.search(content)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def extract_session_id(self, raw_output: str) -> Optional[str]:
        """
        仅提取 session_id（便捷方法）

        Args:
            raw_output: 原始输出

        Returns:
            session_id 或 None
        """
        events = self._parse_stream_json(raw_output)
        for event in events:
            if event.get("type") == "system" and event.get("subtype") == "init":
                return event.get("session_id")
        return None


# 全局单例
claude_response_parser = ClaudeResponseParser()