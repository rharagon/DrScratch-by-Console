
import argparse
import csv
import json
import os
import re
import sys
import time
from typing import Optional, List, Dict
from tqdm import tqdm

# Choose concurrency backend
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

try:
    import requests
except ImportError:
    print("This script requires the 'requests' package. Install it with: pip install requests")
    sys.exit(1)

API_TEMPLATE = "https://api.scratch.mit.edu/projects/{project_id}"

def get_project_id_from_filename(filename: str) -> Optional[int]:
    """
    Extracts the numeric project id from a filename like '754492227.sb3' or 'project_754492227.sb3'.
    Returns None if not found.
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = re.search(r'(\d{3,})', stem)  # sequence of >=3 digits
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None

def fetch_project_metadata(project_id: int, timeout: float = 15.0, retries: int = 2, sleep_between: float = 0.2) -> Dict[str, Optional[str]]:
    """
    Fetch project metadata from the Scratch API.
    Includes 'Project title' along with Author, Creation/Modified dates, Remix ids.
    Retries transient failures up to 'retries' times.
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            url = API_TEMPLATE.format(project_id=project_id)
            r = requests.get(url, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json()

            author = (data.get("author") or {}).get("username")
            history = data.get("history") or {}
            creation_date = history.get("created")
            modified_date = history.get("modified")
            remix_parent_id = data.get("parent")
            remix_root_id = data.get("root")
            title = data.get("title")

            return {
                "project_id": project_id,
                "Project title": title,
                "Author": author,
                "Creation date": creation_date,
                "Modified date": modified_date,
                "Remix parent id": remix_parent_id,
                "Remix root id": remix_root_id,
            }
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(sleep_between)
            else:
                raise
    # Should not reach
    raise last_err

def iter_sb3_files(input_dir: str, recursive: bool) -> List[str]:
    files = []
    if recursive:
        for root, _dirs, fnames in os.walk(input_dir):
            for f in fnames:
                if f.lower().endswith(".sb3"):
                    files.append(os.path.join(root, f))
    else:
        files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.lower().endswith(".sb3")]
    files.sort()
    return files

def worker(path: str, timeout: float, retries: int, sleep_between: float) -> Dict[str, Optional[str]]:
    pid = get_project_id_from_filename(path)
    base = os.path.basename(path)
    row = {
        "project_id": pid,
        "Project title": None,
        "Author": None,
        "Creation date": None,
        "Modified date": None,
        "Remix parent id": None,
        "Remix root id": None,
        "filename": base,
        "_error": None,
    }
    if pid is None:
        row["_error"] = "No numeric project_id in filename"
        return row
    try:
        meta = fetch_project_metadata(pid, timeout=timeout, retries=retries, sleep_between=sleep_between)
        row.update(meta)
    except Exception as e:
        row["_error"] = str(e)
    return row

def main():
    parser = argparse.ArgumentParser(description="Extract Scratch project metadata from .sb3 files into a CSV using Scratch API (parallel).")
    parser.add_argument("--input", "-i", required=True, help="Folder containing .sb3 files")
    parser.add_argument("--output", "-o", required=True, help="Output CSV path")
    parser.add_argument("--recursive", action="store_true", help="Search .sb3 files recursively in subfolders")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout per request (seconds)")
    parser.add_argument("--retries", type=int, default=2, help="Retries on transient failures")
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep between retries (seconds)")
    parser.add_argument("--workers", type=int, default=0, help="Number of parallel workers (0 = use CPU count)")
    parser.add_argument("--processes", action="store_true", help="Use processes instead of threads")
    args = parser.parse_args()

    input_dir = args.input
    output_csv = args.output

    if not os.path.isdir(input_dir):
        print(f"ERROR: Input folder not found: {input_dir}", file=sys.stderr)
        sys.exit(2)

    sb3_files = iter_sb3_files(input_dir, args.recursive)

    if not sb3_files:
        print("No .sb3 files found in the input folder.", file=sys.stderr)
        sys.exit(0)

    max_workers = args.workers if args.workers > 0 else max(1, cpu_count())

    fieldnames = [
        "project_id",
        "Project title",
        "Author",
        "Creation date",
        "Modified date",
        "Remix parent id",
        "Remix root id",
        "filename",
        "_error",
    ]

    # Choose executor backend
    Executor = ProcessPoolExecutor if args.processes else ThreadPoolExecutor

    results = []
    with Executor(max_workers=max_workers) as ex:
        futures = [ex.submit(worker, path, args.timeout, args.retries, args.sleep) for path in sb3_files]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Procesando proyectos"):
            results.append(fut.result())

    # Sort results by project_id then filename for stable output
    results.sort(key=lambda r: (r.get("project_id") if r.get("project_id") is not None else -1, r.get("filename","")))

    # Write CSV
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)) or ".", exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    ok = sum(1 for r in results if not r.get("_error"))
    failed = len(results) - ok
    print(f"Done. OK: {ok}, Failed: {failed}, Total: {len(results)}")
    print(f"CSV saved to: {output_csv}")

if __name__ == "__main__":
    main()
