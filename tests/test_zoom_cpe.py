import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from zoom_cpe import find_file, is_id_column, main

# --- find_file ---


def test_find_file_returns_last_sorted_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "participants_2024.csv").write_text("")
    (tmp_path / "participants_2025.csv").write_text("")
    assert find_file("participants*.csv").endswith("participants_2025.csv")


def test_find_file_returns_none_when_no_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert find_file("participants*.csv") is None


# --- is_id_column ---


def test_is_id_column_numeric():
    assert is_id_column(pd.Series(["12345", "67890", "11111"])) == True


def test_is_id_column_non_numeric():
    assert is_id_column(pd.Series(["alice", "bob", "carol"])) == False


def test_is_id_column_mixed_mostly_numeric():
    assert is_id_column(pd.Series(["12345", "67890", "notnum"])) == True


def test_is_id_column_empty():
    assert is_id_column(pd.Series([], dtype=str)) == False


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
    "--org",
    "Test Org",
    "--event",
    "Test Event",
    "--start",
    "01/01/2025",
    "--end",
    "01/01/2025",
    "--activity",
    "IPROED",
    "--method",
    "ONLINE",
]


def write_csv_files(tmp_path):
    (tmp_path / "participants_2025.csv").write_text(PARTICIPANTS_CSV)
    (tmp_path / "registration_2025.csv").write_text(REGISTRATION_CSV)


def test_main_creates_output_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS):
        main()
    assert (tmp_path / "final_attendance_cpe_report.csv").exists()
    assert (tmp_path / "isaca_cpe_upload_ready.csv").exists()


def test_main_filters_short_duration(tmp_path, monkeypatch):
    """Bob attended only 30 minutes and should be excluded."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    assert "bob@example.com" not in report["Email"].values


def test_main_cpe_calculation(tmp_path, monkeypatch):
    """Alice (90 min) => 1 CPE, Carol (60 min) => 1 CPE."""
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS):
        main()
    report = pd.read_csv(tmp_path / "final_attendance_cpe_report.csv")
    alice = report[report["Email"] == "alice@example.com"].iloc[0]
    carol = report[report["Email"] == "carol@example.com"].iloc[0]
    assert alice["CPE"] == 1
    assert carol["CPE"] == 1


def test_main_upload_file_columns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_csv_files(tmp_path)
    with patch("sys.argv", BASE_ARGS):
        main()
    upload = pd.read_csv(tmp_path / "isaca_cpe_upload_ready.csv")
    expected_cols = [
        "ID",
        "EMAIL",
        "LAST_NAME",
        "FIRST_NAME",
        "Sponsoring Organization Name",
        "Event Name",
        "Date Format",
        "Event Start Date",
        "Event End Date",
        "CPE Hours Earned",
        "Qualifying Activity",
        "Method of Delivery",
    ]
    assert list(upload.columns) == expected_cols


def test_main_exits_when_files_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("sys.argv", BASE_ARGS):
        with pytest.raises(SystemExit):
            main()
