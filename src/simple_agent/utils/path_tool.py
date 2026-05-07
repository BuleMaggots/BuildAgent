import os

def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(current_file))
    return project_root
def get_abs_path(relative_path : str = ""):
    project_root = get_project_root()
    return os.path.join(project_root, relative_path)
