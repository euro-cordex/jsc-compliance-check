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
    summary = ""
    for test in tests:
        if test.get("msgs"):
            summary += "\n".join(test["msgs"]) + "\n"
    return summary


def summarize(test, results):
    summaries = {}
    test_id = test.split(":")[0]
    summaries = {f"{test_id}:{c}": results[c] for c in cols}
    for prio in prios[test_id]:
        tests = results.get(prio, [])
        summary = concat_messages(tests)
        summaries[f"{test_id}:{prio}"] = summary
    return summaries


def test_open_dataset(filenames):
    valid = filenames.copy()
    failed = {}
    for f in filenames:
        try:
            xr.open_dataset(f)
        except Exception as e:
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
    # Load all available checker classes
    check_suite = CheckSuite()
    check_suite.load_all_available_checkers()

    print(f"checking {len(filenames)} datasets")
    # Run cf and adcc checks
    path = filenames
    #'/mnt/CORDEX_CMIP6_tmp/sim_data/CORDEX/CMIP6/DD/EUR-12/GERICS/ERA5/evaluation/r1i1p1f1/REMO2020/v1-r1/mon/tas/v20241120/tas_EUR-12_ERA5_evaluation_r1i1p1f1_GERICS_REMO2020_v1-r1_mon_197901-198812.nc'
    # path = "/mnt/CORDEX_CMIP6_tmp/aux_data/cordex-cmip5/CORDEX/output/EUR-11/DMI/ECMWF-ERAINT/evaluation/r1i1p1/HIRHAM5/v1/fx/orog/v20140620/orog_EUR-11_ECMWF-ERAINT_evaluation_r1i1p1_DMI-HIRHAM5_v1_fx.nc"
    checker_names = ["cf", "cc6"]
    verbose = 1
    criteria = "normal"
    output_filename = report_filename
    output_format = ["json_new", "html"]
    """
    Inputs to ComplianceChecker.run_checker

    path            Dataset location (url or file)
    checker_names   List of string names to run, should match keys of checkers dict (empty list means run all)
    verbose         Verbosity of the output (0, 1, 2)
    criteria        Determines failure (lenient, normal, strict)
    output_filename Path to the file for output
    output_format   Format of the output

    @returns                If the tests failed (based on the criteria)
    """

    return_value, errors = ComplianceChecker.run_checker(
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
    """
    Create a dictionary with the dataset id as key and the filename as value.
    """
    stem = Path(filename).stem
    path = str(Path(filename).parent)
    version = path.split("/")[-1]
    values = stem.split("_")[0 : len(id_attrs) - 1] + [version]
    return dict(zip(id_attrs, values))


def filename_to_id(filename):
    """
    Extract the dataset id from the filename.
    """
    values = list(filename_to_attrs(filename).values())
    return ".".join(values)


def collect_non_empty_msgs(results):
    """
    Collect non-empty messages from the results.
    """
    non_empty_msgs = {}
    for test_result in results:
        if test_result["msgs"]:
            non_empty_msgs[test_result["name"]] = test_result["msgs"]
    return non_empty_msgs


def get_non_empty_errors(cc_data):
    """
    Extract non-empty error messages from the compliance checker data.
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
            # medium_priority_msgs = collect_non_empty_msgs(results['medium_priorities'])
            # slow_priority_msgs = collect_non_empty_msgs(results['low_priorities'])

    return all_non_empty_msgs


def issue_exists(issue_title):
    """
    Check if an issue with the given title already exists in the repository.
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
    """
    Create a GitHub issue if it doesn't already exist.
    """
    if issue_exists(issue_title):
        print(f"Issue with title '{issue_title}' already exists. Skipping creation.")
        return

    # Payload for the issue
    payload = {
        "title": issue_title,
        "body": issue_body,
        "labels": labels or [],  # Add labels if provided
    }

    # Make the POST request to create the issue
    response = requests.post(issues_url, headers=headers, json=payload)
    if response.status_code == 201:
        print("Issue created successfully:", response.json()["html_url"])
    else:
        print("Failed to create issue:", response.status_code, response.json())


def log_issues_from_errors(errors):
    """
    Create GitHub issues for each key-value pair in the errors dictionary.
    """
    priority = "high priority"

    for dataset_id, error_details in errors.items():
        # Construct issue title
        issue_title = f"`{dataset_id}`"
        filename = error_details["file"]
        msgs = error_details[priority]
        # Construct issue body
        issue_body = f"Issues for dataset `{dataset_id}`:\n\n"
        issue_body += f"Filename: `{filename}`\n\n"
        for section, messages in msgs.items():
            issue_body += f"### {section}\n"
            issue_body += "\n".join(f"- {msg}" for msg in messages)
            issue_body += "\n\n"

        issue_body += "This issue was created automatically by the compliance checker."

        # Create the issue
        create_github_issue(issue_title, issue_body, labels=[priority])


def write_report(cc_data, corrupt):
    result = {}
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
    df.to_csv(f"{report_filename}.csv", index=False)


def main():
    os.makedirs(report_dir, exist_ok=True)
    # Collect the files from the catalog
    filenames = collect_files(
        "https://raw.githubusercontent.com/euro-cordex/joint-evaluation/refs/heads/main/catalog.csv"
    )[50:100]
    # Test if the files can be opened
    failed_files = test_open_dataset(filenames)
    cc_data = compliance_check(
        [
            f for f in filenames if f not in failed_files.filename.tolist()
        ]  # Exclude failed files
    )

    # non_empty_errors = get_non_empty_errors(cc_data)
    # for k, v in non_empty_errors.items():
    #    log.error(f"{k}: {v}")
    #    log_issues_from_errors(non_empty_errors)
    # return non_empty_errors

    write_report(cc_data, failed_files)


if __name__ == "__main__":
    main()
