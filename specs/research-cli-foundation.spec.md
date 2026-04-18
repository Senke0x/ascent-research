spec: task
name: "research-cli-foundation"
inherits: project
tags: [research-cli, foundation, rust, phase-3]
estimate: 1d
depends: []
---

## 意图

建立 `research` CLI 的最小骨架:Cargo crate 结构、binary 入口、全局 flag、子命令树
占位、session dir 布局约定。不实装任何子命令的真实逻辑(那些是后续 spec 的范围)——
本 task 的目标是让 `research --help` 能跑、所有子命令返回 "not yet implemented" 的
统一错误,且 spec-driven 的 session 目录契约落地到代码里。

完成之后,后续 task 只需填写每个子命令的具体实现,不再碰脚手架。

## 已定决策

- Cargo crate 路径:`research-api-adapter/packages/research/`
- Cargo 名:`research`(binary = `research`)
- edition = 2024
- 全局 flag:
  - `--json`(默认 plain text 输出)
  - `--verbose` / `-v`(tracing 级别调到 debug)
  - `--no-color`(TTY 中禁彩色)
- 子命令骨架(每个暂时返回 `NOT_IMPLEMENTED` fatal):
  ```
  research new <topic> [--preset <name>]
  research list
  research show <slug>
  research status [<slug>]
  research resume <slug>
  research add <url>
  research sources [<slug>]
  research synthesize [<slug>]
  research close [<slug>]
  research rm <slug>
  research route <url> [--prefer browser] [--rules <path>]
  research help
  ```
- **Active session 概念**:`~/.actionbook/research/.active` 是一个文件,内容为当前
  active session 的 slug。`research new` 写入,`research close`/`rm` 清空。大多数
  子命令 `<slug>` 可省略时即读 `.active`。
- Session 目录布局(契约):
  ```
  ~/.actionbook/research/<slug>/
  ├── session.md         # 活文档,LLM-readable
  ├── session.jsonl      # 追加日志,一行一事件
  ├── session.toml       # per-session config(preset, max_sources, ...)
  ├── raw/               # 所有抓取原始数据
  │   └── <n>-<kind>-<host>.json
  ├── report.json        # synthesize 产出
  └── report.html        # json-ui render 产物
  ```
- slug 规则:`[a-z0-9-]+`,≤ 60 字符;中文主题由用户或 LLM 显式给英文 slug
  (CLI 不做翻译,不做自动 transliteration)
- 冲突策略:`new` 遇到同名目录报 `SLUG_EXISTS` 要求用户显式带 `--force` 或改 slug
- 日志事件类型(session.jsonl 的 `event` 字段):
  - `session_created`
  - `source_attempted` / `source_accepted` / `source_rejected`
  - `synthesize_started` / `synthesize_completed` / `synthesize_failed`
  - `session_closed` / `session_removed`
- **不**在本 task 实装:route 逻辑、add 的真实 fetch、synthesize 的真实合成、
  smell test——这些是后续 task
- **不**引入 daemon(CLI 每次调用都是短命进程;session 状态靠文件系统)
- **不**维护 cookie / 凭据(子进程 `actionbook` 和 `postagent` 各自处理)

## 边界

### 允许修改
- `research-api-adapter/packages/research/**`(新 Rust crate)
- `research-api-adapter/Cargo.toml`(新 workspace root,如需)
- `research-api-adapter/presets/`(占位空目录,TOML preset 由下一个 task 写入)

### 禁止做
- 不实装子命令真实逻辑(占位 `NOT_IMPLEMENTED` 即可)
- 不调用 `actionbook` 或 `postagent` 子进程(进程调用模式由后续 task 引入)
- 不新建 daemon
- 不用 sqlite / lmdb(session 状态纯文件)
- 不加 prompt-toolkit / inquirer 等交互组件(本 task 只做 non-interactive 命令)

## 完成条件

场景: `research --help` 输出所有 12 个子命令
  测试:
    包: research-api-adapter/packages/research
    过滤: `cargo run --release -- --help`
  层级: unit
  当 执行 `research --help`
  那么 stdout 包含 12 个子命令名(new list show status resume add sources synthesize close rm route help)
  并且 退出码 0
  并且 `--json` / `--verbose` / `--no-color` 出现在全局 options 段

场景: 每个未实装的子命令返回结构化 NOT_IMPLEMENTED
  测试:
    包: research-api-adapter/packages/research
    过滤: research_foundation_stubs
  层级: unit
  当 执行 `research new hello --json`(以及其他未实装命令)
  那么 stdout 是合法 JSON 含 `{"ok": false, "error": {"code": "NOT_IMPLEMENTED", ...}}`
  并且 退出码为非 0(例如 64)
  并且 `context.command` 字段为对应子命令名

场景: Session dir 契约落地为代码常量 / 枚举
  测试:
    包: research-api-adapter/packages/research
    过滤: session_dir_layout_consts
  层级: unit
  假设 新增模块 `session::layout`
  当 编译成功
  那么 有公共常量或函数导出 session 目录的每一条路径(session.md / session.jsonl /
    session.toml / raw/ / report.json / report.html)
  并且 有 slug 验证函数 `fn is_valid_slug(s: &str) -> bool`,单元测试覆盖正负例

场景: Active session 读写 API 存在
  测试:
    包: research-api-adapter/packages/research
    过滤: active_session_roundtrip
  层级: unit
  假设 调用 `set_active("foo")` + `get_active()`
  当 读写 `.active` 文件
  那么 `get_active()` 返回 "foo"
  并且 `clear_active()` 后再调 `get_active()` 返回 None

场景: Session.jsonl 事件结构有 serde 定义并 round-trip
  测试:
    包: research-api-adapter/packages/research
    过滤: session_event_serde
  层级: unit
  假设 有 enum `SessionEvent { SessionCreated, SourceAttempted, ... }`
  当 serialize 后 deserialize
  那么 结果等价
  并且 至少 7 个事件变体(session_created, source_attempted/accepted/rejected,
    synthesize_started/completed/failed, session_closed, session_removed)
  并且 每个事件都带 `timestamp` 字段(RFC3339)

场景: 本 task 不引入 daemon 或外部进程调用
  测试:
    包: research-api-adapter/packages/research
    过滤: grep / static audit
  层级: docs/review
  当 审查本 task 的 Rust 源码
  那么 没有 `std::process::Command`(除测试代码)
  并且 没有绑定 socket / 启动 subprocess 的模块

## 排除范围

- 任何子命令的真实逻辑(全部留给独立 task)
- TOML preset 加载(归 `research-route-toml-presets` spec)
- Actionbook / postagent 子进程调用(归 `research-add-source` spec)
- 交互式 prompt / TUI
- session.md 的自动生成模板(归 `research-session-lifecycle` spec)
- 跨平台的 `~/.actionbook/research/` 路径(暂定 `dirs::home_dir().join(".actionbook/research")`)
