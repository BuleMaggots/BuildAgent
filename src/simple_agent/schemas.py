import datetime
from typing import Literal, Any

from pydantic import BaseModel, Field


WorkflowType =Literal[
    "planner_executor"
]
BuiltinCapability =Literal[
    "filesystem",
    "fs_list",
    "fs_read",
    "fs_write",
]
TraceEventType = Literal[
    "run_started",
    "node_entered",
    "node_exited",
    "route_selected",
    "message_generated",
    "state_updated",
    "run_finished",
]
DEEPSEEK = "deepseek-v4-flash"


def utc_now_iso() -> str:
    return datetime.now(datetime.timezone.utc).isoformat()

class WorkflowDefinition(BaseModel):
    id: str
    name:str = Field(min_length=1, max_length=80)
    type: WorkflowType
    specialist_agent_ids: list[str] = Field(default_factory=list)
    router_prompt: str = Field(default="你是一个工作流路由器,根据用户意图选择最合适的专家。")
    finalizer_enabled: bool = True

class AgentDefinition(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1, max_length=2000)
    model: str | None = DEEPSEEK
    skill_names: list[str] = Field(default_factory=list)
    builtin_capabilities: list[BuiltinCapability] = Field(default_factory=list)

class TraceEvent(BaseModel):
    type: TraceEventType
    title: str
    detail: str
    at: str = Field(default_factory=utc_now_iso)
    payload: dict[str, Any] = Field(default_factory=dict)

class WorkflowNode(BaseModel):
    id: str
    label: str
    kind: Literal["start", "logic", "agent", "final", "end", "group"]
    parent_id: str | None = None


class WorkflowEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class WorkflowGraph(BaseModel):
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]

class RunArtifacts(BaseModel):
    route_agent_id: str | None = None
    route_agent_name: str | None = None
    route_reason: str | None = None
    specialist_answer: str | None = None
    final_answer: str | None = None

class WorkflowRunResponse(BaseModel):
    workflow_id: str
    user_input: str
    assistant_message: str
    artifacts: RunArtifacts
    conversation_id: str | None = None

