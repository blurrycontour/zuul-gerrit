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

import angular from 'angular'

import './styles/zuul.css'
import './jquery.zuul'
import { getSourceUrl, getAdminSourceUrl } from './util'

angular.module('zuulTenants', []).component('zuulApp', {
  template: require('./templates/tenants.html'),
  controller: function ($scope, $http, $location) {
    $scope.tenants = undefined
    $scope.tenants_fetch = function () {
      $http.get(getSourceUrl('tenants', $location))
        .then(result => {
          this.tenants = result.data
        })
    }
    $scope.tenants_fetch()
  }
})

angular.module('zuulProjects', []).component('zuulApp', {
  template: require('./templates/projects.html'),
  controller: function ($http) {
    this.projects = undefined
    this.projects_fetch = function () {
      $http.get(getSourceUrl('projects'))
        .then(result => {
          this.projects = result.data
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
  controller: function ($http, $location, $window) {
    let queryArgs = $location.search()
    this.project_name = queryArgs['project_name']
    if (!this.project_name) {
      this.project_name = 'config-projects'
    }
    this.project = undefined
    this.project_fetch = function () {
      $http.get(getSourceUrl('projects/' + this.project_name))
        .then(result => {
          this.project = result.data
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
    this.jobs = undefined
    this.jobs_fetch = function () {
      $http.get(getSourceUrl('jobs', $location))
        .then(result => {
          this.jobs = result.data
          for (let job of this.jobs) {
            job.expanded = false
            job.details = undefined
          }
        })
    }
    this.job_fetch = function (job) {
      if (!job.details) {
        $http.get(getSourceUrl('jobs/' + job.name))
          .then(result => {
            job.details = result.data
          })
      }
      job.expanded = !job.expanded
    }
    this.jobs_fetch()
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
    this.job_fetch = function () {
      $http.get(getSourceUrl('jobs/' + this.job_name))
        .then(result => {
          this.variants = result.data
          for (let variant of this.variants) {
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
                this.labels_color[node[0]] = '#' + (r | g | b).toString(16)
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
  controller: function ($http, $location, $window, $document) {
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
      $http.get(remoteLocation)
        .then(result => {
          for (let build of result.data) {
            if (!build.node_name) {
              build.node_name = 'master'
            }
            /* Fix incorect url for post_failure job */
            if (build.log_url === build.job_name) {
              build.log_url = undefined
            }
          }
          this.builds = result.data
        })
    }
    this.reenqueue = function (build) {
        let queryString = getAdminSourceUrl('', $location)
        queryString += this.tenant
        queryString += "/" + build.project
        queryString += "/" + build.pipeline
        let payload = {}
        payload.trigger = 'gerrit'
        if (build.newrev) {
            queryString += "/enqueue_ref"
            payload.ref = build.ref
            payload.newrev = build.newrev
        } else {
            queryString += "/enqueue"
            payload.change = build.change + "," + build.patchset
        }
        console.log(queryString)
        console.log(payload)
        // Get the modal
        var modal = $document[0].getElementById('alertModal')
        // Get the button that opens the modal
        var modalText = $document[0].getElementById('alertContent')
        // Get the <span> element that closes the modal
        var span = $document[0].getElementsByClassName("close")[0]

        // When the user clicks on <span> (x), close the modal
        span.onclick = function() {
            modal.style.display = "none"
        }
        // When the user clicks anywhere outside of the modal, close it
        $window.onclick = function(event) {
            if (event.target == modal) {
                modal.style.display = "none"
            }
        }
        $http.post(queryString, payload)
            .then(function successCB(data) {
                modalText.innerHTML = "<h4>Success</h4><br />Job successfully re-enqueued."
                modal.style.display = "block"
                console.log(data)
            }, function errorCB(data) {
                // TODO: status-specific messages ?
                if (data.status == 401) {
                    modalText.innerHTML = "<h4>Unauthorized</h4><br />You are not allowed to perform this operation."
                }
                else if (data.status == 404) {
                    modalText.innerHTML = "<h4>Unsupported</h4><br />There is no admin API endpoint on this deployment."
                }
                else if (data.status > 500 ){
                    modalText.innerHTML = "<h4>Server Side Error</h4><br />Please contact the administrator. Error was: <p>" + data.data.message + "</p>"
                }
                else {
                    modalText.innerHTML = "<h4>Unknown Error</h4><br />Please contact the administrator. Error was: <p>" + data.statusText + "</p>"
                }
                modal.style.display = "block"
                console.log(data)
            });
    }
    this.builds_fetch()
  }
})
