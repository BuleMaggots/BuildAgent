from collections.abc import Callable
from typing import TypedDict

from langgraph.constants import START, END

from llm import call_llm, run_agent
from simple_agent.prompts import fallback_plan_tasks, build_router_prompt, fallback_route_keyword, \
    build_finalize_prompt, build_fallback_response
from store import Store
from schemas import WorkflowDefinition, AgentDefinition, WorkflowRunResponse, RunArtifacts
from langgraph.graph import StateGraph
from prompts import build_plan_tasks_prompt

PLANNER_NODE = "planner_core"
VALIDATOR_NODE = "planner_validator"
DISPATCHER_NODE = "task_dispatcher"
SYNTH_NODE = "synthesizer"

#工作流状态类
class PlannerState(TypedDict, total=False):
    user_input: str     #用户输入
    tasks: list[str]    #任务
    plan_source: str    #任务来源
    planning_round: int #规划轮数
    replan_required: bool#是否需要重新规划
    task_index: int     #当前任务索引
    current_task: str   #当前任务
    current_worker_id: str  #当前执行者id
    current_worker_name: str#当前执行者名称
    current_route_reason: str#执行原因
    task_reports: list[str] #任务报告
    combined_report: str    #整体报告
    ai_message: str     #AI消息




#搭建工作流
def _compile_planner_app(
        workflow: WorkflowDefinition,
        workers: list[AgentDefinition],
        planner_node: Callable[[PlannerState], PlannerState],
        validator_node: Callable[[PlannerState], PlannerState],
        dispatcher_node: Callable[[PlannerState], PlannerState],
        make_worker_node: Callable[[AgentDefinition], Callable[[PlannerState], PlannerState]],
        validator_next: Callable[[PlannerState], str],
        dispatch_next: Callable[[PlannerState], str],
        worker_next: Callable[[PlannerState], str],
        synth_node: Callable[[PlannerState], PlannerState] | None = None
):
    builder = StateGraph(PlannerState)
    builder.add_node(PLANNER_NODE, planner_node)
    builder.add_node(VALIDATOR_NODE, validator_node)
    builder.add_node(DISPATCHER_NODE, dispatcher_node)
    for worker in workers:
        builder.add_node(worker.id, make_worker_node(worker))
    if workflow.finalizer_enabled and synth_node is not None:
        builder.add_node(SYNTH_NODE, synth_node)

    builder.add_edge(START,PLANNER_NODE)
    builder.add_edge(PLANNER_NODE, VALIDATOR_NODE)
    builder.add_conditional_edges(
        VALIDATOR_NODE,
        validator_next,
        {
            PLANNER_NODE: PLANNER_NODE,
            DISPATCHER_NODE: DISPATCHER_NODE
        },
    )
    dispatch_targets = {worker.id: worker.id for worker in workers}
    if workflow.finalizer_enabled and synth_node is not None:
        dispatch_targets[SYNTH_NODE] = SYNTH_NODE
    else:
        dispatch_targets[END] = END
    builder.add_conditional_edges(DISPATCHER_NODE,dispatch_next,dispatch_targets)
    for worker in workers:
        builder.add_conditional_edges(worker.id,worker_next,{DISPATCHER_NODE: DISPATCHER_NODE})
    if workflow.finalizer_enabled and synth_node is not None:
        builder.add_edge(SYNTH_NODE, END)
    return builder.compile()



def _fallback_split_for_replan(user_input: str) -> list[str]:
    raw = user_input.strip()
    if len(raw) <= 36:
        return [raw]
    midpoint = len(raw) // 2
    return [raw[:midpoint].strip(), raw[midpoint:].strip()]

def _needs_replan(user_input: str, tasks: list[str]) -> bool:
    if len(tasks) >= 2:
        return False
    lowered = user_input.lower()
    multi_hints = (
        " and ",
        " also ",
        " then ",
        "同时",
        "另外",
        "并且",
        "然后",
        "接着",
        "最后",
    )
    return any(hint in lowered for hint in multi_hints) or len(user_input.strip()) > 120

def run_planner_executor(
        store: Store,
        workflow: WorkflowDefinition,
        user_input: str,
) -> WorkflowRunResponse:
    workers: list[AgentDefinition] = []
    for agent_id in workflow.specialist_agent_ids:
        agent = store.get_agent(store.id_get_agent(agent_id))
        if agent is not None:
            workers.append(agent)
    if len(workers) < 2:
        raise ValueError("At least two workers are required")
    worker_by_id = {worker.id: worker for worker in workers}

    def planner_node(state: PlannerState) -> PlannerState:
        print("="*10,"Planner_node","="*10)
        planner_round = int(state.get("planning_round", 0))
        is_replan = planner_round > 0
        try:
            print("LLM:", state["user_input"])
            prompt = build_plan_tasks_prompt(
                state["user_input"],
                max_tasks=4,
                force_multi=is_replan,
                agents=workers,
            )
            response = call_llm(prompt,temperature=0)
            import json
            import re
            match = re.search(r'\[.*\]', response,re.DOTALL)
            if match:
                tasks = json.loads(match.group())
                if isinstance(tasks, list) and tasks:
                    plan_source = "llm"
                else:
                    tasks = []
            else:
                tasks = []
        except Exception:
            print("LLM error:", response)
            tasks = []
        if not tasks:
            tasks = fallback_plan_tasks(state["user_input"])
            plan_source = "rule"
        if is_replan and len(tasks) < 2:
            tasks = _fallback_split_for_replan(state["user_input"])
            plan_source = "rule"
        for task in tasks:
            print(task)
        print("任务数:", len(tasks))
        return {
            "tasks": tasks,
            "plan_source": plan_source,
            "task_index": 0,
        }

    def validator_node(state: PlannerState) -> PlannerState:
        print("=" * 10, "validator_node", "=" * 10)
        planning_round = int(state.get("planning_round", 0))
        tasks = state.get("tasks",[])
        should_replan = planning_round == 0 and _needs_replan(state["user_input"],tasks)
        if should_replan:
            return {"replan_required": True, "planning_round": planning_round + 1}
        return {"replan_required": False}

    def dispatcher_node(state: PlannerState) -> PlannerState:
        print("=" * 10, "dispatcher_node", "=" * 10)
        tasks = state.get("tasks",[])
        task_index = int(state.get("task_index", 0))
        if task_index >= len(tasks):
            return {}
        task = tasks[task_index]
        try:
            prompt = build_router_prompt(task,workers)
            response = call_llm(prompt,temperature=0)
            parts = response.split("|",1)
            routed_worker_id = parts[0].strip()
            routed_reason = parts[1].strip() if len(parts) > 1 else "模型未返回解释,使用默认解释"
            print(f"{routed_worker_id}:{routed_reason}")
            if routed_worker_id not in worker_by_id:
                raise ValueError(f"Worker{routed_worker_id}not found")
        except Exception:
            fallback_result = fallback_route_keyword(task,workers)
            if fallback_result:
                routed_worker_id, routed_reason = fallback_result
            else:
                routed_worker_id = workers[0].id
                routed_reason = "降级策略：默认选择首个工作节点"
        worker = worker_by_id[routed_worker_id]
        return {
            "current_task": task,
            "current_worker_id":worker.id,
            "current_worker_name":worker.name,
            "current_route_reason": routed_reason,
        }

    def make_worker_node(worker: AgentDefinition):
        def worker_node(state: PlannerState) -> PlannerState:
            print("=" * 10, f"worker_node_{worker.name}", "=" * 10)
            task_index = int(state.get("task_index", 0))
            tasks = state.get("tasks",[])
            if task_index >= len(tasks):
                return {}
            prior_reports = list(state.get("task_reports", []))
            prior_reports_text = "\n\n".join(prior_reports) if prior_reports else "None yet."
            human_index = task_index + 1
            worker_input = (
                f"原始用户请求：\n{state['user_input']}\n\n"
                "之前工作中已可用的内容：\n"
                f"{prior_reports_text}\n\n"
                f"当前任务 {human_index}：\n{state['current_task']}\n\n"
                "直接执行当前任务。\n"
                "这是一个执行类任务，而非讨论类任务。请优先使用工具操作，而非仅输出文字。\n"
                "在相关情况下，应基于已有的前期工作成果，而不是忽略它们。\n\n"
                "硬性规则：\n"
                "1. 如果任务涉及文件、目录、代码、项目产出物、桌面路径、下载路径或生成的工件，在做出事实性声明前，必须使用文件系统工具进行验证或创建。\n"
                "2. 不要猜测文件、目录、项目或产出物是否存在。\n"
                "3. 如果预期的文件或目录不存在且当前任务需要它，请创建它，而不仅仅是描述它。\n"
                "4. 如果需要正确的路径，先进行搜索或列出目录，然后再读取或写入。\n"
                "5. 不要用推测来替代缺失的工具操作。\n"
                "6. 除非当前任务明确仅为分析性质，否则不要编写项目管理更新、计划回顾或通用建议。\n"
                "7. 如果你更改、创建或验证了文件，请准确说明涉及了哪些路径。\n"
                "8. 如果无法完成任务，请说明具体的阻碍因素以及你已通过工具验证过的内容。\n"
                "9. 如果当前任务是构建页面、应用、功能或工具，当任务仍要求实现功能性行为时，不要将静态外壳或仅样式的输出视为完成。\n"
                "10. 你的结果消息必须总结具体实现的行为，而不仅仅是视觉或结构上的变化。\n\n"
                "执行策略：\n"
                "- 需要确认某物是否存在：先用工具检查。\n"
                "- 如果目标路径或交付物已经很明确，优先直接创建或写入，而不是一再地先列出或搜索。\n"
                "- 需要目录：创建它。\n"
                "- 需要文件：写入它。\n"
                "- 需要文件内容：读取它。\n"
                "- 需要找到合适的目标：先搜索/列出，然后再操作。\n\n"
                "用自然语言回复，仅包含当前任务的具体结果。如果任务期望的是可工作的行为，请明确描述已实现的功能行为，而不仅仅是说创建了文件或 UI。"
            )
            task_answer = run_agent(
                worker,
                worker_input
            )
            task_reports = prior_reports
            task_reports.append(f"Task {human_index} by {worker.name}:\n{task_answer}")
            next_index = task_index + 1
            return {
                "task_reports": task_reports,
                "task_index": next_index,
                "combined_report": "\n\n".join(task_reports),
            }
        return worker_node

    def synth_node(state: PlannerState) -> PlannerState:
        print("=" * 10, "synth_node", "=" * 10)
        combined_report = state.get("combined_report", "")
        finalize_worker = worker_by_id.get(state.get("current_worker_id",""), workers[0])
        try:
            prompt = build_finalize_prompt(
                user_input=state["user_input"],
                agent=finalize_worker,
                specialist_answer=combined_report,
            )
            assistant_message = call_llm(prompt,temperature=0.1)
        except Exception:
            assistant_message = build_fallback_response(
                agent_name=finalize_worker.name,
                answer=combined_report,
            )
        print("Finalize:", assistant_message)
        return {"ai_message": assistant_message}

    def validator_next(state: PlannerState) -> str:
        return PLANNER_NODE if bool(state.get("replan_required")) else DISPATCHER_NODE

    def dispatch_next(state: PlannerState) -> str:
        task_index = int(state.get("task_index", 0))
        tasks_len = len(state.get("tasks", []))
        if task_index >= tasks_len:
            return SYNTH_NODE if workflow.finalizer_enabled else END
        worker_id = str(state.get("current_worker_id", ""))
        if worker_id in worker_by_id:
            return worker_id
        return workers[0].id

    def worker_next(state: PlannerState) -> str:
        return DISPATCHER_NODE

    app = _compile_planner_app(
        workflow,
        workers,
        planner_node=planner_node,
        validator_node=validator_node,
        dispatcher_node=dispatcher_node,
        make_worker_node=make_worker_node,
        validator_next=validator_next,
        dispatch_next=dispatch_next,
        worker_next=worker_next,
        synth_node=synth_node if workflow.finalizer_enabled else None,
    )
    final_state = app.invoke(
        {
            "user_input": user_input,
            "planning_round": 0,
            "task_index": 0,
            "task_reports": [],
        }
    )

    combined_report = str(final_state.get("combined_report", ""))
    if not combined_report:
        combined_report = "\n\n".join(final_state.get("task_reports", []))
    if workflow.finalizer_enabled:
        assistant_message = str(final_state.get("ai_message", combined_report))
    else:
        assistant_message = combined_report

    route_agent_id = str(final_state.get("current_worker_id", ""))
    route_agent_name = str(final_state.get("current_worker_name", ""))
    plan_source = str(final_state.get("plan_source", ""))
    artifacts = RunArtifacts(
        route_agent_id=route_agent_id or None,
        route_agent_name=route_agent_name or None,
        route_reason=(f"Planner source={plan_source}; approved {len(final_state.get('tasks', []))} task(s)."),
        specialist_answer=combined_report or None,
        final_answer=assistant_message,
    )
    return WorkflowRunResponse(
        workflow_id=workflow.id,
        user_input=user_input,
        assistant_message=assistant_message,
        artifacts=artifacts,
    )

if __name__ == "__main__":
    store = Store()
    workflow = WorkflowDefinition(
        id="planner_executor",
        name="Planner Executor",
        type="planner_executor",
        specialist_agent_ids=["product_manager","designer","developer"],
    )
    user_input = input("User input: ")
    run_planner_executor(store,workflow,user_input)