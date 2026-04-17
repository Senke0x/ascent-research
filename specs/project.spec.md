spec: project
name: "research-api-adapter"
tags: [coordination, research, postagent, active-research]
---

## 意图

`research-api-adapter` 是一个跨项目协调 repo，用来把 `postagent`（API 客户端）作为
API-first source adapter 接入 `active-research`（研究 skill），让研究编排器在遇到
结构化源（Hacker News / GitHub / arXiv 等）时优先走 HTTP API 而不是浏览器。

本 repo 不直接承载可执行代码，只承载：设计文档（DESIGN.md）、task 合同（specs/）、
跨项目工作追踪脚本（scripts/ 与 tests/）。所有实际改动都落到上游：
- `postagent` 仓库的 Rust 源码
- `~/.claude/skills/active-research/SKILL.md`

## 已定决策

- 研究入口只保留 `active-research` / `deep-research` 现有命令，不新起 CLI
- 三层架构：`active-research`（orchestrator）/ `postagent`（API adapter）/ `actionbook browser`（UI adapter）
- 命令面真相源：`packages/cli/src/cli.rs` 的 `BrowserCommands` enum
- 验证脚本一律使用 bash / shell，不引入 Python / Node 测试运行时
- 每个跨项目修改都通过 task spec 追踪，禁止"无合同绕过"修改上游文件

## 边界

### 允许修改
- /Users/zhangalex/Work/Projects/actionbook/research-api-adapter/**

### 禁止做
- 不把任何可执行代码从上游 repo 复制到本 repo
- 不引入新的编程语言运行时（除 bash 之外）
- 不为了本项目创建新的用户命令入口

## 完成条件

场景: 所有 task spec 通过 lint 最低分门槛
  测试:
    包: research-api-adapter
    过滤: agent-spec lint specs/*.spec.md --min-score 0.7
  层级: human-review
  命中: specs/*.spec.md
  假设 仓库下 `specs/` 存在至少一份 task spec
  当 执行 `agent-spec lint` 对每一份 task spec 检查
  那么 每份 spec 的 quality 分数不低于 70%

场景: 跨项目改动必须匹配一份本 repo 的 task spec
  测试:
    包: research-api-adapter
    过滤: 人工审计跨项目 commit
  层级: human-review
  命中: postagent, ~/.claude/skills/active-research/SKILL.md
  假设 有新改动落到 `postagent` repo 或 active-research SKILL.md
  当 该改动进入代码审查流程
  那么 存在一份 `specs/*.spec.md` 明确声明其 intent、decisions、boundaries
  并且 该 spec 的 allowed changes 覆盖改动路径

场景: 产出的研究报告满足最低质量门
  测试:
    包: research-api-adapter
    过滤: 人工审计 output/*.json
  层级: human-review
  命中: /active-research 流程产出的 json-ui 报告
  假设 一次 `/active-research` 执行已经生成 `output/<slug>.json`
  当 审查该 JSON 报告
  那么 至少包含 2 种 distinct source type(API 源 + 浏览器源 至少各 1 个)
    — 但当主题本质上只有单一源类型(e.g. 纯学术论文 → 只有 arXiv API)时允许豁免,
    需在 Methodology 段落显式声明豁免理由
  并且 至少包含 4 条 distinct 的 finding 或 metric 条目(在 ContributionList / MetricsGrid / Table 之一)
  并且 包含 Methodology 段落,列出所有实际使用过的源,以及通过 content smell test 的证据
  并且 `Sources` LinkGroup 引用的每一条 URL,都在 Methodology 段落里有对应的 API/browser 路由说明
  并且 **不**包含使用过但被 smell test drop 掉的源(禁止把空数据静默合成到报告里)

场景: 研究工作流遵循 observability-over-terseness 原则
  测试:
    包: research-api-adapter
    过滤: 人工审计 skill 修订
  层级: human-review
  命中: ~/.claude/skills/active-research/SKILL.md
  假设 研究工作流的原语层(`browser text` / `postagent send`)或更上层的编排发生改动
  当 新增任何 "高层一步到位" 的命令或宏
  那么 必须保留每个中间步骤状态(URL / 字节数 / warning)对 LLM 可观测
    — 不得把 N 个原语折成一个黑盒 result,否则 silent failure 会导致空报告被合成
  并且 新命令的 response 结构中每个子步骤的 {success,url,bytes,warnings} 都可独立断言
