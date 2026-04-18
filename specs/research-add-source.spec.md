spec: task
name: "research-add-source"
inherits: project
tags: [research-cli, fetch, smell-test, phase-3]
estimate: 1d
depends: [research-cli-foundation, research-session-lifecycle, research-route-toml-presets]
---

## 意图

实装 `research add <url>` 和 `research sources` —— 这是 `research` CLI 的"核心动词"。
用户给一个 URL,CLI 自动完成:**route → 以子进程调 postagent 或 actionbook → smell
test → 存 raw/ → append session.jsonl → 更新 session.md Sources 段**。LLM 不再需要
记住步骤,也不能绕过 smell test。

Silent failure 在本层彻底杜绝:每一步失败都产生 `source_rejected` 事件,带结构化原因。
accepted 源才会进入 synthesize 环节。

## 已定决策

- 命令:`research add <url> [--slug <s>] [--timeout <ms>] [--readable|--no-readable]`
  - 无 `--slug` 读 `.active`
  - `--readable` 默认根据 URL 推断(包含 `/blog/`, `/post/`, `/rfd/`, 路径长度>=3 → readable;
    其它 → 不 readable)
- 流程(CLI 内部固定,无 flag 绕过):
  1. Load session(读 session.toml 的 `preset`)
  2. Route(调内部 route 模块,或直接 `research route` 的 library 版本)
  3. Log `source_attempted` 事件到 jsonl(含 URL + 路由结果)
  4. Subprocess:
     - `executor == "postagent"` → spawn `postagent send --anonymous <api_url>`
     - `executor == "browser"` → spawn `actionbook browser new-tab + wait-idle + text`
       序列(3 个子进程调用,每步 JSON 模式,捕获输出)
       **或**:暂时先只用 `actionbook browser new-tab + wait network-idle + text`(不
       在 v1 MVP 中 parallel;后续优化)
  5. Smell test(本 task 新增,见下)
  6. 通过 → 写 raw/<n>-<kind>-<host>.json,jsonl 追加 `source_accepted`
  7. 不通过 → jsonl 追加 `source_rejected`,不写 raw/,子进程原始输出**也**落盘到
     `raw/<n>-<kind>-<host>.rejected.json`(便于人工调试,但不进 synthesize)
- Smell test 规则(硬编码,不从 config 读):
  - API 响应:HTTP status 2xx(通过 postagent 的 response envelope 字段)+ body 非空
    (JSON 至少一个非空 array/object 键;atom 至少 1 个 `<entry>`)
  - Browser 响应:`context.url` 匹配请求 URL(忽略 trailing slash / query 规范化),
    不能是 `about:blank` 或 `chrome-error://`;`data.value` 长度 >= 500 字符(article)
    或 >= 100 字符(其它)
  - 阈值在常量里,future task 可配置
- Rejected reasons(枚举,进入 jsonl):
  - `fetch_failed`:子进程退出码非 0 或超时
  - `wrong_url`:context.url 不匹配请求(about:blank 类)
  - `empty_content`:长度低于阈值
  - `api_error`:HTTP status 4xx/5xx
  - `duplicate`:该 URL 已在本 session 的 raw/ 里(去重检查)
- Source trust score(持久化到 jsonl,非 gate):
  - API (executor=postagent) + smell passed: **+2**
  - Article (browser + readable + len ≥ 2000): **+1.5**
  - Browser page (smell passed,其它): **+1**
  - Rejected: **不记分**(该条用 rejected status 标记)
  score 写入 `source_accepted` 事件的 `trust_score` 字段
- `research sources [--slug <s>] [--rejected] [--json]`:
  - 默认只列 accepted
  - `--rejected` 也列被拒绝的源
  - JSON 模式返回完整结构(trust_score, url, kind, executor, path_on_disk, rejected_reason)
- **不**在本 task 里做 parallel add(single-URL,single-session-at-a-time);后续 task
  可做 `research add-batch <urls-file>`
- **子进程错误**:subprocess panic / crash 视为 `fetch_failed`;如果子进程找不到
  (which lookup fail)直接 fatal `MISSING_DEPENDENCY`
- **进程级并发**:允许**多个 `research add` 并发跑**(不同 URL),但对同一 session 的
  jsonl 写入必须走 file-lock(flock)避免行交织
- **session.md 的 Sources 段**:用一个 markdown marker 标识起止,CLI 在两个 marker
  之间 atomic 重写整段(从 jsonl 的 accepted 事件列表生成)

## 边界

### 允许修改
- `research-api-adapter/packages/research/src/commands/add.rs`
- `research-api-adapter/packages/research/src/commands/sources.rs`
- `research-api-adapter/packages/research/src/fetch/`(postagent / actionbook 子进程封装)
- `research-api-adapter/packages/research/src/smell/`(smell test 模块)
- `research-api-adapter/packages/research/src/session/log.rs`(jsonl append + file-lock)
- `research-api-adapter/packages/research/tests/`(E2E 用 mock 子进程 + 真实 fixture)

### 禁止做
- 不直接发 HTTP 或开 browser(所有 IO 穿过 `postagent` / `actionbook` 子进程)
- 不调用 LLM(score 是 heuristic,不是 AI 判断)
- 不做 semantic dedup(只做 URL string dedup,忽略 query param 排序等归一化)
- 不做 cross-session cache(后续 task,未决)
- 不做 parallel multi-URL add(single-URL per invocation)
- 不在本 task 改 preset / route 规则(route 来自依赖 task)
- 不改 actionbook 或 postagent 源码(只以用户身份调)

## 完成条件

场景: API 路径 add 一个 HN 源到 accepted
  测试:
    包: research-api-adapter/packages/research
    过滤: add_hn_api_accepted
  层级: integration(用真实 postagent 子进程 + mock HN response or 真实 HN)
  假设 session "s1" 已 new
  当 `research add "https://news.ycombinator.com/item?id=42" --slug s1`
  那么 退出码 0
  并且 `~/.actionbook/research/s1/raw/1-hn-item-news.ycombinator.com.json` 存在且非空
  并且 session.jsonl 末尾两行分别是 `source_attempted` + `source_accepted`
  并且 `source_accepted.trust_score` = 2
  并且 session.md 的 `## Sources` 段含该 URL

场景: Browser 路径 add 一个博客到 accepted
  测试:
    包: research-api-adapter/packages/research
    过滤: add_blog_browser_accepted
  层级: integration
  假设 session "s2" 已 new
  当 `research add "https://corrode.dev/blog/async/" --slug s2`
  那么 退出码 0
  并且 raw/ 里有 browser 抓取结果
  并且 `trust_score` = 1.5(readable article)

场景: Smell test 拒绝空内容
  测试:
    包: research-api-adapter/packages/research
    过滤: add_rejects_empty_content
  层级: integration
  假设 目标 URL 浏览器抓取返回 < 100 字符
  当 `research add <url>`
  那么 退出码非 0(但不是 crash),error code `SMELL_REJECTED`
  并且 jsonl 有 `source_rejected` 事件,reason = `empty_content`
  并且 raw/ 里**没有** accepted 文件,但有 `<n>-<kind>-<host>.rejected.json`(debug 留存)
  并且 session.md Sources 段**不**含该 URL

场景: Smell test 拒绝 about:blank
  测试:
    包: research-api-adapter/packages/research
    过滤: add_rejects_wrong_url
  层级: integration
  假设 子进程 browser 返回 `context.url: "about:blank"`(模拟 issue #004 类 race)
  当 `research add <url>`
  那么 reject reason = `wrong_url`

场景: 重复 URL 被 duplicate 拒绝
  测试:
    包: research-api-adapter/packages/research
    过滤: add_duplicate_same_session
  层级: integration
  假设 URL X 已 accepted
  当 对同 session 再次 `research add X`
  那么 reject reason = `duplicate`
  并且 raw/ 目录没有多出文件

场景: `research sources` 分列 accepted / rejected
  测试:
    包: research-api-adapter/packages/research
    过滤: sources_list_modes
  层级: unit
  假设 session 有 3 accepted + 2 rejected
  当 `research sources --json`
  那么 `.data.accepted` 长度 3,每项含 {url, kind, executor, trust_score, path}
  并且 `.data.rejected` 不出现(默认隐藏)
  当 `research sources --rejected --json`
  那么 `.data.rejected` 长度 2,每项含 {url, reason}

场景: 并发 add 到同一 session 不破坏 jsonl
  测试:
    包: research-api-adapter/packages/research
    过滤: add_concurrent_jsonl_integrity
  层级: integration
  假设 session "p1" 已 new
  当 并行跑 3 个 `research add <url-N>`(不同 URL,都能匹配 API 规则)
  那么 session.jsonl 每行都是合法 JSON(无行交织)
  并且 `source_accepted` 事件数量 = 3(全部入账)

场景: 缺失 postagent / actionbook binary 时清晰报错
  测试:
    包: research-api-adapter/packages/research
    过滤: add_missing_dependency
  层级: unit
  假设 `postagent` 不在 PATH
  当 `research add <hn-url>`
  那么 error code `MISSING_DEPENDENCY`
  并且 error message 指出缺失的 binary 名 + 安装建议

## 排除范围

- 批量/并行 add(`add-batch` 是未来 task)
- Cross-session cache(同 URL 跨 session 复用下载)
- 自定义 smell test 阈值(常量驱动,后续 task 可配置)
- AI 参与的源筛选(trust score 是规则式,不是 LLM 判断)
- session.md 的 Progress 段自动更新(那是 LLM 的工作,CLI 只维护 Sources 段)
- 历史 rejected 源的 retry(用户重跑 add 即可)
- 远程/云端 session 同步
- rate limit 限速逻辑(子进程自己处理各源的 rate limit)
