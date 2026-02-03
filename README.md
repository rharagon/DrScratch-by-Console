# Dr. Scratch by Console

<img width="1012" height="359" alt="Local De" src="https://github.com/user-attachments/assets/b3314297-e65a-4083-a656-6150fa33e77a" />

**Dr. Scratch** is an analysis tool that evaluates your Scratch projects across various computational areas to provide feedback on aspects such as abstraction, logical thinking, synchronization, parallelism, flow control, user interactivity, and data representation. This analyzer is useful for assessing both your own projects and those of your students.

You can try a beta version at [https://drscratch.org](https://drscratch.org).

**Dr. Scratch by Console** is the console app to get the metrics from Scratch `.sb3` project files in batch mode.

---

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd DrScratch_Console
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

Additional dependencies that may be required:
```bash
pip install requests  # For metadata fetching from Scratch API
```

---

## Console Analyzers

The repository includes several command-line tools for batch analyzing `.sb3` projects:

| Script | Description | Parallelism | Metadata | Progress |
|--------|-------------|-------------|----------|----------|
| `console_analyzer.py` | Basic sequential analyzer | No | No | Yes |
| `console_analyzer_multiprocess.py` | Parallel analyzer | Yes | No | Yes |
| `console_analyzer_with_metadata.py` | Complete analyzer with API metadata | Yes | Yes | Yes |
| `extract_scratch_meta.py` | Metadata extractor only | Yes | Yes | No |
| `extract_total_blocks.py` | Block counter only | Yes | No | Yes |

---

## Script Usage

### 1. console_analyzer.py

Basic sequential analyzer that processes projects one at a time. Good for small datasets or debugging.

```bash
python console_analyzer.py <directory> <output.csv> [--progress <progress.json>]
```

**Arguments:**
| Argument | Required | Description |
|----------|----------|-------------|
| `directory` | Yes | Directory containing `.sb3` files |
| `output` | Yes | Path to output CSV file |
| `--progress` | No | Path to progress file (default: `analysis_progress.json`) |

**Example:**
```bash
python console_analyzer.py ./projects ./results/analysis.csv
python console_analyzer.py ./projects ./results/analysis.csv --progress ./custom_progress.json
```

**Output CSV columns:**
- `project` - Filename
- `total_blocks` - Total number of blocks
- `mastery_total_points` - Total CT mastery points achieved
- `mastery_total_max` - Maximum possible CT points
- `mastery_competence` - Competence level (Basic, Developing, Proficient)
- `Abstraction`, `Parallelization`, `Logic`, `Synchronization`, `FlowControl`, `UserInteractivity`, `DataRepresentation`, `MathOperators`, `MotionOperators` - Individual CT skill scores
- `duplicateScripts` - Number of duplicate scripts
- `deadCode` - Number of dead code scripts
- `spriteNaming` - Number of default sprite names
- `backdropNaming` - Number of default backdrop names
- `babia_num_sprites` - Number of sprites

---

### 2. console_analyzer_multiprocess.py

Parallel analyzer that uses multiple CPU cores for faster processing. Recommended for large datasets.

```bash
python console_analyzer_multiprocess.py <directory> <output.csv> [options]
```

**Arguments:**
| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `directory` | Yes | - | Directory containing `.sb3` files |
| `output` | Yes | - | Path to output CSV file |
| `--progress` | No | `analysis_progress.json` | Path to progress file |
| `--processes` | No | CPU count (max 8) | Number of worker processes |
| `--chunk-size` | No | Auto | Size of work chunks per process |
| `--log-file` | No | None | Path to log file |

**Examples:**
```bash
# Basic usage
python console_analyzer_multiprocess.py ./projects ./results/analysis.csv

# Using 4 processes with logging
python console_analyzer_multiprocess.py ./projects ./results/analysis.csv --processes 4 --log-file analysis.log

# Custom chunk size for memory optimization
python console_analyzer_multiprocess.py ./projects ./results/analysis.csv --chunk-size 50
```

---

### 3. console_analyzer_with_metadata.py

Complete analyzer that combines CT metrics with project metadata from the Scratch API. Projects without blocks are included with zero metrics instead of being marked as failed.

```bash
python console_analyzer_with_metadata.py <directory> <output.csv> [options]
```

**Arguments:**
| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `directory` | Yes | - | Directory containing `.sb3` files |
| `output` | Yes | - | Path to output CSV file |
| `--progress` | No | `analysis_progress.json` | Path to progress file |
| `--processes` | No | CPU count (max 8) | Number of worker processes |
| `--chunk-size` | No | Auto | Size of work chunks per process |
| `--log-file` | No | None | Path to log file |
| `--no-metadata` | No | False | Skip fetching metadata from Scratch API |
| `--metadata-timeout` | No | 15.0 | HTTP timeout for metadata requests (seconds) |
| `--metadata-retries` | No | 2 | Number of retries for metadata requests |
| `--reprocess` | No | False | Ignore progress file and reprocess all files |

**Examples:**
```bash
# Full analysis with metadata
python console_analyzer_with_metadata.py ./projects ./results/full_analysis.csv

# Analysis without API metadata (offline mode)
python console_analyzer_with_metadata.py ./projects ./results/analysis.csv --no-metadata

# Reprocess all files ignoring previous progress
python console_analyzer_with_metadata.py ./projects ./results/analysis.csv --reprocess

# Custom API timeout and retries
python console_analyzer_with_metadata.py ./projects ./results/analysis.csv --metadata-timeout 30 --metadata-retries 5
```

**Additional output columns (with metadata):**
- `has_blocks` - Whether the project has any blocks (True/False)
- `project_id` - Numeric project ID
- `Project title` - Project title from Scratch
- `Author` - Username of the project author
- `Creation date` - When the project was created
- `Modified date` - When the project was last modified
- `Remix parent id` - ID of the parent project (if remix)
- `Remix root id` - ID of the original project (if remix)
- `_meta_error` - Error message if metadata fetch failed

---

### 4. extract_scratch_meta.py

Extracts only metadata from the Scratch API for `.sb3` files. Does not analyze project content.

```bash
python extract_scratch_meta.py -i <input_dir> -o <output.csv> [options]
```

**Arguments:**
| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `-i, --input` | Yes | - | Folder containing `.sb3` files |
| `-o, --output` | Yes | - | Output CSV path |
| `--recursive` | No | False | Search `.sb3` files recursively in subfolders |
| `--timeout` | No | 15.0 | HTTP timeout per request (seconds) |
| `--retries` | No | 2 | Retries on transient failures |
| `--sleep` | No | 0.2 | Sleep between retries (seconds) |
| `--workers` | No | CPU count | Number of parallel workers |
| `--processes` | No | False | Use processes instead of threads |

**Examples:**
```bash
# Basic metadata extraction
python extract_scratch_meta.py -i ./projects -o ./metadata.csv

# Recursive search with custom workers
python extract_scratch_meta.py -i ./projects -o ./metadata.csv --recursive --workers 10

# Using processes instead of threads
python extract_scratch_meta.py -i ./projects -o ./metadata.csv --processes
```

**Output CSV columns:**
- `project_id` - Numeric project ID extracted from filename
- `Project title` - Project title
- `Author` - Username of the project author
- `Creation date` - When the project was created
- `Modified date` - When the project was last modified
- `Remix parent id` - ID of the parent project (if remix)
- `Remix root id` - ID of the original project (if remix)
- `filename` - Original filename
- `_error` - Error message if metadata fetch failed

---

### 5. extract_total_blocks.py

Simplified script that extracts only the project ID and total block count. Fastest option for basic analysis.

```bash
python extract_total_blocks.py <directory> <output.csv> [options]
```

**Arguments:**
| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `directory` | Yes | - | Directory containing `.sb3` files |
| `output` | Yes | - | Path to output CSV file |
| `--progress` | No | `blocks_progress.json` | Path to progress file |
| `--processes` | No | CPU count (max 8) | Number of worker processes |

**Examples:**
```bash
# Basic block counting
python extract_total_blocks.py ./projects ./blocks.csv

# Using 4 processes
python extract_total_blocks.py ./projects ./blocks.csv --processes 4
```

**Output CSV columns:**
- `project_id` - Filename without extension
- `total_blocks` - Total number of blocks in the project

---

## Progress Files

All analyzers support progress tracking through JSON files. This allows:

- **Resume interrupted analyses**: If the process is interrupted, re-running the command will continue from where it left off
- **Incremental updates**: Add new files to the directory and run again to analyze only the new files

To force a complete reanalysis, either:
- Delete the progress file
- Use `--reprocess` flag (where available)

---

## File Naming Convention

For metadata extraction to work correctly, `.sb3` files should be named with their Scratch project ID:
- `754492227.sb3` (just the ID)
- `project_754492227.sb3` (with prefix)

The scripts extract numeric IDs with 3 or more digits from filenames.

---

## CT (Computational Thinking) Metrics

The analyzers evaluate projects across 9 computational thinking dimensions:

| Dimension | Description | Max Score |
|-----------|-------------|-----------|
| Abstraction | Use of custom blocks and clones | 4 |
| Parallelization | Multiple scripts running simultaneously | 4 |
| Logic | Boolean operations and conditions | 4 |
| Synchronization | Coordination between scripts | 4 |
| FlowControl | Loops and control structures | 4 |
| UserInteractivity | User input handling | 4 |
| DataRepresentation | Variables and lists | 4 |
| MathOperators | Mathematical operations | 4 |
| MotionOperators | Motion and positioning | 4 |

**Competence Levels:**
- **Basic**: 0-7 points
- **Developing**: 8-15 points
- **Proficient**: 16+ points

---

## Project Structure

```
DrScratch_Console/
├── app/
│   ├── hairball3/           # Core analysis modules
│   │   ├── mastery.py       # CT mastery analysis
│   │   ├── duplicateScripts.py
│   │   ├── deadCode.py
│   │   ├── babiaInfo.py
│   │   ├── spriteNaming.py
│   │   └── backdropNaming.py
│   └── consts_drscratch.py  # Constants and configurations
├── console_analyzer.py
├── console_analyzer_multiprocess.py
├── console_analyzer_with_metadata.py
├── extract_scratch_meta.py
├── extract_total_blocks.py
├── requirements.txt
└── README.md
```

---

## License

This project is based on the original Dr. Scratch project. See the original project for license details.
