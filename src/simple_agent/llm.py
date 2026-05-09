import os
from collections.abc import Callable
from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langchain_deepseek import ChatDeepSeek
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from openai import OpenAI
from deepagents import create_deep_agent
from deepagents.middleware import SkillsMiddleware
from deepagents.backends import FilesystemBackend

from simple_agent.schemas import AgentDefinition
from tools import tools


@wrap_tool_call
def monitor_tool(
        request:ToolCallRequest,
        handler:Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    print(f"[monitor_tool]执行工具:{request.tool_call['name']}")
    print(f"[monitor_tool]传入工具:{request.tool_call['args']}")
    try:
        result = handler(request)
        print(f"[monitor_tool]工具====={request.tool_call['name']}=====调用成功")
        if request.tool_call["name"] == "fill_context_for_report":
            request.runtime.context["report"] = True
        return result
    except Exception as e:
        print(f"[monitor_tool]工具{request.tool_call['name']}执行异常:{str(e)}")
        raise e

def call_llm(
        prompt: str,
        temperature: int = 0,
        model: str = "deepseek-v4-flash",
):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable is not set")
    client = OpenAI(
       api_key=api_key,
        base_url="https://api.deepseek.com",
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {str(e)}") from e


def run_agent(agent: AgentDefinition, input: str):
    backend = FilesystemBackend(virtual_mode=False)
    sources = [f"src/simple_agent/Skills/{skill}" for skill in agent.skill_names] if agent.skill_names else []
    skills_middleware = SkillsMiddleware(
        backend=backend,
        sources=sources,
    )
    print(f"Using skills: {sources}")
    model_instance = ChatDeepSeek(
        model="deepseek-v4-flash",
        temperature=0,
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        extra_body={"thinking": {"type": "disabled"}}
    )
    middleware = [skills_middleware, monitor_tool] if sources else [monitor_tool]
    agent_instance = create_deep_agent(
        model=model_instance,
        middleware=middleware,
        tools=tools,
        system_prompt=agent.system_prompt,
    )

    result = agent_instance.invoke({"messages": [{"role": "user", "content": input}]})
    return result["messages"][-1].content