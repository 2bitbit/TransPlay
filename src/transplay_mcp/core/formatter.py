import json
from pathlib import Path


def format_json_files(dir_path: str | Path) -> None:
    path = Path(dir_path)
    if not path.exists():
        raise FileNotFoundError(f"Directory {dir_path} does not exist")

    for file_path in path.rglob("*.json"):
        # 过滤掉以 "." 开头的任何隐藏或敏感子目录（如 .git, .pytest_cache, .venv 等）
        if any(part.startswith(".") for part in file_path.parent.parts):
            continue

        if file_path.is_file():
            # 读取文件内容（兼容带 BOM 的 UTF-8 文件）
            with open(file_path, encoding="utf-8-sig") as f:
                content = f.read()

            # 解析 JSON 文本
            data = json.loads(content)

            # 递归排序字典键，并以 2 空格缩进格式化
            formatted = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)

            # 安全原子写入保护：先写入临时文件，写入成功后再替换原文件
            # 防止中途断电或崩溃损坏原始 Mod JSON 文件
            temp_file = file_path.with_suffix(file_path.suffix + ".tmp")
            try:
                with open(temp_file, "w", encoding="utf-8", newline="\n") as f:
                    f.write(formatted)
                temp_file.replace(file_path)
            except Exception:
                if temp_file.exists():
                    temp_file.unlink()
                raise
