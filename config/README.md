# Review Topic Configuration

`review_topic.yml` drives the reusable literature-review workflow scripts.

For a new review direction, copy the file and edit:

- `project.title`
- `paths.*` if you want outputs in topic-specific filenames or directories
- `pubmed.date_filter`, `pubmed.variables`, and `pubmed.queries`
- `screening.system_prompt` and conservative include terms
- `core_selection.category_quotas`, ordered `categories`, and priority term lists
- `extraction.system_prompt` and `required_schema` if the extraction template needs domain-specific fields

Run scripts with a custom config:

```bash
uv run python scripts/pubmed_search.py --config config/my_topic.yml
uv run python scripts/batch_screen.py --config config/my_topic.yml
uv run python scripts/select_core_papers.py --config config/my_topic.yml
uv run python scripts/download_sources.py --config config/my_topic.yml
uv run python scripts/extract_notes.py --config config/my_topic.yml
uv run python scripts/export_nbib.py --config config/my_topic.yml
```
