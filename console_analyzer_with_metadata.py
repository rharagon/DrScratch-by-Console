"""Multiprocess console tool to analyze Scratch .sb3 projects with DrScratch metrics and metadata.

This script combines the functionality of console_analyzer_multiprocess.py and extract_scratch_meta.py.
It processes projects in parallel, computes DrScratch metrics, and fetches metadata from Scratch API.

Key difference: Projects without blocks are now included with total_blocks=0 and all CT metrics set to 0,
rather than being marked as failed.
"""

import argparse
import csv
import json
import os
import sys
import logging
import contextlib
import re
import time as time_module
from functools import partial
from multiprocessing import cpu_count
from typing import List, Optional, Set, Dict, Any
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from time import time
from zipfile import ZipFile

try:
    import requests
except ImportError:
    requests = None

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

API_TEMPLATE = "https://api.scratch.mit.edu/projects/{project_id}"


@dataclass
class ProcessingResult:
    """Resultado del procesamiento de un archivo."""
    filename: str
    success: bool
    row: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time: float = 0.0
    has_blocks: bool = True


class ProgressManager:
    """Gestor mejorado del progreso con guardado automatico."""

    def __init__(self, progress_path: str, save_interval: int = 10, ignore_progress: bool = False):
        self.progress_path = Path(progress_path)
        self.save_interval = save_interval
        self.ignore_progress = ignore_progress
        self.processed: Set[str] = set() if ignore_progress else self._load_progress()
        self.counter = 0
        self.total_processed = len(self.processed)

    def _load_progress(self) -> Set[str]:
        """Load processed file names from the progress file."""
        if self.progress_path.exists():
            try:
                with open(self.progress_path, 'r', encoding='utf-8') as fh:
                    return set(json.load(fh))
            except (json.JSONDecodeError, Exception):
                return set()
        return set()

    def add(self, filename: str) -> None:
        """Anade un archivo procesado y guarda si es necesario."""
        if filename not in self.processed:
            self.processed.add(filename)
            self.counter += 1
            self.total_processed += 1

            if self.counter >= self.save_interval:
                self.save()
                self.counter = 0

    def save(self) -> None:
        """Guarda el progreso actual."""
        with open(self.progress_path, 'w', encoding='utf-8') as fh:
            json.dump(sorted(self.processed), fh)
        self.counter = 0

    def __contains__(self, filename: str) -> bool:
        return filename in self.processed


def safe_print(message: str) -> None:
    """Imprime mensajes de forma segura, manejando problemas de encoding."""
    try:
        print(message)
    except UnicodeEncodeError:
        safe_message = message.encode('ascii', errors='replace').decode('ascii')
        print(safe_message)
    except Exception:
        print("Processing file...")


def setup_logging(log_file: Optional[str] = None) -> logging.Logger:
    """Configura el logging para el proceso."""
    logger = logging.getLogger('scratch_analyzer_meta')
    logger.setLevel(logging.INFO)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8', errors='replace')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            logger.addHandler(file_handler)
        except Exception:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            logger.addHandler(file_handler)

    return logger


def load_json_project(path_projectsb3: str) -> dict:
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


def count_blocks_in_project(json_project: dict) -> int:
    """Count the total number of blocks in a project."""
    total_blocks = 0
    for key, list_info in json_project.items():
        if key == "targets":
            for dict_target in list_info:
                for dicc_key, dicc_value in dict_target.items():
                    if dicc_key == "blocks":
                        for blocks, blocks_value in dicc_value.items():
                            if isinstance(blocks_value, dict):
                                total_blocks += 1
    return total_blocks


def get_empty_metrics() -> dict:
    """Return empty metrics structure for projects without blocks."""
    empty_mastery = {
        'total_blocks': 0,
        'total_points': [0, sum(DEFAULT_SKILL_POINTS.values())],
        'max_points': sum(DEFAULT_SKILL_POINTS.values()),
        'average_points': 0,
        'competence': 'Basic',
    }
    for skill in DEFAULT_SKILL_POINTS:
        empty_mastery[skill] = [0, DEFAULT_SKILL_POINTS[skill]]

    return {
        'mastery': empty_mastery,
        'mastery_vanilla': {},
        'duplicateScript': {'total_duplicate_scripts': 0},
        'deadCode': {'total_dead_code_scripts': 0},
        'babia': {'num_sprites': 0},
        'spriteNaming': {'number': 0, 'sprite': []},
        'backdropNaming': {'number': 0, 'backdrop': []},
    }


def analyze_file_safe(path: str, skill_points: dict) -> tuple:
    """
    Compute DrScratch metrics for a project.
    Returns (metrics, has_blocks) tuple.
    If project has no blocks, returns empty metrics with has_blocks=False.
    """
    json_project = load_json_project(path)

    # Check if project has blocks
    block_count = count_blocks_in_project(json_project)
    if block_count == 0:
        # Return empty metrics for project without blocks
        metrics = get_empty_metrics()
        # Still try to get babia info for sprite count
        try:
            babia = Babia(path, json_project).finalize()
            metrics['babia'] = babia
        except Exception:
            pass
        return metrics, False

    # Normal processing for projects with blocks
    mastery = Mastery(path, json_project, skill_points, 'Default').finalize()
    duplicate = DuplicateScripts(path, json_project).finalize()
    dead = DeadCode(path, json_project).finalize()
    babia = Babia(path, json_project).finalize()
    sprite = _parse_naming(SpriteNaming(path, json_project).finalize())
    backdrop = _parse_naming(BackdropNaming(path, json_project).finalize())

    metrics = {
        'mastery': mastery['extended'],
        'mastery_vanilla': mastery.get('vanilla', {}),
        'duplicateScript': duplicate['result'],
        'deadCode': dead['result'],
        'babia': babia,
        'spriteNaming': sprite,
        'backdropNaming': backdrop,
    }
    return metrics, True


def flatten_metrics(project_name: str, metrics: dict) -> dict:
    """Flatten metrics dictionary to a single row for CSV."""
    row = {'project': project_name}
    mastery = metrics['mastery']
    row['total_blocks'] = mastery.get('total_blocks', 0)
    row['mastery_total_points'] = mastery['total_points'][0]
    row['mastery_total_max'] = mastery['total_points'][1]
    row['mastery_competence'] = mastery['competence']

    for skill in DEFAULT_SKILL_POINTS:
        if skill in mastery:
            row[skill] = mastery[skill][0]
        else:
            row[skill] = 0

    dup = metrics['duplicateScript']
    row['duplicateScripts'] = dup.get('total_duplicate_scripts', 0)
    dead = metrics['deadCode']
    row['deadCode'] = dead.get('total_dead_code_scripts', 0)
    sprite = metrics['spriteNaming']
    row['spriteNaming'] = sprite.get('number', 0)
    backdrop = metrics['backdropNaming']
    row['backdropNaming'] = backdrop.get('number', 0)
    babia = metrics['babia']
    row['babia_num_sprites'] = babia.get('num_sprites', 0)

    return row


def get_project_id_from_filename(filename: str) -> Optional[int]:
    """
    Extracts the numeric project id from a filename like '754492227.sb3'.
    Returns None if not found.
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = re.search(r'(\d{3,})', stem)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def fetch_project_metadata(
    project_id: int,
    timeout: float = 15.0,
    retries: int = 2,
    sleep_between: float = 0.2
) -> Dict[str, Optional[str]]:
    """
    Fetch project metadata from the Scratch API.
    """
    if requests is None:
        return {
            "project_id": project_id,
            "Project title": None,
            "Author": None,
            "Creation date": None,
            "Modified date": None,
            "Remix parent id": None,
            "Remix root id": None,
            "_meta_error": "requests module not available",
        }

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
            remix = data.get("remix") or {}
            remix_parent_id = remix.get("parent")
            remix_root_id = remix.get("root")
            title = data.get("title")

            return {
                "project_id": project_id,
                "Project title": title,
                "Author": author,
                "Creation date": creation_date,
                "Modified date": modified_date,
                "Remix parent id": remix_parent_id,
                "Remix root id": remix_root_id,
                "_meta_error": None,
            }
        except Exception as e:
            last_err = e
            if attempt < retries:
                time_module.sleep(sleep_between)

    return {
        "project_id": project_id,
        "Project title": None,
        "Author": None,
        "Creation date": None,
        "Modified date": None,
        "Remix parent id": None,
        "Remix root id": None,
        "_meta_error": str(last_err) if last_err else "Unknown error",
    }


def _worker_analyze(input_dir: str, fname: str) -> ProcessingResult:
    """Worker para analizar un archivo .sb3."""
    start_time = time()
    path = os.path.join(input_dir, fname)

    try:
        if not os.path.exists(path):
            return ProcessingResult(
                filename=fname,
                success=False,
                error="File not found"
            )

        file_size = os.path.getsize(path)
        if file_size == 0:
            return ProcessingResult(
                filename=fname,
                success=False,
                error="Empty file"
            )

        if file_size > 100 * 1024 * 1024:
            return ProcessingResult(
                filename=fname,
                success=False,
                error="File too large (>100MB)"
            )

        if not fname.lower().endswith('.sb3'):
            return ProcessingResult(
                filename=fname,
                success=False,
                error="Invalid file extension"
            )

        # Analyze file with safe method that handles no-blocks case
        with open(os.devnull, 'w') as devnull, \
             contextlib.redirect_stdout(devnull), \
             contextlib.redirect_stderr(devnull):
            metrics, has_blocks = analyze_file_safe(path, DEFAULT_SKILL_POINTS)

        row = flatten_metrics(fname, metrics)
        processing_time = time() - start_time

        return ProcessingResult(
            filename=fname,
            success=True,
            row=row,
            processing_time=processing_time,
            has_blocks=has_blocks
        )

    except MemoryError:
        return ProcessingResult(
            filename=fname,
            success=False,
            error="Memory error - file too large"
        )
    except PermissionError:
        return ProcessingResult(
            filename=fname,
            success=False,
            error="Permission denied"
        )
    except Exception as exc:
        error_msg = str(exc).encode('ascii', errors='replace').decode('ascii')
        return ProcessingResult(
            filename=fname,
            success=False,
            error=f"{type(exc).__name__}: {error_msg}"
        )


def get_sb3_files(input_dir: Path, processed: ProgressManager) -> List[str]:
    """Obtiene la lista de archivos .sb3 no procesados."""
    try:
        all_files = [
            f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() == '.sb3'
        ]
        files = [f.name for f in all_files if f.name not in processed]
        return sorted(files)
    except PermissionError:
        raise ValueError(f"No se puede acceder al directorio: {input_dir}")
    except FileNotFoundError:
        raise ValueError(f"Directorio no encontrado: {input_dir}")


def get_fieldnames(include_metadata: bool = True) -> List[str]:
    """Returns the list of fieldnames for the CSV."""
    fieldnames = [
        'project', 'total_blocks', 'mastery_total_points', 'mastery_total_max',
        'mastery_competence'
    ]
    fieldnames += list(DEFAULT_SKILL_POINTS.keys())
    fieldnames += [
        'duplicateScripts', 'deadCode',
        'spriteNaming', 'backdropNaming',
        'babia_num_sprites',
        'has_blocks'
    ]

    if include_metadata:
        fieldnames += [
            'project_id',
            'Project title',
            'Author',
            'Creation date',
            'Modified date',
            'Remix parent id',
            'Remix root id',
            '_meta_error'
        ]

    return fieldnames


def analyze_directory_with_metadata(
    input_dir: str,
    csv_path: str,
    progress_path: str,
    processes: Optional[int] = None,
    chunk_size: Optional[int] = None,
    log_file: Optional[str] = None,
    fetch_metadata: bool = True,
    metadata_timeout: float = 15.0,
    metadata_retries: int = 2,
    ignore_progress: bool = False,
) -> None:
    """Analiza todos los proyectos .sb3 en input_dir y obtiene metadatos."""
    logger = setup_logging(log_file)
    safe_print(f"Iniciando analisis con metadatos de: {input_dir}")
    logger.info(f"Iniciando analisis con metadatos de: {input_dir}")

    input_path = Path(input_dir)
    csv_file_path = Path(csv_path)

    # Validaciones iniciales
    if not input_path.exists():
        error_msg = f"El directorio no existe: {input_path}"
        logger.error(error_msg)
        safe_print(f"ERROR: {error_msg}")
        return

    if not input_path.is_dir():
        error_msg = f"La ruta no es un directorio: {input_path}"
        logger.error(error_msg)
        safe_print(f"ERROR: {error_msg}")
        return

    try:
        csv_file_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = csv_file_path.parent / "test_write_access.tmp"
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            test_file.unlink()
        except Exception:
            error_msg = f"Sin permisos de escritura en: {csv_file_path.parent}"
            logger.error(error_msg)
            safe_print(f"ERROR: {error_msg}")
            return
    except Exception as e:
        error_msg = f"Error creando directorio de salida: {e}"
        logger.error(error_msg)
        safe_print(f"ERROR: {error_msg}")
        return

    progress_manager = ProgressManager(progress_path, ignore_progress=ignore_progress)

    if ignore_progress:
        safe_print("Modo reprocesar: ignorando progreso anterior")
        logger.info("Modo reprocesar: ignorando progreso anterior")

    try:
        files = get_sb3_files(input_path, progress_manager)
    except ValueError as e:
        logger.error(str(e))
        safe_print(f"ERROR: {str(e)}")
        return

    if not files:
        msg = "No hay archivos .sb3 para procesar"
        logger.info(msg)
        safe_print(msg)
        return

    safe_print(f"Archivos a procesar: {len(files)}")
    safe_print(f"Archivos ya procesados: {progress_manager.total_processed}")
    safe_print(f"Obtencion de metadatos: {'Activada' if fetch_metadata else 'Desactivada'}")

    fieldnames = get_fieldnames(include_metadata=fetch_metadata)

    # Check if CSV exists and has header
    # If reprocessing, treat as new file (will overwrite)
    csv_exists = csv_file_path.exists() and csv_file_path.stat().st_size > 0 and not ignore_progress

    # Configurar procesamiento
    num_processes = processes or min(cpu_count(), len(files), 8)
    effective_chunk_size = chunk_size or max(1, len(files) // (num_processes * 4))

    safe_print(f"Usando {num_processes} procesos para analisis")

    # Estadisticas
    start_time = time()
    successful = 0
    failed = 0
    no_blocks_count = 0
    total_processing_time = 0.0

    try:
        # Use 'w' mode if reprocessing to overwrite, otherwise 'a' to append
        file_mode = 'w' if ignore_progress else 'a'
        with open(csv_file_path, file_mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not csv_exists or ignore_progress:
                writer.writeheader()

            worker = partial(_worker_analyze, str(input_path))

            try:
                with ProcessPoolExecutor(max_workers=num_processes) as executor:
                    future_to_filename = {}

                    for i in range(0, len(files), effective_chunk_size):
                        chunk = files[i:i + effective_chunk_size]
                        for fname in chunk:
                            future = executor.submit(worker, fname)
                            future_to_filename[future] = fname

                    for future in as_completed(future_to_filename):
                        try:
                            result = future.result()
                            project_id_str = os.path.splitext(result.filename)[0]

                            if result.success:
                                row = result.row.copy()
                                row['has_blocks'] = result.has_blocks

                                # Fetch metadata if enabled
                                if fetch_metadata:
                                    pid = get_project_id_from_filename(result.filename)
                                    if pid:
                                        meta = fetch_project_metadata(
                                            pid,
                                            timeout=metadata_timeout,
                                            retries=metadata_retries
                                        )
                                        row.update(meta)
                                    else:
                                        row['project_id'] = None
                                        row['Project title'] = None
                                        row['Author'] = None
                                        row['Creation date'] = None
                                        row['Modified date'] = None
                                        row['Remix parent id'] = None
                                        row['Remix root id'] = None
                                        row['_meta_error'] = "No project ID in filename"

                                writer.writerow(row)
                                progress_manager.add(result.filename)
                                successful += 1
                                total_processing_time += result.processing_time

                                if not result.has_blocks:
                                    no_blocks_count += 1
                                    safe_print(f"> {project_id_str}, {result.processing_time:.2f}s (sin bloques)")
                                else:
                                    safe_print(f"> {project_id_str}, {result.processing_time:.2f}s")
                            else:
                                failed += 1
                                safe_print(f"< {project_id_str}, ERROR: {result.error}")

                            csvfile.flush()

                        except Exception as e:
                            safe_print(f"Error procesando resultado: {e}")
                            continue

            except KeyboardInterrupt:
                safe_print("\nProceso interrumpido - guardando progreso...")
            except Exception as e:
                safe_print(f"ERROR durante procesamiento: {e}")
            finally:
                progress_manager.save()

    except Exception as e:
        error_msg = f"Error abriendo archivo CSV: {e}"
        logger.error(error_msg)
        safe_print(f"ERROR: {error_msg}")
        return

    # Estadisticas finales
    total_time = time() - start_time
    stats_lines = [
        "\n=== RESUMEN DE ANALISIS ===",
        f"Archivos procesados exitosamente: {successful}",
        f"  - Con bloques: {successful - no_blocks_count}",
        f"  - Sin bloques: {no_blocks_count}",
        f"Archivos con errores: {failed}",
        f"Total procesado: {successful + failed}",
        f"Tiempo total: {total_time:.2f}s"
    ]

    if successful > 0:
        stats_lines.extend([
            f"Tiempo promedio por archivo: {total_processing_time/successful:.2f}s",
            f"Velocidad: {successful/total_time:.2f} archivos/s"
        ])

    for line in stats_lines:
        logger.info(line)
        safe_print(line)


def main() -> None:
    if sys.platform.startswith('win'):
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description='Analyze Scratch .sb3 projects with metrics and metadata.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('directory', help='Directory containing .sb3 files')
    parser.add_argument('output', help='Path to output CSV file')
    parser.add_argument('--progress', default='analysis_progress.json',
                        help='Path to progress file')
    parser.add_argument('--processes', type=int, default=None,
                        help='Number of worker processes (default: CPU count, max 8)')
    parser.add_argument('--chunk-size', type=int, default=None,
                        help='Size of work chunks per process')
    parser.add_argument('--log-file', type=str, default=None,
                        help='Path to log file (default: console only)')
    parser.add_argument('--no-metadata', action='store_true',
                        help='Skip fetching metadata from Scratch API')
    parser.add_argument('--metadata-timeout', type=float, default=15.0,
                        help='HTTP timeout for metadata requests (seconds)')
    parser.add_argument('--metadata-retries', type=int, default=2,
                        help='Number of retries for metadata requests')
    parser.add_argument('--reprocess', action='store_true',
                        help='Ignore progress file and reprocess all files from scratch')

    args = parser.parse_args()

    try:
        analyze_directory_with_metadata(
            args.directory,
            args.output,
            args.progress,
            args.processes,
            args.chunk_size,
            args.log_file,
            fetch_metadata=not args.no_metadata,
            metadata_timeout=args.metadata_timeout,
            metadata_retries=args.metadata_retries,
            ignore_progress=args.reprocess,
        )
    except KeyboardInterrupt:
        safe_print("\nProceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        safe_print(f"Error fatal: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
