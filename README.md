# zoom-to-isaca-cpe

A command-line tool that processes Zoom attendance and registration reports to generate ISACA CPE upload files.

## How It Works

1. Reads a Zoom participants CSV and a Zoom registration CSV from the current directory
2. Merges attendance data with registrant details by email address
3. Filters out attendees who were present for less than 50 minutes
4. Auto-detects the ISACA member ID column from the registration file
5. Calculates CPE hours earned (1 CPE per 50 minutes attended)
6. Outputs an internal attendance report and an ISACA-ready upload file

## Requirements

- Python 3.8+

```
pip install -r requirements.txt
```

## Input Files

Place the following Zoom export CSV files in the same directory as the script before running:

| File | Description |
|---|---|
| `participants*.csv` | Zoom meeting participants report (exported from Zoom) |
| `registration*.csv` | Zoom meeting registration report (exported from Zoom) |

If multiple files match either pattern, the script uses the last one alphabetically.

## Usage

```
python zoom_cpe.py \
  --org "Your Organization" \
  --event "Event Name" \
  --start "MM/DD/YYYY" \
  --end "MM/DD/YYYY" \
  --activity "IPROED" \
  --method "ONLINE"
```

### Arguments

| Argument | Description | Example |
|---|---|---|
| `--org` | Sponsoring organization name | `"ISACA Chicago"` |
| `--event` | Event name | `"Annual Conference 2025"` |
| `--start` | Event start date | `"01/15/2025"` |
| `--end` | Event end date | `"01/15/2025"` |
| `--activity` | ISACA qualifying activity code | `"IPROED"`, `"PROED"` |
| `--method` | Method of delivery | `"ONLINE"`, `"INPERSON"` |

## Output Files

Both files are written to the current directory.

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
├── zoom_cpe.py               # Main script
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
