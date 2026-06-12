from __future__ import annotations

import csv
import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from review_config import PROJECT_ROOT, add_config_arg, display_path, get_nested, load_config, lower_terms, resolve_path

INPUT_PATH = PROJECT_ROOT / "search" / "pubmed_results.csv"
AI_SCREENED_PATH = PROJECT_ROOT / "screening" / "ai_screened.csv"
BORDERLINE_PATH = PROJECT_ROOT / "screening" / "borderline_review.csv"
FINAL_PATH = PROJECT_ROOT / "screening" / "final_screened.csv"

BATCH_SIZE = 20
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

OUTPUT_COLUMNS = ["PMID", "Title", "Year", "Journal", "DOI", "Score", "Reason"]
BORDERLINE_COLUMNS = [
    "PMID",
    "Title",
    "Year",
    "Journal",
    "Abstract",
    "DOI",
    "Reason",
    "Include",
]


SYSTEM_PROMPT = """You are screening PubMed records for a Chinese narrative literature review.
Topic: applications of artificial intelligence in liver diseases.
Return strict JSON only.

Scoring rubric:
Score 2 = Include. Meets any:
- AI/ML/deep learning/NLP/LLM/radiomics/digital pathology/omics AI directly applied to liver disease, hepatology, MASLD/MASH, fibrosis, cirrhosis, viral hepatitis, HCC/liver cancer, liver transplantation, clinical workflow, prognosis, diagnosis, treatment decision, screening, monitoring, or patient management.
- Recent review, guideline, practice guidance, scoping review, or perspective with clear relevance to AI in hepatology or liver disease.

Score 1 = Borderline. Meets any:
- Gastroenterology or abdominal AI paper with partial liver relevance.
- Single narrow technical paper whose relevance to the review background is uncertain.
- Liver disease paper with digital health or decision support, but weak or unclear AI component.

Score 0 = Exclude. Meets any:
- Not liver/hepatology.
- Not AI/ML/NLP/LLM/radiomics/digital pathology/decision support.
- Basic science, animal-only, or molecular mechanism paper without clinical AI application.
- Editorial/news/comment with little evidence value.

For each record, return:
{"PMID":"...", "Score":0|1|2, "Reason":"<=15 English words"}
"""

CONSERVATIVE_INCLUDE = {
    "high_value_terms": [
        "review",
        "guideline",
        "practice guidance",
        "scoping",
        "consensus",
        "hepatology",
        "liver transplantation",
        "hepatocellular carcinoma",
        "masld",
        "mash",
    ],
    "ai_terms": ["artificial intelligence", "machine learning", "deep learning", "radiomics", "large language model"],
    "domain_terms": ["liver", "hepatic", "hepatology", "hepatocellular", "cirrhosis", "fibrosis", "masld", "mash"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen PubMed records with an LLM using review-topic config.")
    add_config_arg(parser)
    parser.add_argument("--input", help="Override configured PubMed results CSV path.")
    parser.add_argument("--ai-screened", help="Override configured AI-screened CSV path.")
    parser.add_argument("--borderline", help="Override configured borderline CSV path.")
    parser.add_argument("--final", help="Override configured final screened CSV path.")
    return parser.parse_args()


def batched(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def load_processed_pmids() -> set[str]:
    if not AI_SCREENED_PATH.exists():
        return set()
    with AI_SCREENED_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["PMID"] for row in reader if row.get("PMID")}


def write_rows(path: Path, rows: list[dict[str, Any]], columns: list[str], append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    mode = "a" if append else "w"
    with path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not append or not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def records_for_model(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    payload = []
    for row in rows:
        payload.append(
            {
                "PMID": str(row["PMID"]),
                "Title": str(row.get("Title", "")),
                "Year": str(row.get("Year", "")),
                "Journal": str(row.get("Journal", "")),
                "Abstract": str(row.get("Abstract", ""))[:2500],
                "DOI": str(row.get("DOI", "")),
            }
        )
    return payload


def parse_json_response(text: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    results = parsed.get("results", parsed if isinstance(parsed, list) else [])
    if not isinstance(results, list):
        raise ValueError("Model response did not contain a results list")
    return results


def screen_batch(client: OpenAI, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    user_prompt = {
        "records": records_for_model(rows),
        "output_schema": {"results": [{"PMID": "string", "Score": "integer 0-2", "Reason": "string"}]},
    }
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    raw_results = parse_json_response(content)
    by_pmid = {str(item.get("PMID", "")): item for item in raw_results}

    output: list[dict[str, Any]] = []
    for row in rows:
        pmid = str(row["PMID"])
        item = by_pmid.get(pmid, {})
        try:
            score = int(item.get("Score", 0))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(score, 2))
        reason = str(item.get("Reason", "")).replace("\n", " ").strip()[:180]
        if not reason:
            reason = "No usable model reason"
        output.append(
            {
                "PMID": pmid,
                "Title": row.get("Title", ""),
                "Year": row.get("Year", ""),
                "Journal": row.get("Journal", ""),
                "DOI": row.get("DOI", ""),
                "Score": score,
                "Reason": reason,
            }
        )
    return output


def conservative_borderline_include(row: pd.Series) -> int:
    text = f"{row.get('Title', '')} {row.get('Journal', '')} {row.get('Abstract', '')}".lower()
    high_value = any(term in text for term in lower_terms(CONSERVATIVE_INCLUDE.get("high_value_terms", [])))
    ai_liver = any(term in text for term in lower_terms(CONSERVATIVE_INCLUDE.get("ai_terms", []))) and any(
        term in text for term in lower_terms(CONSERVATIVE_INCLUDE.get("domain_terms", []))
    )
    return 1 if high_value and ai_liver else 0


def build_review_files() -> None:
    screened = pd.read_csv(AI_SCREENED_PATH, dtype={"PMID": str})
    source = pd.read_csv(INPUT_PATH, dtype={"PMID": str})
    merged = screened.merge(
        source[["PMID", "Abstract"]],
        on="PMID",
        how="left",
    )

    borderline = merged[merged["Score"] == 1].copy()
    if not borderline.empty:
        borderline["Include"] = borderline.apply(conservative_borderline_include, axis=1)
    else:
        borderline["Include"] = []
    write_rows(BORDERLINE_PATH, borderline.to_dict("records"), BORDERLINE_COLUMNS, append=False)

    final = screened.copy()
    include_map = dict(zip(borderline["PMID"], borderline["Include"]))
    final["Score"] = final.apply(
        lambda row: 2 if row["Score"] == 1 and include_map.get(row["PMID"], 0) == 1 else (0 if row["Score"] == 1 else row["Score"]),
        axis=1,
    )
    write_rows(FINAL_PATH, final.to_dict("records"), OUTPUT_COLUMNS, append=False)


def main() -> None:
    global AI_SCREENED_PATH, BASE_URL, BATCH_SIZE, BORDERLINE_PATH, CONSERVATIVE_INCLUDE, FINAL_PATH, INPUT_PATH, MODEL, SYSTEM_PROMPT
    args = parse_args()
    config = load_config(args.config)
    INPUT_PATH = PROJECT_ROOT / args.input if args.input else resolve_path(config, "paths.search_results", "search/pubmed_results.csv")
    AI_SCREENED_PATH = PROJECT_ROOT / args.ai_screened if args.ai_screened else resolve_path(config, "paths.ai_screened", "screening/ai_screened.csv")
    BORDERLINE_PATH = PROJECT_ROOT / args.borderline if args.borderline else resolve_path(config, "paths.borderline_review", "screening/borderline_review.csv")
    FINAL_PATH = PROJECT_ROOT / args.final if args.final else resolve_path(config, "paths.final_screened", "screening/final_screened.csv")
    BATCH_SIZE = int(get_nested(config, "screening.batch_size", BATCH_SIZE))
    MODEL = str(get_nested(config, "screening.default_model", MODEL))
    BASE_URL = str(get_nested(config, "screening.default_base_url", BASE_URL))
    SYSTEM_PROMPT = str(get_nested(config, "screening.system_prompt", SYSTEM_PROMPT))
    CONSERVATIVE_INCLUDE = dict(get_nested(config, "screening.conservative_include", CONSERVATIVE_INCLUDE) or CONSERVATIVE_INCLUDE)

    load_dotenv(PROJECT_ROOT / ".env")
    BATCH_SIZE = int(os.getenv("SCREEN_BATCH_SIZE", str(BATCH_SIZE)))
    MODEL = os.getenv("SCREEN_MODEL", MODEL)
    BASE_URL = os.getenv("DEEPSEEK_BASE_URL", BASE_URL)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is missing from .env")

    df = pd.read_csv(INPUT_PATH, dtype={"PMID": str}).fillna("")
    df = df[df["Abstract"].str.strip() != ""].copy()
    processed = load_processed_pmids()
    pending = [row for row in df.to_dict("records") if str(row["PMID"]) not in processed]
    print(f"Records with abstracts: {len(df)}", flush=True)
    print(f"Already processed: {len(processed)}", flush=True)
    print(f"Pending: {len(pending)}", flush=True)

    client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=60.0, max_retries=2)
    for index, batch in enumerate(batched(pending, BATCH_SIZE), start=1):
        rows = screen_batch(client, batch)
        write_rows(AI_SCREENED_PATH, rows, OUTPUT_COLUMNS, append=True)
        counts = {score: sum(1 for row in rows if row["Score"] == score) for score in [0, 1, 2]}
        print(f"Batch {index}: n={len(rows)} include={counts[2]} borderline={counts[1]} exclude={counts[0]}", flush=True)
        time.sleep(0.25)

    build_review_files()
    screened = pd.read_csv(AI_SCREENED_PATH)
    final = pd.read_csv(FINAL_PATH)
    print("Screening complete", flush=True)
    print(f"AI screened rows: {len(screened)}", flush=True)
    print(f"AI score counts: {screened['Score'].value_counts().sort_index().to_dict()}", flush=True)
    print(f"Final score counts: {final['Score'].value_counts().sort_index().to_dict()}", flush=True)
    print(f"Outputs: {display_path(AI_SCREENED_PATH)}, {display_path(BORDERLINE_PATH)}, {display_path(FINAL_PATH)}", flush=True)


if __name__ == "__main__":
    main()
