from __future__ import annotations

import argparse
import os
import time

import pandas as pd
from Bio import Entrez
from dotenv import load_dotenv

from review_config import PROJECT_ROOT, add_config_arg, display_path, load_config, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export PubMed records as NBIB/Medline for Zotero import.")
    add_config_arg(parser)
    parser.add_argument(
        "--input",
        default=None,
        help="CSV file with a PMID column, relative to project root.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output NBIB file, relative to project root.",
    )
    return parser.parse_args()


def fetch_nbib(pmids: list[str]) -> str:
    chunks: list[str] = []
    for start in range(0, len(pmids), 100):
        batch = pmids[start : start + 100]
        with Entrez.efetch(db="pubmed", id=",".join(batch), rettype="medline", retmode="text") as handle:
            chunks.append(handle.read().strip())
        time.sleep(0.35)
    return "\n\n".join(chunk for chunk in chunks if chunk)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    load_dotenv(PROJECT_ROOT / ".env")
    Entrez.email = os.getenv("ENTREZ_EMAIL", "codex@example.com")
    api_key = os.getenv("NCBI_API_KEY") or os.getenv("ENTREZ_API_KEY")
    if api_key:
        Entrez.api_key = api_key

    input_path = PROJECT_ROOT / args.input if args.input else resolve_path(config, "paths.core_screened", "screening/core_screened.csv")
    output_path = PROJECT_ROOT / args.out if args.out else resolve_path(config, "paths.nbib", "search/included_papers.nbib")
    df = pd.read_csv(input_path, dtype={"PMID": str}).fillna("")
    pmids = [str(pmid).strip() for pmid in df["PMID"].tolist() if str(pmid).strip()]
    if not pmids:
        raise RuntimeError(f"No PMIDs found in {display_path(input_path)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    nbib = fetch_nbib(pmids)
    output_path.write_text(nbib + "\n", encoding="utf-8")

    print(f"Exported {len(pmids)} PubMed records")
    print(f"Input: {display_path(input_path)}")
    print(f"Output: {display_path(output_path)}")


if __name__ == "__main__":
    main()
