# 综述主题配置

`review_topic.yml` 是这个工作流的主题配置模板。它默认带有
`REPLACE_WITH_...` 占位符，不能直接运行。任何脚本在读取到占位符时都会
立即报错，避免误用旧主题或空主题生成结果。

## 最小填写项

开始一个新综述前，至少需要完成这些字段：

- `project.title`：综述暂定题目。
- `project.description`：一句话说明综述目的和边界。
- `project.target_journal`、`project.intended_audience`：用于约束写作风格和字数。
- `pubmed.variables.domain_terms`：领域词，例如疾病、人群、技术对象或场景。
- `pubmed.variables.method_terms`：方法词或核心概念词。
- `screening.system_prompt`：把纳入、边界、排除标准写成明确规则。

## 推荐流程

1. 先用人工判断锁定综述问题：读者是谁、要解决什么争议、哪些文献必须纳入。
2. 改写 `pubmed.queries`，保留宽检索和至少一个章节/转化相关检索式。
3. 调整 `core_selection.category_quotas` 和 `categories`，让核心文献集合覆盖你的章节框架。
4. 如需特殊字段，修改 `extraction.required_schema`；字段名应保持通用、可迁移。
5. 运行脚本前先执行：

```bash
uv run python scripts/pubmed_search.py --help
uv run python scripts/pubmed_search.py --config config/review_topic.yml
```

如果配置里仍有占位符，第二条命令会报错并指出需要修改的位置。

## 自定义配置

也可以复制一份配置文件，例如：

```bash
cp config/review_topic.yml config/my_topic.yml
uv run python scripts/pubmed_search.py --config config/my_topic.yml
uv run python scripts/batch_screen.py --config config/my_topic.yml
uv run python scripts/select_core_papers.py --config config/my_topic.yml
uv run python scripts/download_sources.py --config config/my_topic.yml
uv run python scripts/extract_notes.py --config config/my_topic.yml
uv run python scripts/export_nbib.py --config config/my_topic.yml
```

## 人工检查点

配置只能帮助脚本运行，不能替代综述判断。每次修改主题后，应人工检查：

- PubMed 检索式是否过宽或过窄。
- `Score=1` 边界文献是否已在 `screening/borderline_review.csv` 中人工处理。
- 核心文献是否覆盖背景、机制/方法、应用、验证与转化限制。
- 提取笔记中的数字、队列、数据集和结论是否能追溯到摘要或全文。
