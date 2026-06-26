import json
import os
import pytest
from pathlib import Path

# Set testing environment variable before importing server
os.environ["TRANSPLAY_TESTING"] = "1"

# We will write a temporary mcp_config.json for the server to load
@pytest.fixture(autouse=True)
def setup_mcp_config(tmp_path, monkeypatch):
    vault_dir = tmp_path / "TransPlayVault"
    vault_dir.mkdir()
    
    # Inject configuration via environment variables
    monkeypatch.setenv("TransPlayVault", str(vault_dir.absolute()))
    monkeypatch.setenv("TransPlayMaxCommits", "3")
    return vault_dir

def test_server_resources_and_tools(setup_mcp_config):
    from transplay_mcp.server import (
        get_vault_path,
        get_max_commits,
        format_json_files_tool,
        git_diff_check_tool,
        git_commit_version_tool,
    )
    
    vault_dir = setup_mcp_config

    # Test Resources
    assert get_vault_path() == str(vault_dir.absolute())
    assert get_max_commits() == "3"

    # Test git_diff_check_tool (should auto-init repo)
    game_id = "noita"
    mod_id = "test_mod"
    res_diff_init = git_diff_check_tool(game_id, mod_id, need_origin=True, need_ir_origin=False)
    assert res_diff_init == ""

    # Test format_json_files_tool
    sub_dir = "origin"
    target_dir = vault_dir / game_id / mod_id / sub_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    
    json_file = target_dir / "data.json"
    json_file.write_text('{"b": 2, "a": 1}')
    
    res = format_json_files_tool(game_id, mod_id, sub_dir)
    assert "formatted successfully" in res
    assert json_file.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}'

    # Test git_diff_check_tool again, now it should detect the new data.json
    res_diff = git_diff_check_tool(game_id, mod_id, need_origin=True, need_ir_origin=False)
    assert "data.json" in res_diff
    
    # Test git_commit_version_tool
    # Create a change to commit
    new_json_file = target_dir / "new.json"
    new_json_file.write_text('{"x": 1}')
    
    res_commit = git_commit_version_tool(game_id, mod_id, version="1.1.0", message="Add new file")
    assert "committed successfully" in res_commit
    
    # Verify commit exists in repo
    import subprocess
    repo_path = vault_dir / game_id / mod_id
    result = subprocess.run(
        ["git", "log", "-n", "1", "--format=%B"],
        cwd=str(repo_path),
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    assert "version: 1.1.0" in result.stdout


def test_server_config_invalid_max_commits(monkeypatch):
    import importlib
    import transplay_mcp.server
    
    # 模拟错误的 TransPlayMaxCommits (非整数)
    monkeypatch.setenv("TransPlayMaxCommits", "not-an-int")
    
    with pytest.raises(SystemExit) as excinfo:
        importlib.reload(transplay_mcp.server)
    assert excinfo.value.code == 1


def test_server_config_invalid_max_commits_less_than_2(monkeypatch):
    import importlib
    import transplay_mcp.server
    
    # 模拟错误的 TransPlayMaxCommits (< 2)
    monkeypatch.setenv("TransPlayMaxCommits", "1")
    
    with pytest.raises(SystemExit) as excinfo:
        importlib.reload(transplay_mcp.server)
    assert excinfo.value.code == 1


def test_server_path_traversal_protection(setup_mcp_config):
    from transplay_mcp.server import (
        format_json_files_tool,
        git_diff_check_tool,
        git_commit_version_tool,
    )
    
    # 传入含有 ../ 越界路径的参数
    bad_game = "../bad_game"
    bad_mod = "bad_mod"
    
    res1 = format_json_files_tool(bad_game, bad_mod, "origin")
    assert "Invalid path identifier detected" in res1
    
    res2 = git_diff_check_tool(bad_game, bad_mod, need_origin=True, need_ir_origin=False)
    assert "Invalid path identifier detected" in res2
    
    res3 = git_commit_version_tool(bad_game, bad_mod, version="1.0.0", message="msg")
    assert "Invalid path identifier detected" in res3

    # 传入含有 "." 或相对指示符号的非法参数
    res_dot = format_json_files_tool(".", "test_mod", "origin")
    assert "Invalid path identifier detected" in res_dot


def test_server_concurrency_lock(setup_mcp_config):
    from transplay_mcp.server import git_diff_check_tool
    
    game_id = "concurrency_game"
    mod_id = "test_mod"
    
    # 用多线程模拟并发调用同一个仓库的 tool
    results = []
    
    def worker():
        # 调用 git_diff_check_tool (会触发 _get_repo_lock 串行化)
        res = git_diff_check_tool(game_id, mod_id, need_origin=True, need_ir_origin=False)
        results.append(res)

    import threading
    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    # 验证是否都顺利返回（没有爆出 index.lock 冲突引发的失败）
    assert len(results) == 2
