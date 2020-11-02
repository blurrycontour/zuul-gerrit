// Copyright 2020 BMW Group
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

const builds = [
  {
    uuid: '3d7cc402eaa9464a96790075a926da87',
    job_name: 'opendev-promote-docs',
    result: 'SUCCESS',
    held: false,
    start_time: '2020-10-28T20:36:34',
    end_time: '2020-10-28T20:37:33',
    duration: 59.0,
    voting: true,
    log_url:
      'https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/',
    node_name: null,
    error_detail: null,
    final: true,
    artifacts: [
      {
        name: 'Download all logs',
        url:
          'https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/download-logs.sh',
        metadata: {
          command:
            'curl "https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/download-logs.sh" | bash',
        },
      },
      {
        name: 'Zuul Manifest',
        url:
          'https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/zuul-manifest.json',
        metadata: {
          type: 'zuul_manifest',
        },
      },
    ],
    provides: [],
    project: 'opendev/base-jobs',
    branch: 'master',
    pipeline: 'promote',
    change: 760222,
    patchset: '1',
    ref: 'refs/changes/22/760222/1',
    newrev: null,
    ref_url: 'https://review.opendev.org/760222',
    event_id: 'b89472fcfbaa4460adec0da44a1f5e9f',
    buildset: {
      uuid: '11f9f71e25df4eeaac721a1a28683e51',
    },
  },
  {
    uuid: '62b460dee0534dd4b004daa5df229489',
    job_name: 'opendev-promote-docs',
    result: 'FAILURE',
    held: false,
    start_time: '2020-09-23T04:36:27',
    end_time: '2020-09-23T04:37:03',
    duration: 36.0,
    voting: true,
    log_url:
      'https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/',
    node_name: null,
    error_detail: null,
    final: true,
    artifacts: [
      {
        name: 'Download all logs',
        url:
          'https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/download-logs.sh',
        metadata: {
          command:
            'curl "https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/download-logs.sh" | bash',
        },
      },
      {
        name: 'Zuul Manifest',
        url:
          'https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/zuul-manifest.json',
        metadata: {
          type: 'zuul_manifest',
        },
      },
    ],
    provides: [],
    project: 'opendev/base-jobs',
    branch: 'master',
    pipeline: 'promote',
    change: 753498,
    patchset: '1',
    ref: 'refs/changes/98/753498/1',
    newrev: null,
    ref_url: 'https://review.opendev.org/753498',
    event_id: '0e6442ab758b4f849a591b7eeb9fe7a7',
    buildset: {
      uuid: 'fb025dd2d1e74757a64e9e31c5a03097',
    },
  },
  {
    uuid: '516e74f78d7549e894aecd1842074ae4',
    job_name: 'opendev-tox-docs',
    result: 'SUCCESS',
    held: null,
    start_time: '2020-09-09T08:00:45',
    end_time: '2020-09-09T08:04:51',
    duration: 246.0,
    voting: true,
    log_url:
      'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/',
    node_name: null,
    error_detail: null,
    final: true,
    artifacts: [
      {
        name: 'Download all logs',
        url:
          'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/download-logs.sh',
        metadata: {
          command:
            'curl "https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/download-logs.sh" | bash',
        },
      },
      {
        name: 'Zuul Manifest',
        url:
          'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/zuul-manifest.json',
        metadata: {
          type: 'zuul_manifest',
        },
      },
      {
        name: 'Docs archive',
        url:
          'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/docs-html.tar.gz',
        metadata: {
          type: 'docs_archive',
        },
      },
      {
        name: 'Docs preview site',
        url:
          'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/docs/',
        metadata: {
          type: 'docs_site',
        },
      },
    ],
    provides: [],
    project: 'opendev/gear',
    branch: 'master',
    pipeline: 'check',
    change: 742165,
    patchset: '2',
    ref: 'refs/changes/65/742165/2',
    newrev: null,
    ref_url: 'https://review.opendev.org/742165',
    event_id: '795ec38efc2f4d5796dea5c704e321ad',
    buildset: {
      uuid: '2cd00a7b42b2496ea5a5b62684d60f98',
    },
  },
  {
    uuid: '45fcac2ca3d8415080e2e05e2e57bd89',
    job_name: 'tox-pep8',
    result: 'SUCCESS',
    held: null,
    start_time: '2020-09-09T08:05:15',
    end_time: '2020-09-09T08:08:36',
    duration: 201.0,
    voting: true,
    log_url:
      'https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/',
    node_name: null,
    error_detail: null,
    final: true,
    artifacts: [
      {
        name: 'Download all logs',
        url:
          'https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/download-logs.sh',
        metadata: {
          command:
            'curl "https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/download-logs.sh" | bash',
        },
      },
      {
        name: 'Zuul Manifest',
        url:
          'https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/zuul-manifest.json',
        metadata: {
          type: 'zuul_manifest',
        },
      },
    ],
    provides: [],
    project: 'opendev/gear',
    branch: 'master',
    pipeline: 'check',
    change: 742165,
    patchset: '2',
    ref: 'refs/changes/65/742165/2',
    newrev: null,
    ref_url: 'https://review.opendev.org/742165',
    event_id: '795ec38efc2f4d5796dea5c704e321ad',
    buildset: {
      uuid: '2cd00a7b42b2496ea5a5b62684d60f98',
    },
  },
  {
    uuid: '6a466ed2e0764fa79154aafd2affe99a',
    job_name: 'tox-py27',
    result: 'SUCCESS',
    held: null,
    start_time: '2020-09-09T08:05:11',
    end_time: '2020-09-09T08:09:15',
    duration: 244.0,
    voting: true,
    log_url:
      'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/',
    node_name: null,
    error_detail: null,
    final: true,
    artifacts: [
      {
        name: 'Download all logs',
        url:
          'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/download-logs.sh',
        metadata: {
          command:
            'curl "https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/download-logs.sh" | bash',
        },
      },
      {
        name: 'Zuul Manifest',
        url:
          'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/zuul-manifest.json',
        metadata: {
          type: 'zuul_manifest',
        },
      },
      {
        name: 'Unit Test Report',
        url:
          'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/testr_results.html',
        metadata: {
          type: 'unit_test_report',
        },
      },
    ],
    provides: [],
    project: 'opendev/gear',
    branch: 'master',
    pipeline: 'check',
    change: 742165,
    patchset: '2',
    ref: 'refs/changes/65/742165/2',
    newrev: null,
    ref_url: 'https://review.opendev.org/742165',
    event_id: '795ec38efc2f4d5796dea5c704e321ad',
    buildset: {
      uuid: '2cd00a7b42b2496ea5a5b62684d60f98',
    },
  },
  {
    "uuid": null,
    "job_name": "openstack-operator:functional",
    "result": "SKIPPED",
    "held": null,
    "start_time": null,
    "end_time": "2020-03-14T23:44:13",
    "duration": null,
    "voting": true,
    "log_url": null,
    "node_name": null,
    "error_detail": null,
    "final": true,
    "artifacts": [

    ],
    "provides": [

    ],
    "project": "vexxhost/openstack-operator",
    "branch": "master",
    "pipeline": "check",
    "change": 713104,
    "patchset": "27",
    "ref": "refs/changes/04/713104/27",
    "newrev": null,
    "ref_url": "https://review.opendev.org/713104",
    "event_id": "0deb87607e84483b9b780b1cd37d27de",
    "buildset": {
      "uuid": "e54d699992b0446098bba82af66fb4f4"
    }
  }
]

const buildsets = [
  {
    uuid: '4007623170a64988be278dc229d38cc5',
    result: 'MERGER_FAILURE',
    message:
      'Merge Failed.\n\nThis change or one of its cross-repo dependencies was unable to be automatically merged with the current state of its repository. Please rebase the change and upload a new patchset.',
    project: 'zuul/zuul-jobs',
    branch: 'master',
    pipeline: 'check',
    change: 706254,
    patchset: '3',
    ref: 'refs/changes/54/706254/3',
    newrev: null,
    ref_url: 'https://review.opendev.org/706254',
    event_id: 'c18d2e28955d4a8195e58aabdb8c95f7',
  },
  {
    uuid: '11f9f71e25df4eeaac721a1a28683e51',
    result: 'SUCCESS',
    message: 'Build succeeded (promote pipeline).',
    project: 'opendev/base-jobs',
    branch: 'master',
    pipeline: 'promote',
    change: 760222,
    patchset: '1',
    ref: 'refs/changes/22/760222/1',
    newrev: null,
    ref_url: 'https://review.opendev.org/760222',
    event_id: 'b89472fcfbaa4460adec0da44a1f5e9f',
    builds: [
      {
        uuid: '3d7cc402eaa9464a96790075a926da87',
        job_name: 'opendev-promote-docs',
        result: 'SUCCESS',
        held: false,
        start_time: '2020-10-28T20:36:34',
        end_time: '2020-10-28T20:37:33',
        duration: 59.0,
        voting: true,
        log_url:
          'https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/',
        node_name: null,
        error_detail: null,
        final: true,
        artifacts: [
          {
            name: 'Download all logs',
            url:
              'https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/download-logs.sh',
            metadata: {
              command:
                'curl "https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/download-logs.sh" | bash',
            },
          },
          {
            name: 'Zuul Manifest',
            url:
              'https://5f7d2cb60ef717b7fac3-527800346901bf238f0ec00fffcd6188.ssl.cf1.rackcdn.com/760222/1/promote/opendev-promote-docs/3d7cc40/zuul-manifest.json',
            metadata: {
              type: 'zuul_manifest',
            },
          },
        ],
        provides: [],
      },
    ],
    retry_builds: [],
  },
  {
    uuid: 'fb025dd2d1e74757a64e9e31c5a03097',
    result: 'FAILURE',
    message: 'Build failed (promote pipeline).',
    project: 'opendev/base-jobs',
    branch: 'master',
    pipeline: 'promote',
    change: 753498,
    patchset: '1',
    ref: 'refs/changes/98/753498/1',
    newrev: null,
    ref_url: 'https://review.opendev.org/753498',
    event_id: '0e6442ab758b4f849a591b7eeb9fe7a7',
    builds: [
      {
        uuid: '62b460dee0534dd4b004daa5df229489',
        job_name: 'opendev-promote-docs',
        result: 'FAILURE',
        held: false,
        start_time: '2020-09-23T04:36:27',
        end_time: '2020-09-23T04:37:03',
        duration: 36.0,
        voting: true,
        log_url:
          'https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/',
        node_name: null,
        error_detail: null,
        final: true,
        artifacts: [
          {
            name: 'Download all logs',
            url:
              'https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/download-logs.sh',
            metadata: {
              command:
                'curl "https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/download-logs.sh" | bash',
            },
          },
          {
            name: 'Zuul Manifest',
            url:
              'https://3711994d16c5584484c7-f031700b2c1819893a02a03206c89279.ssl.cf2.rackcdn.com/753498/1/promote/opendev-promote-docs/62b460d/zuul-manifest.json',
            metadata: {
              type: 'zuul_manifest',
            },
          },
        ],
        provides: [],
      },
    ],
    retry_builds: [],
  },
  {
    uuid: '2cd00a7b42b2496ea5a5b62684d60f98',
    result: 'SUCCESS',
    message: 'Build succeeded (check pipeline).',
    project: 'opendev/gear',
    branch: 'master',
    pipeline: 'check',
    change: 742165,
    patchset: '2',
    ref: 'refs/changes/65/742165/2',
    newrev: null,
    ref_url: 'https://review.opendev.org/742165',
    event_id: '795ec38efc2f4d5796dea5c704e321ad',
    builds: [
      {
        uuid: '516e74f78d7549e894aecd1842074ae4',
        job_name: 'opendev-tox-docs',
        result: 'SUCCESS',
        held: null,
        start_time: '2020-09-09T08:00:45',
        end_time: '2020-09-09T08:04:51',
        duration: 246.0,
        voting: true,
        log_url:
          'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/',
        node_name: null,
        error_detail: null,
        final: true,
        artifacts: [
          {
            name: 'Download all logs',
            url:
              'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/download-logs.sh',
            metadata: {
              command:
                'curl "https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/download-logs.sh" | bash',
            },
          },
          {
            name: 'Zuul Manifest',
            url:
              'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/zuul-manifest.json',
            metadata: {
              type: 'zuul_manifest',
            },
          },
          {
            name: 'Docs archive',
            url:
              'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/docs-html.tar.gz',
            metadata: {
              type: 'docs_archive',
            },
          },
          {
            name: 'Docs preview site',
            url:
              'https://6bada6c701a456914114-92a01e1da4e956a5b782691fa3feaba0.ssl.cf5.rackcdn.com/742165/2/check/opendev-tox-docs/516e74f/docs/',
            metadata: {
              type: 'docs_site',
            },
          },
        ],
        provides: [],
      },
      {
        uuid: '45fcac2ca3d8415080e2e05e2e57bd89',
        job_name: 'tox-pep8',
        result: 'SUCCESS',
        held: null,
        start_time: '2020-09-09T08:05:15',
        end_time: '2020-09-09T08:08:36',
        duration: 201.0,
        voting: true,
        log_url:
          'https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/',
        node_name: null,
        error_detail: null,
        final: true,
        artifacts: [
          {
            name: 'Download all logs',
            url:
              'https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/download-logs.sh',
            metadata: {
              command:
                'curl "https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/download-logs.sh" | bash',
            },
          },
          {
            name: 'Zuul Manifest',
            url:
              'https://c38e4bef900b642bfa20-f384da8b2417ba9694313b91ba24934b.ssl.cf5.rackcdn.com/742165/2/check/tox-pep8/45fcac2/zuul-manifest.json',
            metadata: {
              type: 'zuul_manifest',
            },
          },
        ],
        provides: [],
      },
      {
        uuid: '6a466ed2e0764fa79154aafd2affe99a',
        job_name: 'tox-py27',
        result: 'SUCCESS',
        held: null,
        start_time: '2020-09-09T08:05:11',
        end_time: '2020-09-09T08:09:15',
        duration: 244.0,
        voting: true,
        log_url:
          'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/',
        node_name: null,
        error_detail: null,
        final: true,
        artifacts: [
          {
            name: 'Download all logs',
            url:
              'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/download-logs.sh',
            metadata: {
              command:
                'curl "https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/download-logs.sh" | bash',
            },
          },
          {
            name: 'Zuul Manifest',
            url:
              'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/zuul-manifest.json',
            metadata: {
              type: 'zuul_manifest',
            },
          },
          {
            name: 'Unit Test Report',
            url:
              'https://0112c37c2e19f5099a42-3a487fdd6175381de80a35ca6bdfdf63.ssl.cf2.rackcdn.com/742165/2/check/tox-py27/6a466ed/testr_results.html',
            metadata: {
              type: 'unit_test_report',
            },
          },
        ],
        provides: [],
      },
      {
        uuid: 'f0bc85c163894201b7d3129ce368cd8a',
        job_name: 'tox-py35',
        result: 'SUCCESS',
        held: null,
        start_time: '2020-09-09T08:06:10',
        end_time: '2020-09-09T08:10:41',
        duration: 271.0,
        voting: true,
        log_url:
          'https://a23e1d5d8671587c8417-333846024fbe3cd00d8d8f9166c680e2.ssl.cf2.rackcdn.com/742165/2/check/tox-py35/f0bc85c/',
        node_name: null,
        error_detail: null,
        final: true,
        artifacts: [
          {
            name: 'Download all logs',
            url:
              'https://a23e1d5d8671587c8417-333846024fbe3cd00d8d8f9166c680e2.ssl.cf2.rackcdn.com/742165/2/check/tox-py35/f0bc85c/download-logs.sh',
            metadata: {
              command:
                'curl "https://a23e1d5d8671587c8417-333846024fbe3cd00d8d8f9166c680e2.ssl.cf2.rackcdn.com/742165/2/check/tox-py35/f0bc85c/download-logs.sh" | bash',
            },
          },
          {
            name: 'Zuul Manifest',
            url:
              'https://a23e1d5d8671587c8417-333846024fbe3cd00d8d8f9166c680e2.ssl.cf2.rackcdn.com/742165/2/check/tox-py35/f0bc85c/zuul-manifest.json',
            metadata: {
              type: 'zuul_manifest',
            },
          },
          {
            name: 'Unit Test Report',
            url:
              'https://a23e1d5d8671587c8417-333846024fbe3cd00d8d8f9166c680e2.ssl.cf2.rackcdn.com/742165/2/check/tox-py35/f0bc85c/testr_results.html',
            metadata: {
              type: 'unit_test_report',
            },
          },
        ],
        provides: [],
      },
      {
        uuid: 'da85bd49675640409a79ede9424f37cb',
        job_name: 'build-python-release',
        result: 'SUCCESS',
        held: null,
        start_time: '2020-09-09T08:01:29',
        end_time: '2020-09-09T08:03:35',
        duration: 126.0,
        voting: true,
        log_url:
          'https://storage.bhs.cloud.ovh.net/v1/AUTH_dcaab5e32b234d56b626f72581e3644c/zuul_opendev_logs_da8/742165/2/check/build-python-release/da85bd4/',
        node_name: null,
        error_detail: null,
        final: true,
        artifacts: [
          {
            name: 'Download all logs',
            url:
              'https://storage.bhs.cloud.ovh.net/v1/AUTH_dcaab5e32b234d56b626f72581e3644c/zuul_opendev_logs_da8/742165/2/check/build-python-release/da85bd4/download-logs.sh',
            metadata: {
              command:
                'curl "https://storage.bhs.cloud.ovh.net/v1/AUTH_dcaab5e32b234d56b626f72581e3644c/zuul_opendev_logs_da8/742165/2/check/build-python-release/da85bd4/download-logs.sh" | bash',
            },
          },
          {
            name: 'Zuul Manifest',
            url:
              'https://storage.bhs.cloud.ovh.net/v1/AUTH_dcaab5e32b234d56b626f72581e3644c/zuul_opendev_logs_da8/742165/2/check/build-python-release/da85bd4/zuul-manifest.json',
            metadata: {
              type: 'zuul_manifest',
            },
          },
          {
            name: 'Python wheel',
            url:
              'https://storage.bhs.cloud.ovh.net/v1/AUTH_dcaab5e32b234d56b626f72581e3644c/zuul_opendev_logs_da8/742165/2/check/build-python-release/da85bd4/artifacts/gear-0.15.2.dev1-py2.py3-none-any.whl',
            metadata: {
              type: 'python_wheel',
            },
          },
          {
            name: 'Python sdist',
            url:
              'https://storage.bhs.cloud.ovh.net/v1/AUTH_dcaab5e32b234d56b626f72581e3644c/zuul_opendev_logs_da8/742165/2/check/build-python-release/da85bd4/artifacts/gear-0.15.2.dev1.tar.gz',
            metadata: {
              type: 'python_sdist',
            },
          },
        ],
        provides: [],
      },
    ],
    retry_builds: [],
  },
]

module.exports = {
  builds,
  buildsets,
}
