"""
Agent Nodes - 专业节点目录

V2 架构：各节点职责分离，由 Router 统一路由
"""

# 路由节点
from app.agent.nodes.router import router_node, get_intent_routing_edges, RouterState

# 闲聊节点
from app.agent.nodes.chat import chat_node

# 专业节点（V2 架构）
from app.agent.nodes.retrieval import retrieval_node
from app.agent.nodes.troubleshooting import troubleshooting_node
from app.agent.nodes.system_action import system_action_node
from app.agent.nodes.blueprint import blueprint_node
from app.agent.nodes.param_update import param_update_node
from app.agent.nodes.skill_form_builder import skill_form_builder_node

# SKILL 相关
from app.agent.nodes.skill_execute import skill_execute_node, handle_skill_execute

# 沙箱规划
from app.agent.nodes.sandbox_planner import sandbox_planner_node

__all__ = [
    # 路由
    "router_node",
    "get_intent_routing_edges",
    "RouterState",
    # 闲聊
    "chat_node",
    # 专业节点
    "retrieval_node",
    "troubleshooting_node",
    "system_action_node",
    "blueprint_node",
    "param_update_node",
    "skill_form_builder_node",
    "skill_execute_node",
    "sandbox_planner_node",
    # SKILL
    "handle_skill_execute",
]
