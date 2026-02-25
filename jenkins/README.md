# Pin3D CI for ORFS-Research

Pin3D CI defaults:
- ORFS-Research branch: `maple/pin3Dflow`
- OpenROAD-Research branch: `arxiv` (checked out into `tools/OpenROAD`)

Main command (executed in `flow-Pin3D/`):
- `python3 run_experiments.py --run-CI`

Jenkins entrypoints:
- PR/manual: `jenkins/public_tests_all.Jenkinsfile`
- Nightly: `jenkins/public_nightly.Jenkinsfile`

## CI stages

Both Jenkinsfiles follow this sequence:
1. Checkout ORFS-Research + submodules
2. Checkout OpenROAD-Research (`arxiv`) into `tools/OpenROAD`
3. Run Pin3D CI command in `flow-Pin3D`
4. Print metrics board (`ci_metrics_summary.csv`)
5. Compare against golden (`test/ci_metrics_golden.csv`) when present
6. Archive logs/reports/metrics artifacts

## Local CI testing

Use the local wrapper to emulate Jenkins logic:

```bash
bash jenkins/run_local_pin3d_ci.sh
```

This script:
- validates required tools (`git`, `python3`)
- runs the Pin3D CI command
- checks metrics summary exists
- runs `test/metrics_comparison.py` if golden exists

### Common options (environment variables)

Defaults are aligned with Jenkins:

```bash
ORFS_EXPECTED_BRANCH=maple/pin3Dflow
OPENROAD_RESEARCH_URL=https://github.com/ieee-ceda-datc/OpenROAD-Research.git
OPENROAD_RESEARCH_BRANCH=arxiv
PIN3D_DIR=flow-Pin3D
PIN3D_CMD="python3 run_experiments.py --run-CI"
METRICS_SUMMARY=ci_metrics_summary.csv
METRICS_GOLDEN=test/ci_metrics_golden.csv
FAIL_ON_REGRESSION=1
CHECKOUT_OPENROAD=0
CLEAN_OPENROAD_DIR=1
```

Examples:

```bash
# 1) Basic local run (use current tools/OpenROAD content)
bash jenkins/run_local_pin3d_ci.sh

# 2) Force fresh OpenROAD-Research checkout from arxiv branch
CHECKOUT_OPENROAD=1 bash jenkins/run_local_pin3d_ci.sh

# 3) Do not fail build when metrics regression is detected
FAIL_ON_REGRESSION=0 bash jenkins/run_local_pin3d_ci.sh
```

## CI outputs

- `flow-Pin3D/ci_metrics_summary.csv`
- `flow-Pin3D/run_logs/**/*.log`
- `flow-Pin3D/reports/**/*.rpt`
- `flow-Pin3D/ci_metrics_compare.log` (if comparison runs)
- `flow-Pin3D/ci_metrics_compare_report.csv` (if comparison script writes it)
