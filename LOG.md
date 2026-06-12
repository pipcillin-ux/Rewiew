# Session Log

## Template
```
## YYYY-MM-DD
- Phase: X
- Done: [what was completed]
- Next: [what to do next session]
```

---

## 2026-06-11
- Phase: AI liver disease review workflow phases 1-5
- Done: Created PubMed search, AI screening, core-paper selection, source acquisition, extraction sync, synthesis, outline, factual audit, and the formal draft `draft/AI在肝病中的应用_国内外现状及趋势_workflow.md`.
- Next: Review the formal draft for project-specific wording and decide whether to merge it into `课题框架.md`.

## 2026-06-11
- Phase: Zotero integration check
- Done: Confirmed Zotero local API is running, added `scripts/export_nbib.py`, exported 62 core PubMed records to `search/included_papers.nbib`, and documented remaining Zotero steps in `references/zotero_integration_status.md`.
- Next: Import NBIB into Zotero, export Better BibTeX to `references/library.bib`, and optionally create a citekey-based draft.

## 2026-06-11
- Phase: Workflow parameterization
- Done: Added `config/review_topic.yml`, `config/README.md`, and shared config loader `scripts/review_config.py`; updated search, screening, core selection, source acquisition, extraction, NBIB export, and source-sync scripts to read topic settings from YAML config with `--config` overrides.
- Next: For a new review direction, copy `config/review_topic.yml`, update queries/prompts/categories/paths, then rerun the workflow scripts with `--config`.

## 2026-06-11
- Phase: Workflow compliance audit
- Done: Audited Phase 1-5 artifacts, source acquisition, Zotero status, citation checks, and parameterization changes; saved report to `synthesis/workflow_audit_20260611.md`.
- Next: Complete Zotero import/Better BibTeX export and decide whether to move `config/` into an AGENTS-approved workflow directory.

## 2026-06-11
- Phase: PMC PDF acquisition fix
- Done: Fixed `scripts/download_sources.py` to use PMC OA deprecated HTTPS paths and retry Entrez/PDF requests; reran source acquisition, increasing local PDFs from 0 to 26 and syncing extraction source labels.
- Next: For remaining non-PMC or 403 records, use Zotero Connector, publisher pages, Unpaywall/OpenAlex, or institutional access where available.

## 2026-06-12
- Phase: Project reset
- Done: Cleared search results, screening tables, extraction notes, PDFs, draft files, synthesis/outline/reference process files, and Python script cache.
- Next: Reinitialize the review topic and rerun the workflow from search.

## 2026-06-12
- Phase: Workflow integration and template generalization
- Done: Initialized a lightweight Git baseline, merged the executable workflow with the human-in-the-loop writing and verification process, generalized the default config and agent instructions, removed old topic-specific defaults from scripts, and added placeholder validation.
- Next: Fill `config/review_topic.yml` for the next concrete review topic, then rerun the workflow from Phase 1.
