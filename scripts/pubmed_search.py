from __future__ import annotations

import csv
import os
import time
import argparse
from dataclasses import dataclass
from typing import Any

from Bio import Entrez
from dotenv import load_dotenv

from review_config import PROJECT_ROOT, add_config_arg, display_path, get_nested, load_config, render_template, resolve_path


@dataclass(frozen=True)
class QuerySpec:
    name: str
    query: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search PubMed using review-topic config queries.")
    add_config_arg(parser)
    parser.add_argument("--out", help="Override configured search results CSV path.")
    return parser.parse_args()


def load_queries(config: dict[str, Any]) -> list[QuerySpec]:
    variables = dict(get_nested(config, "pubmed.variables", {}) or {})
    variables["date_filter"] = get_nested(config, "pubmed.date_filter", "")
    queries = []
    for item in get_nested(config, "pubmed.queries", []) or []:
        name = str(item["name"])
        query = render_template(str(item["query"]), variables)
        queries.append(QuerySpec(name, query))
    if not queries:
        raise ValueError("No PubMed queries configured under pubmed.queries")
    return queries


def text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def extract_year(pub_date: dict[str, Any]) -> str:
    if "Year" in pub_date:
        return text_or_empty(pub_date["Year"])
    if "MedlineDate" in pub_date:
        return text_or_empty(pub_date["MedlineDate"])[:4]
    return ""


def extract_authors(article: dict[str, Any]) -> str:
    authors = article.get("AuthorList", [])
    names: list[str] = []
    for author in authors:
        collective = author.get("CollectiveName")
        if collective:
            names.append(text_or_empty(collective))
            continue
        last = text_or_empty(author.get("LastName"))
        initials = text_or_empty(author.get("Initials"))
        if last:
            names.append(f"{last} {initials}".strip())
    return "; ".join(names[:12])


def extract_abstract(article: dict[str, Any]) -> str:
    abstract = article.get("Abstract", {}).get("AbstractText", [])
    parts: list[str] = []
    for part in abstract:
        label = getattr(part, "attributes", {}).get("Label")
        content = text_or_empty(part)
        if label and content:
            parts.append(f"{label}: {content}")
        elif content:
            parts.append(content)
    return " ".join(parts)


def extract_doi(record: dict[str, Any]) -> str:
    for article_id in record.get("PubmedData", {}).get("ArticleIdList", []):
        attrs = getattr(article_id, "attributes", {})
        if attrs.get("IdType") == "doi":
            return text_or_empty(article_id)
    return ""


def parse_record(record: dict[str, Any], query_name: str) -> dict[str, str]:
    citation = record["MedlineCitation"]
    article = citation["Article"]
    journal = article.get("Journal", {})
    pub_date = journal.get("JournalIssue", {}).get("PubDate", {})
    return {
        "PMID": text_or_empty(citation.get("PMID")),
        "Title": text_or_empty(article.get("ArticleTitle")),
        "Authors": extract_authors(article),
        "Journal": text_or_empty(journal.get("Title") or journal.get("ISOAbbreviation")),
        "Year": extract_year(pub_date),
        "Abstract": extract_abstract(article),
        "DOI": extract_doi(record),
        "QueryName": query_name,
    }


def search_pmids(spec: QuerySpec, retmax: int) -> tuple[int, list[str]]:
    with Entrez.esearch(db="pubmed", term=spec.query, retmax=retmax, sort="relevance") as handle:
        result = Entrez.read(handle)
    count = int(result.get("Count", 0))
    ids = [str(pmid) for pmid in result.get("IdList", [])]
    return count, ids


def fetch_records(pmids: list[str], query_name: str) -> list[dict[str, str]]:
    if not pmids:
        return []
    records: list[dict[str, str]] = []
    for start in range(0, len(pmids), 100):
        batch = pmids[start : start + 100]
        with Entrez.efetch(db="pubmed", id=",".join(batch), rettype="xml", retmode="xml") as handle:
            result = Entrez.read(handle)
        for record in result.get("PubmedArticle", []):
            records.append(parse_record(record, query_name))
    return records


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    output_path = PROJECT_ROOT / args.out if args.out else resolve_path(config, "paths.search_results", "search/pubmed_results.csv")
    retmax_per_query = int(get_nested(config, "pubmed.retmax_per_query", 180))
    queries = load_queries(config)

    load_dotenv(PROJECT_ROOT / ".env")
    Entrez.email = os.getenv("ENTREZ_EMAIL", "codex@example.com")
    api_key = os.getenv("NCBI_API_KEY") or os.getenv("ENTREZ_API_KEY")
    if api_key:
        Entrez.api_key = api_key
    delay_seconds = 0.35 if api_key else 1.0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen: dict[str, dict[str, str]] = {}
    summary: list[tuple[str, int, int]] = []
    for spec in queries:
        count, pmids = search_pmids(spec, retmax_per_query)
        time.sleep(delay_seconds)
        rows = fetch_records(pmids, spec.name)
        time.sleep(delay_seconds)
        for row in rows:
            pmid = row["PMID"]
            if pmid not in seen:
                seen[pmid] = row
        summary.append((spec.name, count, len(pmids)))

    fieldnames = ["PMID", "Title", "Authors", "Journal", "Year", "Abstract", "DOI", "QueryName"]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(seen.values())

    print("PubMed search complete")
    for name, total, fetched in summary:
        print(f"- {name}: total_hits={total}, fetched={fetched}")
    print(f"Deduplicated records: {len(seen)}")
    print(f"Output: {display_path(output_path)}")


if __name__ == "__main__":
    main()
