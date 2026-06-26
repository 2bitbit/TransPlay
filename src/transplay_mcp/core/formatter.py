import json
from pathlib import Path


def format_json_files(dir_path: str | Path) -> None:
    path = Path(dir_path)
    if not path.exists():
        raise FileNotFoundError(f"Directory {dir_path} does not exist")

    for file_path in path.rglob("*.json"):
        if file_path.is_file():
            # 读取文件内容
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # 解析 JSON 文本
            data = json.loads(content)

            # 递归排序字典键，并以 2 空格缩进格式化
            formatted = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)

            # 写回文件
            with open(file_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(formatted)
