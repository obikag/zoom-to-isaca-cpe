import argparse
import glob
import logging
import os
import re
import sys
from datetime import datetime

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

VALID_ACTIVITIES = {"IPROED", "PROED"}
VALID_METHODS = {"ONLINE", "INPERSON"}
DATE_FORMAT = "%m/%d/%Y"


def find_file(pattern):
    """Returns the last alphabetically sorted file matching the given glob pattern,
    or None if no files match."""
    files = glob.glob(pattern)
    return sorted(files)[-1] if files else None


def find_header_row(filepath, required_columns, max_rows=10):
    """Scans the first max_rows rows of a CSV to find the row index that contains
    all required_columns (case-insensitive). Returns the row index or raises
    ValueError if no matching header row is found."""
    for i in range(max_rows):
        df = pd.read_csv(filepath, skiprows=i, nrows=0)
        if all(c.lower() in [col.lower() for col in df.columns] for c in required_columns):
            return i
    raise ValueError(
        f"Could not find a header row containing {required_columns} in '{filepath}'"
    )


def is_id_column(series):
    """Returns True if more than 50% of non-null values in the series consist
    entirely of digits, indicating the column likely holds numeric member IDs."""
    vals = series.dropna().astype(str).str.strip()
    if len(vals) == 0:
        return False
    numeric_count = vals.apply(lambda x: bool(re.match(r"^\d+$", x))).sum()
    return (numeric_count / len(vals)) > 0.5


def validate_date(value):
    """Parses and returns a datetime from a MM/DD/YYYY string. Raises
    argparse.ArgumentTypeError if the format is invalid."""
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected format: MM/DD/YYYY"
        )


def main():
    # Parse and validate all CLI arguments before any file I/O
    parser = argparse.ArgumentParser(
        description="Process Zoom reports and generate ISACA CPE upload files."
    )
    parser.add_argument("--org", required=True, help="Sponsoring Organization Name")
    parser.add_argument("--event", required=True, help="Event Name")
    parser.add_argument("--start", required=True, type=validate_date, help="Event Start Date (MM/DD/YYYY)")
    parser.add_argument("--end", required=True, type=validate_date, help="Event End Date (MM/DD/YYYY)")
    parser.add_argument(
        "--activity",
        required=True,
        choices=VALID_ACTIVITIES,
        help=f"Qualifying Activity ({', '.join(sorted(VALID_ACTIVITIES))})",
    )
    parser.add_argument(
        "--method",
        required=True,
        choices=VALID_METHODS,
        help=f"Method of Delivery ({', '.join(sorted(VALID_METHODS))})",
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=50,
        help="Minimum attendance duration in minutes to qualify for CPE (default: 50)",
    )
    parser.add_argument(
        "--participants",
        help="Path to Zoom participants CSV (auto-detected from current directory if omitted)",
    )
    parser.add_argument(
        "--registration",
        help="Path to Zoom registration CSV (auto-detected from current directory if omitted)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where output CSV files will be written",
    )

    args = parser.parse_args()

    if args.end < args.start:
        logger.error("--end date cannot be before --start date.")
        sys.exit(1)

    # Validate output directory exists
    if not os.path.isdir(args.output_dir):
        logger.error(f"Output directory does not exist: '{args.output_dir}'")
        sys.exit(1)

    # Use explicit paths if provided, otherwise auto-detect from the current directory
    p_file = args.participants or find_file("participants*.csv")
    r_file = args.registration or find_file("registration*.csv")

    if not p_file or not r_file:
        logger.error("Missing required participants or registration CSV files.")
        sys.exit(1)

    # Dynamically detect the header row to handle Zoom export format changes
    try:
        p_skip = find_header_row(p_file, ["email", "duration (minutes)"])
        r_skip = find_header_row(r_file, ["first name", "last name", "email"])
    except ValueError as e:
        logger.error(e)
        sys.exit(1)

    participants_df = pd.read_csv(p_file, skiprows=p_skip)
    registration_df = pd.read_csv(r_file, skiprows=r_skip)

    # Identify the ISACA member ID column by finding the first non-excluded column
    # whose values are predominantly numeric
    exclude_cols = {
        "first name", "last name", "email", "approval status",
        "registration time", "industry", "organization",
    }
    potential_cols = [c for c in registration_df.columns if c.lower() not in exclude_cols]

    id_col_name = None
    for col in potential_cols:
        if is_id_column(registration_df[col]):
            id_col_name = col
            break

    if not id_col_name:
        logger.error("Could not identify an ID column with numeric data.")
        sys.exit(1)

    # Normalise emails and warn about any rows dropped due to missing email
    null_emails = participants_df["Email"].isna().sum()
    if null_emails:
        logger.warning(f"{null_emails} participant row(s) dropped due to missing email.")

    # Sum duration across multiple rows for the same attendee (e.g. rejoined sessions)
    participants_summary = (
        participants_df.groupby("Email")["Duration (minutes)"].sum().reset_index()
    )
    participants_summary["Email"] = participants_summary["Email"].str.lower().str.strip()
    registration_df["Email"] = registration_df["Email"].str.lower().str.strip()

    merged_df = pd.merge(participants_summary, registration_df, on="Email", how="inner")

    # Filter out attendees below the minimum duration threshold
    df_filtered = merged_df[merged_df["Duration (minutes)"] >= args.min_duration].copy()

    # Filter out registrants with missing or non-numeric ISACA member IDs
    df_filtered = df_filtered.dropna(subset=[id_col_name])
    df_filtered[id_col_name] = df_filtered[id_col_name].astype(str).str.strip()
    final_df = df_filtered[df_filtered[id_col_name].str.match(r"^\d+$")].copy()

    # Calculate CPE hours by flooring total minutes to the nearest 50-minute block
    # e.g. 90 min => 1 CPE, 100 min => 2 CPE
    final_df["CPE"] = (final_df["Duration (minutes)"] // args.min_duration).astype(int)

    # Build and write the internal attendance report sorted by attendee name
    final_df["Report_Name"] = (
        final_df["Last Name"].str.strip() + ", " + final_df["First Name"].str.strip()
    )
    report_df = final_df[
        [id_col_name, "Report_Name", "Email", "Duration (minutes)", "CPE"]
    ].copy()
    report_df.columns = ["ID", "Name", "Email", "Duration", "CPE"]
    report_df = report_df.sort_values(by="Name").reset_index(drop=True)
    report_path = os.path.join(args.output_dir, "final_attendance_cpe_report.csv")
    report_df.to_csv(report_path, index=False)

    # Build and write the ISACA CPE upload file sorted by last name
    start_str = args.start.strftime("%m/%d/%Y")
    end_str = args.end.strftime("%m/%d/%Y")
    upload_df = pd.DataFrame(
        {
            "ID": final_df[id_col_name],
            "EMAIL": final_df["Email"],
            "LAST_NAME": final_df["Last Name"].str.strip(),
            "FIRST_NAME": final_df["First Name"].str.strip(),
            "Sponsoring Organization Name": args.org,
            "Event Name": args.event,
            "Date Format": "MM/dd/yyyy",
            "Event Start Date": start_str,
            "Event End Date": end_str,
            "CPE Hours Earned": final_df["CPE"],
            "Qualifying Activity": args.activity,
            "Method of Delivery": args.method,
        }
    )
    upload_df = upload_df.sort_values(by=["LAST_NAME", "FIRST_NAME"]).reset_index(drop=True)
    upload_path = os.path.join(args.output_dir, "isaca_cpe_upload_ready.csv")
    upload_df.to_csv(upload_path, index=False)

    logger.info("Success!")
    logger.info(f"- Internal report: '{report_path}'")
    logger.info(f"- ISACA Upload file: '{upload_path}'")



if __name__ == "__main__":
    main()
