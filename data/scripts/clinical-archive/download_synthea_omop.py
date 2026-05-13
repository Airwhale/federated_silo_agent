"""Download the Synthea-OMOP dataset from AWS Open Data Registry.

Reference: https://registry.opendata.aws/synthea-omop/

The bucket exposes three datasets at:
  - s3://synthea-omop/synthea1k/   (1,000 patients, plain CSV)
  - s3://synthea-omop/synthea100k/ (100,000 patients, LZO-compressed CSV)
  - s3://synthea-omop/synthea23m/  (~23M patients, LZO-compressed CSV)

We download the 1k dataset by default — it's plain CSV (no LZO toolchain
required) and small (~28 MB). For larger demos, switch to synthea100k
(requires `lzop` or `python-lzo` for decompression).

Downloaded files land in data/raw/synthea_omop_{size}/.

Note: this dataset does NOT include OMOP vocabulary tables (concept,
concept_relationship, etc.). We handle vocabulary lookups via a small
in-repo concept map covering the conditions and drugs we care about
(see data/scripts/vocab.py).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from tqdm import tqdm


BUCKET_URL = "https://synthea-omop.s3.us-east-1.amazonaws.com"
S3_NAMESPACE = "{http://s3.amazonaws.com/doc/2006-03-01/}"

# Default size is the 1k dataset because:
#   - it's plain CSV (no LZO toolchain needed)
#   - 28 MB total — instant on any network
#   - we replicate-with-perturbation across 5 silos for the demo,
#     so 1k unique patients per silo of 1k is functionally fine.
DEFAULT_SIZE = "1k"
SIZE_TO_PREFIX = {
    "1k": "synthea1k/",
    "100k": "synthea100k/",
    "23m": "synthea23m/",
}


def list_bucket(prefix: str) -> list[tuple[str, int]]:
    """List files in the bucket under `prefix`, returning [(key, size_bytes), ...]."""
    url = f"{BUCKET_URL}/?list-type=2&prefix={prefix}&max-keys=1000"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for content in root.findall(f"{S3_NAMESPACE}Contents"):
        key = content.find(f"{S3_NAMESPACE}Key").text
        size = int(content.find(f"{S3_NAMESPACE}Size").text)
        if size > 0:  # skip the empty directory marker
            out.append((key, size))
    return out


def download_file(key: str, size: int, dest_dir: Path) -> Path:
    """Download a single key to dest_dir/{basename}, with progress bar."""
    filename = key.split("/")[-1]
    out_path = dest_dir / filename
    if out_path.exists() and out_path.stat().st_size == size:
        return out_path

    url = f"{BUCKET_URL}/{key}"
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()

    with open(out_path, "wb") as f, tqdm(
        total=size, unit="B", unit_scale=True, desc=filename, leave=False
    ) as pbar:
        for chunk in r.iter_content(chunk_size=64 * 1024):
            f.write(chunk)
            pbar.update(len(chunk))
    return out_path


def main(size: str = DEFAULT_SIZE, dest_root: Path | None = None) -> None:
    if size not in SIZE_TO_PREFIX:
        raise SystemExit(f"Unknown size {size!r}. Choose from: {list(SIZE_TO_PREFIX)}")

    prefix = SIZE_TO_PREFIX[size]
    if dest_root is None:
        dest_root = Path(__file__).resolve().parents[1] / "raw"
    dest_dir = dest_root / f"synthea_omop_{size}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"Listing s3://synthea-omop/{prefix} ...")
    files = list_bucket(prefix)
    if not files:
        raise SystemExit(f"No files found under {prefix}. Has the bucket layout changed?")

    total_bytes = sum(s for _, s in files)
    print(f"Found {len(files)} files, {total_bytes / 1024 / 1024:.1f} MB total")
    print()

    t0 = time.time()
    for key, sz in files:
        local = download_file(key, sz, dest_dir)
        print(f"  {sz/1024/1024:>10.2f} MB  {local.name}")
    elapsed = time.time() - t0

    print()
    print(f"Downloaded to: {dest_dir}")
    print(f"Elapsed: {elapsed:.1f}s")
    print()

    # Summary by table
    print("Table inventory:")
    for key, sz in files:
        local = dest_dir / key.split("/")[-1]
        if local.suffix == ".csv":
            # Count lines (rough row count, includes header)
            with open(local, "rb") as f:
                lines = sum(1 for _ in f)
            print(f"  {local.stem:<28} {lines-1:>10,} rows  ({sz/1024/1024:>7.2f} MB)")
        else:
            print(f"  {local.name:<28} (compressed; need lzop/python-lzo to count rows)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--size",
        choices=list(SIZE_TO_PREFIX),
        default=DEFAULT_SIZE,
        help=f"Dataset size (default {DEFAULT_SIZE})",
    )
    args = parser.parse_args()
    main(size=args.size)
