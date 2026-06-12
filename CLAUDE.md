# CLAUDE.md — Narrative Literature Review Workflow Instructions

> Claude Code reads this file automatically at the start of each session.
> Keep it aligned with `AGENTS.md` so both agents follow the same workflow.

---

## Project Identity

**Project type:** Reusable Narrative Literature Review (NLR) workflow template.

**Default topic:** None. The review topic must be supplied in
`config/review_topic.yml` before running workflow scripts.

**Core principle:** This is a human-in-the-loop workflow. Scripts and AI models help
search, screen, extract, draft, and audit, but humans decide the review question,
argument structure, boundary cases, and final factual acceptability.

**Narrative review constraint:** The manuscript must read as a narrative synthesis,
not a systematic review. It should use papers to support arguments rather than
enumerate a formally bounded corpus.

---

## Directory Layout

```text
literature-review/
├── AGENTS.md               ← Codex project instructions
├── CLAUDE.md               ← Claude Code project instructions
├── README.md               ← human-facing workflow manual
├── LOG.md                  ← session log
├── config/                 ← topic YAML templates and notes
├── search/                 ← PubMed/raw search outputs and local abstracts
├── screening/              ← ai_screened, borderline_review, final/core CSVs
├── pdfs/                   ← full-text PDFs + pdf_map.csv
├── extractions/            ← one structured note per paper
├── synthesis/              ← clusters, gap analysis, factual audits
├── outline/                ← outline drafts and outline_current.md
├── draft/                  ← section drafts
├── manuscript/             ← assembled manuscript versions and final docx
├── references/             ← Better BibTeX library and citation reports
└── scripts/                ← Python automation scripts
```

**Rule:** Write project artifacts inside this structure unless the user explicitly
approves another location. Root-level workflow files (`README.md`, `AGENTS.md`,
`CLAUDE.md`, `LOG.md`, `pyproject.toml`, `uv.lock`, `.env.example`) are allowed.

---

## Workflow Phases

**Phase 0 — Topic framing.** Define the target audience, journal, clinical or
scientific tension, in-scope/out-of-scope boundaries, and the provisional argument.
Use AI to brainstorm frames, but do not let it choose the final thesis without
human review.

**Phase 1 — Broad literature acquisition.** Configure PubMed queries in
`config/review_topic.yml`, then run `scripts/pubmed_search.py`. Prefer a broad
first pass that gives enough material for AI-assisted framework building.

**Phase 2 — Screening and core selection.** Run `scripts/batch_screen.py`, manually
review `screening/borderline_review.csv`, rerun screening sync if needed, then run
`scripts/select_core_papers.py`. Boundary papers require human judgment.

**Phase 3 — Source acquisition and extraction.** Run `scripts/download_sources.py`
and `scripts/extract_notes.py`. Use abstracts when full text is unavailable, but
mark source limitations clearly.

**Phase 4 — Synthesis and outline.** Cluster papers, identify gaps, then build an
argument-driven outline with word budgets, figure/table plans, and section-specific
evidence sources.

**Phase 5 — Drafting.** Draft one section at a time using `/lit-draft` or the
documented prompts. Keep `[FirstAuthorYear]` placeholders until citation conversion.

**Phase 6 — Verification and polish.** Run factual audit before style polishing.
Every numeric claim, dataset name, model name, cohort size, and metric must trace
back to extraction notes or source text. When abstracts are insufficient, verify
against DOI/full-text Results sections before accepting the claim.

**Phase 7 — Citation and Word export.** Use Zotero + Better BibTeX for stable
citekeys, `/lit-cite` for placeholder conversion, and `pandoc --lua-filter=zotero.lua`
for Word files with live Zotero fields.

---

## Configuration Rules

- `config/review_topic.yml` is a template. Replace all `REPLACE_WITH_...` values
  before running workflow scripts.
- Scripts accept `--config` and should fail fast when placeholders remain.
- Keep topic-specific scope, PubMed terms, screening rules, category quotas, and
  extraction schema in YAML rather than hard-coding them into scripts.
- Do not silently reuse an old topic configuration for a new review direction.

---

## Zotero Integration

- Import method: NBIB bulk import from `search/included_papers.nbib`.
- After import, rename the Zotero collection to the project-specific name recorded
  in `.env` as `ZOTERO_COLLECTION`.
- Better BibTeX is required for stable citekeys and `references/library.bib`.
- Do not use pandoc `--citeproc` or `--bibliography` for the final Word manuscript;
  those produce static citations that Zotero cannot edit afterward.

---

## Writing Style Guidelines

- Voice: third-person academic, active where possible.
- Structure: narrative synthesis, not annotated bibliography.
- Main text should avoid bullet lists unless the target journal explicitly allows them.
- Avoid vague openers such as "Recently" and "In recent years".
- Use `[FirstAuthorYear]` placeholders during drafting.
- Use em dashes sparingly, no more than 8-10 per 10,000 words.

### Narrative vs. Systematic Review Language

Avoid:

- Exact paper counts describing the review's own collection.
- Exhaustive-corpus statements such as "none of the reviewed studies".
- Meta-sentences such as "this review synthesizes N studies".
- Repeated use of "the corpus" to describe the review's paper set.

Prefer:

- "the reviewed literature", "published work", or "studies examined here".
- Qualitative scope descriptors such as "the dominant evidence base" or
  "relatively few published studies".
- Gap language such as "prospective validation has not been reported".

Numbers are encouraged when they come from a specific cited study, such as sample
sizes, AUC values, hazard ratios, cohort counts, or validation metrics.

---

## Screening CSV Format

`screening/ai_screened.csv` columns:

| Column | Description |
|---|---|
| PMID | PubMed ID |
| Title | Article title |
| Year | Publication year |
| Journal | Journal name |
| DOI | DOI |
| Score | 2 = Include · 1 = Borderline · 0 = Exclude |
| Reason | Short AI justification |

`screening/borderline_review.csv` contains Score=1 papers plus an `Include`
column. Fill `1` to include, `0` to exclude, and leave blank only if still undecided.

---

## Extraction Note Format

Each file in `extractions/` should follow this template:

```markdown
# [Short title or FirstAuthorYear]

## Metadata
- **Full title:**
- **Authors:**
- **Journal / Conference:**
- **Year:**
- **DOI:**
- **Zotero key:**
- **Paper type:** (Original research / Review / Guideline / Perspective / Other)
- **Text source:** (Full text PDF / PubMed abstract / Other)
- **Modalities covered:**
- **Domain / condition:**
- **In-scope score:** (1 = peripheral, 2 = relevant, 3 = core)

## Methods
- **Framework / Architecture:**
- **Key techniques:**
- **Datasets used:**
- **Validation approach:**

## Quantitative Evidence
- **Architecture name:**
- **Validation type:** (internal / external / prospective / review / not reported)
- **Datasets (name · n patients · institution):**
- **Key metrics (metric · value · dataset · n):**

## Key Findings
(2-4 bullet points)

## Limitations (as stated or implied)

## Relevance to This Review
- **Which section(s) it feeds:**
- **Key claim to cite:**
- **Any conflicting findings with other papers:**
```

---

## Python Environment

- Run scripts with `uv run python scripts/xxx.py`.
- Add packages with `uv add <package-name>`.
- Do not use `pip install` directly.
- `.env` is local and must not be committed.

---

## Session Startup Checklist

At the beginning of each Claude Code session:

1. Read `CLAUDE.md`.
2. Read `outline/outline_current.md` if it exists.
3. Check `LOG.md` for the last session.
4. State the current phase and intended work.
5. Ask before destructive actions such as deleting files or overwriting user-edited outputs.

---

## LOG.md Convention

Append a brief entry at the end of each substantial session:

```markdown
## YYYY-MM-DD
- Phase: X
- Done: [what was completed]
- Next: [what to do next session]
```
