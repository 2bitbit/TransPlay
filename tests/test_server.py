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
    # Import inside test after environment and config mock are set up
    from transplay_mcp.server import (
        get_vault_path,
        format_json_files_tool,
        git_diff_check_tool,
        git_commit_version_tool,
    )
    
    vault_dir = setup_mcp_config

    # Test Resource get_vault_path
    assert get_vault_path() == str(vault_dir.absolute())

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
