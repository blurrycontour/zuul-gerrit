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

const frTranslations = {
  app: {
    Status: "Statut",
    Projects: "Projets",
    Jobs: "Jobs",
    Labels: "Labels",
    Nodes: "Exécuteurs",
    Builds: "Builds",
    Buildsets: "Résultats",
    isFetching: "Chargement en cours ...",
    configErrors: "Erreurs de configuration",
    errorCount: "%{count} erreurs",
    errorCount_0: "%{count} erreur",
    errorCount_1: "%{count} erreur",
    api: "API",
    Documentation: "Documentation",
    Tenant: "Domaine",
  },
  tenantsPage: {
    name: "Nom",
    status: "Statut",
    projects: "Projets",
    jobs: "Jobs",
    builds: "Builds",
    buildsets: "Résultats",
    projects_count: "Nombre de projets",
    queue: "Queue",
  },
  refreshable: {
    refresh: "actualiser",
  },
  statusPage: {
    title: "Statut de Zuul",
    queueLengths: "Longueur des queues: ",
    events: ' événements',
    events_0: ' événement',
    events_1: ' événement',
    management_events: ' événements de management',
    management_events_0: ' événement de management',
    management_events_1: ' événement de management',
    results: " résultats",
    results_0: " résultat",
    result_1: " résultat",
    zuul_version: "Version de Zuul: ",
    last_reconfigured: "Dernière reconfiguration: ",
    formPlaceholder: "changement ou projet",
    clearFilter: "Supprimer le filtre",
    expandByDefault: "Vue détaillée par défaut",
    autoReload: "actualisation automatique",
  },
  streamPage: {
    title: 'Flux Zuul | %{id}',
    endOfStream: '\n--- FIN DU FLUX ---\n',
    search: "recherche",
    useRegex: "Utiliser regex:",
    caseSensitive: "Sensible à la casse",
    wholeWord: "Mot entier",
  },
  projectsPage: {
    title: "Projets Zuul",
    loading: "Chargement ...",
    name: "Nom",
    connection: "Connexion",
    type: "Type",
    lastBuilds: "Derniers Builds",
  },
  projectPage: {
    title: "Projet Zuul | %{projectName}"
  },
  OpenApiPage: {
    title: "API Zuul"
  }
}

export default frTranslations
