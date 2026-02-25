@Library('utils@orfs-v2.3.5') _

node('hnode35') {

  properties([
    buildDiscarder(logRotator(daysToKeepStr: '20', numToKeepStr: '30')),
    parameters([
      string(name: 'ORFS_RESEARCH_URL',
             defaultValue: 'https://github.com/ieee-ceda-datc/ORFS-Research.git',
             description: 'ORFS-Research repo URL'),
      string(name: 'ORFS_BRANCH',
             defaultValue: 'maple/pin3Dflow',
             description: 'ORFS-Research branch for Pin3D CI (default: maple/pin3Dflow)'),
      string(name: 'OPENROAD_RESEARCH_URL',
             defaultValue: 'https://github.com/ieee-ceda-datc/OpenROAD-Research.git',
             description: 'OpenROAD-Research repo URL'),
      string(name: 'OPENROAD_RESEARCH_BRANCH',
             defaultValue: 'arxiv',
             description: 'OpenROAD-Research branch (default: arxiv)'),

      string(name: 'PIN3D_DIR',
             defaultValue: 'flow-Pin3D',
             description: 'Pin3D working directory'),
      string(name: 'PIN3D_CMD',
             defaultValue: 'python3 run_experiments.py --run-CI',
             description: 'Command to run in flow-Pin3D'),

      string(name: 'METRICS_SUMMARY',
             defaultValue: 'ci_metrics_summary.csv',
             description: 'Metrics summary csv (relative to flow-Pin3D)'),
      string(name: 'METRICS_GOLDEN',
             defaultValue: 'test/ci_metrics_golden.csv',
             description: 'Golden csv (relative to flow-Pin3D)'),
      booleanParam(name: 'FAIL_ON_REGRESSION',
                   defaultValue: true,
                   description: 'Fail build when metrics regression detected')
    ])
  ])

  try {
    stage('Clean Workspace') {
      deleteDir()
    }

    stage('Checkout ORFS-Research + submodules') {
      checkout([
        $class: 'GitSCM',
        branches: [[name: "*/${params.ORFS_BRANCH}"]],
        doGenerateSubmoduleConfigurations: false,
        userRemoteConfigs: [[url: params.ORFS_RESEARCH_URL]],
        extensions: [
          [$class: 'CloneOption', noTags: false, timeout: 30],
          [$class: 'SubmoduleOption', recursiveSubmodules: true, parentCredentials: true, timeout: 60]
        ]
      ])

      def msg = sh(script: "git log -1 --pretty=%B", returnStdout: true).trim()
      if (msg ==~ /(?is).*\[(ci skip|skip ci)\].*/) {
        currentBuild.result = 'SKIPPED'
        return
      }

      sh """#!/usr/bin/env bash
        set -euo pipefail
        echo "[ORFS-Research] branch=${params.ORFS_BRANCH}"
        echo "[ORFS-Research] HEAD=$(git rev-parse --short HEAD)"
        git submodule status --recursive || true
      """
    }

    stage('Checkout OpenROAD-Research (arxiv) -> tools/OpenROAD') {
      sh '''#!/usr/bin/env bash
        set -euo pipefail
        rm -rf tools/OpenROAD
      '''

      checkout([
        $class: 'GitSCM',
        branches: [[name: "*/${params.OPENROAD_RESEARCH_BRANCH}"]],
        doGenerateSubmoduleConfigurations: false,
        userRemoteConfigs: [[url: params.OPENROAD_RESEARCH_URL]],
        extensions: [
          [$class: 'RelativeTargetDirectory', relativeTargetDir: 'tools/OpenROAD'],
          [$class: 'CloneOption', noTags: false, timeout: 30],
          [$class: 'SubmoduleOption', recursiveSubmodules: true, parentCredentials: true, timeout: 60]
        ]
      ])

      sh '''#!/usr/bin/env bash
        set -euo pipefail
        echo "[OpenROAD-Research] HEAD=$(cd tools/OpenROAD && git rev-parse --short HEAD)"
      '''
    }

    stage('Run Pin3D CI') {
      dir(params.PIN3D_DIR) {
        sh """#!/usr/bin/env bash
          set -euo pipefail
          echo "[Pin3D] PWD=\$PWD"
          echo "[Pin3D] CMD: ${params.PIN3D_CMD}"
          ${params.PIN3D_CMD}
        """
      }
    }

    stage('Metrics Board') {
      def csvPath = "${params.PIN3D_DIR}/${params.METRICS_SUMMARY}"
      if (!fileExists(csvPath)) {
        error "Metrics summary not found: ${csvPath}"
      }

      echo "======= Pin3D CI Metrics Summary ======="
      sh """#!/usr/bin/env bash
        set -euo pipefail
        (command -v column >/dev/null 2>&1 && column -t -s, "${csvPath}") || cat "${csvPath}"
      """
    }

    stage('Compare Metrics (optional)') {
      def flowDir = params.PIN3D_DIR
      def summary = params.METRICS_SUMMARY
      def golden  = params.METRICS_GOLDEN

      if (!fileExists("${flowDir}/${golden}")) {
        echo "[Compare] Golden not found: ${flowDir}/${golden}. Skip comparison."
        return
      }
      if (!fileExists("${flowDir}/test/metrics_comparison.py")) {
        error "Compare script not found: ${flowDir}/test/metrics_comparison.py"
      }

      def rc = sh(
        script: """#!/usr/bin/env bash
          set -euo pipefail
          cd "${flowDir}"
          python3 test/metrics_comparison.py \\
            --summary "${summary}" \\
            --golden "${golden}" \\
            --keys "tech,case" \\
            2>&1 | tee ci_metrics_compare.log
        """,
        returnStatus: true
      )

      if (rc != 0) {
        if (params.FAIL_ON_REGRESSION) {
          error "Metrics comparison failed (exit=${rc}). See ${flowDir}/ci_metrics_compare.log"
        } else {
          currentBuild.result = 'UNSTABLE'
          echo "Metrics comparison failed but marked UNSTABLE (FAIL_ON_REGRESSION=false)."
        }
      } else {
        echo "Metrics comparison passed."
      }
    }

  } finally {
    archiveArtifacts artifacts: """
      ${params.PIN3D_DIR}/run_logs/**/*.log,
      ${params.PIN3D_DIR}/reports/**/*.rpt,
      ${params.PIN3D_DIR}/${params.METRICS_SUMMARY},
      ${params.PIN3D_DIR}/ci_metrics_compare.log,
      ${params.PIN3D_DIR}/ci_metrics_compare_report.csv
    """, allowEmptyArchive: true
  }
}
