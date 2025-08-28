"""Compliance checking utilities for CORDEX/CMIP6 datasets.

This module loads a catalog of NetCDF dataset file paths, runs compliance
checks (CF and cc6) via ``compliance_checker``, summarizes the results into
CSV/Excel reports, and can optionally open GitHub issues for high-priority
problems.

Main steps (see ``main``):
    1. Collect representative files (one per dataset id) from a remote CSV catalog.
    2. Attempt to open each file (record unreadable/corrupt files).
    3. Run compliance checks on readable files.
    4. Summarize scores & priority messages into a tabular report.
    5. Produce a human-readable Excel workbook (one sheet per institution).

Notes
-----
Network access is required for fetching the catalog and (optionally) creating
GitHub issues. The GitHub token is read from the ``ISSUE_TOKEN`` environment
variable.
"""

from compliance_checker.runner import ComplianceChecker, CheckSuite
import pandas as pd
import json
import os
import xarray as xr
from pathlib import Path

import requests

# Replace these with your GitHub details
GITHUB_TOKEN = os.environ.get(
    "ISSUE_TOKEN"
)  # Replace with your GitHub Personal Access Token
REPO_OWNER = (
    "euro-cordex"  # Replace with the repository owner's username or organization name
)
REPO_NAME = "jsc-compliance-check"  # Replace with the repository name

# GitHub API URL for listing and creating issues
issues_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"

# Headers for authentication
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
# Define the priorities for each checker
prios = {
    "cf": ["low_priorities", "medium_priorities", "high_priorities"],
    "cc6": ["low_priorities", "medium_priorities", "high_priorities"],
}

cols = ["scored_points", "possible_points", "high_count", "medium_count", "low_count"]

id_attrs = [
    "variable_id",
    "domain_id",
    "driving_source_id",
    "driving_experiment_id",
    "driving_variant_label",
    "institution_id",
    "source_id",
    "version_realization",
    "frequency",
    "version",
]

report_dir = "./report"
report_filename = os.path.join(report_dir, "compliance-report")


def collect_files(catalog_filename):
    """Collect one representative file path per unique dataset id.

    Parameters
    ----------
    catalog_filename : str | pathlib.Path
        Path or URL to a CSV catalog containing at least the columns in
        ``id_attrs`` plus a ``path`` column and ``mip_era``.

    Returns
    -------
    list[str]
        List of file paths (one per unique combination of identifying
        attributes) filtered to CMIP6 entries.
    """
    catalog = pd.read_csv(catalog_filename)
    catalog = catalog[catalog["mip_era"] == "CMIP6"]  # only check CMIP6 data

    files = (
        catalog.groupby(id_attrs)
        .apply(lambda x: x.iloc[0].path)  # only use first file for each unique dataset
        .reset_index(drop=True)
        .to_list()
    )

    return files


def concat_messages(tests):
    """Concatenate message lists from test result dicts.

    Parameters
    ----------
    tests : list[dict]
        Iterable of test result dictionaries (each optionally containing
        a ``"msgs"`` key with a list of strings).

    Returns
    -------
    str
        Newline-separated concatenation of all non-empty messages.
    """
    summary = ""
    for test in tests:
        if test.get("msgs"):
            summary += "\n".join(test["msgs"]) + "\n"
    return summary


def summarize(test, results):
    """Summarize score counts and aggregated messages for a test.

    Parameters
    ----------
    test : str
        Test key as produced by the compliance checker (may contain
        a colon-delimited prefix; only the first segment is used for
        priority mapping).
    results : dict
        Result structure for a single test including numeric score
        components listed in ``cols`` and priority lists (e.g.
        ``high_priorities``) each holding dicts with optional messages.

    Returns
    -------
    dict
        Mapping of ``"{test_id}:{metric}"`` to numeric values for each
        score metric plus ``"{test_id}:{priority}"`` to concatenated
        messages.
    """
    summaries = {}
    test_id = test.split(":")[0]
    summaries = {f"{test_id}:{c}": results[c] for c in cols}
    for prio in prios[test_id]:
        tests = results.get(prio, [])
        summary = concat_messages(tests)
        summaries[f"{test_id}:{prio}"] = summary
    return summaries


def test_open_dataset(filenames):
    """Attempt to open datasets to detect unreadable/corrupt files.

    Parameters
    ----------
    filenames : list[str]
        List of NetCDF file paths to test.

    Returns
    -------
    pandas.DataFrame
        DataFrame with a row per failed file containing columns:
        ``filename`` and ``not_readable`` (exception string). Empty if all
        files were readable. Also written to ``report/corrupt_files.csv``.
    """
    valid = filenames.copy()
    failed = {}
    for f in filenames:
        try:
            xr.open_dataset(f)
        except Exception as e:  # noqa: BLE001 broad for logging only
            print(f"Failed to open {f}: {e}")
            valid.remove(f)
            failed[f] = str(e)
            continue
    df = (
        pd.DataFrame.from_dict(failed, orient="index", columns=["not_readable"])
        .reset_index()
        .rename(columns={"index": "filename"})
    )
    df.to_csv(os.path.join(report_dir, "corrupt_files.csv"), index=False)
    return df


def compliance_check(filenames):
    """Run compliance checks (CF & cc6) and load JSON results.

    Parameters
    ----------
    filenames : list[str]
        Dataset locations (file paths or URLs). Passed directly to
        ``ComplianceChecker.run_checker`` via the ``path`` argument.

    Returns
    -------
    dict
        Parsed JSON structure produced by compliance checker containing
        per-file test results and scores.

    Notes
    -----
    The compliance checker writes output side-effects: ``*.json`` and
    ``*.html`` files with the base name in ``report_filename``.
    """
    # Load all available checker classes
    check_suite = CheckSuite()
    check_suite.load_all_available_checkers()

    print(f"checking {len(filenames)} datasets")
    path = filenames
    checker_names = ["cf", "cc6"]
    verbose = 1
    criteria = "normal"
    output_filename = report_filename
    output_format = ["json_new", "html"]

    _return_value, _errors = ComplianceChecker.run_checker(
        path,
        checker_names,
        verbose,
        criteria,
        output_filename=output_filename,
        output_format=output_format,
    )

    # Open the JSON output and get the compliance scores
    with open(f"{output_filename}.json", "r") as fp:
        cc_data = json.load(fp)

    return cc_data


def filename_to_attrs(filename):
    """Parse identifying attributes from a dataset filename.

    Parameters
    ----------
    filename : str | pathlib.Path
        Full path to a NetCDF file following the expected CORDEX/CMIP6
        naming convention (underscore-delimited components).

    Returns
    -------
    dict
        Mapping of each name in ``id_attrs`` to extracted values. The final
        element (``version``) is read from the directory name containing the
        file; others are parsed from the filename stem.
    """
    stem = Path(filename).stem
    path = str(Path(filename).parent)
    version = path.split("/")[-1]
    values = stem.split("_")[0 : len(id_attrs) - 1] + [version]
    return dict(zip(id_attrs, values))


def filename_to_id(filename):
    """Build a dot-delimited dataset identifier string.

    Parameters
    ----------
    filename : str | pathlib.Path
        Dataset file path.

    Returns
    -------
    str
        Identifier composed of all attribute values joined by ``'.'``.
    """
    values = list(filename_to_attrs(filename).values())
    return ".".join(values)


def collect_non_empty_msgs(results):
    """Collect non-empty ``msgs`` lists from test result dictionaries.

    Parameters
    ----------
    results : list[dict]
        Sequence of test result dictionaries each containing at least
        ``name`` and ``msgs`` keys.

    Returns
    -------
    dict[str, list[str]]
        Mapping test name -> list of messages for entries with non-empty
        message lists.
    """
    non_empty_msgs = {}
    for test_result in results:
        if test_result["msgs"]:
            non_empty_msgs[test_result["name"]] = test_result["msgs"]
    return non_empty_msgs


def get_non_empty_errors(cc_data):
    """Extract non-empty high-priority error messages.

    Parameters
    ----------
    cc_data : dict
        Compliance checker JSON output structure keyed by filename then
        test name.

    Returns
    -------
    dict
        Mapping of dataset id -> details dict with keys ``file`` and
        ``high priority`` (the latter maps test names to lists of messages).
    """
    all_non_empty_msgs = {}
    for file, report in cc_data.items():
        for test, results in report.items():
            high_priority_msgs = collect_non_empty_msgs(results["high_priorities"])
            if high_priority_msgs:
                all_non_empty_msgs[filename_to_id(file)] = {
                    "file": file,
                    "high priority": high_priority_msgs,
                }
    return all_non_empty_msgs


def issue_exists(issue_title):
    """Check if a GitHub issue with a given title already exists.

    Parameters
    ----------
    issue_title : str
        Title to search among open issues of the configured repository.

    Returns
    -------
    bool
        True if an open issue with the exact title exists, else False.
    """
    response = requests.get(issues_url, headers=headers)
    if response.status_code == 200:
        issues = response.json()
        for issue in issues:
            if issue["title"] == issue_title:
                return True  # Issue already exists
    else:
        print("Failed to fetch issues:", response.status_code, response.json())
    return False


def create_github_issue(issue_title, issue_body, labels=None):
    """Create a GitHub issue if not already present.

    Parameters
    ----------
    issue_title : str
        Desired title of the issue.
    issue_body : str
        Markdown-formatted body content.
    labels : list[str], optional
        Labels to apply to the issue.

    Returns
    -------
    None
        Logs creation success/failure to stdout.
    """
    if issue_exists(issue_title):
        print(f"Issue with title '{issue_title}' already exists. Skipping creation.")
        return

    payload = {
        "title": issue_title,
        "body": issue_body,
        "labels": labels or [],
    }

    response = requests.post(issues_url, headers=headers, json=payload)
    if response.status_code == 201:
        print("Issue created successfully:", response.json()["html_url"])
    else:
        print("Failed to create issue:", response.status_code, response.json())


def log_issues_from_errors(errors):
    """Create one GitHub issue per dataset with high-priority errors.

    Parameters
    ----------
    errors : dict
        Structure produced by ``get_non_empty_errors`` describing high
        priority message content per dataset id.

    Returns
    -------
    None
        Issues are created via the GitHub API (idempotent per title).
    """
    priority = "high priority"

    for dataset_id, error_details in errors.items():
        issue_title = f"`{dataset_id}`"
        filename = error_details["file"]
        msgs = error_details[priority]
        issue_body = f"Issues for dataset `{dataset_id}`:\n\n"
        issue_body += f"Filename: `{filename}`\n\n"
        for section, messages in msgs.items():
            issue_body += f"### {section}\n"
            issue_body += "\n".join(f"- {msg}" for msg in messages)
            issue_body += "\n\n"

        issue_body += "This issue was created automatically by the compliance checker."

        create_github_issue(issue_title, issue_body, labels=[priority])


def write_report(cc_data, corrupt):
    """Write the consolidated compliance CSV report.

    Parameters
    ----------
    cc_data : dict
        Output of ``compliance_check`` with per-file results.
    corrupt : pandas.DataFrame
        DataFrame from ``test_open_dataset`` containing unreadable file
        info (may be empty).

    Returns
    -------
    str
        Path to the generated CSV report (``compliance-report.csv``).
    """
    result = {}
    report = f"{report_filename}.csv"
    for filename, tests in cc_data.items():
        for test, results in tests.items():
            summary = summarize(test, results)
            result[filename] = filename_to_attrs(filename) | summary
    df = (
        pd.DataFrame.from_dict(result, orient="index")
        .reset_index()
        .rename(columns={"index": "filename"})
    )
    df = df.merge(corrupt, on="filename", how="left")
    df.to_csv(report, index=False)
    return report


def human_readable(df):
    """Prepare a MultiIndex, sorted, NaN-free view for reporting.

    Parameters
    ----------
    df : pandas.DataFrame
        Raw report DataFrame including identifying columns and score
        columns. Must contain the index column names listed below.

    Returns
    -------
    pandas.DataFrame
        DataFrame sorted by index columns, set to a MultiIndex, with
        missing values filled by empty strings for cleaner Excel export.
    """
    index = [
        "domain_id",
        "source_id",
        "driving_experiment_id",
        "driving_source_id",
        "driving_variant_label",
        "version_realization",
        "variable_id",
        "frequency",
        "version",
        "filename",
    ]
    return df.sort_values(index).set_index(index).fillna("")


def create_excel(filename, cols=None):
    """Create a human-readable multi-sheet Excel workbook.

    Parameters
    ----------
    filename : str | pathlib.Path
        Path to the CSV report produced by ``write_report``.

    Returns
    -------
    str
        Path to the generated ``.xlsx`` file (same stem as input CSV).
    """
    df = pd.read_csv(filename)

    if cols is None:
        cols = [
            "cc6:high_priorities",
            "cf:high_priorities",
            "cc6:mediumg_priorities",
            "cf:medium_priorities",
        ]

    sheets = {
        institution_id: human_readable(df)[cols]
        for institution_id, df in df.groupby("institution_id")
    }

    stem, _suffix = os.path.splitext(filename)
    xlsxfile = f"{stem}.xlsx"

    with pd.ExcelWriter(xlsxfile, engine="xlsxwriter") as writer:
        workbook = writer.book
        wrap_format = workbook.add_format(
            {"text_wrap": True, "align": "left", "valign": "top"}
        )
        grey_format = workbook.add_format(
            {"bg_color": "#F2F2F2", "text_wrap": True, "align": "left", "valign": "top"}
        )

        header_format = workbook.add_format(
            {
                "bold": True,
                "text_wrap": True,
                "valign": "top",
                "fg_color": "#D7E4BC",
                "border": 1,
            }
        )
        for sheet_name, sheet_df in sheets.items():
            print(sheet_name)
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=True)
            worksheet = writer.sheets[sheet_name]

            n_index = len(sheet_df.index.names)
            n_rows = len(sheet_df)
            n_cols = len(sheet_df.columns)

            for col_num, value in enumerate(sheet_df.index.names):
                worksheet.write(0, col_num, value, header_format)

            for col_num, value in enumerate(sheet_df.columns):
                worksheet.write(0, col_num + n_index, value, header_format)

            for idx in range(n_index):
                worksheet.set_column(idx, idx, 30, wrap_format)

            for col_num in range(n_index, n_index + n_cols):
                worksheet.set_column(col_num, col_num, 50, wrap_format)

            for row in range(1, n_rows + 1):
                fmt = grey_format if row % 2 == 0 else wrap_format
                for col in range(n_cols):
                    value = sheet_df.iloc[row - 1, col]
                    worksheet.write(row, col + n_index, value, fmt)

            idx_df = pd.DataFrame(sheet_df.index.tolist(), columns=sheet_df.index.names)
            start_row = 1

            for col in range(n_index - 1, n_index):
                col_values = idx_df.iloc[:, col]
                last_val = None
                merge_start = start_row
                for row in range(n_rows):
                    val = col_values.iloc[row]
                    if val != last_val and row > 0:
                        if row + start_row - merge_start > 1:
                            worksheet.merge_range(
                                merge_start,
                                col,
                                row + start_row - 1,
                                col,
                                last_val,
                                wrap_format,
                            )
                        merge_start = row + start_row
                    last_val = val
                if n_rows + start_row - merge_start > 1:
                    worksheet.merge_range(
                        merge_start,
                        col,
                        n_rows + start_row - 1,
                        col,
                        last_val,
                        wrap_format,
                    )

    return xlsxfile


def main():
    """Run the full compliance checking pipeline (CLI entrypoint).

    Steps
    -----
    1. Ensure report directory exists.
    2. Fetch remote catalog and collect representative dataset files.
    3. Detect unreadable files.
    4. Run compliance checks on readable subset.
    5. Write CSV report and Excel workbook.
    """
    os.makedirs(report_dir, exist_ok=True)
    filenames = collect_files(
        "https://raw.githubusercontent.com/euro-cordex/joint-evaluation/refs/heads/main/catalog.csv"
    )[50:100]
    failed_files = test_open_dataset(filenames)
    cc_data = compliance_check(
        [f for f in filenames if f not in failed_files.filename.tolist()]
    )
    report = write_report(cc_data, failed_files)
    create_excel(report)


if __name__ == "__main__":
    main()
