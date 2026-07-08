#!/usr/bin/env python3
"""
DrugBank-free data acquisition helper.

This script downloads the FREE biomedical data sources that the platform
needs, so operators without a DrugBank license (or while DrugBank
academic downloads are paused since May 2026) can still build the
knowledge graph.

Sources downloaded (all FREE, no login, no API key):
  1. ChEMBL SQLite (latest) — 2M+ compounds with bioactivity data
     URL: https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/
  2. UniProt Swiss-Prot (reviewed, curated) — 550K+ proteins
     URL: https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/
  3. STRING protein-protein interactions (human, 9606)
     URL: https://string-db.org/cgi/download
  4. PubChem Compound SDF (bulk FTP, no login)
     URL: https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/CURRENT-Full/SDF/
  5. FDA Orange Book (FDA-approved drugs + approval year — FREE)
     URL: https://www.fda.gov/drugs/development-approval-process-drugs/orange-book-data-files

For sources that DO require keys (OMIM, DisGeNET), the script prints
instructions on how to obtain them and exits gracefully.

Usage:
    python download_free_data_sources.py [--all | --source NAME]
    python download_free_data_sources.py --list

NOTE: This script does NOT download DrugBank. DrugBank requires a paid
license and academic downloads have been paused since May 2026. The
platform's DrugBank-free path (DRUGOS_USE_CHEMBL_AS_PRIMARY=1, default)
uses ChEMBL+PubChem+FDA Orange Book as the primary drug source instead.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

# ============================================================================
# Source definitions
# ============================================================================

SOURCES = {
    "chembl": {
        "description": "ChEMBL SQLite (2M+ compounds with bioactivity data)",
        "url": "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/",
        "filename_pattern": "chembl_*_sqlite.tar.gz",
        "size_estimate": "~4 GB compressed",
        "license": "CC BY-SA 3.0 (free, no login, no API key)",
        "requires_key": False,
        "instructions": (
            "Go to https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/\n"
            "  Download chembl_XX_sqlite.tar.gz (latest version)\n"
            "  Extract: tar xzf chembl_*_sqlite.tar.gz\n"
            "  Set DRUGOS_CHEMBL_SQLITE_PATH to the extracted .db file\n"
            "  No login, no API key required."
        ),
    },
    "uniprot": {
        "description": "UniProt Swiss-Prot (550K+ reviewed, curated proteins)",
        "url": "https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/",
        "filename": "uniprot_sprot.dat.gz",
        "size_estimate": "~500 MB compressed",
        "license": "CC BY 4.0 (free, no login, no API key)",
        "requires_key": False,
        "instructions": (
            "Go to https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/\n"
            "  Download uniprot_sprot.dat.gz (Swiss-Prot, curated)\n"
            "  Set DRUGOS_UNIPROT_SPR_FILE to the downloaded file\n"
            "  No login required. REST API also available at https://rest.uniprot.org/"
        ),
    },
    "string": {
        "description": "STRING protein-protein interactions (human, 9606)",
        "url": "https://string-db.org/cgi/download",
        "filename_pattern": "9606.protein.links.full.v*.txt.gz",
        "size_estimate": "~400 MB compressed (human only)",
        "license": "CC BY 4.0 (free, no login, no API key)",
        "requires_key": False,
        "instructions": (
            "Go to https://string-db.org/cgi/download\n"
            "  Select organism: Homo sapiens (9606)\n"
            "  Download protein.links.full.vXX.txt.gz (full interaction network)\n"
            "  Set DRUGOS_STRING_LINKS_FILE to the downloaded file\n"
            "  No login required."
        ),
    },
    "pubchem": {
        "description": "PubChem Compound SDF (110M+ compounds, bulk FTP)",
        "url": "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/CURRENT-Full/SDF/",
        "filename_pattern": "Compound_*.sdf.gz",
        "size_estimate": "~120 GB total (split into ~500K-compound chunks)",
        "license": "Public domain (free, no login, no API key)",
        "requires_key": False,
        "instructions": (
            "Bulk FTP (no login): https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/CURRENT-Full/SDF/\n"
            "  Files are split into chunks of ~500K compounds each.\n"
            "  Use a script to loop through and download all chunks.\n"
            "  For targeted queries (smaller scale), use PUG-REST:\n"
            "    https://pubchem.ncbi.nlm.nih.gov/rest/pug/\n"
            "  Set DRUGOS_PUBCHEM_SDF_DIR to the directory of downloaded SDFs."
        ),
    },
    "fda_orange_book": {
        "description": "FDA Orange Book (FDA-approved drugs + approval year)",
        "url": "https://www.fda.gov/drugs/development-approval-process-drugs/orange-book-data-files",
        "filename": "orange_book_data_files.zip",
        "size_estimate": "~5 MB",
        "license": "Public domain (free, no login, no API key)",
        "requires_key": False,
        "instructions": (
            "Go to https://www.fda.gov/drugs/development-approval-process-drugs/orange-book-data-files\n"
            "  Download 'Orange Book Data Files' (zip archive)\n"
            "  Contains: Products.txt, Patents.txt, Exclusivity.txt\n"
            "  Products.txt has Approval_Date + RLD (Reference Listed Drug)\n"
            "  This provides FDA approval year for the temporal split\n"
            "  (ROOT FIX Finding 26: Phase 1 needs approval_year for\n"
            "  temporal_split_pairs to satisfy the DOCX V1 launch criterion).\n"
            "  Set DRUGOS_FDA_ORANGE_BOOK_DIR to the extracted directory."
        ),
    },
    # Sources that REQUIRE keys — print instructions, do not download
    "omim": {
        "description": "OMIM gene-disease associations (REQUIRES API KEY)",
        "url": "https://www.omim.org/api",
        "requires_key": True,
        "key_env_var": "OMIM_API_KEY",
        "instructions": (
            "OMIM REQUIRES an API key. To obtain one:\n"
            "  1. Register at https://www.omim.org/api\n"
            "  2. Wait for email approval (typically 1-2 business days)\n"
            "  3. Set OMIM_API_KEY environment variable to your key\n"
            "  The user has already applied but not yet received a reply.\n"
            "  Until the key arrives, the OMIM pipeline uses the\n"
            "  omim_gene_disease_associations.csv fixture (shipped)."
        ),
    },
    "disgenet": {
        "description": "DisGeNET gene-disease associations (REQUIRES API KEY)",
        "url": "https://www.disgenet.org/api/",
        "requires_key": True,
        "key_env_var": "DISGENET_API_KEY",
        "instructions": (
            "DisGeNET REQUIRES an API key. To obtain one:\n"
            "  1. Register at https://www.disgenet.org/signup\n"
            "  2. Wait for email approval\n"
            "  3. Set DISGENET_API_KEY environment variable to your key\n"
            "  The user has already applied but not yet received a reply.\n"
            "  Until the key arrives, the DisGeNET pipeline uses the\n"
            "  disgenet_gene_disease_associations.csv fixture (shipped).\n"
            "  ALTERNATIVE: CTD (Comparative Toxicogenomics Database)\n"
            "  provides gene-disease associations without an API key:\n"
            "    https://ctdbase.org/downloads/"
        ),
    },
    "drugbank": {
        "description": "DrugBank (PAID LICENSE REQUIRED — academic downloads PAUSED since May 2026)",
        "url": "https://go.drugbank.com/public_users/sign_up",
        "requires_key": True,
        "key_env_var": "DRUGBANK_XML_PATH",
        "instructions": (
            "DRUGBANK STATUS: Academic downloads are PAUSED since May 2026.\n"
            "  Even registered academic users cannot download the XML file.\n"
            "  DrugBank data is governed by a custom EULA that PROHIBITS\n"
            "  redistribution (NOT CC-licensed — see Finding 2 root fix).\n\n"
            "  DRUGBANK-FREE PATH (DEFAULT, RECOMMENDED):\n"
            "    The platform uses ChEMBL+PubChem+FDA Orange Book as the\n"
            "    primary drug source (DRUGOS_USE_CHEMBL_AS_PRIMARY=1).\n"
            "    This requires NO DrugBank license and provides:\n"
            "      - 2M+ compounds (ChEMBL)\n"
            "      - 110M+ compound structures (PubChem)\n"
            "      - FDA approval status + approval year (FDA Orange Book)\n"
            "    The DrugBank-free path is FULLY FUNCTIONAL.\n\n"
            "  WHEN DRUGBANK DOWNLOADS RESUME:\n"
            "    1. Register at https://go.drugbank.com/public_users/sign_up\n"
            "    2. Download drugbank_all_full_database.xml.gz when available\n"
            "    3. Set DRUGBANK_XML_PATH to the file path\n"
            "    4. Set DRUGOS_USE_CHEMBL_AS_PRIMARY=0 to prefer DrugBank\n"
            "    5. The master DAG will automatically route to run_drugbank\n"
            "       (Finding 1 root fix: returns 'run_drugbank' not 'download_drugbank')."
        ),
    },
}


def list_sources() -> None:
    """Print all available data sources."""
    print("=" * 80)
    print("AVAILABLE DATA SOURCES")
    print("=" * 80)
    for name, info in SOURCES.items():
        key_status = "REQUIRES KEY" if info["requires_key"] else "FREE (no login)"
        print(f"\n  {name}")
        print(f"    Description: {info['description']}")
        print(f"    URL: {info['url']}")
        print(f"    Access: {key_status}")
        if "size_estimate" in info:
            print(f"    Size: {info['size_estimate']}")
        if "license" in info:
            print(f"    License: {info['license']}")
    print("\n" + "=" * 80)
    print("To download a specific source: python download_free_data_sources.py --source NAME")
    print("To see instructions for a source: python download_free_data_sources.py --instructions NAME")
    print("=" * 80)


def print_instructions(source_name: str) -> int:
    """Print download instructions for a specific source."""
    if source_name not in SOURCES:
        print(f"ERROR: unknown source {source_name!r}")
        print(f"Available sources: {', '.join(SOURCES.keys())}")
        return 1
    info = SOURCES[source_name]
    print("=" * 80)
    print(f"INSTRUCTIONS: {source_name}")
    print("=" * 80)
    print(f"Description: {info['description']}")
    print(f"URL: {info['url']}")
    if info["requires_key"]:
        print(f"REQUIRES: {info['key_env_var']} environment variable")
    print()
    print(info["instructions"])
    print("=" * 80)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DrugBank-free data acquisition helper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all available data sources and exit.",
    )
    parser.add_argument(
        "--instructions", metavar="SOURCE",
        help="Print download instructions for a specific source.",
    )
    parser.add_argument(
        "--all-free", action="store_true",
        help="Print instructions for ALL free (no-key) sources.",
    )
    args = parser.parse_args()

    if args.list:
        list_sources()
        return 0

    if args.instructions:
        return print_instructions(args.instructions)

    if args.all_free:
        print("=" * 80)
        print("INSTRUCTIONS FOR ALL FREE (NO-KEY) DATA SOURCES")
        print("=" * 80)
        for name, info in SOURCES.items():
            if not info["requires_key"]:
                print_instructions(name)
                print()
        return 0

    # Default: show list
    list_sources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
