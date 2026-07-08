#!/usr/bin/env python3
"""
Download ChEMBL molecule structures (InChIKey, SMILES, MW) for ALL
FDA-approved drugs using the batch API endpoint.

This is the REAL data download — not a sample. It fetches structures
for all 2,996 ChEMBL approved drugs so they can flow through the
Phase 1 entity resolution pipeline.

Uses the ChEMBL batch endpoint /data/molecule/set/{ID1;ID2;...}.json
which fetches ~20 molecules per request (URL length limit).
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CHEMBL_DIR = os.path.join(HERE, "chembl")
IDS_FILE = os.path.join(CHEMBL_DIR, "chembl_ids.txt")
OUTPUT_FILE = os.path.join(CHEMBL_DIR, "molecule_structures_all.jsonl")
BATCH_SIZE = 20  # ChEMBL URL length limit


def fetch_batch(chembl_ids, batch_num, total_batches):
    """Fetch a batch of molecule structures from ChEMBL."""
    ids_param = ";".join(chembl_ids)
    url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/set/{ids_param}.json"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return data.get("molecules", [])
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  Batch {batch_num}/{total_batches}: rate limited, waiting 10s...")
            time.sleep(10)
            return fetch_batch(chembl_ids, batch_num, total_batches)
        print(f"  Batch {batch_num}/{total_batches}: HTTP {e.code} - {e.reason}")
        return []
    except Exception as e:
        print(f"  Batch {batch_num}/{total_batches}: error - {e}")
        return []


def extract_record(m):
    """Extract the fields we need from a ChEMBL molecule record."""
    props = m.get("molecule_properties", {}) or {}
    structs = m.get("molecule_structures", {}) or {}
    return {
        "chembl_id": m.get("molecule_chembl_id"),
        "name": m.get("pref_name"),
        "inchikey": structs.get("standard_inchi_key"),
        "smiles": structs.get("canonical_smiles"),
        "molecular_weight": props.get("full_mwt"),
        "molecular_formula": props.get("full_formula"),
        "max_phase": m.get("max_phase"),
        "first_approval": m.get("first_approval"),
        "drug_type": m.get("drug_type"),
        "withdrawn_flag": m.get("withdrawn_flag"),
        "black_box_warning": m.get("black_box_warning"),
        "atc_codes": [a.get("code") for a in (m.get("atc_classification") or [])],
    }


def main():
    # Load all ChEMBL IDs
    with open(IDS_FILE) as f:
        all_ids = [line.strip() for line in f if line.strip()]
    print(f"Total ChEMBL IDs to fetch: {len(all_ids)}")

    # Check for existing progress (resume support)
    existing_count = 0
    existing_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        if rec.get("chembl_id"):
                            existing_ids.add(rec["chembl_id"])
                            existing_count += 1
                    except json.JSONDecodeError:
                        pass
        print(f"Resuming: {existing_count} structures already downloaded")
        all_ids = [cid for cid in all_ids if cid not in existing_ids]
        print(f"Remaining: {len(all_ids)} to fetch")

    if not all_ids:
        print("All structures already downloaded!")
        return 0

    total_batches = (len(all_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    results = []
    errors = 0

    # Open output in append mode for resume support
    with open(OUTPUT_FILE, "a") as out_f:
        for batch_idx in range(0, len(all_ids), BATCH_SIZE):
            batch = all_ids[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1
            molecules = fetch_batch(batch, batch_num, total_batches)
            for m in molecules:
                record = extract_record(m)
                out_f.write(json.dumps(record) + "\n")
                results.append(record)
            if batch_num % 10 == 0:
                print(f"  Batch {batch_num}/{total_batches}: +{len(molecules)} "
                      f"(total this session: {len(results)})")
            # Small delay to be nice to the API
            if batch_num % 5 == 0:
                time.sleep(0.3)

    # Print summary
    total = existing_count + len(results)
    print(f"\nDownloaded {len(results)} new structures this session")
    print(f"Total structures: {total}")

    # Count quality
    all_records = []
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            for line in f:
                if line.strip():
                    try:
                        all_records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    print(f"Records with InChIKey: {sum(1 for r in all_records if r.get('inchikey'))}")
    print(f"Records with SMILES: {sum(1 for r in all_records if r.get('smiles'))}")
    print(f"Records with first_approval: {sum(1 for r in all_records if r.get('first_approval'))}")
    withdrawn = sum(
        1 for r in all_records
        if r.get("withdrawn_flag") and r["withdrawn_flag"] not in ("0", 0, None)
    )
    print(f"Records with withdrawn_flag=True: {withdrawn}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
