# TransPlay MCP Server

## 非技术用户阅读此节：

### 这是什么
***接下来我会用最直白、最直接、最不绕弯子、最真相、最扎心、最硬核、最干脆、最不墨迹、最戳痛点、最一针见血、最开门见山、最单刀直入、最不废话、最不装、最只讲干货、最只说重点的方式来告诉你***：你想玩什么mod，都有汉化版（或其他语言的翻译版）了。

### 怎么安装
让 agent 给你搭配好环境--包括1个 `SKILL.md` 和整个 `src/` 目录（那是一个mcp，需要进行配置，可以由agent进行配置指导）

### 怎么使用
交给 agent 使用。

---

## 技术用户阅读此节：
TransPlay MCP 是一个面向 AI 智能体（Agent）的、用于辅助游戏 Mod 增量翻译与版本管理的 Model Context Protocol (MCP) 本地服务端。

支持包括文本、常见二进制文件（如 .esp）的增量翻译、版本管理。
（注：为避免占用大量硬盘空间，只支持保存最近3个历史版本。这个数字可以自行调整，见下文配置。）

原理很暴力：生成与原 mod 文件几乎一模一样，仅仅是字符串被改变了的新 mod 文件。以实现高汉化覆盖率。

支持 Steam 创意工坊。（由agent负责覆盖入创意工坊目录）

### Prerequisites (环境依赖)
- Python环境：包括Python解释器、以及`mcp`包的安装。
- Git: 系统 PATH 中需安装有 `git` 命令行工具

### Installation (安装)
`git pull` 拉取后 `uv sync`。

然后配置1个 `SKILL.md`（在 `transplay-localization/` 下）+ harness 框架的 MCP 配置。

### Local Configuration & MCP Client Setup (本地配置与集成)
本服务器运行前必须配置以下两个核心参数。它们都会在启动时进行自检（Fast-fail），如果检测不到或配置不合法，服务器将直接崩溃退出：
1. `TransPlayVault`：用于持久化存放原始 mod、翻译后的 mod 的统一管理物理路径。
2. `TransPlayMaxCommits`：模组版本仓库中限制的 Git 最大历史提交总数（必须是 $\ge 2$ 的正整数，如推荐配置为 `3`）。

此外，还支持以下可选参数（若检测不到或为空，则静默忽略，不进行 Fast-fail 强退校验）：
3. `TransPlaySteamWorkshopPath`（可选）：本地 Steam 创意工坊 content 目录的物理路径，配置后可用于协助大模型实装覆盖。

### 配置示例

向你的客户端集成软件对应的 MCP 配置文件中，写入类似下面这种结构，**注意需将占位符替换为您自己本地对应的绝对路径**：

```json
{
  "mcpServers": {
    "transplay-mcp": {
      "cwd": "<your_cloned_repository_absolute_path>",
      "command": "uv",
      "args": [
        "run",
        "transplay-mcp"
      ],
      "env": {
        "TransPlayVault": "<your_transplay_vault_absolute_path>",
        "TransPlayMaxCommits": "3",
        "TransPlaySteamWorkshopPath": "<your_steam_workshop_content_absolute_path_optional>"
      }
    }
  }
}
```

#### 手动配置与集成指引
1. **参数占位符说明**：
   - `<your_cloned_repository_absolute_path>`：克隆本仓库到您本地的绝对路径。
   - `<your_transplay_vault_absolute_path>`：您本地用于统一存放和版本管理汉化模组的根目录文件夹（该目录在运行前**必须由您手动创建好**）。
   - `<your_steam_workshop_content_absolute_path_optional>`（可选）：本地 Steam 创意工坊的 content 存放路径，通常位于 `<Steam安装路径>/steamapps/workshop/content`。配置后方可使 Agent 执行覆盖实装功能。
2. **在 Cursor 中集成**：
   - 打开 Cursor Settings -> Features -> MCP。
   - 点击 `+ Add New MCP Server`。
   - Name 写入 `transplay-mcp`，Type 选择 `command`，Command 写入 `uv run --project <your_repository_path> transplay-mcp`。
   - 点击 `+ Add Env` 分别追加 `TransPlayVault`、`TransPlayMaxCommits` 及可选的 `TransPlaySteamWorkshopPath` 环境变量值。
3. **在 Claude Desktop 中集成**：
   - 将上述 JSON 配置片段写入到您的 `%APPDATA%\Claude\claude_desktop_config.json` 中并保存。
   - 重启 Claude Desktop 客户端即可成功加载本服务。


## Development & Test (开发与测试)

若需在本地运行单元测试或进行静态代码检查，可直接使用以下指令：

### 1. 运行自动化测试
```bash
uv run pytest
```

### 2. 静态分析与代码格式检查
```bash
# 代码检查
uv run ruff check src/
# 严格类型安全检查
uv run pyright src/
```

## 附：如何畅享天下好玩
- 搜 mod：浏览器用沉浸式翻译等插件，浏览创意工坊或nexus等mod网站
- 译 mod：使用 agent，利用 TransPlay MCP 轻松管理汉化


<p style="text-align: center; font-size: 12px; color: #666666;">
  ( •̀ ω •́ )y     No Trans, No Play. Trans here, Play here. Trans for Play, Play for Trans. Trans me, Play me. I Trans, I play.              ٩(｡・ω・｡)﻿و
</p>