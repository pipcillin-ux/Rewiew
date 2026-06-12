from __future__ import annotations

import json
import argparse
import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from review_config import PROJECT_ROOT, add_config_arg, display_path, get_nested, load_config, resolve_path


CORE_PATH = PROJECT_ROOT / "screening" / "core_screened.csv"
SOURCE_MAP_PATH = PROJECT_ROOT / "pdfs" / "pdf_map.csv"
EXTRACTION_DIR = PROJECT_ROOT / "extractions"

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"


SYSTEM_PROMPT = """You extract structured notes for a narrative literature review.
Use only the supplied title, metadata, category, reason, and local source text.
Do not invent quantitative values, dataset names, sample sizes, validation types, or architecture names.
If a field is absent from the supplied text, write "not reported".
Return strict JSON only with the requested keys.
"""
SOURCE_TEXT_CHARS = 7000
REQUIRED_SCHEMA: dict[str, Any] = {
    "short_title": "string",
    "paper_type": "Original research / Review / Guideline / Perspective / Other",
    "modalities_covered": "string",
    "domain_context": "string",
    "in_scope_score": "integer 1-3",
    "framework_architecture": "string",
    "key_techniques": "string",
    "datasets_used": "string",
    "validation_approach": "string",
    "architecture_name": "string",
    "validation_type": "internal / external / prospective / review / not reported",
    "datasets_detail": "string",
    "key_metrics": "string",
    "key_findings": ["2-4 bullet strings"],
    "limitations": "string",
    "review_sections": "string",
    "key_claim_to_cite": "string",
    "conflicting_findings": "string",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract structured notes from configured core records.")
    add_config_arg(parser)
    parser.add_argument("--core", help="Override configured core screened CSV path.")
    parser.add_argument("--source-map", help="Override configured PDF/source map CSV path.")
    parser.add_argument("--out-dir", help="Override configured extraction directory.")
    return parser.parse_args()


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value[:80] or "paper"


def first_author(authors: str) -> str:
    if not authors:
        return "Unknown"
    first = authors.split(";")[0].strip()
    if not first:
        return "Unknown"
    return re.sub(r"[^A-Za-z]", "", first.split()[0]) or "Unknown"


def output_path(row: pd.Series) -> Path:
    author = first_author(str(row.get("Authors", "")))
    year = str(row.get("Year", "")).split(".")[0] or "Year"
    pmid = str(row.get("PMID", ""))
    title_slug = slugify(str(row.get("Title", "")))[:45]
    return EXTRACTION_DIR / f"{author}{year}_{pmid}_{title_slug}.md"


def load_source_map() -> dict[str, dict[str, str]]:
    if not SOURCE_MAP_PATH.exists():
        return {}
    df = pd.read_csv(SOURCE_MAP_PATH, dtype={"PMID": str}).fillna("")
    return {str(row["PMID"]): dict(row) for _, row in df.iterrows()}


def read_pdf_text(path: Path, max_pages: int = 8) -> str:
    import fitz

    with fitz.open(path) as doc:
        pages = [doc[i].get_text("text") for i in range(min(max_pages, len(doc)))]
    return "\n".join(pages).strip()


def read_local_source(row: pd.Series, source_map: dict[str, dict[str, str]]) -> tuple[str, str]:
    pmid = str(row.get("PMID", ""))
    source = source_map.get(pmid, {})
    source_type = str(source.get("SourceType", "")).strip() or "PubMed abstract"
    pdf_path = str(source.get("PdfPath", "")).strip()
    abstract_path = str(source.get("AbstractPath", "")).strip()

    if source_type == "PMC full text PDF" and pdf_path:
        full_path = PROJECT_ROOT / pdf_path
        if full_path.exists():
            return read_pdf_text(full_path), f"PMC full text PDF (local source: {pdf_path})"

    if abstract_path:
        full_path = PROJECT_ROOT / abstract_path
        if full_path.exists():
            text = full_path.read_text(encoding="utf-8")
            return text, f"PubMed abstract (local source: {abstract_path})"

    return str(row.get("Abstract", "")), "PubMed abstract"


def parse_json_response(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Model response is not a JSON object")
    return parsed


def extract_one(client: OpenAI, row: pd.Series) -> dict[str, Any]:
    payload = {
        "PMID": str(row.get("PMID", "")),
        "Title": str(row.get("Title", "")),
        "Authors": str(row.get("Authors", "")),
        "Journal": str(row.get("Journal", "")),
        "Year": str(row.get("Year", "")),
        "DOI": str(row.get("DOI", "")),
        "Category": str(row.get("Category", "")),
        "ScreeningReason": str(row.get("Reason", "")),
        "SourceText": str(row.get("_SourceText", row.get("Abstract", "")))[:SOURCE_TEXT_CHARS],
        "required_schema": REQUIRED_SCHEMA,
    }
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return parse_json_response(response.choices[0].message.content or "{}")


def clean(value: Any) -> str:
    if value is None:
        return "not reported"
    text = str(value).strip()
    return text if text else "not reported"


def bullet_lines(values: Any) -> str:
    if isinstance(values, list):
        items = [clean(v) for v in values if clean(v) != "not reported"]
    else:
        items = [clean(values)]
    if not items:
        items = ["not reported"]
    return "\n".join(f"- {item}" for item in items[:4])


def render_markdown(row: pd.Series, data: dict[str, Any]) -> str:
    title = clean(data.get("short_title")) if data.get("short_title") else f"{first_author(str(row.get('Authors', '')))}{row.get('Year', '')}"
    text_source = clean(row.get("_SourceDescription", "PubMed abstract"))
    return f"""# {title}

## Metadata
- **Full title:** {clean(row.get("Title"))}
- **Authors:** {clean(row.get("Authors"))}
- **Journal / Conference:** {clean(row.get("Journal"))}
- **Year:** {clean(row.get("Year"))}
- **DOI:** {clean(row.get("DOI"))}
- **Zotero key:** not available
- **Paper type:** {clean(data.get("paper_type"))}
- **Text source:** {text_source}
- **Modalities covered:** {clean(data.get("modalities_covered"))}
- **Domain / condition:** {clean(data.get("domain_context"))}
- **In-scope score:** {clean(data.get("in_scope_score"))}

## Methods
- **Framework / Architecture:** {clean(data.get("framework_architecture"))}
- **Key techniques:** {clean(data.get("key_techniques"))}
- **Datasets used:** {clean(data.get("datasets_used"))}
- **Validation approach:** {clean(data.get("validation_approach"))}

## Quantitative Evidence
- **Architecture name:** {clean(data.get("architecture_name"))}
- **Validation type:** {clean(data.get("validation_type"))}
- **Datasets (name · n patients · institution):** {clean(data.get("datasets_detail"))}
- **Key metrics (metric · value · dataset · n):** {clean(data.get("key_metrics"))}

## Key Findings
{bullet_lines(data.get("key_findings"))}

## Limitations (as stated or implied)

{clean(data.get("limitations"))}

## Relevance to This Review
- **Which section(s) it feeds:** {clean(data.get("review_sections"))}
- **Key claim to cite:** {clean(data.get("key_claim_to_cite"))}
- **Any conflicting findings with other papers:** {clean(data.get("conflicting_findings"))}
"""


def main() -> None:
    global BASE_URL, CORE_PATH, EXTRACTION_DIR, MODEL, REQUIRED_SCHEMA, SOURCE_MAP_PATH, SOURCE_TEXT_CHARS, SYSTEM_PROMPT
    args = parse_args()
    config = load_config(args.config)
    CORE_PATH = PROJECT_ROOT / args.core if args.core else resolve_path(config, "paths.core_screened", "screening/core_screened.csv")
    SOURCE_MAP_PATH = PROJECT_ROOT / args.source_map if args.source_map else resolve_path(config, "paths.pdf_map", "pdfs/pdf_map.csv")
    EXTRACTION_DIR = PROJECT_ROOT / args.out_dir if args.out_dir else resolve_path(config, "paths.extractions_dir", "extractions")
    MODEL = str(get_nested(config, "extraction.default_model", MODEL))
    BASE_URL = str(get_nested(config, "extraction.default_base_url", BASE_URL))
    SYSTEM_PROMPT = str(get_nested(config, "extraction.system_prompt", SYSTEM_PROMPT))
    SOURCE_TEXT_CHARS = int(get_nested(config, "extraction.source_text_chars", SOURCE_TEXT_CHARS))
    REQUIRED_SCHEMA = dict(get_nested(config, "extraction.required_schema", REQUIRED_SCHEMA) or REQUIRED_SCHEMA)

    load_dotenv(PROJECT_ROOT / ".env")
    MODEL = os.getenv("EXTRACT_MODEL", os.getenv("SCREEN_MODEL", MODEL))
    BASE_URL = os.getenv("DEEPSEEK_BASE_URL", BASE_URL)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing from .env")

    EXTRACTION_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(CORE_PATH, dtype={"PMID": str}).fillna("")
    source_map = load_source_map()
    client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=60.0, max_retries=2)

    created = 0
    skipped = 0
    for _, row in df.iterrows():
        row = row.copy()
        source_text, source_description = read_local_source(row, source_map)
        row["_SourceText"] = source_text
        row["_SourceDescription"] = source_description
        path = output_path(row)
        if path.exists():
            skipped += 1
            continue
        data = extract_one(client, row)
        path.write_text(render_markdown(row, data), encoding="utf-8")
        created += 1
        print(f"Created {display_path(path)}", flush=True)
        time.sleep(0.25)

    print(f"Extraction complete: created={created}, skipped={skipped}, total={len(df)}", flush=True)


if __name__ == "__main__":
    main()
