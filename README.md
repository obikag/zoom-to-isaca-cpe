# zoom-to-isaca-cpe

![CI](https://github.com/<your-username>/zoom-to-isaca-cpe/actions/workflows/ci.yml/badge.svg)

A command-line tool that processes Zoom attendance and registration reports to generate ISACA CPE upload files.

## How It Works

1. Reads a Zoom participants CSV and a Zoom registration CSV from the current directory
2. Dynamically detects the header row in each file to handle Zoom export format changes
3. Merges attendance data with registrant details by email address
4. Sums duration across multiple rows for attendees who rejoined the session
5. Filters out attendees who were present for less than the minimum duration (default: 50 minutes)
6. Auto-detects the ISACA member ID column from the registration file
7. Filters out registrants with missing or non-numeric ISACA member IDs
8. Calculates CPE hours earned by flooring total minutes to the nearest duration block (e.g. 90 min => 1 CPE)
9. Outputs an internal attendance report and an ISACA-ready upload file

## Requirements

- Python 3.8+
- pandas 1.3+

```
pip install -r requirements.txt
```

## Input Files

Place the following Zoom export CSV files in the same directory as the script before running:

| File | Description |
|---|---|
| `participants*.csv` | Zoom meeting participants report (exported from Zoom) |
| `registration*.csv` | Zoom meeting registration report (exported from Zoom) |

If `--participants` and `--registration` are omitted, the script auto-detects files matching `participants*.csv` and `registration*.csv` in the current working directory. If multiple files match either pattern, the last one alphabetically is used.

## Usage

### Run directly

```
python zoom_cpe.py \
  --org "Your Organization" \
  --event "Event Name" \
  --start "MM/DD/YYYY" \
  --end "MM/DD/YYYY" \
  --activity "IPROED" \
  --method "ONLINE" \
  --output-dir "./output"
```

### Install as a CLI tool

```
pip install .
zoom-cpe --org "Your Organization" \
         --event "Event Name" \
         --start "MM/DD/YYYY" \
         --end "MM/DD/YYYY" \
         --activity "IPROED" \
         --method "ONLINE" \
         --output-dir "/path/to/output" \
         --participants "/path/to/participants.csv" \
         --registration "/path/to/registration.csv"
```

### Arguments

| Argument | Description | Required | Example |
|---|---|---|---|
| `--org` | Sponsoring organization name | Yes | `"ISACA Chicago"` |
| `--event` | Event name | Yes | `"Annual Conference 2025"` |
| `--start` | Event start date | Yes | `"01/15/2025"` |
| `--end` | Event end date (must be >= start) | Yes | `"01/15/2025"` |
| `--activity` | ISACA qualifying activity code | Yes | `"IPROED"`, `"PROED"` |
| `--method` | Method of delivery | Yes | `"ONLINE"`, `"INPERSON"` |
| `--output-dir` | Directory to write output files to | Yes | `"./output"` |
| `--participants` | Path to participants CSV | No | `"~/downloads/participants.csv"` |
| `--registration` | Path to registration CSV | No | `"~/downloads/registration.csv"` |
| `--min-duration` | Minimum minutes to qualify for CPE | No | `50` (default) |
| `--verbose` | Enable debug logging | No | |
| `--quiet` | Suppress all output except errors | No | |

## Output Files

Both files are written to `--output-dir`. If no qualifying attendees remain after filtering, no output files are written and the script exits with a warning.

**`final_attendance_cpe_report.csv`** — Internal attendance report sorted by name:

| Column | Description |
|---|---|
| ID | ISACA member ID |
| Name | Last, First |
| Email | Attendee email |
| Duration | Total minutes attended |
| CPE | CPE hours earned |

**`isaca_cpe_upload_ready.csv`** — Formatted for direct upload to the ISACA CPE portal, sorted by last name.

## Running Tests

**Windows:**
```
run_tests.bat
```

**macOS/Linux:**
```
chmod +x run_tests.sh
./run_tests.sh
```

## Project Structure

```
zoom-to-isaca-cpe/
├── .github/
│   └── workflows/
│       └── ci.yml            # GitHub Actions CI workflow
├── zoom_cpe.py               # Main script
├── pyproject.toml            # Installable package configuration
├── requirements.txt          # Python dependencies
├── run_tests.bat             # Test runner (Windows)
├── run_tests.sh              # Test runner (macOS/Linux)
├── pytest.ini                # Pytest configuration
├── conftest.py               # Root pytest conftest
├── LICENSE
├── README.md
└── tests/
    ├── conftest.py           # Adds project root to sys.path
    └── test_zoom_cpe.py      # Unit and integration tests
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
