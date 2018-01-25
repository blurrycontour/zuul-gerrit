/* global jQuery */
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
import { getSourceUrl } from './util'

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
      if (pipeline === 'check') {
        // Inject patchset-created event
        nodes.push({'id': 'patchset-created', 'group': 'event'})
        links.push({'source': 'patchset-created', 'target': pipeline})
      }
      if (pipeline === 'release') {
        // Inject ref-updated event
        nodes.push({'id': 'ref-updated', 'group': 'event'})
        tips.forEach(function (tip) {
          links.push({'source': tip, 'target': 'ref-updated'})
        })
        tips = ['ref-updated']
      }
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
        let jobName = pipeline + '/' + job.name
        nodes.push({'id': jobName, 'group': pipeline})
        job.dependencies.forEach(function (parent) {
          let parentName
          if (parent === pipeline) {
            parentName = pipeline
          } else {
            parentName = pipeline + '/' + parent
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
      if (pipeline === 'gate') {
        // Inject change-merged event
        nodes.push({'id': 'change-merged', 'group': 'event'})
        tips.forEach(function (tip) {
          links.push({'source': tip, 'target': 'change-merged'})
        })
        tips = ['change-merged']
      }
    }
  })

  // Render graph
  let w = d3.select('#projectGraph').attr('width')
  let h = d3.select('#projectGraph').attr('height')
  let r = 150
  let svg = d3.select('#projectGraph')

  // Fix first and last node initial position
  nodes[0].fx = 0 + 10
  nodes[0].fy = h / 2
  nodes[nodes.length - 1].fx = w - r
  nodes[nodes.length - 1].fy = h / 2

  let color = d3.scaleOrdinal(d3.schemeCategory20)
  let simulation = d3.forceSimulation()
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('link', d3.forceLink().distance(r / 2).id(function (d) {
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
    node
      .attr('cx', function(d) {
          return d.x = Math.max(r, Math.min(w - r, d.x))
      })
      .attr('cy', function(d) {
          return d.y = Math.max(r, Math.min(h - r, d.y))
      })
     .attr('transform', function (d) {
        return 'translate(' + d.x + ',' + d.y + ')'
     })

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
    this.graph = undefined
    // Capture this in a closure variable so it's in scope in the callback
    let ctrl = this
    this.project_fetch = function () {
      $http.get(getSourceUrl('projects/' + ctrl.project_name))
        .then(function success (result) {
          ctrl.project = result.data
        })
    }
    this.toggleGraph = function () {
      jQuery('#projectTable').toggle()
      jQuery('#projectGraph').toggle()
      if (!ctrl.graph) {
        ctrl.graph = projectGraph(ctrl.project)
      }
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
    this.graph = undefined
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
    this.toggleGraph = function () {
      jQuery('#jobTable').toggle()
      jQuery('#jobGraph').toggle()
      if (!ctrl.graph) {
        ctrl.graph = jobsGraph(ctrl.jobs)
      }
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
