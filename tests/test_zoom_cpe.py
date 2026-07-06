import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from zoom_cpe import find_file, find_header_row, is_id_column, main, validate_date

# --- find_file ---


def test_find_file_returns_last_sorted_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "participants_2024.csv").write_text("")
    (tmp_path / "participants_2025.csv").write_text("")
    assert find_file("participants*.csv").endswith("participants_2025.csv")


def test_find_file_returns_none_when_no_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert find_file("participants*.csv") is None


# --- find_header_row ---


def test_find_header_row_detects_correct_row(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("ignored\nignored\nignored\nEmail,Duration (minutes)\n")
    assert find_header_row(str(f), ["email", "duration (minutes)"]) == 3


def test_find_header_row_raises_when_not_found(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("col1,col2\nval1,val2\n")
    with pytest.raises(ValueError):
        find_header_row(str(f), ["email"])


# --- validate_date ---


def test_validate_date_valid():
    from datetime import datetime
    assert validate_date("01/15/2025") == datetime(2025, 1, 15)


def test_validate_date_invalid():
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
    series = pd.Series(values, dtype=str) if values else pd.Series([], dtype=str)
    assert is_id_column(series) == expected


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
    (tmp_path / "participants_2025.csv").write_text(participants)
    (tmp_path / "registration_2025.csv").write_text(registration)


def base_args(tmp_path):
    """Returns BASE_ARGS with --output-dir set to tmp_path."""
    return BASE_ARGS + ["--output-dir", str(tmp_path)]


def test_main_creates_output_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    assert (tmp_path / "final_attendance_cpe_report.csv").exists()
    assert (tmp_path / "isaca_cpe_upload_ready.csv").exists()


def test_main_filters_short_duration(tmp_path, monkeypatch):
    """Bob attended only 30 minutes and should be excluded."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "bob@example.com" not in report["Email"].values


def test_main_cpe_calculation(tmp_path, monkeypatch):
    """Alice (90 min) => 1 CPE, Carol (60 min) => 1 CPE."""
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
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", base_args(tmp_path)):
        with pytest.raises(SystemExit):
            main()


@pytest.mark.skipif(sys.platform == "win32", reason="chmod read-only not reliable on Windows")
def test_main_exits_when_output_dir_not_writable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    read_only_dir = tmp_path / "readonly"
    read_only_dir.mkdir()
    os.chmod(read_only_dir, 0o444)
    with patch("sys.argv", BASE_ARGS + ["--output-dir", str(read_only_dir)]):
        with pytest.raises(SystemExit):
            main()
    os.chmod(read_only_dir, 0o755)  # restore so tmp_path cleanup succeeds


def test_main_exits_when_output_dir_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS + ["--output-dir", str(tmp_path / "nonexistent")]):
        with pytest.raises(SystemExit):
            main()


def test_main_exits_when_participants_file_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS + [
        "--participants", str(tmp_path / "missing.csv"),
        "--registration", str(tmp_path / "registration_2025.csv"),
        "--output-dir", str(tmp_path),
    ]):
        with pytest.raises(SystemExit):
            main()


@pytest.mark.skipif(sys.platform == "win32", reason="chmod read-only not reliable on Windows")
def test_main_exits_when_participants_file_not_readable(tmp_path, monkeypatch):
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
    """A CSV with a valid header but no data rows should produce no qualifying attendees."""
    monkeypatch.chdir(tmp_path)
    participants = PARTICIPANTS_HEADER + "Name,Email,Duration (minutes)\n"
    write_csv_files(tmp_path, participants=participants)
    with patch("sys.argv", base_args(tmp_path)):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0


def test_main_verbose_flag(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    import logging
    with patch("sys.argv", base_args(tmp_path) + ["--verbose"]):
        with caplog.at_level(logging.DEBUG):
            main()


def test_main_quiet_suppresses_info(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    import logging
    with patch("sys.argv", base_args(tmp_path) + ["--quiet"]):
        with caplog.at_level(logging.INFO, logger="zoom_cpe"):
            main()
    assert not any(r.levelno == logging.INFO for r in caplog.records)


def test_main_verbose_and_quiet_are_mutually_exclusive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--verbose", "--quiet"]):
        with pytest.raises(SystemExit):
            main()


def test_main_warns_and_exits_when_no_qualifying_attendees(tmp_path, monkeypatch):
    """All attendees below min duration — no output files should be written."""
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


def test_main_warns_on_null_emails(tmp_path, monkeypatch, caplog):
    """Participants with missing emails should trigger a warning."""
    monkeypatch.chdir(tmp_path)
    participants = (
        PARTICIPANTS_HEADER
        + "Name,Email,Duration (minutes)\n"
        + "Alice Smith,alice@example.com,90\n"
        + "Unknown,,60\n"
    )
    write_csv_files(tmp_path, participants=participants)
    import logging
    with patch("sys.argv", base_args(tmp_path)):
        with caplog.at_level(logging.WARNING, logger="zoom_cpe"):
            main()
    assert any("missing email" in r.message for r in caplog.records)


def test_main_explicit_input_files(tmp_path, monkeypatch):
    """Explicit --participants and --registration paths should be used instead of auto-detection."""
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
    """Attendees with non-numeric ISACA IDs should be excluded from output."""
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
    """An attendee who rejoins should have their durations summed before filtering."""
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
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    bad_args = base_args(tmp_path).copy()
    bad_args[bad_args.index("IPROED")] = "INVALID"
    with patch("sys.argv", bad_args):
        with pytest.raises(SystemExit):
            main()


def test_main_exits_on_invalid_method(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    bad_args = base_args(tmp_path).copy()
    bad_args[bad_args.index("ONLINE")] = "INVALID"
    with patch("sys.argv", bad_args):
        with pytest.raises(SystemExit):
            main()


def test_main_custom_min_duration(tmp_path, monkeypatch):
    """With --min-duration 30, Bob (30 min) should now qualify."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", base_args(tmp_path) + ["--min-duration", "30"]):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "bob@example.com" in report["Email"].values
