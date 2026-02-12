# Pin3D CI for ORFS-Research (maple/pin3Dflow)

This CI runs Pin3D experiments from:
- ORFS-Research branch: maple/pin3Dflow
- OpenROAD-Research branch: arxiv (checked out into tools/OpenROAD)

Main command (executed in flow-Pin3D/):
- python3 run_experiment.py --run-CI

Outputs:
- flow-Pin3D/ci_metrics_summary.csv
- flow-Pin3D/run_logs/**/*
- flow-Pin3D/reports/**/*
- flow-Pin3D/ci_metrics_compare.log (if golden exists)
- flow-Pin3D/ci_metrics_compare_report.csv (if comparison script writes it)

Jenkins entrypoints:
- PR/manual:   jenkins/public_tests_all.Jenkinsfile
- Nightly:     jenkins/public_nightly.Jenkinsfile