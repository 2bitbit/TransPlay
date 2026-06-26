import subprocess
from pathlib import Path


def _run_git(
    repo_path: str | Path,
    args: list[str],
    stdin_data: str | None = None,
    timeout: float = 30.0,
) -> str:
    # 覆盖 Git LFS 全局配置，防止在后台 pipe 通信时启动 git-lfs 长生命周期过滤器进程发生管道死锁
    override_config = [
        "-c",
        "filter.lfs.required=false",
        "-c",
        "filter.lfs.smudge=",
        "-c",
        "filter.lfs.clean=",
        "-c",
        "filter.lfs.process=",
    ]
    try:
        result = subprocess.run(
            ["git"] + override_config + args,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=stdin_data,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Git command timed out after {timeout} seconds: git {' '.join(args)}"
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"Git command failed: git {' '.join(args)}\n"
            f"Exit code: {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result.stdout.strip()

# 进程级缓存，保存已配置过 Git local user 的仓库物理路径，避免冗余探测
_configured_repos: set[str] = set()

def _ensure_git_user_config(repo_path: str | Path) -> None:
    repo_str = str(Path(repo_path).resolve())
    if repo_str in _configured_repos:
        return

    # 确保本地 git 配置设置了 user.name 和 user.email，
    # 以便在无头环境（如 CI/CD）中能正常进行 commit 提交
    try:
        _run_git(repo_path, ["config", "--local", "user.name"])
    except RuntimeError:
        _run_git(repo_path, ["config", "--local", "user.name", "TransPlay Agent"])

    try:
        _run_git(repo_path, ["config", "--local", "user.email"])
    except RuntimeError:
        _run_git(
            repo_path,
            ["config", "--local", "user.email", "agent@transplay.local"],
        )
    _configured_repos.add(repo_str)

def git_diff_check(repo_path: str, need_origin: bool, need_ir_origin: bool) -> str:
    path = Path(repo_path)
    if not (path / ".git").exists():
        _run_git(path, ["init"])
        _ensure_git_user_config(path)
        # 提交一个初始的空 commit，以确立 HEAD 分支指针
        _run_git(path, ["commit", "--allow-empty", "-m", "Initial commit"])
    else:
        _ensure_git_user_config(path)

    # 运行 git add -N .，以追踪未跟踪的新文件以便进行差异比对
    _run_git(path, ["add", "-N", "."])

    diffs: list[str] = []
    if need_origin:
        # 检查 origin 目录是否存在以防报错
        if (path / "origin").exists():
            diff_out = _run_git(path, ["diff", "HEAD", "--", "origin"])
            if diff_out:
                diffs.append(diff_out)

    if need_ir_origin:
        # 检查 ir/origin 目录是否存在
        if (path / "ir" / "origin").exists():
            diff_out = _run_git(path, ["diff", "HEAD", "--", "ir/origin"])
            if diff_out:
                diffs.append(diff_out)

    return "\n\n".join(diffs)

def git_commit_version(repo_path: str, version: str, message: str) -> None:
    path = Path(repo_path)
    if not (path / ".git").exists():
        # 如果未初始化仓库，则进行初始化
        git_diff_check(repo_path, need_origin=False, need_ir_origin=False)
    else:
        _ensure_git_user_config(path)

    # 检查 git 状态，看是否有任何变更（包括未跟踪文件）
    status = _run_git(path, ["status", "--porcelain"])
    if not status:
        # 无任何变更需要提交，静默返回
        return

    # 将所有更改的文件添加到暂存区
    _run_git(path, ["add", "-A"])

    commit_msg = f"version: {version}\n\n{message}"
    _run_git(path, ["commit", "-m", commit_msg])

def squash_history(repo_path: str, max_commits: int) -> None:
    path = Path(repo_path)
    if not (path / ".git").exists():
        return

    # 校验 max_commits 参数的合法性，防止逻辑错误
    if max_commits < 2:
        raise ValueError("max_commits must be at least 2 to keep linear history.")

    # 获取线性历史中的 commit hash 列表（从新到旧）
    commits = _run_git(path, ["rev-list", "HEAD"]).splitlines()
    if len(commits) <= max_commits:
        return

    # C_squash_root 在 max_commits - 1 的索引位置（例如 max_commits=3 时为索引 2）
    c_squash_root = commits[max_commits - 1]
    t_squash_root = _run_git(path, ["rev-parse", f"{c_squash_root}^{{tree}}"])

    # 获取当前分支名称
    branch_name = _run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])

    # 1. 使用 squash 根节点的 tree 创建一个全新的根 commit
    # 移除命令行里的 -m 参数，改通过标准输入传给 commit-tree 避免命令行超长溢出崩溃
    r_prev = _run_git(
        path, ["commit-tree", t_squash_root], stdin_data="squashed history"
    )

    # 2. 从旧到新，依次重新链式提交保留的 commits（索引从 max_commits - 2 递减到 0）
    for i in range(max_commits - 2, -1, -1):
        c_curr = commits[i]
        t_curr = _run_git(path, ["rev-parse", f"{c_curr}^{{tree}}"])
        msg_curr = _run_git(path, ["show", "-s", "--format=%B", c_curr])
        r_next = _run_git(
            path, ["commit-tree", t_curr, "-p", r_prev], stdin_data=msg_curr
        )
        r_prev = r_next

    # 3. 更新分支指向，并硬重置工作区以使文件同步
    # 若 branch_name 为 "HEAD" 说明处于游离状态，更新目标应直接为 "HEAD"
    # 而不是诡异的 refs/heads/HEAD 引用分支
    ref_target = "HEAD" if branch_name == "HEAD" else f"refs/heads/{branch_name}"
    _run_git(path, ["update-ref", ref_target, r_prev])
    _run_git(path, ["reset", "--hard", r_prev])
