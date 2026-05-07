from ..schemas import WorkflowDefinition
from path_tool import get_abs_path
import yaml

def workflow_get_config_yaml(workflow_id: str,path: str = get_abs_path("config/workflow_config.yml")) ->WorkflowDefinition:
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        for workflow in config:
            if workflow["id"] == workflow_id:
                return WorkflowDefinition(**workflow)
