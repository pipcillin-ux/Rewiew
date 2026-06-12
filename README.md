# NLR-workflow

**Narrative Literature Review workflow — 通用、人机协作的叙述性综述工作流**

这个仓库是一套用于生物医学及相关科研主题的叙述性文献综述
（Narrative Literature Review, NLR）工作流模板。它把两类流程合在一起：

- 可执行的工程流水线：PubMed 检索、AI 初筛、核心文献选择、资料提取、Zotero/Pandoc 导出。
- 人类写作流程：选题判断、论点框架、章节级补充检索、逐句事实核查、最终引用校验。

本模板默认不绑定任何具体主题。开始前必须先填写
`config/review_topic.yml`；只要配置里仍有 `REPLACE_WITH_...` 占位符，脚本会
直接报错，避免误用旧主题。

---

## 工作流总览

| Phase | 目标 | 输入 | 动作 | 输出 | 人工检查点 |
|---|---|---|---|---|---|
| 0 | 选题与框架 | 研究方向、目标期刊、特刊要求 | 明确读者、问题意识、综述边界和潜在论点 | 完成的 `config/review_topic.yml` | 人决定主题，不让 AI 直接替代立意 |
| 1 | 宽检索建材料池 | PubMed 检索式 | `scripts/pubmed_search.py` | `search/pubmed_results.csv` | 检索量是否足以支撑框架，是否过宽/过窄 |
| 2 | 初筛与核心集 | 检索结果 | `scripts/batch_screen.py`、人工复查、`scripts/select_core_papers.py` | `screening/final_screened.csv`、`core_screened.csv` | `Score=1` 必须人工决定 |
| 3 | 资料获取与提取 | 核心文献、摘要/PDF | `scripts/download_sources.py`、`scripts/extract_notes.py` | `extractions/*.md` | 数字、队列、数据集、结论是否可追溯 |
| 4 | 综合与大纲 | 提取笔记 | 聚类、gap 分析、生成大纲 | `synthesis/*.md`、`outline/outline_current.md` | 大纲是否由论点驱动，而不是论文罗列 |
| 5 | 分章节写作 | 大纲、提取笔记 | `/lit-draft` 或逐节写作提示 | `draft/*.md`、`manuscript_v1.md` | 每段是否有明确主张和代表性证据 |
| 6 | 事实审查与润色 | 初稿、提取笔记、原文 | `/lit-audit`、逐句核查、去 AI 痕迹、门控检查 | `manuscript_v2-v5.md`、审查报告 | 含引用的句子必须被来源支持 |
| 7 | 引文与 Word 导出 | 最终稿、Zotero、Better BibTeX | `/lit-cite`、Pandoc + `zotero.lua` | `manuscript.docx` | Word 中 Zotero 引文与参考文献一致 |

---

## 环境准备

### 1. 安装依赖

```bash
uv sync
```

始终使用 `uv run python scripts/xxx.py` 运行脚本，使用 `uv add <package>` 添加依赖，
不要直接 `pip install`。

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写真实值：

```dotenv
ENTREZ_EMAIL=your_email@example.com
NCBI_API_KEY=your_ncbi_api_key
DEEPSEEK_API_KEY=your_deepseek_key
SCREEN_MODEL=deepseek-chat
EXTRACT_MODEL=deepseek-chat
ZOTERO_COLLECTION=Your-Review-Collection
```

`.env` 已被 `.gitignore` 忽略，不要提交。

### 3. 系统工具

Phase 7 需要 Pandoc：

```bash
brew install pandoc
```

Zotero 需要安装 Better BibTeX 插件，用于生成稳定 citekey 和导出
`references/library.bib`。

---

## Phase 0：选题与配置

在跑脚本之前，先把综述问题说清楚。建议人工完成这些判断：

- 目标读者是谁：临床医生、方法学研究者、转化医学团队，还是政策/管理读者。
- 综述要解决什么张力：证据碎片化、技术落地困难、机制不清、临床验证不足等。
- 哪些文献必须纳入：指南、里程碑方法、代表性临床研究、关键负面结果。
- 哪些文献排除：纯背景、纯机制、纯技术、动物实验、会议摘要等，按主题决定。
- 目标期刊/特刊是否有字数、图表、结构或语言要求。

然后填写 `config/review_topic.yml`。至少替换：

- `project.*`
- `pubmed.variables.domain_terms`
- `pubmed.variables.method_terms`
- `screening.system_prompt`
- `core_selection.category_quotas`
- `core_selection.categories`

如果配置未完成，任何脚本都会快速失败，并提示仍含占位符的位置。

---

## Phase 1：文献检索

运行：

```bash
uv run python scripts/pubmed_search.py --config config/review_topic.yml
```

脚本会读取 `pubmed.queries`，逐条检索 PubMed，按 PMID 去重，并输出：

```text
search/pubmed_results.csv
```

建议第一轮检索稍宽，目标是建立 200-400 篇左右的材料池，方便 AI 辅助判断
领域结构和潜在写作角度。若结果太少，放宽领域词；若结果太杂，增加主题边界或
方法词。

---

## Phase 2：AI 初筛、人工复查、核心文献选择

### 2.1 AI 初筛

```bash
uv run python scripts/batch_screen.py --config config/review_topic.yml
```

输出：

- `screening/ai_screened.csv`
- `screening/borderline_review.csv`
- `screening/final_screened.csv`

评分规则：

- `2`：纳入。
- `1`：边界，需要人工判断。
- `0`：排除。

### 2.2 人工复查边界文献

打开 `screening/borderline_review.csv`，在 `Include` 列填写：

- `1`：纳入。
- `0`：排除。
- 空白：仍不确定，保留为边界。

保存后重新运行：

```bash
uv run python scripts/batch_screen.py --config config/review_topic.yml
```

脚本会保留已完成的 AI 初筛结果，读取你在 `Include` 列中的人工决定，并同步到
`screening/final_screened.csv`。

### 2.3 选择核心文献集

```bash
uv run python scripts/select_core_papers.py --config config/review_topic.yml
```

输出：

```text
screening/core_screened.csv
```

这个文件不是“全部纳入文献”，而是供提取和写作优先使用的核心证据集。它应覆盖
背景、方法/机制、临床应用、验证转化、伦理实施等关键板块。配额和类别由
`core_selection` 控制。

---

## Phase 3：资料获取与结构化提取

### 3.1 保存摘要并尝试获取开放全文

```bash
uv run python scripts/download_sources.py --config config/review_topic.yml
```

输出：

- `search/abstracts/*.md`
- `pdfs/*.pdf`，如果能从开放来源获取
- `pdfs/pdf_map.csv`

当前工作流不新增 Zotero PDF 复制脚本。若某些文献没有开放全文，可通过 Zotero、
机构权限、出版商页面或手动下载补齐 PDF，再更新 `pdfs/pdf_map.csv`。

### 3.2 批量提取笔记

```bash
uv run python scripts/extract_notes.py --config config/review_topic.yml
```

输出：

```text
extractions/*.md
```

每个提取笔记记录：

- 文献信息、来源类型、领域/疾病/场景。
- 方法框架、关键技术、数据集、验证方式。
- 样本量、指标值、数据集名称、模型名称。
- 局限性、适合支撑的章节、可引用主张。

提取笔记是后续事实核查的来源，不要把模型没有明确读到的数字补进去。

---

## Phase 4：综合、gap 分析与大纲

这一阶段主要靠 AI 辅助整理，但结论由人确认。

建议产物：

- `synthesis/clusters.md`：主题聚类，按方法、应用、疾病/场景、证据层级归类。
- `synthesis/gap_analysis.md`：研究空白、方法空白、临床转化空白、冲突证据。
- `outline/outline_current.md`：当前写作大纲。

大纲应包含：

- 6-8 个主章节。
- 每节 2-3 句话说明核心论点。
- 每节目标字数。
- 对应的文献/聚类来源。
- 图表计划。

叙述性综述的大纲应先有论点，再选择文献支撑；不要按论文逐篇排队。

---

## Phase 5：分章节写作

推荐逐节写：

```text
/lit-draft 3
/lit-draft "Section title"
```

也可以手动给 AI 提示：

1. 读取 `outline/outline_current.md` 中该节的目标和字数。
2. 只读取与该节相关的 `extractions/*.md`。
3. 每段先提出综合性主张，再用 2-4 篇代表性文献支撑。
4. 保留 `[FirstAuthorYear]` 占位符，不提前转换为正式引用。
5. 不写“本综述纳入了 N 篇研究”这类系统综述语言。

章节写完后组装为：

```text
manuscript/manuscript_v1.md
```

---

## Phase 6：事实审查与润色

这一阶段是整套流程的安全阀，顺序不要颠倒。

### 6.1 事实准确性审查

```text
/lit-audit manuscript/manuscript_v1.md
```

核查对象：

- AUC、C-index、准确率、HR、样本量。
- 数据集名称、队列来源、中心数。
- 模型/框架名称。
- 验证类型：内部、外部、前瞻性、回顾性。

所有 mismatch 或无法追溯的数字，必须在进入润色前修正。

### 6.2 逐句来源核查

对每一个带引用的关键句，按这个顺序检查：

1. 先看提取笔记是否支持该句。
2. 如果提取笔记不够，查看摘要。
3. 如果摘要仍不够，通过 DOI 或 PDF 查看原文 Results/Methods。
4. 如果原文不支持，删除、降级或重写该句。

这一步对应人工防幻觉流程：AI 可以帮忙比对，但最终接受或拒绝由人决定。

### 6.3 去 AI 痕迹与叙述性综述门控

```text
/lit-deregister
/lit-gate manuscript/manuscript_v5.md
```

重点检查：

- 对立构式和空泛评价词是否过多。
- 是否像系统综述一样报告文献库数量。
- 引言和结论是否过空。
- 段落是否像 annotated bibliography。
- 字数、摘要、占位符、引文密度是否达标。

---

## Phase 7：Zotero、引文和 Word 导出

### 7.1 导出 NBIB 并导入 Zotero

```bash
uv run python scripts/export_nbib.py --config config/review_topic.yml
```

输出：

```text
search/included_papers.nbib
```

在 Zotero 中导入该文件。导入后将集合重命名为 `.env` 中的
`ZOTERO_COLLECTION`。

### 7.2 导出 Better BibTeX

在 Zotero 中导出 Better BibTeX 到：

```text
references/library.bib
```

### 7.3 转换占位符

```text
/lit-cite manuscript/manuscript_v5.md
```

输出：

```text
manuscript/manuscript_cited.md
```

### 7.4 生成 Word

在 `manuscript/` 目录运行：

```bash
pandoc -s --lua-filter=zotero.lua manuscript_cited.md -o manuscript.docx
```

然后在 Word 中使用 Zotero 插件设置引用格式并插入参考文献列表。

不要使用 `pandoc --citeproc` 或 `--bibliography` 生成最终稿，因为它们会生成
静态引用，Word Zotero 插件无法继续编辑。

---

## 常用命令

```bash
uv run python scripts/pubmed_search.py --config config/review_topic.yml
uv run python scripts/batch_screen.py --config config/review_topic.yml
uv run python scripts/select_core_papers.py --config config/review_topic.yml
uv run python scripts/download_sources.py --config config/review_topic.yml
uv run python scripts/extract_notes.py --config config/review_topic.yml
uv run python scripts/export_nbib.py --config config/review_topic.yml
```

状态检查和写作技能：

```text
/lit-status
/lit-draft [section]
/lit-audit
/lit-deregister
/lit-gate
/lit-cite
```

---

## 写作原则

- 综述要围绕问题和论点组织，而不是围绕论文清单组织。
- 每段最好有一个明确主张、若干代表性证据和一句解释/限制。
- 具体数字必须来自具体文献，不得由 AI 推断。
- 不在正文中精确统计本综述自己的文献数量。
- 不写 “This review synthesizes N studies” 这类系统综述式句子。
- 可以使用“the reviewed literature”“published work”“relatively few studies”等叙述性表达。

---

## 项目日志

每次重要会话结束，在 `LOG.md` 追加：

```markdown
## YYYY-MM-DD
- Phase: X
- Done: [what was completed]
- Next: [what to do next session]
```

---

## 许可证

MIT License。
