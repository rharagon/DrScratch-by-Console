"""Multiprocess console tool to analyze Scratch .sb3 projects with DrScratch metrics.

This script offers the same functionality as ``console_analyzer.py`` but
processes projects in parallel using Python's ``multiprocessing`` module.
"""

import argparse
import csv
import os
import contextlib
from functools import partial
from multiprocessing import Pool, cpu_count
from typing import List, Tuple, Optional

from console_analyzer import (
    DEFAULT_SKILL_POINTS,
    analyze_file,
    flatten_metrics,
    load_progress,
    save_progress,
)


def _worker(input_dir: str, fname: str) -> Tuple[str, Optional[dict], Optional[str]]:
    """Process a single file and return its CSV row or an error message."""
    path = os.path.join(input_dir, fname)
    try:
        with open(os.devnull, 'w') as devnull, \
                     contextlib.redirect_stdout(devnull), \
                     contextlib.redirect_stderr(devnull):
                    metrics = analyze_file(path, DEFAULT_SKILL_POINTS)
        row = flatten_metrics(fname, metrics)
        project_id = os.path.splitext(fname)[0]
        print(f"> {project_id}, OK")
        return fname, row, None
    except Exception as exc:  # pragma: no cover - logged in parent process
        return fname, None, str(exc)


def analyze_directory_multiprocess(
    input_dir: str,
    csv_path: str,
    progress_path: str,
    processes: Optional[int] = None,
) -> None:
    """Analyze all ``.sb3`` projects in *input_dir* using multiple processes."""
    processed = load_progress(progress_path)
    os.makedirs(os.path.dirname(csv_path) or '.', exist_ok=True)
    files = [
        f for f in sorted(os.listdir(input_dir))
        if f.endswith('.sb3') and f not in processed
    ]

    csv_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    fieldnames: List[str] = []

    if csv_exists:
        with open(csv_path, newline='', encoding='utf-8') as fh:
            reader = csv.reader(fh)
            fieldnames = next(reader)
    else:
        # Determine fieldnames from the first successfully analysed project
        while files and not fieldnames:
            fname = files.pop(0)
            path = os.path.join(input_dir, fname)
            try:
                with open(os.devnull, 'w') as devnull, \
                     contextlib.redirect_stdout(devnull), \
                     contextlib.redirect_stderr(devnull):
                    metrics = analyze_file(path, DEFAULT_SKILL_POINTS)
                row = flatten_metrics(fname, metrics)
                fieldnames = list(row.keys())
                with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerow(row)
                processed.add(fname)
                save_progress(progress_path, processed)
                project_id = os.path.splitext(fname)[0]
                print(f"> {project_id}, OK")
            except Exception as exc:
                # print(f"Error processing {fname}: {exc}")
                project_id = os.path.splitext(fname)[0]
                print(f"< {project_id}, NOK,{exc}")
                continue
        if not fieldnames:
            return

    with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        worker = partial(_worker, input_dir)
        with Pool(processes=processes or cpu_count()) as pool:
            for fname, row, error in pool.imap_unordered(worker, files):
                if error:
                    # print(f"Error processing {fname}: {error}")
                    project_id = os.path.splitext(fname)[0]
                    print(f"< {project_id}, NOK,{error}")
                    continue
                writer.writerow(row)
                processed.add(fname)
                save_progress(progress_path, processed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Analyze Scratch .sb3 projects in parallel and export metrics to CSV.'
    )
    parser.add_argument('directory', help='Directory containing .sb3 files')
    parser.add_argument('output', help='Path to output CSV file')
    parser.add_argument('--progress', default='analysis_progress.json',
                        help='Path to progress file (default: analysis_progress.json)')
    parser.add_argument('--processes', type=int, default=None,
                        help='Number of worker processes (default: CPU count)')
    args = parser.parse_args()
    analyze_directory_multiprocess(args.directory, args.output, args.progress, args.processes)


if __name__ == '__main__':
    main()
