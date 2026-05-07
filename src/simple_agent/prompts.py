from simple_agent.schemas import AgentDefinition


PLAN_TASKS_PROMPT = """你是一个规划模块.
将用户的请求分解为最多 {max_tasks} 个可执行任务.
{multi_hint}
{agent_catalog}
进返回一个 JSON 字符串数组.
用户请求:{user_input}
"""
def build_plan_tasks_prompt(
        user_input: str,
        max_tasks: int = 4,
        force_multi: bool = False,
        agents: list[AgentDefinition] | None = None,
) -> str:
    # 构建规划器提示词
    multi_hint = (
        "当包含多个意图时,优先创建至少2个任务"
        if force_multi
        else "使用所需最少任务量"
    )
    agent_catalog = ""
    if agents:
        catalog_lines = "\n".join(
            f"- name:{agent.name};description:{agent.description}"
            for agent in agents
        )
        agent_catalog = ("当前可用的专家:\n"
                         f"{catalog_lines}\n"
                         "规划任务时,确保它们能清晰地映射到可用的专家代理上.\n"
                         "当请求合理地跨越产品/设计/工程领域时,在任务拆分中体现这一点.\n"
                         "优先使用能让最佳专家代理选择变得明显的的任务表述方式.\n"
                         )
    return PLAN_TASKS_PROMPT.format(
        max_tasks=max_tasks,
        multi_hint=multi_hint,
        agent_catalog=agent_catalog,
        user_input=user_input,
    )


def fallback_plan_tasks(user_input: str, max_tasks: int = 4) -> list[str]:
    """备用任务规划：通过简单分割实现"""
    # 按常见分隔符拆分
    separators = ["，", "。", ";", "\n"]
    tasks = [user_input]

    for sep in separators:
        new_tasks = []
        for task in tasks:
            new_tasks.extend(task.split(sep))
        if len(new_tasks) > len(tasks):
            tasks = new_tasks
            break
    # 清理并限制数量
    tasks = [t.strip() for t in tasks if t.strip()]
    return tasks[:max_tasks]


ROUTER_PROMPT = """你是一个路由模块.从下面的specialist agent中选出最适合用户请求的一个.
只返回一行,格式必须是: agent_id|reason
可选 agent:
{agent_catalog}
用户请求:{user_input}
"""
def build_router_prompt(user_input: str, agents: list[AgentDefinition]) -> str:
    catalog = "\n".join(
        f"- id:{agent.id};name:{agent.name};description:{agent.description}"
        for agent in agents
    )
    return ROUTER_PROMPT.format(
        user_input=user_input,
        agent_catalog=catalog,
    )


FALLBACK_ROUTE_KEYWORDS: dict[str, list[str]] = {
    "product_manager": ["需求", "产品", "功能", "优先级", "验收", "范围"],
    "designer": ["设计", "界面", "交互", "页面", "视觉", "用户体验"],
    "developer": ["代码", "实现", "技术", "开发", "编程", "部署"],
}
def fallback_route_keyword(user_input: str, agents: list[AgentDefinition]) -> tuple[str, str] | None:
    input_lower = user_input.lower()
    for agent_id, keywords in FALLBACK_ROUTE_KEYWORDS.items():
        if any(kw.lower() in input_lower for kw in keywords):
            for agent in agents:
                if agent.id == agent_id or agent_id in agent.name.lower():
                    return agent.id, f"使用关键字检索: {keywords}"
    return None


FINALIZE_PROMPT = """你是 workflow finalizer。请根据用户原始请求和 specialist 的回答，
输出最终对用户可见的答案，控制在 6 句话以内。
用户请求：{user_input}
specialist: {agent_name}
specialist 回复：{specialist_answer}"""
def build_finalize_prompt(
    user_input: str,
    agent: AgentDefinition,
    specialist_answer: str,
) -> str:
    return FINALIZE_PROMPT.format(
        user_input=user_input,
        agent_name=agent.name,
        specialist_answer=specialist_answer,
    )


FALLBACK_FINALIZE_RESPONSE = (
    "系统已将请求路由给 {agent_name}。\n"
    "{agent_name} 的回答如下：\n{answer}"
)
def build_fallback_response(agent_name: str, answer: str) -> str:
    return FALLBACK_FINALIZE_RESPONSE.format(
        agent_name=agent_name,
        answer=answer,
    )