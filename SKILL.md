---
name: transplay-localization
description: 模组汉化与增量翻译工作流。当用户要求汉化、翻译、更新游戏模组（mod）或检查模组文件差异时使用。
version: "1.0.0"
---

# 模组汉化与增量翻译工作流 (TransPlay-Localization)

本技能指导 Agent 在面对任何游戏模组（Mod）汉化、翻译或更新请求时，如何利用 `transplay-mcp` 服务的底层工具（资源、差异对比、JSON 格式化、Git 版本历史管理）并结合**多级子代理分工**及**人机协同沟通**执行强工程规范的工作流。

---

## 0. 核心架构与目录同构规范

1. **绝对路径隔离**：模组在本地的绝对物理路径映射均由 MCP 服务端隐式计算（基于客户端注入 of `TransPlayVault` 根路径），Agent 仅与 MCP 服务端进行交互，不直接暴露或操作硬编码的绝对物理路径。
2. **目录同构原则**：模组内部的任意子目录及文件结构，在 `origin/`、`translated/`、`ir/origin/` 和 `ir/translated/` 中**必须保持完全一致的目录层级与同构关系**。

---

## 1. 启动探活：获取配置与配置校验

在执行任何具体翻译操作之前，必须首先获取由客户端注入的环境变量参数：

1. **读取 Resource 资源**：
   - 读取 `transplay://config/vault_path` 获取模组仓库的存放目录。
   - 读取 `transplay://config/max_commits` 获取 Git 历史剪枝的提交上限。
2. **启动异常警示**：
   - 依据环境变量 Fast-fail 设计，若客户端未配置对应的环境变量，MCP 服务端将在模块顶级加载时直接强退。若发生连接 MCP 失败，Agent 应当优先引导并协助用户检查并补全客户端 MCP 配置文件中的 `env` block。

---

## 2. 路由分发：状态决策机制

当接收到汉化或更新请求（涉及特定 `<game_id>` 和 `<mod_id>`）时，检查对应模组的物理目录状态：

1. **状态决策分支**：
   - 检查 `origin/` 是否存在 (记为 `exist_o`)，及原版版本号 `version_o`。
   - 检查 `translated/` 是否存在 (记为 `exist_t`)，及译文版本号 `version_t`。
2. **路由决策规则**：
   - **分支 A (全新翻译)**：若 `exist_t` 不存在。执行 **[3. 全新翻译流程]**。
   - **分支 B (增量更新)**：若 `exist_t` 存在，且 `version_t < version_o`。执行 **[4. 增量更新流程]**。
   - **分支 C (无需更新)**：若 `exist_t` 存在，且 `version_t >= version_o`。直接提示用户此 Mod 已经翻译过，并告知译文所在的相对查看路径。
   - **异常 / Fallback 分支**：若处于其他未知异常状态，Agent 必须**立即主动与用户进行双向交流沟通**，引导用户核对模组状态或环境配置。

---

## 3. 全新翻译流程

1. **源码写入**：将原始模组的所有文件写入 `origin/` 目录中。
2. **仓库初始化**：在做任何修改或分类前，先调用一次 `git_diff_check_tool(need_origin=True, need_ir_origin=False)` 触发底层 Git 仓库自动完成 `init` 并创建 Initial Commit。
3. **文件分类环节**：扫描 `origin/`，执行文件类型分类：
   - **无需翻译的媒体类**（音频、图片、视频等）。
   - **需翻译的纯文本源文件**。
   - **需翻译的二进制源文件**。
4. **多级并行代理翻译**：
   - **纯文本源文件**：
     - 创建 **[一级子代理 (文本翻译)]** 指派纯文本汉化任务。
     - 一级子代理调用**批量的二级子代理**，并行翻译并输出至 `translated/`（严格保持原目录结构）。
   - **二进制源文件**：
     - 创建 **[一级子代理 (二进制解析)]** 指派二进制汉化任务。
     - 一级子代理自行设计 JSON 序列化方案，建立 `ir/spec.md` 描述映射，并将反编译序列化的 JSON 输出到 `ir/origin/`。
     - **确定性强格式化**：调用 `format_json_files_tool` 对 `ir/origin` 的所有 JSON 进行 Key 字典序强排序与 2 空格缩进格式化，防止产生 Git 格式噪点。
     - 一级子代理启动**并行二级子代理**，翻译 `ir/origin` 的 JSON 输出到 `ir/translated/`。
     - 一级子代理读取 `ir/translated/`，依据 `ir/spec.md` 反序列化打包生成汉化二进制，回填输出到 `translated/`。
   - **无需翻译的文件**：
     - 主代理负责将这些资产直接拷贝/同步至 `translated/` 对应层级下。
5. **译文强格式化**：在提交固化前，对 `translated/` 和 `ir/translated/` 下生成的所有 JSON 文件调用 `format_json_files_tool` 强格式化。
6. **提交版本固化**：调用 `git_commit_version_tool` 提交版本（包含版本号及 commit 说明）。服务端会自动完成 Git commit 并自动执行 Git 提交历史裁剪（保留最后 `max_commits` 个历史）。
7. **后置操作整理**：执行 **[5. 最终整理与用户协商流程]**。

---

## 4. 增量更新流程

1. **新文件覆盖**：将新版本的原始模组文件覆盖写入 `origin/` 目录。
2. **提取源码差异 (首次 Diff)**：
   - 调用 `git_diff_check_tool(need_origin=True, need_ir_origin=False)` 获取原版新旧文件的增量差异。
   - 依据差异内容进行分类：无变化文件 / 需更新纯文本 / 需更新二进制。
3. **针对性增量更新翻译**：
   - **纯文本源文件**：
     - 创建 **[一级子代理 (增量文本)]**。
     - 调动二级子代理仅对发生 Diff 变化的文件/行进行针对性增量翻译并写入更新至 `translated/`。
   - **二进制源文件**：
     - 创建 **[一级子代理 (增量二进制)]**。
     - 反编译新版本输出新的序列化 JSON 至 `ir/origin/` 并调用 `format_json_files_tool` 进行强格式化。
     - **提取 IR 差异 (二次 Diff)**：调用 `git_diff_check_tool(need_origin=False, need_ir_origin=True)` 获取新旧序列化 JSON 的差异增量。
     - 调动二级子代理仅针对 IR JSON 的增量差异键值对进行翻译，合并写入 `ir/translated/`。
     - 读取 `ir/translated/` 并依据 `spec.md` 反序列化封包输出最新汉化二进制至 `translated/`。
4. **译文强格式化**：对 `translated/` 和 `ir/translated/` 下新生成或修改过的 JSON 文件运行 `format_json_files_tool`。
5. **提交版本固化**：调用 `git_commit_version_tool` 提交版本，触发服务端自动进行 linear 历史裁剪。
6. **后置操作整理**：执行 **[5. 最终整理与用户协商流程]**。

---

## 5. 最终整理与用户协商流程

完成版本提交固化后，Agent **绝对不能擅自直接**清理目录或强行覆盖文件，必须遵循以下步骤：

1. **双向沟通协商**：Agent **必须主动与用户进行沟通**，询问用户需要执行哪些后置整理操作，并提供选择。
2. **在获得用户明确授权意向（Opt-in）后**，执行对应操作：
   - **选择 A (清理缓存)**：清理除了 `TransPlayVault/` 库下以外，在整个翻译流程中在外部生成的临时无用目录（同时友情提醒用户原始英文原件和译文已在仓库 origin 和 translated 中完整备份，无需担心丢失）。
   - **选择 B (覆盖实装)**：直接协助将 `translated/` 目录下汉化完成的终极成果覆盖写入到用户的游戏 Mod 本地目录或 Steam 创意工坊对应路径下。
