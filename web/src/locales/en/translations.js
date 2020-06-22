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

const enTranslations = {
  app: {
    Status: 'Status',
    Projects: 'Projects',
    Jobs: 'Jobs',
    Labels: 'Labels',
    Nodes: 'Nodes',
    Builds: 'Builds',
    Buildsets: 'Buildsets',
    isFetching: 'Fetching info...',
    configErrors: 'Config Errors',
    errorCount: '%{count} errors',
    errorCount_0: '%{count} error',
    errorCount_1: '%{count} error',
    api: 'API',
    Documentation: 'Documentation',
    Tenant: 'Tenant',
  },
  tenantsPage: {
    title: 'Zuul Tenants',
    name: 'Name',
    status: 'Status',
    projects: 'Projects',
    jobs: 'Jobs',
    builds: 'Builds',
    buildsets: 'Buildsets',
    projects_count: 'Projects Count',
    queue: 'Queue',
  },
  refreshableContainer: {
    refresh: 'refresh',
  },
  statusPage: {
    title: 'Zuul Status',
    queueLengths: 'Queue lengths: ',
    events: ' events',
    events_0: ' event',
    events_1: ' event',
    management_events: ' management events',
    management_events_0: ' management event',
    management_events_1: ' management event',
    results: 'results',
    results_0: 'result',
    result_1: 'result',
    zuul_version: 'Zuul version: ',
    last_reconfigured: 'Last reconfigured: ',
    formPlaceholder: 'change or project name',
    clearFilter: 'Clear filter',
    expandByDefault: 'Expand by default',
    autoReload: 'auto reload',
  },
  streamPage: {
    title: 'Zuul Stream | %{id}',
    endOfStream: '\n--- END OF STREAM ---\n',
    search: 'search',
    useRegex: 'Use regex:',
    caseSensitive: 'Case sensitive',
    wholeWord: 'Whole word',
  },
  projectsPage: {
    title: 'Zuul Projects',
    loading: 'Loading...',
    name: 'Name',
    connection: 'Connection',
    type: 'Type',
    lastBuilds: 'Last Builds',
  },
  projectPage: {
    title: 'Zuul Project | %{projectName}'
  },
  OpenApiPage: {
    title: 'Zuul API'
  },
  nodesPage: {
    title: 'Zuul Nodes',
    id: 'id',
    labels: 'labels',
    connection: 'connection',
    server: 'server',
    provider: 'provider',
    state: 'state',
    age: 'age',
    comment: 'comment',
    state_building: 'building',
    state_testing: 'testing',
    state_ready: 'ready',
    state_in_use: 'in use',
    state_used: 'used',
    state_hold: 'on hold',
    state_deleting: 'deleting',
  },
  logFilePage: {
    title: 'Zuul Build Logfile'
  },
  labelsPage: {
    title: 'Zuul Labels',
    loading: 'Loading...',
    name: 'name',
  },
  jobsPage: {
    title: 'Zuul Jobs',
  },
  jobPage: {
    title: 'Zuul Job | %{jobName}',
  },
  configErrorsPage: {
    refresh: 'refresh',
  },
  changeStatusPage: {
    title: '%{changeId} | Zuul Status',
  },
  buildsetsPage: {
    title: 'Zuul Buildsets',
    project: 'Project',
    branch: 'Branch',
    pipeline: 'Pipeline',
    change: 'Change',
    result: 'Result',
    filterBy: 'Filter by %{filter}',
    buildset: 'Buildset',
    filterByUUID: 'Filter by Buildset UUID',
    loading: 'Loading...',
    SUCCESS: 'SUCCESS',
    FAILURE: 'FAILURE',
  },
  buildsetPage: {
    title: 'Zuul Buildset',
  },
  buildsPage: {
    title: 'Zuul Builds',
    job: 'Job',
    project: 'Project',
    branch: 'Branch',
    pipeline: 'Pipeline',
    change: 'Change',
    duration: 'Duration',
    start_time: 'Start Time',
    result: 'Result',
    filterBy: 'Filter by %{filter}',
    build: 'Build',
    filterByUUID: 'Filter by Build UUID',
    loading: 'Loading...',
    SUCCESS: 'SUCCESS',
    FAILURE: 'FAILURE',
    SKIPPED: 'SKIPPED',
    POST_FAILURE: 'FAILURE IN POST PLAYBOOK',
    NODE_FAILURE: 'NODE FAILURE',
    RETRY_LIMIT: 'RETRY LIMIT',
    TIMED_OUT: 'TIMED OUT',
    CANCELED: 'CANCELED BY ZUUL',
    ABORTED: 'CANCELED DUE TO AN UNKNOWN ERROR',
    ERROR: 'ERROR',
  },
  buildLogsPage: {
    title: 'Zuul Build',
  },
  buildConsolePage: {
    title: 'Zuul Build',
  },
  buildPage: {
    title: 'Zuul Build',
  },
  tableFiltersContainer: {
    clear: 'Clear All Filters',
  },
  errorBoundaryContainer: {
    error: 'Something went wrong.',
  },
  statusContainer: {
    change: {
      failing_reasons: {
        neededChangeFailing: 'a needed change is failing',
        mergeConflict: 'it has a merge conflict',
        invalidConfig: 'it has an invalid configuration',
        oneJobFailed: 'at least one job failed',
        didNotMerge: 'it did not merge',
        nonLive: 'is a non-live item with no items behind',
      },
      succeeding: 'Succeeding',
      inactive: 'Waiting until closer to head of queue to start jobs',
      dependentChange: 'Dependent change required for testing',
      failing: 'Failing because ',
    },
    changePanel: {
      unknown: 'unknown',
      renderJob: ' (attempt #%{count})',
      estimatedTimeRemaining: 'Estimated time remaining: ',
      remainingTime: 'Remaining Time',
      elapsedTime: 'Elapsed Time',
      success: 'success',
      failure: 'failure',
      unstable: 'unstable',
      retry_limit: 'retry limit',
      timed_out: 'timed out',
      post_failure: 'post failure',
      node_failure: 'node failure',
      paused: 'paused',
      skipped: 'skipped',
      in_progress: 'in progress',
      queued: 'queued',
      lost: 'lost',
      aborted: 'aborted',
      waiting: 'waiting',
      nonvoting: '(non-voting)'
    },
    changeQueue: {
      queue: 'Queue: ',
    },
  },
  projectContainer: {
    projectVariant: {
      mergeMode: 'Merge mode',
      templates: 'Templates',
      queue: 'Queue: ',
      pipelineJobs: '%{pipeline} jobs',
    }
  }
}

export default enTranslations
