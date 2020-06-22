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
    Status: 'Statut',
    Projects: 'Projets',
    Jobs: 'Jobs',
    Labels: 'Labels',
    Nodes: 'Exécuteurs',
    Builds: 'Builds',
    Buildsets: 'Buildsets',
    isFetching: 'Chargement en cours ...',
    configErrors: 'Erreurs de configuration',
    errorCount: '%{count} erreurs',
    errorCount_0: '%{count} erreur',
    errorCount_1: '%{count} erreur',
    api: 'API',
    Documentation: 'Documentation',
    Tenant: 'Domaine',
  },
  tenantsPage: {
    title: 'Domaines Zuul',
    name: 'Nom',
    status: 'Statut',
    projects: 'Projets',
    jobs: 'Jobs',
    builds: 'Builds',
    buildsets: 'Buildsets',
    projects_count: 'Nombre de projets',
    queue: 'Queue',
  },
  refreshableContainer: {
    refresh: 'actualiser',
  },
  statusPage: {
    title: 'Statut de Zuul',
    queueLengths: 'Longueur des queues: ',
    events: ' événements',
    events_0: ' événement',
    events_1: ' événement',
    management_events: ' événements de management',
    management_events_0: ' événement de management',
    management_events_1: ' événement de management',
    results: ' résultats',
    results_0: ' résultat',
    result_1: ' résultat',
    zuul_version: 'Version de Zuul: ',
    last_reconfigured: 'Dernière reconfiguration: ',
    formPlaceholder: 'changement ou projet',
    clearFilter: 'Supprimer le filtre',
    expandByDefault: 'Vue détaillée par défaut',
    autoReload: 'actualisation automatique',
  },
  streamPage: {
    title: 'Flux Zuul | %{id}',
    endOfStream: '\n--- FIN DU FLUX ---\n',
    search: 'recherche',
    useRegex: 'Utiliser regex:',
    caseSensitive: 'Sensible à la casse',
    wholeWord: 'Mot entier',
  },
  projectsPage: {
    title: 'Projets Zuul',
    loading: 'Chargement ...',
    name: 'Nom',
    connection: 'Connexion',
    type: 'Type',
    lastBuilds: 'Derniers Builds',
  },
  projectPage: {
    title: 'Projet Zuul | %{projectName}'
  },
  OpenApiPage: {
    title: 'API Zuul'
  },
  nodesPage: {
    title: 'Exécuteurs Zuul',
    id: 'identifiant',
    labels: 'labels',
    connection: 'connexion',
    server: 'serveur',
    provider: 'fournisseur',
    state: 'état',
    age: 'âge',
    comment: 'commentaires',
    state_building: 'en cours de création',
    state_testing: 'en cours de test',
    state_ready: 'prêt',
    state_in_use: 'en cours d\'utilisation',
    state_used: 'utilisé',
    state_hold: 'suspendu',
    state_deleting: 'en cours de suppression',
  },
  logFilePage: {
    title: 'Log de Build Zuul',
  },
  labelsPage: {
    title: 'Labels Zuul',
    loading: 'Chargement ...',
    name: 'nom',
  },
  jobsPage: {
    title: 'Jobs Zuul',
  },
  jobPage: {
    title: 'Job Zuul | %{jobName}',
  },
  configErrorsPage: {
    refresh: 'actualiser',
  },
  changeStatusPage: {
    title: '%{changeId} | Statut Zuul',
  },
  buildsetsPage: {
    title: 'Buildsets Zuul',
    project: 'Projet',
    branch: 'Branche',
    pipeline: 'Pipeline',
    change: 'Changement',
    result: 'Résultat',
    filterBy: 'Filtrer par %{filter}',
    buildset: 'Buildset',
    filterByUUID: 'Filtrer par l\'UUID du buildset',
    loading: 'Chargement ...',
    SUCCESS: 'SUCCÈS',
    FAILURE: 'ÉCHEC',
  },
  buildsetPage: {
    title: 'Zuul Buildset',
  },
  buildsPage: {
    title: 'Builds Zuul',
    job: 'Job',
    project: 'Projet',
    branch: 'Branche',
    pipeline: 'Pipeline',
    change: 'Changement',
    duration: 'Durée',
    start_time: 'Début',
    result: 'Résultat',
    filterBy: 'Filtrer par %{filter}',
    build: 'Build',
    filterByUUID: 'Filtrer par l\'UUID du build',
    loading: 'Chargement ...',
    SUCCESS: 'SUCCÈS',
    FAILURE: 'ÉCHEC',
    SKIPPED: 'IGNORÉ',
    POST_FAILURE: 'ÉCHEC EN PLAYBOOK POST',
    NODE_FAILURE: 'ÉCHEC D\'UN EXÉCUTEUR',
    RETRY_LIMIT: 'LIMITE DE TENTATIVES ATTEINTE',
    TIMED_OUT: 'EXPIRÉ',
    CANCELED: 'ANNULÉ PAR ZUUL',
    ABORTED: 'ANNULÉ POUR CAUSE D\'ERREUR INCONNUE',
    ERROR: 'ERREUR',
  },
  buildLogsPage: {
    title: 'Build Zuul',
  },
  buildConsolePage: {
    title: 'Build Zuul',
  },
  buildPage: {
    title: 'Build Zuul',
  },
  tableFiltersContainer: {
    clear: 'Réinitialiser les filtres',
  },
  errorBoundaryContainer: {
    error: 'Une erreur s\'est produite.',
  },
  statusContainer: {
    change: {
      failing_reasons: {
        neededChangeFailing: 'un changement requis a échoué',
        mergeConflict: 'en conflit d\'intégration',
        invalidConfig: 'la configuration du changement est invalide',
        oneJobFailed: 'au moins un job a échoué',
        didNotMerge: 'le changement n\'a pas pu être intégré',
        nonLive: 'le changement est inactif et sans autre changement à sa suite',
      },
      succeeding: 'En succès',
      inactive: 'En attente d\'être en tête de la queue pour commencer les jobs',
      dependentChange: 'Une dépendance est requise pour tester',
      failing: 'En échec car ',
    },
    changePanel: {
      unknown: 'inconnu',
      renderJob: ' (essai n°%{count})',
      estimatedTimeRemaining: 'Temps restant estimé: ',
      remainingTime: 'Temps restant',
      elapsedTime: 'Temps écoulé',
      success: 'succès',
      failure: 'échec',
      unstable: 'instable',
      retry_limit: 'limite atteinte',
      timed_out: 'temps expiré',
      post_failure: 'échec post',
      node_failure: 'échec exécuteur',
      paused: 'en pause',
      skipped: 'ignoré',
      in_progress: 'en cours',
      queued: 'en queue',
      lost: 'perdu',
      aborted: 'annulé',
      waiting: 'en attente',
      nonvoting: '(non votant)'
    },
    changeQueue: {
      queue: 'Queue: ',
    },
  },
  projectContainer: {
    projectVariant: {
      mergeMode: 'Mode d\'intégration du code',
      templates: 'Modèles',
      queue: 'Queue: ',
      pipelineJobs: 'Jobs en pipeline %{pipeline}',
    }
  },
  logfileContainer: {
    logFile: {
      buildResult: 'Résultat du build %{uuid}',
      all: 'Tout',
      logSeverity1: 'Debug',
      logSeverity2: 'Info',
      logSeverity3: 'Warning',
      logSeverity4: 'Error',
      logSeverity5: 'Trace',
      logSeverity6: 'Audit',
      logSeverity7: 'Critical',
    }
  },
  jobsContainer: {
    jobs: {
      jobName: 'nom du job',
      clearFilter: 'Supprimer le filtre',
      flattenList: 'Aplatir la liste',
    }
  },
  jobContainer: {
    nodeset: {
      nodeName: 'Nom de l\'exécuteur',
      labelName: 'Nom du label',
      groups: 'Groupes',
      nodes: 'Exécuteurs',
    },
    jobVariant: {
      voting: 'Votant',
      nonVoting: 'Non votant',
      abstract: 'Abstrait',
      final: 'Final',
      postReview: 'Après passage en revue',
      protected: 'Protégé',
      jobInfos: {
        description: 'description',
        context: 'contexte',
        builds: 'builds',
        status: 'statut',
        parent: 'parent',
        attempts: 'nombre d\'essais',
        timeout: 'limite de temps',
        semaphore: 'sémaphore',
        nodeset: 'Exécuteurs',
        variables: 'variables',
        override_checkout: 'outrepassement du checkout',
      },
      buildHistory: 'historique des builds',
      jobInfosList: {
        required_projects: 'projets requis',
        dependencies: 'dépendances',
        files: 'fichiers',
        irrelevant_files: 'fichiers non pertinents',
        roles: 'roles',
      },
      soft: '%{dependency} (faible)',
    },
    jobProject: {
      overrideBranch: ' ( outrepassement de branche: %{item} )',
      overrideCheckout: ' ( outrepassement du checkout: %{item} )',
    },
  },
  buildContainer: {
    summary: {
      columns: {
        job_name: 'job',
        result: 'résultat',
        buildset: 'Buildset',
        voting: 'votant',
        pipeline: 'pipeline',
        start_time: 'début',
        end_time: 'fin',
        duration: 'durée',
        project: 'projet',
        branch: 'branche',
        change: 'changement',
        patchset: 'révision du changement',
        oldrev: 'révision précédente',
        newrev: 'nouvelle révision',
        ref: 'ref',
        new_rev: 'nouvelle révision',
        ref_url: 'URL de la ref',
        log_url: 'URL des logs',
        event_id: 'ID d\'événement',
      },
      buildHistory: 'historique du build',
      true: 'oui',
      false: 'non',
      artifacts: 'Artéfacts',
      results: 'Résultats',
    },
    manifest: {
      raw: 'brut',
    },
    console: {
      results: 'résultats',
      clickForDetails: 'Cliquer pour plus de détails',
      FAILED: 'FAILED',
      CHANGED: 'CHANGED',
      SKIPPED: 'SKIPPED',
      OK: 'OK',
      permalink: 'Permalien',
      infoTrusted: 'Ce playbook est exécuté dans un contexte sûr, ce qui permet l\'exécution de code sur l`exécuteur Zuul et autorise l\'accès à toutes les fonctionnalités d\'Ansible.',
      trusted: 'sûr',
      playbookPhase: 'playbook %{phase}',
      play: 'Play: %{playname}',
    },
    buildset: {
      columns: {
        change: 'changement',
        project: 'projet',
        branch: 'branche',
        pipeline: 'pipeline',
        result: 'résultat',
        message: 'message',
        event_id: 'ID de l\'événement',
      },
      buildColumns: {
        job: 'job',
        result: 'résultat',
        voting: 'votant',
        duration: 'durée',
      },
      votingTrue: 'oui',
      votingFalse: 'non',
      buildsetResult: 'Résultats du buildset %{uuid}',
      builds: 'Builds',
    },
    buildOutput: {
      taskOK: 'Tâche OK',
      taskChanged: 'Tâche de modification',
      taskFailure: 'Tâche échouée',
    },
    build: {
      buildResult: 'Résultat du build %{uuid}',
      summary: 'Résumé',
      logs: 'Logs',
      console: 'Console',
    },
  },
}

export default frTranslations
