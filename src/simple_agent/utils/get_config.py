from simple_agent.schemas import WorkflowDefinition
from simple_agent.utils.path_tool import get_abs_path
import yaml

def workflow_get_config_yaml(workflow_id: str,path: str = get_abs_path("config/workflow_config.yml")) ->WorkflowDefinition:
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        if isinstance(config, list):
            for workflow in config:
                if workflow.get("id") == workflow_id:
                    return WorkflowDefinition(**workflow)
        elif isinstance(config, dict):
            if workflow_id in config:
                return WorkflowDefinition(**config[workflow_id])
        raise ValueError(f"Workflow {workflow_id} not found")