import json
import os
import sys
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

# 1. 加载 TransPlayVault 和 TransPlayMaxCommits 环境变量
vault_path_str = os.environ.get("TransPlayVault")
max_commits_str = os.environ.get("TransPlayMaxCommits")

# 若未在环境变量中设置，则尝试从全局 mcp_config.json 配置文件中加载
if not vault_path_str or not max_commits_str:
    global_config_path = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    if global_config_path.exists():
        try:
            with open(global_config_path, encoding="utf-8") as f:
                global_config = json.load(f)

            # 从 mcpServers 嵌套配置块中查找
            env_block = (
                global_config.get("mcpServers", {})
                .get("transplay-mcp", {})
                .get("env", {})
            )
            if not vault_path_str:
                vault_path_str = env_block.get("TransPlayVault")
                if not vault_path_str:
                    vault_path_str = global_config.get("TransPlayVault")

            if not max_commits_str:
                max_commits_str = env_block.get("TransPlayMaxCommits")
                if not max_commits_str:
                    val = global_config.get("TransPlayMaxCommits")
                    if val is not None:
                        max_commits_str = str(val)
        except Exception as e:
            if not is_testing:
                print(
                    f"CRITICAL: Failed to parse global mcp_config.json: {e}",
                    file=sys.stderr,
                )
                sys.exit(1)

# 应用并校验配置参数
vault_path: Path | None = None
if vault_path_str:
    vault_path = Path(vault_path_str)

max_commits: int | None = None
if max_commits_str:
    try:
        max_commits = int(max_commits_str)
    except ValueError:
        pass

# 执行崩溃拦截强校验（Fail-fast）
if vault_path is None:
    if is_testing:
        vault_path = Path.cwd() / "dummy_vault"
    else:
        print(
            "CRITICAL: TransPlayVault is not configured. Please define it in "
            "the environment variable 'TransPlayVault' or in your global "
            "mcp_config.json.",
            file=sys.stderr,
        )
        sys.exit(1)

if max_commits is None or max_commits < 2:
    if is_testing:
        max_commits = 3
    else:
        print(
            "CRITICAL: TransPlayMaxCommits is not configured or invalid (must "
            "be an integer >= 2). Please configure it in environment "
            "variables or in global mcp_config.json.",
            file=sys.stderr,
        )
        sys.exit(1)


# 3. 注册并暴露 Resource 资源
@mcp.resource("transplay://config/vault_path")
def get_vault_path() -> str:
    """获取此服务端统一管理的 TransPlayVault 目录的绝对物理路径。"""
    assert vault_path is not None
    return str(vault_path.absolute())


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
    target_dir = vault_path / game_id / mod_id / sub_dir
    if not target_dir.exists():
        return f"Error: Target directory does not exist at {target_dir}"

    try:
        format_json_files(target_dir)
        return f"JSON files in {game_id}/{mod_id}/{sub_dir} formatted successfully."
    except Exception as e:
        return f"Error formatting JSON files: {str(e)}"


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
        need_ir_origin: 是否计算 ir/origin 目录的 diff 差异。
    """
    assert vault_path is not None
    repo_path = vault_path / game_id / mod_id
    # Create directory if it does not exist
    repo_path.mkdir(parents=True, exist_ok=True)

    try:
        diff_output = git_diff_check(
            str(repo_path), need_origin=need_origin, need_ir_origin=need_ir_origin
        )
        return diff_output
    except Exception as e:
        return f"Error checking git diff: {str(e)}"


@mcp.tool()
def git_commit_version_tool(
    game_id: str, mod_id: str, version: str, message: str
) -> str:
    """将当前更改提交至模组 Git 仓库，并根据配置的上限限制自动裁剪/合并提交历史。

    Args:
        game_id: 游戏唯一标识。
        mod_id: 模组唯一标识。
        version: 标记本次提交的模组版本号（例如 1.0.0）。
        message: 详细的提交说明信息。
    """
    assert vault_path is not None
    repo_path = vault_path / game_id / mod_id
    if not repo_path.exists():
        return f"Error: Mod repository path does not exist: {repo_path}"

    try:
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
    except Exception as e:
        return f"Error committing version: {str(e)}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
