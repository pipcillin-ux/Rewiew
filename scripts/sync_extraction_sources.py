from __future__ import annotations

import argparse
import re

import pandas as pd

from review_config import PROJECT_ROOT, add_config_arg, load_config, resolve_path

PDF_MAP_PATH = PROJECT_ROOT / "pdfs" / "pdf_map.csv"
EXTRACTION_DIR = PROJECT_ROOT / "extractions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync extraction note Text source lines from configured PDF map.")
    add_config_arg(parser)
    parser.add_argument("--pdf-map", help="Override configured PDF/source map CSV path.")
    parser.add_argument("--extractions-dir", help="Override configured extraction directory.")
    return parser.parse_args()


def source_label(row: pd.Series) -> str:
    source_type = str(row.get("SourceType", "")).strip() or "PubMed abstract"
    pdf_path = str(row.get("PdfPath", "")).strip()
    abstract_path = str(row.get("AbstractPath", "")).strip()
    if source_type == "PMC full text PDF" and pdf_path:
        return f"{source_type} (local source: {pdf_path})"
    if abstract_path:
        return f"PubMed abstract (local source: {abstract_path})"
    return source_type


def main() -> None:
    global EXTRACTION_DIR, PDF_MAP_PATH
    args = parse_args()
    config = load_config(args.config)
    PDF_MAP_PATH = PROJECT_ROOT / args.pdf_map if args.pdf_map else resolve_path(config, "paths.pdf_map", "pdfs/pdf_map.csv")
    EXTRACTION_DIR = PROJECT_ROOT / args.extractions_dir if args.extractions_dir else resolve_path(config, "paths.extractions_dir", "extractions")

    source_map = pd.read_csv(PDF_MAP_PATH, dtype={"PMID": str}).fillna("")
    updated = 0
    missing = []

    for _, row in source_map.iterrows():
        pmid = str(row.get("PMID", "")).strip()
        matches = list(EXTRACTION_DIR.glob(f"*_{pmid}_*.md"))
        if not matches:
            missing.append(pmid)
            continue
        path = matches[0]
        text = path.read_text(encoding="utf-8")
        new_line = f"- **Text source:** {source_label(row)}"
        new_text, count = re.subn(r"^- \*\*Text source:\*\* .*$", new_line, text, count=1, flags=re.M)
        if count == 0:
            missing.append(pmid)
            continue
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            updated += 1

    print(f"Extraction source sync complete: updated={updated}, checked={len(source_map)}")
    if missing:
        print("Missing extraction/source lines for PMIDs:", ", ".join(missing))


if __name__ == "__main__":
    main()
