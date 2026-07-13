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
        if all(
            c.lower() in [col.lower() for col in df.columns] for c in required_columns
        ):
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


def validate_min_duration(value):
    """Parses and validates --min-duration as a positive integer greater than zero.
    Raises argparse.ArgumentTypeError if the value is not a positive integer."""
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid value '{value}': must be a positive integer."
        )
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(
            f"--min-duration must be greater than zero, got {ivalue}."
        )
    return ivalue


def validate_date(value):
    """Parses and returns a datetime from a MM/DD/YYYY string. Raises
    argparse.ArgumentTypeError if the format is invalid."""
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected format: MM/DD/YYYY"
        )


def build_arg_parser():
    """Builds and returns the argument parser with all CLI arguments defined."""
    parser = argparse.ArgumentParser(
        description="Process Zoom reports and generate ISACA CPE upload files."
    )
    parser.add_argument("--org", required=True, help="Sponsoring Organization Name")
    parser.add_argument("--event", required=True, help="Event Name")
    parser.add_argument(
        "--start",
        required=True,
        type=validate_date,
        help="Event Start Date (MM/DD/YYYY)",
    )
    parser.add_argument(
        "--end", required=True, type=validate_date, help="Event End Date (MM/DD/YYYY)"
    )
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
        type=validate_min_duration,
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
    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument(
        "--verbose", action="store_true", help="Enable verbose (DEBUG) logging"
    )
    log_group.add_argument(
        "--quiet", action="store_true", help="Suppress all output except errors"
    )
    return parser


def validate_args(args):
    """Validates parsed arguments and resolved file paths. Logs an error and
    exits with code 1 on any validation failure."""
    if args.end < args.start:
        logger.error("--end date cannot be before --start date.")
        sys.exit(1)

    if not os.path.isdir(args.output_dir):
        logger.error(f"Output directory does not exist: '{args.output_dir}'")
        sys.exit(1)
    if not os.access(args.output_dir, os.W_OK):
        logger.error(f"Output directory is not writable: '{args.output_dir}'")
        sys.exit(1)

    p_file = args.participants or find_file("participants*.csv")
    r_file = args.registration or find_file("registration*.csv")

    if not p_file or not r_file:
        logger.error("Missing required participants or registration CSV files.")
        sys.exit(1)

    for label, path in (("participants", p_file), ("registration", r_file)):
        if not os.path.isfile(path):
            logger.error(f"{label} file not found: '{path}'")
            sys.exit(1)
        if not os.access(path, os.R_OK):
            logger.error(f"{label} file is not readable: '{path}'")
            sys.exit(1)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        if size_mb > 50:
            logger.warning(
                f"{label} file is large ({size_mb:.1f} MB) and may use significant memory."
            )

    return p_file, r_file


def load_data(p_file, r_file):
    """Loads participants and registration CSVs, dynamically detecting the header
    row in each file. Returns (participants_df, registration_df, id_col_name) or
    exits with code 1 if the header or ID column cannot be found."""
    try:
        p_skip = find_header_row(p_file, ["email", "duration (minutes)"])
        r_skip = find_header_row(r_file, ["first name", "last name", "email"])
    except ValueError as e:
        logger.error(e)
        sys.exit(1)

    participants_df = pd.read_csv(p_file, skiprows=p_skip)
    registration_df = pd.read_csv(r_file, skiprows=r_skip)

    exclude_cols = {
        "first name",
        "last name",
        "email",
        "approval status",
        "registration time",
        "industry",
        "organization",
    }
    potential_cols = [
        c for c in registration_df.columns if c.lower() not in exclude_cols
    ]

    id_col_name = next(
        (col for col in potential_cols if is_id_column(registration_df[col])), None
    )
    if not id_col_name:
        logger.error("Could not identify an ID column with numeric data.")
        sys.exit(1)

    return participants_df, registration_df, id_col_name


def process(participants_df, registration_df, id_col_name, args):
    """Merges, filters, and calculates CPE for attendees. Returns
    (report_df, upload_df) or exits with code 0 if no qualifying attendees remain."""
    null_emails = participants_df["Email"].isna().sum()
    if null_emails:
        logger.warning(
            f"{null_emails} participant row(s) dropped due to missing email."
        )

    participants_summary = (
        participants_df.groupby("Email")["Duration (minutes)"].sum().reset_index()
    )
    participants_summary["Email"] = (
        participants_summary["Email"].str.lower().str.strip()
    )
    registration_df["Email"] = registration_df["Email"].str.lower().str.strip()

    merged_df = pd.merge(participants_summary, registration_df, on="Email", how="inner")

    df_filtered = merged_df[merged_df["Duration (minutes)"] >= args.min_duration].copy()
    df_filtered = df_filtered.dropna(subset=[id_col_name])
    df_filtered[id_col_name] = df_filtered[id_col_name].astype(str).str.strip()
    final_df = df_filtered[df_filtered[id_col_name].str.match(r"^\d+$")].copy()

    final_df["CPE"] = (final_df["Duration (minutes)"] // args.min_duration).astype(int)

    if final_df.empty:
        logger.warning(
            "No qualifying attendees found after filtering. Output files will not be written."
        )
        sys.exit(0)

    final_df["Report_Name"] = (
        final_df["Last Name"].str.strip() + ", " + final_df["First Name"].str.strip()
    )
    report_df = final_df[
        [id_col_name, "Report_Name", "Email", "Duration (minutes)", "CPE"]
    ].copy()
    report_df.columns = ["ID", "Name", "Email", "Duration", "CPE"]
    report_df = report_df.sort_values(by="Name").reset_index(drop=True)

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
    upload_df = upload_df.sort_values(by=["LAST_NAME", "FIRST_NAME"]).reset_index(
        drop=True
    )

    return report_df, upload_df


def main():
    """Entry point. Parses arguments, validates inputs, loads data, processes
    attendees, and writes output files to the specified output directory."""
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    p_file, r_file = validate_args(args)
    participants_df, registration_df, id_col_name = load_data(p_file, r_file)
    report_df, upload_df = process(participants_df, registration_df, id_col_name, args)

    report_path = os.path.join(args.output_dir, "final_attendance_cpe_report.csv")
    upload_path = os.path.join(args.output_dir, "isaca_cpe_upload_ready.csv")
    report_df.to_csv(report_path, index=False)
    upload_df.to_csv(upload_path, index=False)

    logger.info("Success!")
    logger.info(f"- Internal report: '{report_path}'")
    logger.info(f"- ISACA Upload file: '{upload_path}'")


if __name__ == "__main__":
    main()
