import os
import sys
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# 导入核心功能模块
from transplay_mcp.core.formatter import format_json_files
from transplay_mcp.core.git_manager import (
    git_commit_version,
    git_diff_check,
    squash_history,
)

# 1. 初始化 FastMCP 实例
mcp = FastMCP("transplay-mcp")

# 2. 读取配置文件并执行 Fast-fail 强校验
is_testing = os.environ.get("TRANSPLAY_TESTING") == "1"

# 1. 直接从环境变量（由客户端/Harness从全局配置中读取并注入）中获取参数
vault_path_str = os.environ.get("TransPlayVault")
max_commits_str = os.environ.get("TransPlayMaxCommits")

# 2. 应用并校验配置参数
vault_path: Path | None = None
if vault_path_str:
    vault_path = Path(vault_path_str)
else:
    if is_testing:
        vault_path = Path.cwd() / "dummy_vault"
    else:
        print(
            "CRITICAL: Environment variable 'TransPlayVault' is not configured. "
            "Please specify it in the 'env' block of your global MCP config.",
            file=sys.stderr,
        )
        sys.exit(1)

max_commits: int | None = None
if max_commits_str:
    try:
        max_commits = int(max_commits_str)
    except ValueError as e:
        print(
            f"CRITICAL: Environment variable 'TransPlayMaxCommits' is invalid. "
            f"Value '{max_commits_str}' cannot be parsed as an integer: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    if max_commits < 2:
        print(
            "CRITICAL: Environment variable 'TransPlayMaxCommits' value "
            f"({max_commits}) is invalid. It must be an integer >= 2.",
            file=sys.stderr,
        )
        sys.exit(1)
else:
    if is_testing:
        max_commits = 3
    else:
        print(
            "CRITICAL: Environment variable 'TransPlayMaxCommits' is not configured. "
            "Please specify it in the 'env' block of your global MCP config.",
            file=sys.stderr,
        )
        sys.exit(1)


# 3. 注册并暴露 Resource 资源
@mcp.resource("transplay://config/vault_path")
def get_vault_path() -> str:
    """获取此服务端统一管理的 TransPlayVault 目录的绝对物理路径。"""
    assert vault_path is not None
    return str(vault_path.absolute())


@mcp.resource("transplay://config/max_commits")
def get_max_commits() -> str:
    """获取配置的 Git 最大历史提交总数限制。"""
    assert max_commits is not None
    return str(max_commits)


# 并发控制锁机制：针对每个模组仓库拥有独立的排他锁，防止高并发导致 Git 冲突
# 锁的字典键改为规范化后的绝对物理路径字符串，保证同一物理仓库在并发时绝对共享同一个锁
_repo_locks: dict[str | tuple[str, str], threading.Lock] = {}
_repo_locks_lock = threading.Lock()


def _get_repo_lock(game_id: str, mod_id: str) -> threading.Lock:
    assert vault_path is not None
    try:
        resolved_repo = _safe_resolve_path(vault_path, game_id, mod_id)
        key = resolved_repo.resolve().as_posix()
    except Exception:
        key = (game_id, mod_id)

    with _repo_locks_lock:
        if key not in _repo_locks:
            _repo_locks[key] = threading.Lock()
        return _repo_locks[key]


# 安全路径边界检查，防止 game_id、mod_id、sub_dir 进行路径穿越或根目录污染
def _safe_resolve_path(base_path: Path, *parts: str) -> Path:
    # 强校验参数纯净度，禁止相对路径标识 (如 . 或 ..) 以及任何路径斜杠干扰
    for part in parts:
        if part in (".", "..") or "/" in part or "\\" in part:
            raise PermissionError(f"Invalid path identifier detected: '{part}'")

    # 结合 parts 生成路径，resolve 消除相对路径
    resolved = (base_path / Path(*parts)).resolve()
    # 强校验是否仍在 base_path 目录下
    if not resolved.is_relative_to(base_path.resolve()):
        raise PermissionError("Path traversal detected! Access denied.")
    return resolved


# 4. 注册并暴露 Tools 工具接口
@mcp.tool()
def format_json_files_tool(game_id: str, mod_id: str, sub_dir: str) -> str:
    """在指定的模组子目录下，递归地对所有 JSON 文件进行键排序与强格式化。

    路径格式：TransPlayVault/<game_id>/<mod_id>/<sub_dir>/.

    Args:
        game_id: 游戏唯一标识（如 noita、cyberpunk2077）。
        mod_id: 模组唯一标识（如 创意工坊 ID 或模组文件夹名）。
        sub_dir: 待格式化的子目录名（如 origin、ir/origin）。
    """
    assert vault_path is not None
    target_dir = _safe_resolve_path(vault_path, game_id, mod_id, sub_dir)

    if not target_dir.exists():
        raise FileNotFoundError(f"Target directory does not exist at {target_dir}")

    lock = _get_repo_lock(game_id, mod_id)
    with lock:
        format_json_files(target_dir)
        return f"JSON files in {game_id}/{mod_id}/{sub_dir} formatted successfully."


@mcp.tool()
def git_diff_check_tool(
    game_id: str, mod_id: str, need_origin: bool, need_ir_origin: bool
) -> str:
    """检测模组仓库中 origin 目录或 ir/origin 目录的 Git 逻辑差异（增量变更）。

    如果该模组仓库尚未初始化，会自动执行 git init 并进行初始提交。

    Args:
        game_id: 游戏唯一标识。
        mod_id: 模组唯一标识。
        need_origin: 是否计算 origin 目录的 diff 差异。
        need_ir_origin: 是否计算 ir/origin 目录 of diff 差异。
    """
    assert vault_path is not None
    repo_path = _safe_resolve_path(vault_path, game_id, mod_id)

    # Create directory if it does not exist
    repo_path.mkdir(parents=True, exist_ok=True)

    lock = _get_repo_lock(game_id, mod_id)
    with lock:
        diff_output = git_diff_check(
            str(repo_path), need_origin=need_origin, need_ir_origin=need_ir_origin
        )
        return diff_output


@mcp.tool()
def git_commit_version_tool(
    game_id: str, mod_id: str, version: str, message: str
) -> str:
    """将当前更改提交至模组 Git 仓库，并根据配置的上限限制自动裁剪/合并提交历史。

    Args:
        game_id: 游戏唯一标识。
        mod_id: 模组唯一标识.
        version: 标记本次提交的模组版本号（例如 1.0.0）。
        message: 详细的提交说明信息。
    """
    assert vault_path is not None
    repo_path = _safe_resolve_path(vault_path, game_id, mod_id)

    if not repo_path.exists():
        raise FileNotFoundError(f"Mod repository path does not exist: {repo_path}")

    lock = _get_repo_lock(game_id, mod_id)
    with lock:
        # 提交指定版本
        git_commit_version(str(repo_path), version, message)
        # 执行历史剪枝以限制提交总数，控制硬盘空间占用
        assert max_commits is not None
        squash_history(str(repo_path), max_commits)
        return (
            f"Version {version} committed successfully in "
            f"{game_id}/{mod_id} with history pruned "
            f"(limit: {max_commits})."
        )

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
