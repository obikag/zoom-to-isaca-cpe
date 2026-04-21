import argparse
import glob
import re
import sys

import pandas as pd


def find_file(pattern):
    """Finds the most recent file matching a glob pattern."""
    files = glob.glob(pattern)
    return sorted(files)[-1] if files else None


def is_id_column(series):
    """Identifies the ID column by checking if values are primarily numeric."""
    vals = series.dropna().astype(str).str.strip()
    if len(vals) == 0:
        return False
    # Check for columns where over 50% of the data consists of digits
    numeric_count = vals.apply(lambda x: bool(re.match(r"^\d+$", x))).sum()
    return (numeric_count / len(vals)) > 0.5


def main():
    # 1. Setup Argument Parser - All defaults removed and made required
    parser = argparse.ArgumentParser(
        description="Process Zoom reports and generate ISACA CPE upload files."
    )
    parser.add_argument("--org", required=True, help="Sponsoring Organization Name")
    parser.add_argument("--event", required=True, help="Event Name")
    parser.add_argument("--start", required=True, help="Event Start Date (MM/DD/YYYY)")
    parser.add_argument("--end", required=True, help="Event End Date (MM/DD/YYYY)")
    parser.add_argument(
        "--activity", required=True, help="Qualifying Activity (e.g., IPROED, PROED)"
    )
    parser.add_argument(
        "--method", required=True, help="Method of Delivery (e.g., ONLINE, INPERSON)"
    )

    # Parse arguments
    args = parser.parse_args()

    # 2. Detect the Zoom CSV files
    p_file = find_file("participants*.csv")
    r_file = find_file("registration*.csv")

    if not p_file or not r_file:
        print("Error: Missing required participants or registration files.")
        sys.exit(1)

    # 3. Load data
    participants_df = pd.read_csv(p_file, skiprows=3)
    registration_df = pd.read_csv(r_file, skiprows=5)

    # 4. Dynamically identify the ID column based on contents
    exclude_cols = [
        "first name",
        "last name",
        "email",
        "approval status",
        "registration time",
        "industry",
        "organization",
    ]
    potential_cols = [
        c for c in registration_df.columns if c.lower() not in exclude_cols
    ]

    id_col_name = None
    for col in potential_cols:
        if is_id_column(registration_df[col]):
            id_col_name = col
            break

    if not id_col_name:
        print("Error: Could not identify an ID column with numeric data.")
        sys.exit(1)

    # 5. Process Attendance and Merge
    participants_summary = (
        participants_df.groupby("Email")["Duration (minutes)"].sum().reset_index()
    )
    participants_summary["Email"] = (
        participants_summary["Email"].str.lower().str.strip()
    )
    registration_df["Email"] = registration_df["Email"].str.lower().str.strip()

    merged_df = pd.merge(participants_summary, registration_df, on="Email", how="inner")

    # 6. Apply Filters
    # Filter by duration (>= 50 minutes)
    df_filtered = merged_df[merged_df["Duration (minutes)"] >= 50].copy()

    # Filter for VALID NUMERIC IDs only
    df_filtered = df_filtered.dropna(subset=[id_col_name])
    df_filtered[id_col_name] = df_filtered[id_col_name].astype(str).str.strip()
    final_df = df_filtered[df_filtered[id_col_name].str.match(r"^\d+$")].copy()

    # 7. Calculate CPE Column (1 CPE = 50 Minutes, as integer)
    final_df["CPE"] = (final_df["Duration (minutes)"] // 50).astype(int)

    # 8. Create Internal Attendance Report
    final_df["Report_Name"] = (
        final_df["Last Name"].str.strip() + ", " + final_df["First Name"].str.strip()
    )
    report_df = final_df[
        [id_col_name, "Report_Name", "Email", "Duration (minutes)", "CPE"]
    ].copy()
    report_df.columns = ["ID", "Name", "Email", "Duration", "CPE"]
    report_df = report_df.sort_values(by="Name").reset_index(drop=True)
    report_df.to_csv("final_attendance_cpe_report.csv", index=False)

    # 9. Create CPE Upload File
    upload_df = pd.DataFrame(
        {
            "ID": final_df[id_col_name],
            "EMAIL": final_df["Email"],
            "LAST_NAME": final_df["Last Name"].str.strip(),
            "FIRST_NAME": final_df["First Name"].str.strip(),
            "Sponsoring Organization Name": args.org,
            "Event Name": args.event,
            "Date Format": "MM/dd/yyyy",
            "Event Start Date": args.start,
            "Event End Date": args.end,
            "CPE Hours Earned": final_df["CPE"],
            "Qualifying Activity": args.activity,
            "Method of Delivery": args.method,
        }
    )

    # Sort by Last Name
    upload_df = upload_df.sort_values(by=["LAST_NAME", "FIRST_NAME"]).reset_index(
        drop=True
    )
    upload_df.to_csv("isaca_cpe_upload_ready.csv", index=False)

    print(f"Success!")
    print(f"- Internal report: 'final_attendance_cpe_report.csv'")
    print(f"- ISACA Upload file: 'isaca_cpe_upload_ready.csv'")


if __name__ == "__main__":
    main()
