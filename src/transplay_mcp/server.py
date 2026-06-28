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
from transplay_mcp.core.logger import logger

# 1. 初始化 FastMCP 实例
mcp = FastMCP("transplay-mcp")

# 2. 读取配置文件并执行 Fast-fail 强校验
is_testing = os.environ.get("TRANSPLAY_TESTING") == "1"

# 1. 直接从环境变量（由客户端/Harness从全局配置中读取并注入）中获取参数
vault_path_str = os.environ.get("TransPlayVault")
max_commits_str = os.environ.get("TransPlayMaxCommits")
steam_workshop_path_str = os.environ.get("TransPlaySteamWorkshopPath")

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

# Steam 创意工坊可选物理路径（为空即忽略，不进行 Fast-fail 强退校验）
steam_workshop_path: Path | None = None
if steam_workshop_path_str:
    steam_workshop_path = Path(steam_workshop_path_str)


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


@mcp.resource("transplay://config/steam_workshop_path")
def get_steam_workshop_path() -> str:
    """获取此服务端管理的 Steam 创意工坊的绝对物理路径，若未配置则返回空字符串。"""
    if steam_workshop_path is None:
        return ""
    return str(steam_workshop_path.absolute())


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
            logger.debug(f"[_get_repo_lock] Created new Lock object for key: {key}")
        return _repo_locks[key]


# 安全路径边界检查，防止 game_id、mod_id、sub_dir 进行路径穿越或根目录污染
def _safe_resolve_path(base_path: Path, *parts: str) -> Path:
    # 强校验参数纯净度，禁止相对路径标识 (如 . 或 ..) 以及任何路径斜杠干扰
    for part in parts:
        if part in (".", "..") or "/" in part or "\\" in part:
            raise PermissionError(f"Invalid path identifier detected: '{part}'")

    # 结合 parts 生成路径，resolve 消除相对路径
    resolved = (base_path / Path(*parts)).resolve()
    
    # 使用 os.path.realpath 展开 Windows 下可能存在的 8.3 短路径名形式，以防 is_relative_to 误判
    real_resolved = Path(os.path.realpath(resolved))
    real_base = Path(os.path.realpath(base_path))
    
    # 强校验是否仍在 base_path 目录下
    if not real_resolved.is_relative_to(real_base):
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
    logger.info(
        f"[git_diff_check_tool] Received request. game_id: {game_id}, mod_id: {mod_id}, "
        f"need_origin: {need_origin}, need_ir_origin: {need_ir_origin}"
    )
    assert vault_path is not None
    repo_path = _safe_resolve_path(vault_path, game_id, mod_id)

    # Create directory if it does not exist
    repo_path.mkdir(parents=True, exist_ok=True)

    logger.debug(f"[git_diff_check_tool] Acquiring lock for repo: {repo_path}")
    lock = _get_repo_lock(game_id, mod_id)
    with lock:
        logger.debug(f"[git_diff_check_tool] Lock acquired for repo: {repo_path}")
        diff_output = git_diff_check(
            str(repo_path), need_origin=need_origin, need_ir_origin=need_ir_origin
        )
        logger.info(f"[git_diff_check_tool] Successfully finished. Returning diff of length {len(diff_output)}")
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


@mcp.tool()
def get_all_mods_status_tool() -> str:
    """获取所有被纳入管理的 Mod 的状态列表，识别待翻译、待更新或已是最新的 Mod。

    返回格式化好的列表字符串，并在最后提供专属的“只包含 origin 但未被翻译”的 Summary 检查说明行。
    """
    assert vault_path is not None
    if not vault_path.exists():
        return "Vault path does not exist."

    mods_status = []
    only_origin_mods = []

    try:
        games = sorted([d for d in vault_path.iterdir() if d.is_dir() and not d.name.startswith(".")])
    except Exception as e:
        logger.error(f"[get_all_mods_status_tool] Failed to list vault: {e}")
        return f"Error listing vault path: {e}"

    for game_dir in games:
        game_id = game_dir.name
        try:
            mods = sorted([d for d in game_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])
        except Exception as e:
            logger.warning(f"[get_all_mods_status_tool] Failed to list mods for game {game_id}: {e}")
            continue

        for mod_dir in mods:
            mod_id = mod_dir.name
            origin_path = mod_dir / "origin"
            translated_path = mod_dir / "translated"

            # 状态判定逻辑
            if not origin_path.exists():
                # 无 origin 目录的文件夹，视作无效或尚未初始化的非 Mod 物理空间，直接跳过
                continue

            if not translated_path.exists():
                status = "Need Translation (New origin only)"
                only_origin_mods.append(f"{game_id}/{mod_id}")
            else:
                # 若 translated 已存在，则通过底层 Git 比对 origin 的工作区与 HEAD 差异
                # 为防止并发读写引发 index 冲突，加写该 Mod 对应的本地读写锁
                lock = _get_repo_lock(game_id, mod_id)
                with lock:
                    try:
                        diff = git_diff_check(str(mod_dir), need_origin=True, need_ir_origin=False)
                        if diff.strip():
                            status = "Need Update"
                        else:
                            status = "Up to date"
                    except Exception as e:
                        logger.warning(f"[get_all_mods_status_tool] Git diff check failed for {game_id}/{mod_id}: {e}")
                        status = f"Git Error ({e})"

            mods_status.append(f"- [{game_id}] {mod_id}: {status}")

    lines = []
    if mods_status:
        lines.extend(mods_status)
    else:
        lines.append("No managed mods found.")

    lines.append(f"Check Summary: The following mods only have 'origin' directory and have not been translated yet: {only_origin_mods}")
    return "\n".join(lines)


def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
