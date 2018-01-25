/* global jQuery, BuiltinConfig */
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
import * as d3 from 'd3'

import './styles/zuul.css'
import './jquery.zuul'

function getSourceUrl (filename, $location) {
  if (typeof BuiltinConfig !== 'undefined') {
    return BuiltinConfig.api_endpoint + '/' + filename
  } else {
    let queryArgs = $location.search()
    if (queryArgs['source_url']) {
      return queryArgs['source_url'] + '/' + filename
    } else {
      return filename
    }
  }
}

function jobsGraph (jobs) {
  let w = d3.select('#jobGraph').attr('width')
  let h = d3.select('#jobGraph').attr('height')
  let svg = d3.select('#jobGraph').append('g').attr(
    'transform', 'translate(40,0)')

  let stratify = d3.stratify()
      .id(function (d) {
        return d.name
      })
      .parentId(function (d) {
        if (d.name === 'base') {
          return ''
        }
        return d.parent
      })

  let tree = d3.cluster().size([h, w - 250])

  let root = stratify(jobs)

  tree(root)

  svg.selectAll('.link')
      .data(root.descendants().slice(1))
      .enter().append('path')
      .attr('class', 'link')
      .attr('d', function (d) {
        return 'M' + d.y + ',' + d.x + 'C' + (d.parent.y + 100) + ',' + d.x +
          ' ' + (d.parent.y + 100) + ',' + d.parent.x + ' ' +
          d.parent.y + ',' + d.parent.x
      })

  let node = svg.selectAll('.node')
      .data(root.descendants())
      .enter().append('g')
      .attr('transform', function (d) {
        return 'translate(' + d.y + ',' + d.x + ')'
      })

  node.append('circle').attr('r', 2)

  node.append('svg:a')
    .attr('xlink:href', function (d) {
      return 'job.html?job_name=' + d.id
    })
    .attr('target', '_self')
    .append('text')
    .attr('dy', 3)
    .attr('x', function (d) {
      return d.children ? -8 : 8
    })
    .style('text-anchor', function (d) {
      return d.children ? 'end' : 'start'
    })
    .text(function (d) {
      return d.id
    })
  return svg
}

angular.module('zuulTenants', []).controller(
    'mainController', function ($scope, $http, $location) {
      $scope.tenants = undefined
      $scope.tenants_fetch = function () {
        $http.get(getSourceUrl('tenants.json', $location))
          .then(function success (result) {
            $scope.tenants = result.data
          })
      }
      $scope.tenants_fetch()
    })

angular.module('zuulProjects', []).controller(
  'mainController', function ($scope, $http) {
    $scope.projects = undefined
    $scope.projects_fetch = function () {
      $http.get('projects.json')
        .then(function success (result) {
          $scope.projects = result.data
        })
    }
    $scope.projects_fetch()
  })

angular.module('zuulProject', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).controller('mainController', function ($scope, $http, $location) {
  let queryArgs = $location.search()
  $scope.project_name = queryArgs['project_name']
  if (!$scope.project_name) {
    $scope.project_name = 'config-projects'
  }
  $scope.project = undefined
  $scope.project_fetch = function () {
    $http.get('projects/' + $scope.project_name + '.json')
      .then(function success (result) {
        $scope.project = result.data
      })
  }
  $scope.project_fetch()
})

angular.module('zuulJobs', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).controller(
    'mainController', function ($scope, $http, $location) {
      $scope.jobs = undefined
      $scope.graph = undefined
      $scope.jobs_fetch = function () {
        $http.get(getSourceUrl('jobs.json', $location))
            .then(function success (result) {
              $scope.jobs = result.data
              $scope.jobs.forEach(function (job) {
                job.expanded = false
                job.details = undefined
              })
            })
      }
      $scope.job_fetch = function (job) {
        if (!job.details) {
          $http.get('jobs/' + job.name + '.json')
              .then(function success (result) {
                job.details = result.data
              })
        }
        job.expanded = !job.expanded
      }
      $scope.toggleGraph = function () {
        jQuery('#jobTable').toggle()
        jQuery('#jobGraph').toggle()
        if (!$scope.graph) {
          $scope.graph = jobsGraph($scope.jobs)
        }
      }
      $scope.jobs_fetch()
    })

angular.module('zuulJob', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).controller('mainController', function ($scope, $http, $location) {
  let queryArgs = $location.search()
  $scope.job_name = queryArgs['job_name']
  if (!$scope.job_name) {
    $scope.job_name = 'base'
  }
  $scope.labels_color = new Map()
  $scope.variants = undefined
  $scope.job_fetch = function () {
    $http.get('jobs/' + $scope.job_name + '.json')
      .then(function success (result) {
        $scope.variants = result.data
        $scope.variants.forEach(function (variant) {
          if (Object.keys(variant.variables).length === 0) {
            variant.variables = undefined
          } else {
            variant.variables = JSON.stringify(
              variant.variables, undefined, 2)
          }
          if (variant.nodeset.length >= 0) {
            // Generate color based on node label
            variant.nodeset.forEach(function (node) {
              let hash = 0
              for (let idx = 0; idx < node[0].length; idx++) {
                let c = node[0].charCodeAt(idx)
                hash = ((hash << 5) - hash) + c
              }
              let r = (0x800000 + (hash - 0x500000)) & 0xFF0000
              let g = (0x005000 + (hash - 0x00a000)) & 0x00FF00
              let b = (0x000080 + (hash - 0x50)) & 0x0000FF
              $scope.labels_color[node[0]] = '#' + (r | g | b).toString(16)
            })
          }
          if (variant.parent === 'None') {
            variant.parent = 'base'
          }
        })
      })
  }
  $scope.job_fetch()
})

angular.module('zuulBuilds', [], function ($locationProvider) {
  $locationProvider.html5Mode({
    enabled: true,
    requireBase: false
  })
}).controller('mainController', function ($scope, $http, $location) {
  $scope.rowClass = function (build) {
    if (build.result === 'SUCCESS') {
      return 'success'
    } else {
      return 'warning'
    }
  }
  let queryArgs = $location.search()
  let url = $location.url()
  if (queryArgs['source_url']) {
    $scope.tenant = undefined
  } else {
    let tenantStart = url.lastIndexOf(
          '/', url.lastIndexOf('/builds.html') - 1) + 1
    let tenantLength = url.lastIndexOf('/builds.html') - tenantStart
    $scope.tenant = url.substr(tenantStart, tenantLength)
  }
  $scope.builds = undefined
  if (queryArgs['pipeline']) {
    $scope.pipeline = queryArgs['pipeline']
  } else { $scope.pipeline = '' }
  if (queryArgs['job_name']) {
    $scope.job_name = queryArgs['job_name']
  } else { $scope.job_name = '' }
  if (queryArgs['project']) {
    $scope.project = queryArgs['project']
  } else { $scope.project = '' }
  $scope.builds_fetch = function () {
    let queryString = ''
    if ($scope.tenant) { queryString += '&tenant=' + $scope.tenant }
    if ($scope.pipeline) { queryString += '&pipeline=' + $scope.pipeline }
    if ($scope.job_name) { queryString += '&job_name=' + $scope.job_name }
    if ($scope.project) { queryString += '&project=' + $scope.project }
    if (queryString !== '') { queryString = '?' + queryString.substr(1) }
    $http.get(getSourceUrl('builds.json', $location) + queryString)
            .then(function success (result) {
              for (let buildPos = 0;
                     buildPos < result.data.length;
                     buildPos += 1) {
                let build = result.data[buildPos]
                if (build.node_name == null) {
                  build.node_name = 'master'
                }
                /* Fix incorect url for post_failure job */
                if (build.log_url === build.job_name) {
                  build.log_url = undefined
                }
              }
              $scope.builds = result.data
            })
  }
  $scope.builds_fetch()
})
