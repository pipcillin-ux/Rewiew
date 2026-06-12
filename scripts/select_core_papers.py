from __future__ import annotations

import argparse
import re
from typing import Any

import pandas as pd

from review_config import PROJECT_ROOT, add_config_arg, display_path, get_nested, load_config, lower_terms, resolve_path


FINAL_PATH = PROJECT_ROOT / "screening" / "final_screened.csv"
SOURCE_PATH = PROJECT_ROOT / "search" / "pubmed_results.csv"
OUTPUT_PATH = PROJECT_ROOT / "screening" / "core_screened.csv"

CATEGORY_QUOTAS = {
    "general_review_guideline": 10,
    "masld_mash": 10,
    "fibrosis_cirrhosis": 10,
    "viral_hepatitis": 6,
    "hcc_liver_cancer": 14,
    "liver_transplant": 6,
    "llm_nlp_workflow": 6,
}

HIGH_VALUE_JOURNALS = [
    "journal of hepatology",
    "hepatology",
    "gastroenterology",
    "gut",
    "lancet",
    "nature",
    "npj",
    "eclinicalmedicine",
    "clinical gastroenterology and hepatology",
    "gut and liver",
]

CATEGORIES = [
    {"name": "llm_nlp_workflow", "terms": ["large language model", "chatgpt", "natural language processing", "retrieval augmented", "clinical workflow", "electronic health record", "ehr"]},
    {"name": "liver_transplant", "terms": ["transplant", "graft", "donor-recipient", "donor recipient"]},
    {"name": "hcc_liver_cancer", "terms": ["hepatocellular carcinoma", " hcc", "liver cancer", "liver neoplasm", "hepatic tumor", "hepatic tumour"]},
    {"name": "masld_mash", "terms": ["masld", "mash", "nafld", "nash", "steatotic", "fatty liver"]},
    {"name": "fibrosis_cirrhosis", "terms": ["fibrosis", "cirrhosis", "liver stiffness", "portal hypertension", "decompensation", "meld"]},
    {"name": "viral_hepatitis", "terms": ["hepatitis b", "hepatitis c", "hbv", "hcv", "viral hepatitis"]},
]
DEFAULT_CATEGORY = "general_review_guideline"
PRIORITY_CONFIG: dict[str, Any] = {
    "year_weights": {"2026": 7, "2025": 6, "2024": 5, "2023": 3, "2019-2022": 1},
    "review_terms": ["review", "guideline", "practice guidance", "consensus", "scoping review", "position paper"],
    "validation_terms": ["external validation", "multicenter", "multi-center", "prospective", "clinical trial"],
    "explainability_terms": ["explainable", "shap", "interpretability", "interpretable"],
    "multimodal_terms": ["multimodal", "multi-modal", "omics", "radiomics", "pathology", "digital pathology", "whole slide"],
    "ai_terms": ["artificial intelligence", "machine learning", "deep learning", "large language model", "radiomics", "natural language processing"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select a topic-balanced core evidence set using review-topic config.")
    add_config_arg(parser)
    parser.add_argument("--final", help="Override configured final screened CSV path.")
    parser.add_argument("--source", help="Override configured PubMed results CSV path.")
    parser.add_argument("--out", help="Override configured core screened CSV path.")
    return parser.parse_args()


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def classify(text: str) -> str:
    text = text.lower()
    for category in CATEGORIES:
        if contains_any(text, lower_terms(category.get("terms", []))):
            return str(category.get("name"))
    return DEFAULT_CATEGORY


def year_priority(year: int) -> int:
    weights = PRIORITY_CONFIG.get("year_weights", {})
    if str(year) in weights:
        return int(weights[str(year)])
    for key, value in weights.items():
        if "-" not in str(key):
            continue
        start, end = str(key).split("-", 1)
        if start.isdigit() and end.isdigit() and int(start) <= year <= int(end):
            return int(value)
    return 0


def priority(row: pd.Series) -> int:
    title = str(row.get("Title", ""))
    abstract = str(row.get("Abstract", ""))
    journal = str(row.get("Journal", ""))
    text = f"{title} {abstract} {journal}".lower()
    score = 0

    try:
        year = int(float(row.get("Year", 0)))
    except (TypeError, ValueError):
        year = 0
    score += year_priority(year)

    if contains_any(text, lower_terms(PRIORITY_CONFIG.get("review_terms", []))):
        score += 9
    if contains_any(journal.lower(), lower_terms(HIGH_VALUE_JOURNALS)):
        score += 6
    if str(row.get("DOI", "")).strip():
        score += 2
    if contains_any(text, lower_terms(PRIORITY_CONFIG.get("validation_terms", []))):
        score += 5
    if contains_any(text, lower_terms(PRIORITY_CONFIG.get("explainability_terms", []))):
        score += 2
    if contains_any(text, lower_terms(PRIORITY_CONFIG.get("multimodal_terms", []))):
        score += 3
    if contains_any(text, lower_terms(PRIORITY_CONFIG.get("ai_terms", []))):
        score += 4

    title_words = len(re.findall(r"[A-Za-z0-9]+", title))
    if title_words < 4:
        score -= 2
    return score


def main() -> None:
    global CATEGORIES, CATEGORY_QUOTAS, DEFAULT_CATEGORY, FINAL_PATH, HIGH_VALUE_JOURNALS, OUTPUT_PATH, PRIORITY_CONFIG, SOURCE_PATH
    args = parse_args()
    config = load_config(args.config)
    FINAL_PATH = PROJECT_ROOT / args.final if args.final else resolve_path(config, "paths.final_screened", "screening/final_screened.csv")
    SOURCE_PATH = PROJECT_ROOT / args.source if args.source else resolve_path(config, "paths.search_results", "search/pubmed_results.csv")
    OUTPUT_PATH = PROJECT_ROOT / args.out if args.out else resolve_path(config, "paths.core_screened", "screening/core_screened.csv")
    CATEGORY_QUOTAS = dict(get_nested(config, "core_selection.category_quotas", CATEGORY_QUOTAS) or CATEGORY_QUOTAS)
    CATEGORIES = list(get_nested(config, "core_selection.categories", CATEGORIES) or CATEGORIES)
    DEFAULT_CATEGORY = str(get_nested(config, "core_selection.default_category", DEFAULT_CATEGORY))
    HIGH_VALUE_JOURNALS = list(get_nested(config, "core_selection.high_value_journals", HIGH_VALUE_JOURNALS) or HIGH_VALUE_JOURNALS)
    PRIORITY_CONFIG = dict(get_nested(config, "core_selection.priority", PRIORITY_CONFIG) or PRIORITY_CONFIG)

    final = pd.read_csv(FINAL_PATH, dtype={"PMID": str}).fillna("")
    source = pd.read_csv(SOURCE_PATH, dtype={"PMID": str}).fillna("")
    included = final[final["Score"].astype(int) == 2].copy()
    merged = included.merge(
        source[["PMID", "Authors", "Abstract", "QueryName"]],
        on="PMID",
        how="left",
    ).fillna("")

    merged["Category"] = merged.apply(lambda row: classify(f"{row['Title']} {row['Abstract']} {row['Journal']}"), axis=1)
    merged["Priority"] = merged.apply(priority, axis=1)
    merged = merged.sort_values(["Category", "Priority", "Year"], ascending=[True, False, False])

    selected_parts = []
    for category, quota in CATEGORY_QUOTAS.items():
        part = merged[merged["Category"] == category].head(quota)
        selected_parts.append(part)

    selected = pd.concat(selected_parts, ignore_index=True)
    selected = selected.drop_duplicates("PMID").sort_values(["Category", "Priority"], ascending=[True, False])

    columns = [
        "PMID",
        "Title",
        "Authors",
        "Year",
        "Journal",
        "DOI",
        "Category",
        "Priority",
        "Reason",
        "Abstract",
        "QueryName",
    ]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    selected[columns].to_csv(OUTPUT_PATH, index=False)

    print(f"Included pool: {len(included)}")
    print(f"Core selected: {len(selected)}")
    print(selected["Category"].value_counts().sort_index().to_string())
    print(f"Output: {display_path(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()
