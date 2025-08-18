"""Console tool to analyze Scratch .sb3 projects with DrScratch metrics.

The script scans a directory for `.sb3` files, computes all available
metrics for each project and writes them to a CSV file. Progress is
stored in a JSON file so the process can be interrupted and resumed
later.
"""

import argparse
import csv
import json
import os
from zipfile import ZipFile

from app.hairball3.mastery import Mastery
from app.hairball3.duplicateScripts import DuplicateScripts
from app.hairball3.deadCode import DeadCode
from app.hairball3.babiaInfo import Babia
from app.hairball3.spriteNaming import SpriteNaming
from app.hairball3.backdropNaming import BackdropNaming

DEFAULT_SKILL_POINTS = {
    'Abstraction': 4,
    'Parallelization': 4,
    'Logic': 4,
    'Synchronization': 4,
    'FlowControl': 4,
    'UserInteractivity': 4,
    'DataRepresentation': 4,
    'MathOperators': 4,
    'MotionOperators': 4,
}


def load_json_project(path_projectsb3: str):
    """Load the project.json from a Scratch 3 project file."""
    with ZipFile(path_projectsb3, "r") as zf:
        with zf.open("project.json") as project:
            return json.load(project)


def _parse_naming(result: str) -> dict:
    """Parse the textual output of naming plugins."""
    lines = result.split('\n')
    number = int(lines[0].split(' ')[0]) if lines and lines[0] else 0
    items = lines[1:-1] if len(lines) > 2 else []
    key = 'sprite' if 'sprite' in result.lower() else 'backdrop'
    return {'number': number, key: items}


def analyze_file(path: str, skill_points: dict) -> dict:
    """Compute DrScratch metrics for a project."""
    json_project = load_json_project(path)
    mastery = Mastery(path, json_project, skill_points, 'Default').finalize()
    duplicate = DuplicateScripts(path, json_project).finalize()
    dead = DeadCode(path, json_project).finalize()
    babia = Babia(path, json_project).finalize()
    sprite = _parse_naming(SpriteNaming(path, json_project).finalize())
    backdrop = _parse_naming(BackdropNaming(path, json_project).finalize())
    return {
        'mastery': mastery['extended'],
        'mastery_vanilla': mastery.get('vanilla', {}),
        'duplicateScript': duplicate['result'],
        'deadCode': dead['result'],
        'babia': babia,
        'spriteNaming': sprite,
        'backdropNaming': backdrop,
    }

def flatten_metrics(project_name: str, metrics: dict) -> dict:
    row = {'project': project_name}
    mastery = metrics['mastery']
    row['mastery_total_points'] = mastery['total_points'][0]
    row['mastery_total_max'] = mastery['total_points'][1]
    row['mastery_competence'] = mastery['competence']
    for skill in DEFAULT_SKILL_POINTS:
        if skill in mastery:
            row[skill] = mastery[skill][0]
    dup = metrics['duplicateScript']
    row['duplicateScripts'] = dup['total_duplicate_scripts']
    dead = metrics['deadCode']
    row['deadCode'] = dead['total_dead_code_scripts']
    sprite = metrics['spriteNaming']
    row['spriteNaming'] = sprite['number']
    backdrop = metrics['backdropNaming']
    row['backdropNaming'] = backdrop['number']
    babia = metrics['babia']
    row['babia_num_sprites'] = babia.get('num_sprites', 0)
    return row

def load_progress(path: str) -> set:
    """Load processed file names from the progress file."""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as fh:
            try:
                return set(json.load(fh))
            except json.JSONDecodeError:
                return set()
    return set()


def save_progress(path: str, processed: set) -> None:
    """Persist the set of processed files."""
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(sorted(processed), fh)


def analyze_directory(input_dir: str, csv_path: str, progress_path: str) -> None:
    processed = load_progress(progress_path)
    fieldnames = [
        'project', 'mastery_total_points', 'mastery_total_max', 'mastery_competence',
        'Abstraction', 'Parallelization', 'Logic', 'Synchronization', 'FlowControl',
        'UserInteractivity', 'DataRepresentation', 'MathOperators', 'MotionOperators',
        'duplicateScripts', 'deadCode', 'spriteNaming', 'backdropNaming',
        'babia_num_sprites'
    ]

    os.makedirs(os.path.dirname(csv_path) or '.', exist_ok=True)
    csv_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not csv_exists:
            writer.writeheader()
        files = sorted(f for f in os.listdir(input_dir) if f.endswith('.sb3'))
        for fname in files:
            if fname in processed:
                continue
            path = os.path.join(input_dir, fname)
            try:
                metrics = analyze_file(path, DEFAULT_SKILL_POINTS)
                row = flatten_metrics(fname, metrics)
                writer.writerow(row)
                processed.add(fname)
                save_progress(progress_path, processed)
                project_id = os.path.splitext(fname)[0]
                print(f"{project_id},OK")
            except Exception as exc:
                project_id = os.path.splitext(fname)[0]
                print(f"{project_id},NOK,{exc}")
                continue


def main() -> None:
    parser = argparse.ArgumentParser(description='Analyze Scratch .sb3 projects and export metrics to CSV.')
    parser.add_argument('directory', help='Directory containing .sb3 files')
    parser.add_argument('output', help='Path to output CSV file')
    parser.add_argument('--progress', default='analysis_progress.json',
                        help='Path to progress file (default: analysis_progress.json)')
    args = parser.parse_args()
    analyze_directory(args.directory, args.output, args.progress)


if __name__ == '__main__':
    main()
