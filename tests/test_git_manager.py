import os
import subprocess
import pytest
from transplay_mcp.core.git_manager import (
    git_diff_check,
    git_commit_version,
    squash_history,
)

def run_git(repo_path, args):
    result = subprocess.run(
        ["git"] + args,
        cwd=str(repo_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return result.stdout.strip()

def test_git_diff_check_and_init(tmp_path):
    # Set up test paths
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    
    # Under repo, create origin and ir/origin directories
    origin_dir = repo_path / "origin"
    origin_dir.mkdir()
    ir_origin_dir = repo_path / "ir" / "origin"
    ir_origin_dir.mkdir(parents=True)

    # 1. First run: repo is not initialized yet.
    # git_diff_check should auto-initialize the Git repository and create an initial commit.
    diff_init = git_diff_check(str(repo_path), need_origin=True, need_ir_origin=False)
    # Since there are no untracked or modified files yet in origin, diff should be empty.
    assert diff_init == ""
    assert (repo_path / ".git").exists()

    # Verify initial commit exists
    log = run_git(repo_path, ["log", "--oneline"])
    assert "Initial commit" in log

    # 2. Add an untracked file to origin
    file_origin = origin_dir / "test.json"
    file_origin.write_text('{"key": "val"}')

    # Run diff check specifying need_origin=True
    diff_origin = git_diff_check(str(repo_path), need_origin=True, need_ir_origin=False)
    # It should show the new file because of git add -N .
    assert "test.json" in diff_origin
    assert '+{"key":"val"}' in diff_origin.replace(" ", "")

    # Run diff check specifying need_ir_origin=True (which has no changes)
    diff_ir = git_diff_check(str(repo_path), need_origin=False, need_ir_origin=True)
    assert diff_ir == ""

    # Add a file to ir/origin
    file_ir = ir_origin_dir / "ir_test.json"
    file_ir.write_text('{"ir_key": "ir_val"}')

    # Check diff for ir/origin
    diff_ir_new = git_diff_check(str(repo_path), need_origin=False, need_ir_origin=True)
    assert "ir_test.json" in diff_ir_new
    assert '+{"ir_key":"ir_val"}' in diff_ir_new.replace(" ", "")


def test_git_commit_version(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    
    # Initialize repo by running diff check
    git_diff_check(str(repo_path), need_origin=True, need_ir_origin=False)

    # Create a change to commit
    origin_dir = repo_path / "origin"
    origin_dir.mkdir(exist_ok=True)
    (origin_dir / "file.json").write_text('{"x": 1}')

    # Commit the version
    git_commit_version(str(repo_path), version="1.0.0", message="Add file.json")

    # Verify the commit message in log
    log = run_git(repo_path, ["log", "-n", "1", "--format=%B"])
    assert log.startswith("version: 1.0.0\n\nAdd file.json")

    # If there are no changes, committing again should not fail
    git_commit_version(str(repo_path), version="1.0.0", message="No changes")


def test_squash_history(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize
    git_diff_check(str(repo_path), need_origin=True, need_ir_origin=False)
    
    # Create 4 more commits to have a total of 5 commits
    for i in range(1, 5):
        # We need to change a file to commit
        file_path = repo_path / f"file_{i}.txt"
        file_path.write_text(f"content {i}")
        git_commit_version(str(repo_path), version=f"1.0.{i}", message=f"Commit {i}")

    # Total commits should now be 5
    commit_hashes = run_git(repo_path, ["log", "--format=%H"]).splitlines()
    assert len(commit_hashes) == 5

    # Run squash_history
    squash_history(str(repo_path), max_commits=3)

    # Total commits should now be pruned to exactly 3
    new_commit_hashes = run_git(repo_path, ["log", "--format=%H"]).splitlines()
    assert len(new_commit_hashes) == 3

    # Check commit messages
    # The HEAD commit (the last one, Commit 4) should remain intact
    # The HEAD~1 commit (Commit 3) should remain intact
    # The HEAD~2 commit should be the squashed root commit
    # Format commits using a custom separator
    log_output = run_git(repo_path, ["log", "--format=%B---COMMIT_END---"])
    log_messages = [msg.strip() for msg in log_output.split("---COMMIT_END---") if msg.strip()]
    
    assert "Commit 4" in log_messages[0]
    assert "Commit 3" in log_messages[1]
    assert "squashed history" in log_messages[2] or "Initial commit" in log_messages[2]

    # Verify file contents are unchanged (HEAD state is preserved)
    for i in range(1, 5):
        assert (repo_path / f"file_{i}.txt").read_text() == f"content {i}"
