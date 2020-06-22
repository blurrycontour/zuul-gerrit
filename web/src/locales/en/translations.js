// Copyright 2020 Red Hat, Inc
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

// This file only contains English translations when templating is needed (plurals, etc).

const enTranslations = {
  // App.jsx
  errorCount: '%{count} errors',
  errorCount_0: '%{count} error',
  errorCount_1: '%{count} error',
  statusPage: {
    events: ' events',
    events_0: ' event',
    events_1: ' event',
    management_events: ' management events',
    management_events_0: ' management event',
    management_events_1: ' management event',
    results: 'results',
    results_0: 'result',
    results_1: 'result',
  },
  projectsPage: {
    config: 'trusted execution context',
    untrusted: 'untrusted execution context',
  },
  streamPageTitle: 'Zuul Stream | %{id}',
  projectPageTitle: 'Zuul Project | %{projectName}',
  nodestate : {
    'building': 'building',
    'testing': 'testing',
    'ready': 'ready',
    'in-use': 'in use',
    'used': 'used',
    'hold': 'on hold',
    'deleting': 'deleting',
  },
  jobPageTitle: 'Zuul Job | %{jobName}',
  changeStatusPageTitle: '%{changeId} | Zuul Status',
  filterBy: 'Filter by %{filter}',
  // TODO get a full list of buildset states
  'SUCCESS': 'Success',
  'FAILURE': 'Failure',
  'MERGER_FAILURE': 'Failure to merge change',
  // TODO: get a full list of build states
  //'SUCCESS': 'SUCCESS',
  //'FAILURE': 'FAILURE',
  'SKIPPED': 'SKIPPED',
  'POST_FAILURE': 'FAILURE IN POST PLAYBOOK',
  'NODE_FAILURE': 'NODE FAILURE',
  'RETRY_LIMIT': 'RETRY LIMIT',
  'TIMED_OUT': 'TIMED OUT',
  'CANCELED': 'CANCELED BY ZUUL',
  'ABORTED': 'CANCELED DUE TO AN UNKNOWN ERROR',
  'ERROR': 'ERROR',
  jobTries: ' (attempt #%{count})',
  'retry_limit': 'retry limit',
  'timed_out': 'timed out',
  'post_failure': 'post failure',
  'node_failure': 'node failure',
  pipelineJobs: '%{pipeline} jobs',
  buildResult: 'Build result %{uuid}',
  softDependency: '%{dependency} (soft)',
  overrideBranch: ' ( override branch: %{item} )',
  overrideCheckout: ' ( override checkout: %{item} )',
  // Ansible tasks
  ansibleTasksStatus: {
    'FAILED': 'FAILED',
    'CHANGED': 'CHANGED',
    'SKIPPED': 'SKIPPED',
    'OK': 'OK',
  },
  trustedContext: 'This playbook runs in a trusted execution context, which permits executing code on the Zuul executor and allows access to all Ansible features.',
  playbookPhase: '%{phase} playbook',
  play: 'Play: %{playname}',
  buildsetResult: 'Buildset result %{uuid}',
  taskOK: 'Task OK',
}

export default enTranslations
