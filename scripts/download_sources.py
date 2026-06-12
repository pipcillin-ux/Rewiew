from __future__ import annotations

import csv
import argparse
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from Bio import Entrez
from dotenv import load_dotenv

from review_config import PROJECT_ROOT, add_config_arg, display_path, load_config, resolve_path


CORE_PATH = PROJECT_ROOT / "screening" / "core_screened.csv"
ABSTRACT_DIR = PROJECT_ROOT / "search" / "abstracts"
PDF_DIR = PROJECT_ROOT / "pdfs"
PDF_MAP_PATH = PDF_DIR / "pdf_map.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save local abstracts and attempt PMC PDF download for core records.")
    add_config_arg(parser)
    parser.add_argument("--core", help="Override configured core screened CSV path.")
    parser.add_argument("--abstracts-dir", help="Override configured abstracts directory.")
    parser.add_argument("--pdf-dir", help="Override configured PDF directory.")
    parser.add_argument("--pdf-map", help="Override configured PDF map CSV path.")
    return parser.parse_args()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


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


def abstract_path(row: pd.Series) -> Path:
    author = first_author(clean_text(row.get("Authors", "")))
    year = clean_text(row.get("Year", "")).split(".")[0] or "Year"
    pmid = clean_text(row.get("PMID", ""))
    title_slug = slugify(clean_text(row.get("Title", "")))[:45]
    return ABSTRACT_DIR / f"{author}{year}_{pmid}_{title_slug}.md"


def pdf_path(row: pd.Series, pmcid: str) -> Path:
    author = first_author(clean_text(row.get("Authors", "")))
    year = clean_text(row.get("Year", "")).split(".")[0] or "Year"
    pmid = clean_text(row.get("PMID", ""))
    title_slug = slugify(clean_text(row.get("Title", "")))[:45]
    return PDF_DIR / f"{author}{year}_{pmid}_{pmcid}_{title_slug}.pdf"


def write_abstract(row: pd.Series, path: Path) -> None:
    pmid = clean_text(row.get("PMID", ""))
    title = clean_text(row.get("Title", ""))
    text = f"""# {title}

## Metadata
- PMID: {pmid}
- DOI: {clean_text(row.get("DOI", "")) or "not available"}
- Authors: {clean_text(row.get("Authors", ""))}
- Journal: {clean_text(row.get("Journal", ""))}
- Year: {clean_text(row.get("Year", ""))}
- Category: {clean_text(row.get("Category", ""))}
- PubMed: https://pubmed.ncbi.nlm.nih.gov/{pmid}/

## Abstract
{clean_text(row.get("Abstract", "")) or "not available"}
"""
    path.write_text(text, encoding="utf-8")


def linked_pmcids(pmid: str, retries: int = 3) -> list[str]:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with Entrez.elink(dbfrom="pubmed", db="pmc", id=pmid, linkname="pubmed_pmc") as handle:
                result = Entrez.read(handle)
            break
        except Exception as exc:
            last_exc = exc
            if attempt == retries:
                raise
            time.sleep(0.75 * attempt)
    else:
        if last_exc:
            raise last_exc
        result = []
    ids: list[str] = []
    for linkset in result:
        for linkdb in linkset.get("LinkSetDb", []):
            for link in linkdb.get("Link", []):
                value = str(link.get("Id", "")).strip()
                if value:
                    ids.append(f"PMC{value}")
    return ids


def candidate_urls_from_oa_href(url: str) -> list[str]:
    urls: list[str] = []
    ftp_prefix = "ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/"
    https_prefix = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/"
    if url.startswith(ftp_prefix):
        suffix = url[len(ftp_prefix) :]
        urls.append(f"{https_prefix}deprecated/{suffix}")
        urls.append(f"{https_prefix}{suffix}")
    elif url.startswith(https_prefix):
        suffix = url[len(https_prefix) :]
        if not suffix.startswith("deprecated/"):
            urls.append(f"{https_prefix}deprecated/{suffix}")
        urls.append(url)
    else:
        urls.append(url)
    return list(dict.fromkeys(urls))


def candidate_pdf_urls(pmcid: str) -> list[str]:
    urls: list[str] = []
    oa_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"
    try:
        response = requests.get(oa_url, timeout=30)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for link in root.findall(".//link"):
                if link.attrib.get("format", "").lower() == "pdf":
                    href = link.attrib.get("href", "").strip()
                    if href:
                        urls.extend(candidate_urls_from_oa_href(href))
    except Exception:
        pass
    urls.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/")
    return list(dict.fromkeys(urls))


def get_with_retries(url: str, headers: dict[str, str], timeout: int, retries: int = 3) -> requests.Response:
    last_exc: requests.RequestException | None = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == retries:
                raise
            time.sleep(0.75 * attempt)
    if last_exc:
        raise last_exc
    raise RuntimeError("request retry loop exited unexpectedly")


def download_pmc_pdf(pmcid: str, target: Path) -> tuple[str, str]:
    headers = {
        "User-Agent": "literature-review-source-audit/1.0",
        "Accept": "application/pdf,*/*",
    }
    last_error = "no_candidate_url"
    for url in candidate_pdf_urls(pmcid):
        try:
            response = get_with_retries(url, headers=headers, timeout=45)
        except requests.RequestException as exc:
            last_error = f"request_failed:{type(exc).__name__}"
            continue
        if response.status_code != 200:
            last_error = f"http_status_{response.status_code}"
            continue
        content = response.content
        content_type = response.headers.get("content-type", "")
        if not content.startswith(b"%PDF") and "pdf" not in content_type.lower():
            last_error = "response_not_pdf"
            continue
        target.write_bytes(content)
        return "downloaded", response.url
    return "not_downloaded", last_error


def main() -> None:
    global ABSTRACT_DIR, CORE_PATH, PDF_DIR, PDF_MAP_PATH
    args = parse_args()
    config = load_config(args.config)
    CORE_PATH = PROJECT_ROOT / args.core if args.core else resolve_path(config, "paths.core_screened", "screening/core_screened.csv")
    ABSTRACT_DIR = PROJECT_ROOT / args.abstracts_dir if args.abstracts_dir else resolve_path(config, "paths.abstracts_dir", "search/abstracts")
    PDF_DIR = PROJECT_ROOT / args.pdf_dir if args.pdf_dir else resolve_path(config, "paths.pdf_dir", "pdfs")
    PDF_MAP_PATH = PROJECT_ROOT / args.pdf_map if args.pdf_map else resolve_path(config, "paths.pdf_map", "pdfs/pdf_map.csv")

    load_dotenv(PROJECT_ROOT / ".env")
    Entrez.email = os.getenv("ENTREZ_EMAIL", "codex@example.com")
    api_key = os.getenv("NCBI_API_KEY") or os.getenv("ENTREZ_API_KEY")
    if api_key:
        Entrez.api_key = api_key
    delay_seconds = 0.35 if api_key else 1.0

    ABSTRACT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CORE_PATH, dtype={"PMID": str}).fillna("")
    rows: list[dict[str, str]] = []

    for _, row in df.iterrows():
        pmid = clean_text(row.get("PMID", ""))
        apath = abstract_path(row)
        write_abstract(row, apath)

        pmcids: list[str] = []
        pdf_status = "no_pmc_link"
        pdf_file = ""
        pdf_url = ""
        source_type = "PubMed abstract"
        try:
            pmcids = linked_pmcids(pmid)
            time.sleep(delay_seconds)
        except Exception as exc:
            pdf_status = f"pmc_lookup_failed:{type(exc).__name__}"

        if pmcids:
            for pmcid in pmcids:
                target = pdf_path(row, pmcid)
                if target.exists() and target.stat().st_size > 0:
                    pdf_status = "already_downloaded"
                    pdf_file = display_path(target)
                    pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"
                    source_type = "PMC full text PDF"
                    break
                status, detail = download_pmc_pdf(pmcid, target)
                time.sleep(0.2)
                if status == "downloaded":
                    pdf_status = status
                    pdf_file = display_path(target)
                    pdf_url = detail
                    source_type = "PMC full text PDF"
                    break
                pdf_status = detail

        rows.append(
            {
                "PMID": pmid,
                "PMCID": ";".join(pmcids),
                "DOI": clean_text(row.get("DOI", "")),
                "Title": clean_text(row.get("Title", "")),
                "SourceType": source_type,
                "AbstractPath": display_path(apath),
                "PdfPath": pdf_file,
                "PdfStatus": pdf_status,
                "PdfUrl": pdf_url,
            }
        )
        print(f"{pmid}: abstract saved; pdf_status={pdf_status}", flush=True)

    fieldnames = [
        "PMID",
        "PMCID",
        "DOI",
        "Title",
        "SourceType",
        "AbstractPath",
        "PdfPath",
        "PdfStatus",
        "PdfUrl",
    ]
    with PDF_MAP_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Source acquisition complete: {len(rows)} records", flush=True)
    print(f"Abstracts: {display_path(ABSTRACT_DIR)}", flush=True)
    print(f"PDF map: {display_path(PDF_MAP_PATH)}", flush=True)


if __name__ == "__main__":
    main()
