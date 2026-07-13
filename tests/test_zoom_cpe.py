import argparse
import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from zoom_cpe import (build_arg_parser, find_file, find_header_row,
                      is_id_column, load_data, main, process, validate_args,
                      validate_date, validate_min_duration)

# --- find_file ---


def test_find_file_returns_last_sorted_match(tmp_path, monkeypatch):
    """Returns the last file alphabetically when multiple matches exist."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "participants_2024.csv").write_text("")
    (tmp_path / "participants_2025.csv").write_text("")
    assert find_file("participants*.csv").endswith("participants_2025.csv")


def test_find_file_returns_none_when_no_match(tmp_path, monkeypatch):
    """Returns None when no files match the given pattern."""
    monkeypatch.chdir(tmp_path)
    assert find_file("participants*.csv") is None


# --- find_header_row ---


def test_find_header_row_detects_correct_row(tmp_path):
    """Returns the correct row index when the header is preceded by ignored rows."""
    f = tmp_path / "test.csv"
    f.write_text("ignored\nignored\nignored\nEmail,Duration (minutes)\n")
    assert find_header_row(str(f), ["email", "duration (minutes)"]) == 3


def test_find_header_row_raises_when_not_found(tmp_path):
    """Raises ValueError when no row contains all required columns."""
    f = tmp_path / "test.csv"
    f.write_text("col1,col2\nval1,val2\n")
    with pytest.raises(ValueError):
        find_header_row(str(f), ["email"])


# --- validate_date ---


def test_validate_date_valid():
    """Returns a datetime object for a correctly formatted MM/DD/YYYY string."""
    from datetime import datetime

    assert validate_date("01/15/2025") == datetime(2025, 1, 15)


def test_validate_date_invalid():
    """Raises ArgumentTypeError when the date string is not in MM/DD/YYYY format."""
    with pytest.raises(Exception):
        validate_date("2025-01-15")


# --- is_id_column ---


@pytest.mark.parametrize(
    "values, expected",
    [
        (["12345", "67890", "11111"], True),
        (["alice", "bob", "carol"], False),
        (["12345", "67890", "notnum"], True),
        ([], False),
    ],
)
def test_is_id_column(values, expected):
    """Returns True only when more than 50% of values are purely numeric digits."""
    series = pd.Series(values, dtype=str) if values else pd.Series([], dtype=str)
    assert is_id_column(series) == expected


# --- validate_min_duration ---


@pytest.mark.parametrize("value", ["0", "-1", "-100"])
def test_validate_min_duration_rejects_non_positive(value):
    """Raises ArgumentTypeError for zero or negative values."""
    with pytest.raises(argparse.ArgumentTypeError):
        validate_min_duration(value)


def test_validate_min_duration_rejects_non_integer():
    """Raises ArgumentTypeError when the value cannot be parsed as an integer."""
    with pytest.raises(argparse.ArgumentTypeError):
        validate_min_duration("abc")


def test_validate_min_duration_accepts_positive():
    """Returns the integer value when given a valid positive integer string."""
    assert validate_min_duration("50") == 50


# --- main (integration) ---

PARTICIPANTS_HEADER = "ignored\nignored\nignored\n"
REGISTRATION_HEADER = "ignored\nignored\nignored\nignored\nignored\n"

PARTICIPANTS_CSV = (
    PARTICIPANTS_HEADER
    + "Name,Email,Duration (minutes)\n"
    + "Alice Smith,alice@example.com,90\n"
    + "Bob Jones,bob@example.com,30\n"
    + "Carol White,carol@example.com,60\n"
)

REGISTRATION_CSV = (
    REGISTRATION_HEADER
    + "First Name,Last Name,Email,ISACA ID,Approval Status\n"
    + "Alice,Smith,alice@example.com,11111,Approved\n"
    + "Bob,Jones,bob@example.com,22222,Approved\n"
    + "Carol,White,carol@example.com,33333,Approved\n"
)

BASE_ARGS = [
    "zoom_cpe.py",
    "--org", "Test Org",
    "--event", "Test Event",
    "--start", "01/01/2025",
    "--end", "01/01/2025",
    "--activity", "IPROED",
    "--method", "ONLINE",
]


def write_csv_files(tmp_path, participants=PARTICIPANTS_CSV, registration=REGISTRATION_CSV):
    """Writes participants and registration CSV files to tmp_path."""
    (tmp_path / "participants_2025.csv").write_text(participants)
    (tmp_path / "registration_2025.csv").write_text(registration)


def base_args(tmp_path):
    """Returns BASE_ARGS with --output-dir set to tmp_path."""
    return BASE_ARGS + ["--output-dir", str(tmp_path)]


def test_main_creates_output_files(tmp_path, monkeypatch):
    """Both output CSVs are created in the output directory on a successful run."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    assert (tmp_path / "final_attendance_cpe_report.csv").exists()
    assert (tmp_path / "isaca_cpe_upload_ready.csv").exists()


def test_main_filters_short_duration(tmp_path, monkeypatch):
    """Attendees below the minimum duration threshold are excluded from output."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "bob@example.com" not in report["Email"].values


def test_main_cpe_calculation(tmp_path, monkeypatch):
    """CPE hours are calculated by flooring total minutes to the nearest duration block."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    alice = report[report["Email"] == "alice@example.com"].iloc[0]
    carol = report[report["Email"] == "carol@example.com"].iloc[0]
    assert alice["CPE"] == 1
    assert carol["CPE"] == 1


def test_main_upload_file_columns(tmp_path, monkeypatch):
    """The ISACA upload file contains exactly the required columns in the correct order."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    upload = pd.read_csv(tmp_path / "isaca_cpe_upload_ready.csv")
    expected_cols = [
        "ID", "EMAIL", "LAST_NAME", "FIRST_NAME",
        "Sponsoring Organization Name", "Event Name",
        "Date Format", "Event Start Date", "Event End Date",
        "CPE Hours Earned", "Qualifying Activity", "Method of Delivery",
    ]
    assert list(upload.columns) == expected_cols


def test_main_exits_when_files_missing(tmp_path, monkeypatch):
    """Exits with an error when no participants or registration CSVs are found."""
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        with pytest.raises(SystemExit):
            main()


@pytest.mark.skipif(sys.platform == "win32", reason="chmod read-only not reliable on Windows")
def test_main_exits_when_output_dir_not_writable(tmp_path, monkeypatch):
    """Exits with an error when the output directory is not writable."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    read_only_dir = tmp_path / "readonly"
    read_only_dir.mkdir()
    os.chmod(read_only_dir, 0o444)
    with patch("sys.argv", BASE_ARGS + ["--output-dir", str(read_only_dir)]):
        with pytest.raises(SystemExit):
            main()
    os.chmod(read_only_dir, 0o755)


def test_main_exits_when_output_dir_missing(tmp_path, monkeypatch):
    """Exits with an error when the specified output directory does not exist."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS + ["--output-dir", str(tmp_path / "nonexistent")]):
        with pytest.raises(SystemExit):
            main()


def test_main_exits_when_participants_file_not_found(tmp_path, monkeypatch):
    """Exits with an error when the explicitly provided participants file does not exist."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS + [
        "--participants", str(tmp_path / "missing.csv"),
        "--registration", str(tmp_path / "registration_2025.csv"),
        "--output-dir", str(tmp_path),
    ]):
        with pytest.raises(SystemExit):
            main()


def test_main_warns_on_large_file(tmp_path, monkeypatch, capsys):
    """Logs a warning when an input file exceeds 50 MB."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("os.path.getsize", return_value=60 * 1024 * 1024):
        with patch("sys.argv", base_args(tmp_path)):
            main()
    assert "large" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="chmod read-only not reliable on Windows")
def test_main_exits_when_participants_file_not_readable(tmp_path, monkeypatch):
    """Exits with an error when the participants file exists but cannot be read."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    p_file = tmp_path / "participants_2025.csv"
    os.chmod(p_file, 0o000)
    with patch("sys.argv", BASE_ARGS + [
        "--participants", str(p_file),
        "--registration", str(tmp_path / "registration_2025.csv"),
        "--output-dir", str(tmp_path),
    ]):
        with pytest.raises(SystemExit):
            main()
    os.chmod(p_file, 0o644)


def test_main_exits_when_header_only_csv(tmp_path, monkeypatch):
    """Exits with code 0 when the participants CSV has a header but no data rows."""
    monkeypatch.chdir(tmp_path)
    participants = PARTICIPANTS_HEADER + "Name,Email,Duration (minutes)\n"
    write_csv_files(tmp_path, participants=participants)
    with patch("sys.argv", base_args(tmp_path)):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0


def test_main_verbose_flag(tmp_path, monkeypatch, capsys):
    """Enables DEBUG logging when --verbose is passed, producing DEBUG output on stdout."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--verbose"]):
        main()
    assert "DEBUG" in capsys.readouterr().out


def test_main_quiet_suppresses_info(tmp_path, monkeypatch, capsys):
    """Suppresses all stdout output when --quiet is passed."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--quiet"]):
        main()
    assert capsys.readouterr().out == ""


def test_main_verbose_and_quiet_are_mutually_exclusive(tmp_path, monkeypatch):
    """Exits with an error when both --verbose and --quiet are provided."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--verbose", "--quiet"]):
        with pytest.raises(SystemExit):
            main()


def test_main_warns_and_exits_when_no_qualifying_attendees(tmp_path, monkeypatch):
    """Exits with code 0 and writes no output files when no attendees meet the minimum duration."""
    monkeypatch.chdir(tmp_path)
    participants = (
        PARTICIPANTS_HEADER
        + "Name,Email,Duration (minutes)\n"
        + "Alice Smith,alice@example.com,10\n"
    )
    write_csv_files(tmp_path, participants=participants)
    with patch("sys.argv", base_args(tmp_path)):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0
    assert not (tmp_path / "final_attendance_cpe_report.csv").exists()
    assert not (tmp_path / "isaca_cpe_upload_ready.csv").exists()


def test_main_warns_on_null_emails(tmp_path, monkeypatch, capsys):
    """Logs a warning when participant rows have missing email addresses."""
    monkeypatch.chdir(tmp_path)
    participants = (
        PARTICIPANTS_HEADER
        + "Name,Email,Duration (minutes)\n"
        + "Alice Smith,alice@example.com,90\n"
        + "Unknown,,60\n"
    )
    write_csv_files(tmp_path, participants=participants)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    assert "missing email" in capsys.readouterr().out


def test_main_explicit_input_files(tmp_path, monkeypatch):
    """Uses explicitly provided --participants and --registration paths instead of auto-detection."""
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    write_csv_files(input_dir)
    args = BASE_ARGS + [
        "--participants", str(input_dir / "participants_2025.csv"),
        "--registration", str(input_dir / "registration_2025.csv"),
        "--output-dir", str(output_dir),
    ]
    with patch("sys.argv", args):
        main()
    assert (output_dir / "final_attendance_cpe_report.csv").exists()
    assert (output_dir / "isaca_cpe_upload_ready.csv").exists()


def test_main_filters_non_numeric_id(tmp_path, monkeypatch):
    """Attendees with non-numeric ISACA IDs are excluded from both output files."""
    monkeypatch.chdir(tmp_path)
    registration = (
        REGISTRATION_HEADER
        + "First Name,Last Name,Email,ISACA ID,Approval Status\n"
        + "Alice,Smith,alice@example.com,11111,Approved\n"
        + "Dave,Brown,dave@example.com,NOTANID,Approved\n"
    )
    participants = (
        PARTICIPANTS_HEADER
        + "Name,Email,Duration (minutes)\n"
        + "Alice Smith,alice@example.com,90\n"
        + "Dave Brown,dave@example.com,90\n"
    )
    write_csv_files(tmp_path, participants=participants, registration=registration)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "dave@example.com" not in report["Email"].values
    assert "alice@example.com" in report["Email"].values


def test_main_sums_duration_for_rejoined_attendee(tmp_path, monkeypatch):
    """Duration is summed across multiple rows for an attendee who rejoined the session."""
    monkeypatch.chdir(tmp_path)
    participants = (
        PARTICIPANTS_HEADER
        + "Name,Email,Duration (minutes)\n"
        + "Eve Green,eve@example.com,30\n"
        + "Eve Green,eve@example.com,25\n"
    )
    registration = (
        REGISTRATION_HEADER
        + "First Name,Last Name,Email,ISACA ID,Approval Status\n"
        + "Eve,Green,eve@example.com,44444,Approved\n"
    )
    write_csv_files(tmp_path, participants=participants, registration=registration)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "eve@example.com" in report["Email"].values
    assert report[report["Email"] == "eve@example.com"].iloc[0]["Duration"] == 55


def test_main_exits_when_end_before_start(tmp_path, monkeypatch):
    """Exits with an error when --end date is earlier than --start date."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", [
        "zoom_cpe.py",
        "--org", "Test Org", "--event", "Test Event",
        "--start", "12/31/2025", "--end", "01/01/2025",
        "--activity", "IPROED", "--method", "ONLINE",
        "--output-dir", str(tmp_path),
    ]):
        with pytest.raises(SystemExit):
            main()


def test_main_exits_on_invalid_activity(tmp_path, monkeypatch):
    """Exits with an error when --activity is not one of the accepted values."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    bad_args = base_args(tmp_path).copy()
    bad_args[bad_args.index("IPROED")] = "INVALID"
    with patch("sys.argv", bad_args):
        with pytest.raises(SystemExit):
            main()


def test_main_exits_on_invalid_method(tmp_path, monkeypatch):
    """Exits with an error when --method is not one of the accepted values."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    bad_args = base_args(tmp_path).copy()
    bad_args[bad_args.index("ONLINE")] = "INVALID"
    with patch("sys.argv", bad_args):
        with pytest.raises(SystemExit):
            main()


def test_main_custom_min_duration(tmp_path, monkeypatch):
    """Attendees meeting a custom --min-duration threshold are included in output."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--min-duration", "30"]):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "bob@example.com" in report["Email"].values


def test_validate_min_duration_default(tmp_path, monkeypatch):
    """Omitting --min-duration defaults to 50, excluding Bob who attended only 30 minutes."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "bob@example.com" not in report["Email"].values


def test_main_exits_on_zero_min_duration(tmp_path, monkeypatch):
    """Exits with an error when --min-duration is set to zero."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--min-duration", "0"]):
        with pytest.raises(SystemExit):
            main()


def test_main_exits_on_negative_min_duration(tmp_path, monkeypatch):
    """Exits with an error when --min-duration is set to a negative value."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--min-duration", "-10"]):
        with pytest.raises(SystemExit):
            main()
