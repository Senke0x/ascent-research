# ascent-research × hermes-agent — 使用总览

> **面向：** Sen 本人 + 未来新开的 Claude Code 会话做 research 或迭代本集成时的冷启动入口。
> **版本：** Plugin v0.1.0（2026-04-23 起）。
> **读这一份文档足够接住全部上下文；细节再跳去 `README.md` / `TESTING.md` / 源码。**

---

## 1. 项目定位

`ascent-research`（fork 自原 `autoresearch` 的增量研究 CLI）已作为 **16 个工具**
集成到 `hermes-agent`。所有网页抓取强制走 `actionbook` 浏览器，绕开 hermes
自带的 `browser_*` / `web_*` 工具。

**设计原则**：
1. 零 Rust 代码改动——全靠 `ascent-research` 已有的全局 `--json` flag + `Envelope` 输出 + `loop --iterations 1` 作为 `ascent_loop_step`。
2. 零 hermes 代码改动——plugin 走 hermes 官方 plugin system（`~/.hermes/plugins/<name>/`）。
3. 强制 actionbook——不是给 `add`/`batch` 加 flag，而是通过一个「零 postagent 规则、fallback 强制 browser」的 preset。
4. 安全护栏在 handler 层——`ascent_close` 必须 `confirm=true`；`rm`/`wiki rm`/`schema edit` 等破坏性或交互式命令不暴露给 LLM。

---

## 2. 架构一图

```
┌─────────────────────────────────────────────────┐
│  Hermes Agent (CLI / telegram / discord / ...)  │
│  toolsets: [... , ascent-research]              │
│    ↓                                             │
│  Plugin handler (Python, subprocess)             │
│    → integrations/hermes-plugin/cli.py           │
│    ↓ argv += ["--preset", "actionbook-only"]     │
│  ascent-research CLI (Rust, cargo install)       │
│    ↓ fetch::execute → Executor::Browser          │
│  actionbook browser new-tab / text / wait ...    │
│    ↓ CDP                                         │
│  Chromium (local or cloud)                       │
└─────────────────────────────────────────────────┘
                   ↓ 落地
  ~/.actionbook/ascent-research/<slug>/
    session.md, session.jsonl, session.toml
    SCHEMA.md, raw/, wiki/, report.{json,html}
```

---

## 3. 关键路径

| 东西 | 路径 |
|---|---|
| ascent-research 源码 | `~/Document/Github/ascent-research/` |
| hermes-agent 源码 | `~/Document/Github/hermes-agent/` |
| Plugin 实现（仓库内） | `ascent-research/integrations/hermes-plugin/` |
| Plugin 软链（hermes 加载点）| `~/.hermes/plugins/ascent-research` → 上面 |
| actionbook-only preset | `~/.actionbook/research/presets/actionbook-only.toml` |
| session 数据 | `~/.actionbook/ascent-research/<slug>/` |
| ascent-research 二进制 | `~/.cargo/bin/ascent-research` |
| actionbook 二进制 | `~/.superset/bin/actionbook` |
| claude CLI | `~/.superset/bin/claude` (v2.1.118) |
| codex CLI | `~/.superset/bin/codex` |
| hermes CLI | `~/.local/bin/hermes` |
| hermes 配置 | `~/.hermes/config.yaml` (352 行) |

---

## 4. 环境现状（截至 2026-04-23）

已完成：
- [x] `ascent-research` `cargo install --features provider-claude` 完成
- [x] Plugin 软链至 `~/.hermes/plugins/ascent-research`
- [x] `actionbook-only` preset 装至 `~/.actionbook/research/presets/`
- [x] 13/13 plugin→subprocess 链路检查通过（8 正例 + 5 护栏）
- [x] 误导性 API key 文档已清除（PR #2）

还差（下节 TODO 讲）：
- [ ] `~/.hermes/config.yaml` 改 `platform_toolsets`
- [ ] 重启 hermes
- [ ] `/tools list` 确认 16 工具
- [ ] TESTING.md 阶梯验证

**不需要** `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`。`provider=claude` 走 Claude Code 订阅的 Keychain token，`provider=codex` 走 ChatGPT CLI session，都是 subprocess 级复用，不读环境变量 API key。

---

## 5. TODO —— 最小上线路径

**注意：以下 Step 1 有两种方案（A 最小改动 / B 彻底屏蔽），先看下文「禁用 hermes 原生 browser/web」决定选哪个。**

### Step 1 · 编辑 `~/.hermes/config.yaml`

找到第 301-303 行：
```yaml
platform_toolsets:
  cli:
  - hermes-cli
```

- **方案 A（最小改，1 行）**：`cli:` 下再加 `- ascent-research`（browser/web 仍开，靠 prompt 让 LLM 选 `ascent_add`）
- **方案 B（推荐，~16 行）**：把 `- hermes-cli` 替换成 `_HERMES_CORE_TOOLS` 展开去掉 browser/web 后的显式列表，见 README.md「方案 B」

如果还要 telegram / discord 等消息端也走 actionbook，对应平台的 toolset 同样改。

### Step 2 · 重启 hermes

`hermes` TUI 退出 → 重开。如果有 gateway 常驻，一并重启。

### Step 3 · 验证工具加载

hermes 里：
```
/tools list
```
应看到一个 toolset `ascent-research`（或 `🔌 Ascent Research`）下 16 个工具。方案 B 下不该再看到 `browser_*` / `web_*`。

没出现的话：
```bash
tail -50 ~/.hermes/logs/*.log 2>/dev/null | grep -iE 'plugin|ascent'
readlink ~/.hermes/plugins/ascent-research
```

### Step 4 · 烟雾 prompt

```
List all my ascent-research sessions.
```

LLM 应调 `ascent_list`，回 2 个 session（`gpt-image-2` / `gpt-image-2-v2`）。

### Step 5 · 按 TESTING.md 走完 10 级阶梯

`integrations/hermes-plugin/TESTING.md` 里 10 步从免费 smoke 到付费 synthesize。总预算：零 API 费用（走 Claude Code 订阅）+ 订阅额度分摊。

---

## 6. 16 个工具 —— 清单与 LLM trigger

> **命名规则**：都是 `ascent_*` 前缀。toolset 名为 `ascent-research`。
> **返回**：全部是 Envelope JSON 字符串（`{"ok": bool, "data": ..., "error": ...}`）。
> **必传参数**：只有 `ascent_show`、`ascent_wiki_show`、`ascent_new` 有必填的业务参数；其它大多 `slug` 可选（缺则走 active session）。

### 6.1 会话生命周期（5 个）

| 工具 | 作用 | 典型 LLM 触发词 | 破坏性 |
|---|---|---|---|
| `ascent_new` | 新建 session（自动用 `actionbook-only` preset） | "start research on X" / "create a session titled ..." | - |
| `ascent_list` | 列出全部 session，可按 tag 过滤 / tree 展示 | "list my sessions" / "show all research" | - |
| `ascent_show` | 打印 session.md 原文（已被 `_run()` 包成 JSON） | "show me session X" / "what's in session X" | - |
| `ascent_status` | 摘要：source 计数、wiki 页数、closed_at | "status of X" / "how is session X" | - |
| `ascent_close` | 关闭 session（`closed_at` = now）| "close session X" | ✋ 必须 `confirm: true` |

**未暴露**：`rm`、`resume`、`fork`（已被 `ascent_new --from_slug` 覆盖）、`series`（已被 `ascent_list --tag` 覆盖）。

### 6.2 抓取（3 个）

| 工具 | 作用 | 典型 LLM 触发词 |
|---|---|---|
| `ascent_add` | 单 URL 抓取（actionbook browser） | "fetch <url>" / "add this link" |
| `ascent_batch` | 并发抓 N 个 URL（默认 4 线程） | "fetch these URLs in parallel" / "batch add" |
| `ascent_add_local` | 摄入本地文件 / 目录（glob + 尺寸上限） | "ingest ~/docs" / "add these local files" |

**小心**：并发 `ascent_add` 在同一 slug 下会共享 `research-<slug>` actionbook session，可能撞 "profile already owned" 错误。推荐单次并发用 `ascent_batch` 而不是循环多次 `ascent_add`。

### 6.3 分析（2 个）

| 工具 | 作用 | 典型 LLM 触发词 |
|---|---|---|
| `ascent_coverage` | 事实完整度 + `report_ready` blockers | "how complete is session X" |
| `ascent_diff` | 抓了未引用 vs. 引用了没抓 | "what sources are unused" / "any hallucinations" |

### 6.4 Wiki（4 个）

Wiki 是每个 session 的 "外部知识层"（`wiki/<slug>.md`，YAML frontmatter 含 `kind: entity | concept | source | comparison | analysis | ...`）。

| 工具 | 作用 | 典型 LLM 触发词 |
|---|---|---|
| `ascent_wiki_list` | 列 wiki 页（slug + bytes + kind） | "list wiki pages" |
| `ascent_wiki_show` | 读一页原文 | "show wiki page X" |
| `ascent_wiki_query` | 对 wiki 问答，可选 `save_as` 存为新页 | "based on wiki, what is X" / "ask wiki about Y and save as Z" |
| `ascent_schema_show` | 打印 SCHEMA.md（user-authored 研究指引） | "show the research schema" |

**`wiki_query` 是 LLM-backed**，默认 `provider=claude`，走 Claude Code 订阅。

**未暴露**：`wiki rm`（破坏性）、`wiki lint`（内部健康检查）。

### 6.5 生成（3 个）

| 工具 | 作用 | 典型 LLM 触发词 |
|---|---|---|
| `ascent_synthesize` | session → `report.json` + `report-brief.md`（featured）+ report.html（byproduct） | "synthesize the report" / "finalize X" |
| `ascent_illustrate_hero` | 通过 actionbook 驱动 ChatGPT，用真实 GPT-Image-2 生成一张 Apple 风格 hero 封面，写入 `images/hero.png` 并 prepend 到 `report-brief.md` | "generate a hero cover for it" / "illustrate the report" |
| `ascent_loop_step` | autonomous loop 的 **一步**（读 SCHEMA + state → 选 action → 执行） | "run one research-loop step" |

**LLM-backed**：`synthesize`（bilingual 时），`illustrate_hero`（Claude 起草 prompt + ChatGPT 生成），`loop_step`。

**MD 是一等输出**：v0.2 起 `synthesize` 内部 chain 到 `report --format brief-md`。返回 envelope 里 `data.report_md` 指向 `<slug>/report-brief.md`。HTML 仍产出但不 feature。

**`illustrate_hero` 流程**（见 §7a）：无需 API key，复用你已登录的 chatgpt.com Chrome session；每次调用强制重生成（覆盖旧图）；失败即抛错，MD 在失败路径上不会被修改——LLM / 你重调一次即可。

`loop_step` 故意只暴露单步，不暴露完整 `loop`——hermes 没通用 cancel 协议，长任务不可控。想跑多步让 hermes 的 agent loop 自己循环调。

---

## 7a. `ascent_illustrate_hero` workflow 细节

```
User → hermes: "Generate a hero cover for <slug>."
  ↓
Plugin handler (illustrate.py:generate_hero):
  1. _ensure_synthesized(slug) → report.json + report-brief.md 都在?
  2. _read_topic(report.json) → topic 字符串
  3. _craft_prompt():
     • 若 prompt_override 传了 → 直接拼 Apple style 后缀
     • 否则 subprocess → ascent-research wiki query
       "Draft an image-generation prompt..." --provider claude
       → Claude 返回 metaphor-based prompt，拼 Apple style 后缀
  4. actionbook browser new-tab https://chatgpt.com/?new=chat
     --session ascent-hero-gen
  5. actionbook browser wait network-idle (15s)
  6. actionbook browser wait element #prompt-textarea (20s)
     ↑ 这一步**失败 = NOT_LOGGED_IN**（登录态探测）
  7. actionbook browser type #prompt-textarea "Generate an image. <prompt>"
  8. actionbook browser press Enter
  9. actionbook browser wait element
     [data-message-author-role='assistant']:last-of-type img (180s)
     ↑ 失败时读 assistant 文本，映射到 RATE_LIMITED / CONTENT_POLICY /
       IMAGE_NOT_PRODUCED
 10. actionbook browser html <img> → 抽 src
 11. urllib 下载 src → images/hero.png
     失败时退路：actionbook browser screenshot --element <img>
 12. prepend ![hero](images/hero.png) 到 report-brief.md（幂等）
 13. 写 images/hero.meta.json（prompt + src + model + timestamp）
  ↓
Return {ok, data: {hero_image, source_url, md_path, meta, via: "chatgpt"}}
```

**默认行为**：
- **总是覆盖**既有 hero（per user policy）
- **失败即抛错**——MD 未被修改，可重试
- **session 隔离**：actionbook session 固定叫 `ascent-hero-gen`，跟 research session 不冲突，但**共享同一 Chrome profile**（所以能复用你的 ChatGPT 登录）

**FLUX fallback**（可选 `use_flux_fallback: true`）：
ChatGPT 路径任何一步失败时自动回退到 hermes 的 FLUX 2 Pro（via Nous managed gateway）。默认 **off** —— 配合 fail-loud 策略。想开就在 tool args 传 `use_flux_fallback: true`。

**dry_run 模式**：`dry_run: true` 只走到 Step 3（起草 prompt），返回预览，不驱动浏览器。适合调试 prompt 效果。

## 7. 禁用 hermes 原生 browser/web —— 方案对比

hermes 的 `hermes-cli` composite（见 `~/Document/Github/hermes-agent/toolsets.py:31` 的 `_HERMES_CORE_TOOLS`）展开包含：

```
web_search, web_extract,
terminal, process,
read_file, write_file, patch, search_files,
vision_analyze, image_generate,
skills_list, skill_view, skill_manage,
browser_navigate, browser_snapshot, browser_click,
browser_type, browser_scroll, browser_back,
browser_press, browser_get_images,
browser_vision, browser_console,
text_to_speech,
todo, memory
```

### 方案 A · 最小改动

```yaml
platform_toolsets:
  cli:
  - hermes-cli
  - ascent-research   # ← 加这一行
```

**效果**：LLM 同时看到 hermes 的 `browser_navigate` 和我们的 `ascent_add`。靠工具 description 和 system prompt 引导选择。
**何时用**：验证期快速启动 / 不确定是否彻底切断原生 browser。

### 方案 B · 彻底屏蔽（推荐）

```yaml
platform_toolsets:
  cli:
  - terminal
  - process
  - read_file
  - write_file
  - patch
  - search_files
  - vision_analyze
  - image_generate
  - skills_list
  - skill_view
  - skill_manage
  - text_to_speech
  - todo
  - memory
  - ascent-research
```

**效果**：`browser_*` + `web_*` 彻底消失，LLM 根本没法调。
**何时用**：正式使用期。确保抓取路径可控。

方案 B 还一个 byproduct：LLM tool list 少了 12 个工具，system prompt 体积小一点。

### 方案 C（会话内临时）

在 hermes session 里：
```
/tools disable browser_navigate
/tools disable browser_snapshot
/tools disable web_search
/tools disable web_extract
# ... 逐个
```

**何时用**：临时调试。不持久。

---

## 8. 一键 prompt —— skill 激活后（推荐用法）

安装脚本会把 `skill/SKILL.md` 装到 `~/.hermes/skills/ascent-research/SKILL.md`。Hermes 启动时把它注入系统 prompt——你用 trigger 词（"research" / "investigate" / "deep dive" / "ascent-research" 等）开口时，LLM 自动知道完整的 6 步链。

**一行示例**（不需要再写长 prompt）：

```
Use ascent-research to research <topic> and generate a hero image.
```

LLM 自动串：
```
ascent_new → ascent_batch (5-10 stable URLs)
          → ascent_wiki_query (save_as overview)
          → ascent_loop_step (max_actions=3)
          → ascent_synthesize
          → ascent_illustrate_hero
          → 汇报 slug / MD 路径 / hero.png 路径
```

**想跳某步**：
- "quick research on X"（省 loop_step）
- "research X but skip the image"（省 illustrate_hero）
- "rebuild research on X"（先 `rm -rf ~/.actionbook/ascent-research/*` 再起）

**手动每步**：skill 不是强制。你还是可以精准地说 `ascent_add <url> to session <slug>` 做单步操作，LLM 不会多嘴。

## 8b. 手写 prompt 模板（不依赖 skill）

### 8.1 新课题开研

```
Start a new ascent-research session on "<topic>".
Fetch these sources via actionbook batch:
- <url1>
- <url2>
- <url3>

Then ask the wiki: "<deep question>" and save the answer as <page-slug>.
Finally synthesize into a report.
```

触发顺序：`ascent_new` → `ascent_batch` → `ascent_wiki_query(save_as=...)` → `ascent_synthesize`。

### 8.2 续研既有 session

```
Run `ascent_list` to find session <slug-hint>, then show me its status
and coverage. What are the biggest gaps?
```

或者直接：

```
For session <slug>, run one research-loop step with max 3 actions and
claude provider. Tell me what it added.
```

### 8.3 单源快加

```
In session <slug>, add https://<url>
```

### 8.4 Wiki 检索（不新增内容）

```
In session <slug>, what does the wiki say about <topic>?
(Don't save a new page — just answer.)
```

### 8.5 本地文件摄入

```
In session <slug>, ingest these local markdown files as sources:
~/Document/notes/runtime-comparison.md
~/Document/notes/tokio-internals.md
```

### 8.6 编辑器视角：查看底稿

```
In session <slug>, show me:
1. the session.md (ascent_show)
2. the coverage report (ascent_coverage)
3. the diff — unused sources vs hallucinations (ascent_diff)
```

### 8.7 清理（需要 confirm）

```
Close session <slug>. I confirm.
```

LLM 第一次调会收到 `{"error": "... requires confirm=true"}`，它应该问你要不要 confirm，然后带 `confirm: true` 再调。

---

## 9. 故障诊断速查

| 症状 | 原因 / 处理 |
|---|---|
| `/tools list` 看不到 `ascent_*` | `readlink ~/.hermes/plugins/ascent-research` 检查软链；`tail -50 ~/.hermes/logs/*.log | grep -i ascent` 看加载错误 |
| `{"error": "binary 'ascent-research' not found on PATH"}` | `~/.cargo/bin` 不在 PATH；或重跑 `./install.sh` |
| `{"error": "binary 'actionbook' not found on PATH"}` | 装 actionbook；或设 `ACTIONBOOK_BIN` |
| `ascent_loop_step` / `wiki_query` 报 `PROVIDER_NOT_AVAILABLE` | `cargo install --features provider-claude` 或 `provider-codex` 未包含；或对应 CLI 未登录 |
| `ascent_loop_step` cc-sdk auth 报错 | Claude Code session 过期——开 `claude` 发一句话刷新 |
| `browser profile already owned by session ...` | actionbook 单 profile 只能一个 session：`export ACTIONBOOK_BROWSER_SESSION=<holder>`，或关掉占用方 |
| LLM 不挑 ascent，跑去用 `browser_navigate` | 你在方案 A 下；改方案 B，或在 system prompt 里加「prefer ascent_* over browser_*」 |
| `ascent_close` 不小心关了 session | 编辑 `~/.actionbook/ascent-research/<slug>/session.toml` 删 `closed_at`，附赠一条 `session_resumed` 事件到 `session.jsonl`（见本仓库 PR #1 incident note） |
| `ascent_illustrate_hero` → `REPORT_MD_MISSING` | 先跑 `ascent_synthesize`（会自动 chain `report --format brief-md`） |
| `ascent_illustrate_hero` → `NOT_LOGGED_IN` | 打开 chatgpt.com 在 Chrome 登录，保持 tab 或 cookie 有效，重调 |
| `ascent_illustrate_hero` → `RATE_LIMITED` | ChatGPT Plus 每日图生成上限；等重置 / 升 Pro / `use_flux_fallback: true` |
| `ascent_illustrate_hero` → `CONTENT_POLICY` | prompt 被 ChatGPT 拒；传 `prompt_override` 重写 prompt 躲避敏感词 |
| `ascent_illustrate_hero` → `IMAGE_NOT_PRODUCED` 180s 超时 | 看 `<slug>/images/hero-debug.html` 和 `hero-debug.png` 定位；可能 DOM 变了，改 `illustrate.py::SELECTORS` |
| `ascent_illustrate_hero` → `PROMPT_DRAFT_FAILED` | Claude Code session 失效——开 `claude` 刷新；或传 `prompt_override` 绕过起草 |

---

## 10. 文件 / 命令级别索引（deep link）

| 关注点 | 去哪看 |
|---|---|
| 工具 argv 是怎么拼的 | `integrations/hermes-plugin/cli.py:_BUILDERS` |
| synthesize / illustrate_hero 特殊 handler | `cli.py::_handle_synthesize` / `_handle_illustrate_hero` |
| Hero 生成 workflow | `integrations/hermes-plugin/illustrate.py::generate_hero` |
| Hero error codes + 处理 | `illustrate.py::HeroError` + §9 故障诊断表 |
| ChatGPT DOM 选择器（维护点） | `illustrate.py::SELECTORS` |
| Apple 风格 prompt 后缀 | `illustrate.py::APPLE_STYLE_SUFFIX` |
| 每个工具的 JSON schema | `integrations/hermes-plugin/schemas.py` |
| plugin 注册入口 | `integrations/hermes-plugin/__init__.py:register()` |
| preset 定义 | `integrations/hermes-plugin/presets/actionbook-only.toml` |
| 安装脚本 | `integrations/hermes-plugin/install.sh` |
| 端到端测试 ladder | `integrations/hermes-plugin/TESTING.md` |
| hermes plugin loader | `~/Document/Github/hermes-agent/hermes_cli/plugins.py` |
| hermes tool registry | `~/Document/Github/hermes-agent/tools/registry.py` |
| hermes 工具组定义 | `~/Document/Github/hermes-agent/toolsets.py:_HERMES_CORE_TOOLS` |
| ascent CLI 主入口 | `packages/research/src/cli.rs:run()` |
| Envelope 定义 | `packages/research/src/output.rs:Envelope` |
| fetch 路由分发 | `packages/research/src/fetch/mod.rs:execute` |
| actionbook 3-step 实现 | `packages/research/src/fetch/browser.rs:run` |
| ClaudeProvider (cc-sdk) | `packages/research/src/autoresearch/claude.rs` |
| CodexProvider (app-server) | `packages/research/src/autoresearch/codex.rs` |
| route preset schema | `packages/research/src/route/rules.rs:Preset` |

---

## 11. 发展路线（非紧急，记录给将来）

**优先级中**：
- 给 `ascent-research` 加原生 `reopen` 子命令——避免误 close 要改 toml 回滚
- Plugin `on_session_start` hook 在方案 A 下硬性警告 browser/web 仍开

**优先级低**：
- 加 `ascent_reopen` 工具（上面 reopen 的包装）
- Plugin 升级为 Rust MCP server（`ascent-research mcp-serve`）——Claude Code / Codex 也能共用同一套工具
- `ascent_synthesize`、`ascent_loop_step` 注册时加 `max_result_size_chars` 参数——大 session 会超 hermes 默认 result cap
- 多 slug 并发时给 actionbook 用独立 session（session nonce）避免 profile 锁冲突

---

## 12. 最近历史

| 日期 | PR | 变动 |
|---|---|---|
| 2026-04-23 | #1 | `feat(hermes-plugin)` — 初版 16 tools + install + preset + tests |
| 2026-04-23 | #2 | `docs(hermes-plugin)` — 澄清无需 API key，改文案 |

安装期间曾意外 close 过 `gpt-image-2-v2`（`ascent_close {confirm: true}` 无 slug，走了 active session）。已手工复原：删 `session.toml` 的 `closed_at` + 附 `session_resumed` 事件到 `session.jsonl`。`status` 现在显示 `open`。数据零丢失。

---

## 13. 给未来 Claude Code 会话的话

如果你是接手迭代这个集成的新会话：

1. **先读这份 `USAGE.md` + `README.md` + `TESTING.md`**，三份加起来 ~700 行，能接住所有上下文。
2. **跑 `./install.sh --skip-build`** 确认 plugin 还在位（软链可能被清理）。
3. **别直接 commit 到 main**——走 feature branch + 内部 PR（`gh pr create --base main`），合并策略 `--merge`（保留合并 commit，和项目历史保持一致）。
4. **commit message 用 conventional commits**：`feat(hermes-plugin):` / `fix(hermes-plugin):` / `docs(hermes-plugin):`；**不要**加 `Co-Authored-By`（项目全局禁用，见 `~/.claude/settings.json`）。
5. **破坏性操作（close / rm / 改 `~/.hermes/config.yaml`）前先 backup**。
6. **改 `cli.py` builders 后**必须手动 `python3 -c 'from cli import _BUILDERS, run_tool; ...'` 简单测一下，再开 PR。
7. **如果要加工具**：照着 `ADD_LOCAL` 模板，schema + argv builder + 加到 `_BUILDERS` dict + `ALL_SCHEMAS` list，五处改动保持一致。
