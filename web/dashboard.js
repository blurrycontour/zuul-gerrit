// @licstart  The following is the entire license notice for the
// JavaScript code in this page.
//
// Copyright 2017 Red Hat
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
//
// @licend  The above is the entire license notice
// for the JavaScript code in this page.

import 'bootstrap/dist/css/bootstrap.css'
import angular from 'angular'

import './styles/zuul.css'
import './jquery.zuul'
import { getSourceUrl } from './util'

angular.module('zuulTenants', []).component('zuulApp', {
  template: require('./templates/tenants.html'),
  controller: function ($scope, $http, $location) {
    $scope.tenants = undefined
    // Capture this in a closure variable so it's in scope in the callback
    let ctrl = this
    $scope.tenants_fetch = function () {
      $http.get(getSourceUrl('tenants', $location))
        .then(function success (result) {
          ctrl.tenants = result.data
        })
    }
    $scope.tenants_fetch()
  }
})

angular.module('zuulProjects', []).component('zuulApp', {
  template: require('./templates/projects.html'),
  controller: function ($http) {
    this.projects = undefined
    // Capture this in a closure variable so it's in scope in the callback
    let ctrl = this
    this.projects_fetch = function () {
      $http.get(getSourceUrl('projects'))
        .then(function success (result) {
          ctrl.projects = result.data
        })
    }
    this.projects_fetch()
  }
})

angular.module('zuulProject', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).component('zuulApp', {
  template: require('./templates/project.html'),
  controller: function ($http, $location) {
    let queryArgs = $location.search()
    this.project_name = queryArgs['project_name']
    if (!this.project_name) {
      this.project_name = 'config-projects'
    }
    this.project = undefined
    // Capture this in a closure variable so it's in scope in the callback
    let ctrl = this
    this.project_fetch = function () {
      $http.get(getSourceUrl('projects/' + ctrl.project_name))
        .then(function success (result) {
          ctrl.project = result.data
        })
    }
    this.project_fetch()
  }
})

angular.module('zuulJobs', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).component('zuulApp', {
  template: require('./templates/jobs.html'),
  controller: function ($http, $location) {
    // Capture this in a closure variable so it's in scope in the callback
    let ctrl = this
    this.jobs = undefined
    this.jobs_fetch = function () {
      $http.get(getSourceUrl('jobs', $location))
        .then(function success (result) {
          ctrl.jobs = result.data
          for (let job of ctrl.jobs) {
            job.expanded = false
            job.details = undefined
          }
        })
    }
    this.job_fetch = function (job) {
      if (!job.details) {
        $http.get(getSourceUrl('jobs/' + job.name))
          .then(function success (result) {
            job.details = result.data
          })
      }
      job.expanded = !job.expanded
    }
    this.jobs_fetch()
  }
})

angular.module('zuulLabels', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).component('zuulApp', {
  template: require('./templates/labels.html'),
  controller: function ($http, $location) {
    // Capture this in a closure variable so it's in scope in the callback
    let ctrl = this
    this.labels = undefined
    this.labels_fetch = function () {
      $http.get(getSourceUrl('labels', $location))
        .then(function success (result) {
          ctrl.labels = result.data
        })
    }
    this.labels_fetch()
  }
})

angular.module('zuulJob', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).component('zuulApp', {
  template: require('./templates/job.html'),
  controller: function ($http, $location) {
    let queryArgs = $location.search()
    this.job_name = queryArgs['job_name']
    if (!this.job_name) {
      this.job_name = 'base'
    }
    this.labels_color = new Map()
    this.variants = undefined
    // Capture this in a closure variable so it's in scope in the callback
    let ctrl = this
    this.job_fetch = function () {
      $http.get(getSourceUrl('jobs/' + this.job_name))
        .then(function success (result) {
          ctrl.variants = result.data
          for (let variant of ctrl.variants) {
            if (Object.keys(variant.variables).length === 0) {
              variant.variables = undefined
            } else {
              variant.variables = JSON.stringify(
                variant.variables, undefined, 2)
            }
            if (variant.nodeset.length >= 0) {
              // Generate color based on node label
              for (let node of variant.nodeset) {
                let hash = 0
                for (let idx = 0; idx < node[0].length; idx++) {
                  let c = node[0].charCodeAt(idx)
                  hash = ((hash << 5) - hash) + c
                }
                let r = (0x800000 + (hash - 0x500000)) & 0xFF0000
                let g = (0x005000 + (hash - 0x00a000)) & 0x00FF00
                let b = (0x000080 + (hash - 0x50)) & 0x0000FF
                ctrl.labels_color[node[0]] = '#' + (r | g | b).toString(16)
              }
            }
            if (variant.parent === 'None') {
              variant.parent = 'base'
            }
          }
        })
    }
    this.job_fetch()
  }
})

angular.module('zuulBuilds', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).component('zuulApp', {
  template: require('./templates/builds.html'),
  controller: function ($http, $location) {
    this.rowClass = function (build) {
      if (build.result === 'SUCCESS') {
        return 'success'
      } else {
        return 'warning'
      }
    }
    let queryArgs = $location.search()
    let url = $location.url()
    if (queryArgs['source_url']) {
      this.tenant = undefined
    } else {
      let tenantStart = url.lastIndexOf(
        '/', url.lastIndexOf('/builds.html') - 1) + 1
      let tenantLength = url.lastIndexOf('/builds.html') - tenantStart
      this.tenant = url.substr(tenantStart, tenantLength)
    }
    this.builds = undefined
    if (queryArgs['pipeline']) {
      this.pipeline = queryArgs['pipeline']
    } else { this.pipeline = '' }
    if (queryArgs['job_name']) {
      this.job_name = queryArgs['job_name']
    } else { this.job_name = '' }
    if (queryArgs['project']) {
      this.project = queryArgs['project']
    } else { this.project = '' }
    this.builds_fetch = function () {
      let queryString = ''
      if (this.tenant) { queryString += '&tenant=' + this.tenant }
      if (this.pipeline) { queryString += '&pipeline=' + this.pipeline }
      if (this.job_name) { queryString += '&job_name=' + this.job_name }
      if (this.project) { queryString += '&project=' + this.project }
      if (queryString !== '') { queryString = '?' + queryString.substr(1) }
      let remoteLocation = getSourceUrl('builds', $location) + queryString
      // Capture this in a closure variable so it's in scope in the callback
      let ctrl = this
      $http.get(remoteLocation)
        .then(function success (result) {
          for (let build of result.data) {
            if (!build.node_name) {
              build.node_name = 'master'
            }
            /* Fix incorect url for post_failure job */
            if (build.log_url === build.job_name) {
              build.log_url = undefined
            }
          }
          ctrl.builds = result.data
        })
    }
    this.builds_fetch()
  }
})
