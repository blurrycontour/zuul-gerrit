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

function projectGraph (project) {
  let nodes = []
  let links = []
  let tips = []

  let pipelines = ['check', 'gate', 'post', 'release', 'tag']

  // Create nodes and links
  pipelines.forEach(function (pipeline) {
    if (project.pipelines[pipeline]) {
      // Add pipeline and link it to previous last jobs (tips)
      nodes.push({'id': pipeline, 'group': 'pipeline'})
      tips.forEach(function (tip) {
        links.push({'source': tip, 'target': pipeline})
      })
      tips = [pipeline]
      let localJobs = []
      let interJobs = []
      project.pipelines[pipeline].jobs.forEach(function (job) {
        if (job.dependencies.length === 0) {
          job.dependencies = tips.slice(0)
        } else {
          job.dependencies.forEach(function (interJob) {
            interJobs.push(interJob)
          })
        }
        localJobs.push(job)
      })
      // Find new tip and push jobs' links
      tips.length = 0
      localJobs.forEach(function (job) {
        let jobName = pipeline + '-' + job.name
        nodes.push({'id': jobName, 'group': pipeline})
        job.dependencies.forEach(function (parent) {
          let parentName
          if (parent === pipeline) {
            parentName = pipeline
          } else {
            parentName = pipeline + '-' + parent
          }
          links.push({'source': parentName, 'target': jobName})
        })
        let found = false
        let interPos
        for (interPos = 0;
             interPos < interJobs.length;
             interPos += 1) {
          if (job.name === interJobs[interPos]) {
            found = true
            break
          }
        }
        if (found === false) {
          tips.push(jobName)
        }
      })
    }
  })

  // Render graph
  let w = d3.select('#projectGraph').attr('width')
  let h = d3.select('#projectGraph').attr('height')
  let svg = d3.select('#projectGraph')

  let color = d3.scaleOrdinal(d3.schemeCategory20)
  let simulation = d3.forceSimulation()
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('link', d3.forceLink().distance(120).id(function (d) {
        return d.id
      }))
      .force('charge', d3.forceManyBody().strength(-500))

  simulation.nodes(nodes)
  simulation.force('link').links(links)

  let link = svg.selectAll('.link')
      .data(links)
      .enter().append('line')
      .attr('class', 'link')

  let node = svg.selectAll('.node')
      .data(nodes)
      .enter().append('g')
      .attr('class', 'node')
      .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended))

  node.append('circle')
    .attr('r', 5)
    .attr('fill', function (d) {
      return color(d.group)
    })

  node.append('text')
    .attr('dx', 12)
    .attr('dy', '.35em')
    .text(function (d) {
      return d.id
    })

  simulation.on('tick', function () {
    link
      .attr('x1', function (d) {
        return d.source.x
      })
      .attr('y1', function (d) {
        return d.source.y
      })
      .attr('x2', function (d) {
        return d.target.x
      })
      .attr('y2', function (d) {
        return d.target.y
      })

    node.attr('transform', function (d) {
      return 'translate(' + d.x + ',' + d.y + ')'
    })
  })
  function dragstarted (d) {
    if (!d3.event.active) {
      simulation.alphaTarget(0.3).restart()
    }
    d.fx = d.x
    d.fy = d.y
  }

  function dragged (d) {
    d.fx = d3.event.x
    d.fy = d3.event.y
  }

  function dragended (d) {
    if (!d3.event.active) {
      simulation.alphaTarget(0)
    }
    d.fx = null
    d.fy = null
  }
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
  $scope.graph = undefined
  $scope.project_fetch = function () {
    $http.get('projects/' + $scope.project_name + '.json')
      .then(function success (result) {
        $scope.project = result.data
      })
  }
  $scope.toggleGraph = function () {
    jQuery('#projectTable').toggle()
    jQuery('#projectGraph').toggle()
    if (!$scope.graph) {
      $scope.graph = projectGraph($scope.project)
    }
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
