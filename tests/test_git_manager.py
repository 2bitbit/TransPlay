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

def test_git_commit_chinese_message(tmp_path):
    repo_path = tmp_path / "test_repo_zh"
    repo_path.mkdir()
    
    # 自动初始化
    git_diff_check(str(repo_path), need_origin=False, need_ir_origin=False)
    
    # 写入包含中文的文件
    origin_dir = repo_path / "origin"
    origin_dir.mkdir(exist_ok=True)
    (origin_dir / "中文模组.json").write_text('{"测试": "汉化内容"}', encoding="utf-8")
    
    # 进行带中文的 commit
    git_commit_version(str(repo_path), version="1.0.0", message="中文提交测试：添加中文汉化文件")
    
    # 读取最新日志，验证中文没有乱码且成功提交
    # 为 run_git 添加显式的 utf-8 解码，确保测试用例也能正常在 Windows 解码
    result = subprocess.run(
        ["git", "log", "-n", "1", "--format=%B"],
        cwd=str(repo_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=True,
    )
    log_out = result.stdout.strip()
    assert "中文提交测试" in log_out
    assert "添加中文汉化文件" in log_out

def test_squash_history_detached_head(tmp_path):
    repo_path = tmp_path / "test_repo_detached"
    repo_path.mkdir()

    # 初始化
    git_diff_check(str(repo_path), need_origin=False, need_ir_origin=False)
    
    # 写入并提交 4 个 commit
    for i in range(1, 5):
        (repo_path / f"file_{i}.txt").write_text(f"content {i}")
        git_commit_version(str(repo_path), version=f"1.0.{i}", message=f"Commit {i}")
        
    # 获取所有的 commit hashes
    commits = run_git(repo_path, ["log", "--format=%H"]).splitlines()
    assert len(commits) == 5  # 1 initial + 4 commits
    
    # Checkout 游离到 HEAD (即 commits[0]) 上，进入 Detached HEAD 状态
    run_git(repo_path, ["checkout", commits[0]])
    
    # 确认当前确实处于游离 HEAD 状态（分支名为 HEAD）
    branch = run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    assert branch == "HEAD"
    
    # 在游离状态下运行 squash_history 裁剪至 3 个历史
    squash_history(str(repo_path), max_commits=3)
    
    # 验证 refs/heads/HEAD 畸形分支没有被意外创建
    assert not (repo_path / ".git" / "refs" / "heads" / "HEAD").exists()
    
    # 验证当前的 commits 树长度被剪裁成了 3
    new_commits = run_git(repo_path, ["log", "--format=%H"]).splitlines()
    assert len(new_commits) == 3
    
    # 验证当前 HEAD 的 tree 指向最新一次提交 file_4.txt 的内容
    assert (repo_path / "file_4.txt").read_text() == "content 4"

def test_squash_history_ultra_long_message(tmp_path):
    repo_path = tmp_path / "test_repo_long_msg"
    repo_path.mkdir()

    # 初始化
    git_diff_check(str(repo_path), need_origin=False, need_ir_origin=False)
    
    # 提交 4 个 commit，其中一个包含大于 10000 字符的超长消息（模拟在 Windows 突破 8191 字符上限）
    long_msg = "A" * 10000
    for i in range(1, 5):
        (repo_path / f"file_{i}.txt").write_text(f"content {i}")
        msg = long_msg if i == 3 else f"Commit {i}"
        git_commit_version(str(repo_path), version=f"1.0.{i}", message=msg)
        
    # 运行 squash_history 裁剪至 3 个历史
    squash_history(str(repo_path), max_commits=3)
    
    # 验证裁剪成功，历史提交被削减到 3
    new_commits = run_git(repo_path, ["log", "--format=%H"]).splitlines()
    assert len(new_commits) == 3

def test_run_git_timeout(monkeypatch):
    import subprocess
    from transplay_mcp.core.git_manager import _run_git

    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=30.0)

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(RuntimeError) as exc_info:
        _run_git(".", ["status"])
    assert "timed out after" in str(exc_info.value)
