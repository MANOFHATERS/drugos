"""Pathways Pipeline — Biological pathway data from Reactome & KEGG.

This pipeline extracts biological pathway information from public databases
(Reactome and KEGG) and produces pathways.csv for Phase 2 knowledge graph
construction.

DOCX Phase 2 Spec Compliance:
    The Phase 2 specification mandates 5 node types:
    - Drugs (Compounds)
    - Proteins (Genes)
    - Biological Pathways ← THIS PIPELINE
    - Diseases
    - Clinical Outcomes
    
    And 5 edge types including:
    - Protein -> participates_in -> Pathway
    - Pathway -> disrupted_in -> Disease

Data Sources:
    - Reactome: Curated human biological pathways with protein mappings
    - KEGG: Kyoto Encyclopedia of Genes and Genomes pathways

Output Schema (pathways.csv):
    - pathway_id: str — e.g., "REACT:R-HSA-1234" or "KEGG:hsa00010"
    - pathway_name: str — e.g., "Glycolysis"
    - source: str — e.g., "reactome", "kegg"
    - uniprot_ids: str — semicolon-separated UniProt accessions
    - gene_symbols: str — semicolon-separated gene symbols
    - description: str — pathway description

License: MIT — Team Cosmic / VentureLab.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import requests

from config.settings import (
    PROCESSED_DATA_DIR,
    RAW_DOWNLOADS_DIR,
)
from pipelines.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)

# Reactome API endpoints
REACTOME_API_BASE = "https://reactome.org/ContentService/data"
REACTOME_SPECIES = "Homo sapiens"

# KEGG API endpoints  
KEGG_API_BASE = "https://rest.kegg.jp"


class PathwaysPipeline(BasePipeline):
    """Extract biological pathway data from Reactome and KEGG."""
    
    def __init__(self):
        super().__init__(
            source_name="pathways",
            raw_dir=RAW_DOWNLOADS_DIR / "pathways",
        )
        self.pathway_data: List[Dict[str, Any]] = []
        
    def download(self) -> Path:
        """Download pathway data from Reactome and KEGG APIs.
        
        Returns:
            Path to a marker file indicating download completion.
        """
        logger.info("[pathways] Starting pathway data download...")
        t0 = time.perf_counter()
        
        # Ensure raw directory exists
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        
        # Download from Reactome
        reactome_pathways = self._download_reactome()
        logger.info(f"[pathways] Downloaded {len(reactome_pathways)} Reactome pathways")
        
        # Download from KEGG
        kegg_pathways = self._download_kegg()
        logger.info(f"[pathways] Downloaded {len(kegg_pathways)} KEGG pathways")
        
        # Combine and deduplicate
        all_pathways = reactome_pathways + kegg_pathways
        seen_ids: Set[str] = set()
        unique_pathways = []
        for pw in all_pathways:
            if pw["pathway_id"] not in seen_ids:
                seen_ids.add(pw["pathway_id"])
                unique_pathways.append(pw)
                
        self.pathway_data = unique_pathways
        
        elapsed = time.perf_counter() - t0
        logger.info(
            f"[pathways] Download completed in {elapsed:.2f}s — "
            f"{len(unique_pathways)} unique pathways"
        )
        
        # Write marker file
        marker_path = self.raw_dir / "download_complete.txt"
        marker_path.write_text(
            f"Downloaded at: {datetime.now(timezone.utc).isoformat()}\n"
            f"Total pathways: {len(unique_pathways)}\n"
            f"Reactome: {len(reactome_pathways)}\n"
            f"KEGG: {len(kegg_pathways)}\n"
        )
        
        return marker_path
    
    def _download_reactome(self) -> List[Dict[str, Any]]:
        """Download pathway data from Reactome.
        
        Uses Reactome's ContentService API to fetch:
        1. All human pathways
        2. Proteins participating in each pathway
        """
        pathways = []
        
        try:
            # Step 1: Get all top-level pathways for Homo sapiens
            logger.info("[pathways] Fetching Reactome top-level pathways...")
            response = requests.get(
                f"{REACTOME_API_BASE}/species/{REACTOME_SPECIES}/pathways",
                timeout=60,
            )
            response.raise_for_status()
            top_level = response.json()
            
            # Step 2: Recursively get all sub-pathways
            all_pathway_ids = self._collect_all_pathway_ids(top_level)
            logger.info(
                f"[pathways] Found {len(all_pathway_ids)} total Reactome pathways"
            )
            
            # Step 3: For each pathway, get details and participating proteins
            for pw_id in all_pathway_ids:
                try:
                    pw_info = self._fetch_reactome_pathway_info(pw_id)
                    if pw_info:
                        pathways.append(pw_info)
                except Exception as e:
                    logger.warning(
                        f"[pathways] Failed to fetch Reactome pathway {pw_id}: {e}"
                    )
                    
        except Exception as e:
            logger.error(f"[pathways] Reactome download failed: {e}")
            # Return empty list on failure - don't crash the pipeline
            
        return pathways
    
    def _collect_all_pathway_ids(self, pathway_tree: List[Dict]) -> List[str]:
        """Recursively collect all pathway IDs from a pathway tree."""
        ids = []
        for node in pathway_tree:
            if isinstance(node, dict):
                pw_id = node.get("id") or node.get("stId")
                if pw_id:
                    ids.append(pw_id)
                # Recurse into children
                children = node.get("children", [])
                ids.extend(self._collect_all_pathway_ids(children))
        return ids
    
    def _fetch_reactome_pathway_info(self, pathway_id: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed info for a single Reactome pathway."""
        # Get pathway name and description
        try:
            name_response = requests.get(
                f"{REACTOME_API_BASE}/identifier/{pathway_id}/name",
                timeout=30,
            )
            name_response.raise_for_status()
            pathway_name = name_response.json().get("name", pathway_id)
        except Exception:
            pathway_name = pathway_id
            
        # Get participating proteins
        try:
            proteins_response = requests.get(
                f"{REACTOME_API_BASE}/identifier/{pathway_id}/participants",
                timeout=30,
            )
            proteins_response.raise_for_status()
            participants = proteins_response.json()
            
            # Extract UniProt IDs and gene symbols
            uniprot_ids = []
            gene_symbols = []
            for participant in participants:
                if isinstance(participant, dict):
                    # Try to get UniProt ID
                    db_id = participant.get("databaseIdentifier", {})
                    if db_id.get("databaseName") == "UniProt":
                        uniprot_ids.append(db_id.get("identifier", ""))
                    
                    # Try to get gene symbol
                    gene_name = participant.get("displayName", "")
                    if gene_name:
                        gene_symbols.append(gene_name)
                        
        except Exception:
            uniprot_ids = []
            gene_symbols = []
            
        return {
            "pathway_id": f"REACT:{pathway_id}",
            "pathway_name": pathway_name,
            "source": "reactome",
            "uniprot_ids": ";".join(set(uniprot_ids)) if uniprot_ids else "",
            "gene_symbols": ";".join(set(gene_symbols)) if gene_symbols else "",
            "description": f"Reactome pathway: {pathway_name}",
        }
    
    def _download_kegg(self) -> List[Dict[str, Any]]:
        """Download pathway data from KEGG.
        
        Uses KEGG REST API to fetch:
        1. All human pathways
        2. Gene/protein mappings for each pathway
        """
        pathways = []
        
        try:
            # Step 1: Get all KEGG pathway IDs for humans (hsa prefix)
            logger.info("[pathways] Fetching KEGG pathway list...")
            response = requests.get(
                f"{KEGG_API_BASE}/list/pathway/hsa",
                timeout=60,
            )
            response.raise_for_status()
            
            pathway_lines = response.text.strip().split("\n")
            pathway_ids = []
            for line in pathway_lines:
                if line.startswith("path:hsa"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        kegg_id = parts[0].replace("path:", "")
                        pathway_ids.append(kegg_id)
                        
            logger.info(f"[pathways] Found {len(pathway_ids)} KEGG human pathways")
            
            # Step 2: For each pathway, get genes and details
            for kegg_id in pathway_ids[:500]:  # Limit to avoid rate limiting
                try:
                    pw_info = self._fetch_kegg_pathway_info(kegg_id)
                    if pw_info:
                        pathways.append(pw_info)
                except Exception as e:
                    logger.warning(
                        f"[pathways] Failed to fetch KEGG pathway {kegg_id}: {e}"
                    )
                    
        except Exception as e:
            logger.error(f"[pathways] KEGG download failed: {e}")
            
        return pathways
    
    def _fetch_kegg_pathway_info(self, kegg_id: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed info for a single KEGG pathway."""
        # Get pathway name
        try:
            name_response = requests.get(
                f"{KEGG_API_BASE}/get/{kegg_id}",
                timeout=30,
            )
            name_response.raise_for_status()
            
            # Parse KEGG flatfile format
            content = name_response.text
            pathway_name = kegg_id
            description = ""
            
            for line in content.split("\n"):
                if line.startswith("NAME"):
                    pathway_name = line[4:].strip().rstrip(";")
                elif line.startswith("DEFINITION"):
                    description = line[10:].strip()
                    
        except Exception:
            pathway_name = kegg_id
            description = ""
            
        # Get genes in pathway
        try:
            genes_response = requests.get(
                f"{KEGG_API_BASE}/link/genes/{kegg_id}",
                timeout=30,
            )
            genes_response.raise_for_status()
            
            gene_lines = genes_response.text.strip().split("\n")
            gene_symbols = []
            uniprot_ids = []
            
            for line in gene_lines:
                if line.startswith("hsa:"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        gene_symbol = parts[1].replace("hsa:", "")
                        gene_symbols.append(gene_symbol)
                        
        except Exception:
            gene_symbols = []
            uniprot_ids = []
            
        return {
            "pathway_id": f"KEGG:{kegg_id}",
            "pathway_name": pathway_name,
            "source": "kegg",
            "uniprot_ids": ";".join(set(uniprot_ids)) if uniprot_ids else "",
            "gene_symbols": ";".join(set(gene_symbols)) if gene_symbols else "",
            "description": description or f"KEGG pathway: {pathway_name}",
        }
    
    def clean(self, raw_path: Path) -> pd.DataFrame:
        """Clean and normalize pathway data.
        
        Args:
            raw_path: Path to the downloaded data (marker file).
            
        Returns:
            DataFrame with cleaned pathway records.
        """
        logger.info("[pathways] Starting pathway data cleaning...")
        t0 = time.perf_counter()
        
        if not self.pathway_data:
            logger.warning("[pathways] No pathway data to clean")
            return self._empty_output()
            
        # Convert to DataFrame
        df = pd.DataFrame(self.pathway_data)
        
        # Validate required columns
        required_cols = ["pathway_id", "pathway_name", "source"]
        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
            
        # Clean and normalize
        df = df.dropna(subset=["pathway_id"])  # Remove rows without ID
        df = df.drop_duplicates(subset=["pathway_id"])  # Deduplicate by ID
        
        # Normalize column types
        df["pathway_id"] = df["pathway_id"].astype(str).str.strip()
        df["pathway_name"] = df["pathway_name"].astype(str).str.strip()
        df["source"] = df["source"].astype(str).str.lower().str.strip()
        df["uniprot_ids"] = df["uniprot_ids"].fillna("").astype(str).str.strip()
        df["gene_symbols"] = df["gene_symbols"].fillna("").astype(str).str.strip()
        df["description"] = df["description"].fillna("").astype(str).str.strip()
        
        # Reorder columns to match expected schema
        df = df[["pathway_id", "pathway_name", "source", "uniprot_ids", 
                 "gene_symbols", "description"]]
        
        elapsed = time.perf_counter() - t0
        logger.info(
            f"[pathways] Cleaning completed in {elapsed:.2f}s — "
            f"{len(df)} pathways"
        )
        
        return df
    
    def _empty_output(self) -> pd.DataFrame:
        """Return empty DataFrame with expected schema."""
        return pd.DataFrame(columns=[
            "pathway_id", "pathway_name", "source",
            "uniprot_ids", "gene_symbols", "description"
        ])
    
    def load(
        self,
        df: pd.DataFrame,
        session: Optional[Any] = None,
    ) -> int:
        """Load pathway data to database (optional - mainly for CSV output).
        
        Args:
            df: Cleaned pathway DataFrame.
            session: Optional database session.
            
        Returns:
            Number of records loaded.
        """
        if df.empty:
            logger.info("[pathways] No pathway records to load")
            return 0
            
        logger.info(f"[pathways] Loaded {len(df)} pathway records")
        return len(df)


def main():
    """Run the pathways pipeline standalone."""
    logging.basicConfig(level=logging.INFO)
    
    pipeline = PathwaysPipeline()
    
    # Run full pipeline
    raw_path = pipeline.download()
    df = pipeline.clean(raw_path)
    
    # Save to processed_data
    output_path = PROCESSED_DATA_DIR / "pathways.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_path, index=False)
    logger.info(f"[pathways] Saved {len(df)} pathways to {output_path}")
    
    return df


if __name__ == "__main__":
    main()
