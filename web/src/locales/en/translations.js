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
    Status: "Status",
    Projects: "Projects",
    Jobs: "Jobs",
    Labels: "Labels",
    Nodes: "Nodes",
    Builds: "Builds",
    Buildsets: "Buildsets",
    isFetching: "Fetching info...",
    configErrors: "Config Errors",
    errorCount: "%{count} errors",
    errorCount_0: "%{count} error",
    errorCount_1: "%{count} error",
    api: "API",
    Documentation: "Documentation",
    Tenant: "Tenant",
  },
  tenantsPage: {
    name: "Name",
    status: "Status",
    projects: "Projects",
    jobs: "Jobs",
    builds: "Builds",
    buildsets: "Buildsets",
    projects_count: "Projects Count",
    queue: "Queue",
  },
  refreshable: {
    refresh: "refresh",
  },
  statusPage: {
    title: "Zuul Status",
    queueLengths: "Queue lengths: ",
    events: ' events',
    events_0: ' event',
    events_1: ' event',
    management_events: ' management events',
    management_events_0: ' management event',
    management_events_1: ' management event',
    results: "results",
    results_0: "result",
    result_1: "result",
    zuul_version: "Zuul version: ",
    last_reconfigured: "Last reconfigured: ",
    formPlaceholder: "change or project name",
    clearFilter: "Clear filter",
    expandByDefault: "Expand by default",
    autoReload: "auto reload",
  },
  streamPage: {
    title: 'Zuul Stream | %{id}',
    endOfStream: '\n--- END OF STREAM ---\n',
    search: "search",
    useRegex: "Use regex:",
    caseSensitive: "Case sensitive",
    wholeWord: "Whole word",
  },
  projectsPage: {
    title: "Zuul Projects",
    loading: "Loading...",
    name: "Name",
    connection: "Connection",
    type: "Type",
    lastBuilds: "Last Builds",
  },
  projectPage: {
    title: "Zuul Project | %{projectName}"
  },
  OpenApiPage: {
    title: "Zuul API"
  }
}

export default enTranslations
