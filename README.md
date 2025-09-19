# EURO-CORDEX compliance check

Collecting issues related to EURO-CORDEX-CMIP6 datasets at JSC-CORDEX.

This is a dedicated repository that addresses dataset compliance issues at JSC-CORDEX. These are mainly related to the [CF Conventions](https://cfconventions.org) (CF-1.11) and the [CORDEX-CMIP6 archive specifications](https://zenodo.org/records/15047096). Please ensure that your datasets have no high-priority issues. Otherwise, they may not be suitable for evaluation analyses and could cause problems when being published to ESGF.

This repository publishes a [dashboard](https://euro-cordex.github.io/jsc-compliance-check/docs) and an equivalent [excel report](https://github.com/euro-cordex/jsc-compliance-check/raw/refs/heads/main/report/compliance-report.xlsx). The excel report contains one sheet per institution_id while the dashboard allows for more filter options.

## Running the compliance checks locally (conda)

It is recommended to run the checks yourself before uploading data to `jsc-cordex`. Create and activate a minimal environment:

```bash
conda create -n cordex-cc -c conda-forge python=3.11 compliance-checker cc-plugin-cc6
conda activate cordex-cc
```

Run CF-1.11 and CC6 checks on a NetCDF file:

```bash
compliance-checker -t cf:1.11,cc6 path/to/your_file.nc
```

## Acknowledgments

We acknowledge the use of GitHub Copilot, an AI-based code completion tool, which assisted in the web development.

## References

GitHub Copilot. GitHub, Inc. Available at: https://github.com/features/copilot
