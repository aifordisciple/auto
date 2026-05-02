"""Claude 数据模型单元测试"""
import pytest
import uuid
from app.models.claude import ClaudeSession, ClaudeContainer, ClaudeTask
from app.sandbox.agent_service.event_types import (
    PlanEvent, ThinkingEvent, ToolUseEvent, ErrorEvent, UsageEvent
)


VALID_UUID = uuid.uuid4()


class TestClaudeSession:
    def test_create_session_defaults(self):
        """ClaudeSession 默认值验证"""
        session = ClaudeSession(user_id=1)
        assert session.title == "新会话"
        assert session.status == "active"
        assert session.user_id == 1

    def test_session_status_values(self):
        """ClaudeSession 状态字段接受合法值"""
        session = ClaudeSession(user_id=1, status="archived")
        assert session.status == "archived"
        session.status = "closed"
        assert session.status == "closed"


class TestClaudeContainer:
    def test_container_status_values(self):
        """ClaudeContainer 状态值验证"""
        container = ClaudeContainer(
            container_id="abc123",
            status="idle",
        )
        assert container.status == "idle"
        assert container.user_id is None
        assert container.session_id is None

    def test_container_with_user(self):
        """带用户的容器状态验证"""
        container = ClaudeContainer(
            container_id="abc123",
            status="busy",
            user_id=1,
            session_id=VALID_UUID,
        )
        assert container.status == "busy"
        assert container.user_id == 1
        assert container.session_id == VALID_UUID


class TestClaudeTask:
    def test_task_status_lifecycle(self):
        """ClaudeTask 状态机验证"""
        task = ClaudeTask(status="pending")
        assert task.status == "pending"

        task.status = "running"
        assert task.status == "running"

        task.status = "completed"
        assert task.status == "completed"

    def test_task_with_output_files(self):
        """ClaudeTask 输出文件 JSONB 验证"""
        task = ClaudeTask(
            status="completed",
            output_files=[
                {"name": "result.csv", "path": "/workspace/result.csv", "size": 1024},
            ],
        )
        assert len(task.output_files) == 1
        assert task.output_files[0]["name"] == "result.csv"

    def test_task_without_message_id(self):
        """ClaudeTask 允许不关联 message（修复 NOT NULL constraint）"""
        task = ClaudeTask(
            skill_id="test_skill",
            status="pending",
        )
        assert task.message_id is None
        assert task.session_id is None
        assert task.status == "pending"


class TestEventTypes:
    def test_plan_data_serialization_camelcase(self):
        """PlanEvent.to_json() 输出字段为 camelCase"""
        event = PlanEvent(
            title="QC分析",
            steps=[{"title": "步骤1", "description": "质量检查"}],
            codeSnapshot="fastqc input.fastq",
            estimatedCost="5min",
        )
        json_str = event.to_json()
        assert "codeSnapshot" in json_str
        assert "estimatedCost" in json_str
        assert "code_snapshot" not in json_str
        assert "estimated_cost" not in json_str

    def test_usage_event_serialization(self):
        """UsageEvent 序列化验证"""
        event = UsageEvent(input_tokens=100, output_tokens=200)
        json_str = event.to_json()
        assert "usage" in json_str

    def test_all_event_types_to_json_no_exception(self):
        """所有事件类型 to_json() 不抛异常"""
        events = [
            PlanEvent(title="test", steps=[], codeSnapshot="", estimatedCost=""),
            ThinkingEvent(content="test"),
            ToolUseEvent(tool_name="test", tool_input={}, tool_use_id="test"),
            ErrorEvent(message="test", code="TEST"),
            UsageEvent(input_tokens=0, output_tokens=0),
        ]
        for event in events:
            result = event.to_json()
            assert isinstance(result, str)
            assert len(result) > 0
