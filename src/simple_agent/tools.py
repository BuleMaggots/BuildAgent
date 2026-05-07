import shutil

from langchain_core.tools import tool
from utils.path_tool import get_abs_path,get_project_root
import os


@tool()
def fs_root() -> dict:
    """无需参数,获取可供修改的根目录和已有的目录结构,所有的生产活动都只能在根目录或子目录下
    返回值:
    {
        "root":根目录
        "structure": {目录结构列表}
    }
    """
    print("fs_root")
    root_path = get_abs_path("output")
    if not os.path.exists(root_path):
        return f"文件夹 {root_path} 不存在"
    if not os.path.isdir(root_path):
        return f"{root_path} 不是一个文件夹"
    def build_tree(path):
        tree = {"children": []}
        try:
            for item in sorted(os.listdir(path)):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    tree["children"].append(build_tree(item_path))
                else:
                    tree["children"].append({"name": item, "type": "file"})
        except PermissionError:
            pass
        return tree

    structure = build_tree(root_path)
    print(structure)
    return {
        "root": root_path,
        "structure": structure
    }

@tool()
def read_file_list(path: str) -> str:
    """输入文件路径,返回该路径目录下的所有文件名
    Args:
        path: 目录路径('D:/myfiles')
    """
    if not os.path.exists(path):
        return f"文件夹 {path} 不存在"
    if not os.path.isdir(path):
        return f"{path} 不是一个文件夹"
    contents = "\n".join(os.listdir(path))
    return contents

@tool()
def make_dir(path: str):
    """
    创建指定目录
    Args:
        path: 目录路径（例如 'C:/dir'）
    """
    print("make_dir")
    try:
        if os.path.exists(path):
            return f"文件 {path} 已存在"
        os.makedirs(path, exist_ok=True)
        return f"已创建目录: {path}"
    except Exception as e:
        return f"创建目录时出错: {str(e)}"

@tool()
def create_file_with_content(path: str, filename: str, suffix: str, content:  str):
    """
    在指定目录生成指定后缀的文件，并写入内容.若原文件存在,只会写入内容(覆盖原内容)
    Args:
        path: 目录路径（例如 './data' 或 'C:/myfiles'）
        filename:  要创建的文件名（不含后缀，例如 'example'）
        suffix:    该的文件后缀（例如 '.txt' 或 '.html'，注意带点）
        content:   要写入的字符串内容
    """
    print("create_file_with_content")
    try:
        os.makedirs(path, exist_ok=True)
        full_path = os.path.join(path, filename + suffix)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"已创建文件: {full_path}"
    except Exception as e:
        return f"创建文件时出错: {str(e)}"

@tool()
def append_file_content(path: str, filename: str, suffix: str, content: str):
    """
    指定目录下的指定文件内容后追加内容.若文件不存在,会创建该文件并写入内容
    Args:
        path: 目录路径（例如 './data' 或 'C:/myfiles'）
        filename:  文件名（不含后缀，例如 'example'）
        suffix:    该文件的后缀（例如 '.txt' 或 '.html'，注意带点）
        content:   要追加的更新内容
    """
    print("append_file_content")
    try:
        os.makedirs(path, exist_ok=True)
        full_path = os.path.join(path, filename + suffix)
        if os.path.exists(full_path):
            with open(full_path, 'a', encoding='utf-8') as f:
                f.write(content)
            return f"已追加内容到文件: {full_path}"
        else:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"已创建文件并写入内容: {full_path}"
    except Exception as e:
        return f"追加文件内容时出错: {str(e)}"

@tool()
def read_file_content(path: str, filename: str, suffix: str) -> str:
    """
    读取指定目录下的指定文件内容
    Args:
        path: 目录路径（例如 './data' 或 'C:/myfiles'）
        filename: 文件名（不含后缀，例如 'example'）
        suffix: 该文件的后缀（例如 '.txt' 或 '.html'，注意带点）
    """
    print("read_file_content")
    file_path = os.path.join(path, filename + suffix)
    if not os.path.isfile(file_path):
        return f"文件 {file_path} 不存在或不是有效文件"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"读取文件时出错：{e}"

@tool()
def delete_file(path: str, filename: str, suffix: str):
    """
    删除指定目录下的指定文件
    Args:
        path: 目录路径（例如 './data' 或 'C:/myfiles'）
        filename: 要删除的文件名（不含后缀，例如 'example'）
        suffix: 该文件的后缀（例如 '.txt' 或 '.html'，注意带点）
    """
    print("delete_file")
    file_path = os.path.join(path, filename + suffix)
    if not os.path.isfile(file_path):
        return f"文件 {file_path} 不存在"
    os.remove(file_path)
    return f"已删除文件: {file_path}"

@tool()
def move(path: str, filename: str, suffix: str, new_path: str):
    """
    移动指定目录下的指定文件到新的目录
    Args:
        path: 源文件目录路径（例如 './data' 或 'C:/myfiles'）
        filename: 要移动的文件名（不含后缀，例如 'example'）
        suffix: 该文件的后缀（例如 '.txt' 或 '.html'，注意带点）
        new_path: 目标目录路径（例如 './data/new' 或 'C:/myfiles/new'）
    """
    print("move")
    file = filename + suffix
    source_path = os.path.join(path, file)
    if not os.path.isfile(source_path):
        return f"文件 {file} 不存在"

    # 确保目标目录存在
    os.makedirs(new_path, exist_ok=True)
    target_path = os.path.join(new_path, file)
    try:
        shutil.move(source_path, target_path)
        return target_path
    except Exception as e:
        return f"移动文件时出错：{e}"

tools = [
    fs_root,
    read_file_list,
    make_dir,
    create_file_with_content,
    append_file_content,
    read_file_content,
    delete_file,
    move,
]