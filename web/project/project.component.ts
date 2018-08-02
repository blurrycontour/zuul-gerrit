// Copyright 2018 Red Hat
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

import { Component, OnInit } from '@angular/core'
import { ActivatedRoute } from '@angular/router'
import { HttpClient, HttpParams } from '@angular/common/http'
import { Observable } from 'rxjs/Observable'
import 'rxjs/add/operator/map'
import * as d3 from 'd3'

import ZuulService from '../zuul/zuul.service'
import Job from '../jobs/job'

interface Pipeline {
  name: string,
  queue_name: string,
  jobs: Job[]
}
interface Config {
  pipelines: Pipeline[]
  merge_mode: string
  default_branch: string
}

interface ProjectDetail {
  project_name: string
  canonical_name: string
  configs: Config[]
}

@Component({
  template: require('./project.component.html')
})
export default class ProjectComponent implements OnInit {

  project_name: string
  project: ProjectDetail
  graph: Object

  constructor(
    private http: HttpClient, private route: ActivatedRoute,
    private zuul: ZuulService
  ) {}

  async ngOnInit() {
    await this.zuul.setTenant(this.route.snapshot.paramMap.get('tenant'))
    this.project_name = this.route.snapshot.queryParamMap.get('project_name')
    this.graph = undefined

    this.projectFetch()
  }

  projectFetch(): void {
    const remoteLocation = this.zuul.getSourceUrl(
      'project/' + this.project_name)
    if (remoteLocation) {
      this.http.get<ProjectDetail>(remoteLocation)
        .subscribe(project => { this.project = project })
    }
  }

  toggleGraph() {
    jQuery('#projectTable').toggle()
    jQuery('#projectGraph').toggle()
    if (!this.graph) {
      this.graph = this.projectGraph(this.project)
    }
  }

  projectGraph(project) {
    const nodes = []
    const links = []
    let tips = []

    if (!this.project || !this.project.configs || !this.project.configs.length) {
      return
    }

    // Merge configs
    const config = jQuery.extend(true, {}, this.project.configs[0])
    for (let idx = 1; idx < this.project.configs.length; idx += 1) {
      this.project.configs[idx].pipelines.forEach(function (pipeline) {
        config.pipelines.forEach(function (pipeline_parent) {
          if (pipeline.name === pipeline_parent.name) {
            pipeline.jobs.forEach(function (job) {
              pipeline_parent.jobs.push(job)
            })
          }
        })
      })
    }
    const pipelines = ['check', 'gate', 'post', 'release', 'tag']

    // Create nodes and links
    pipelines.forEach(function (pipeline) {
      config.pipelines.forEach(function (project_pipeline) {
        if (project_pipeline.name !== pipeline) {
          return
        }
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
        const localJobs = []
        const interJobs = []
        project_pipeline.jobs.forEach(function (job) {
          // Todo: support job variant
          job = job[0]
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
          const jobName = pipeline + '/' + job.name
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
      })
    })

    // Render graph
    const w = d3.select('#projectGraph').attr('width')
    const h = d3.select('#projectGraph').attr('height')
    const r = 150
    const svg = d3.select('#projectGraph')

    // Fix first and last node initial position
    nodes[0].fx = 0 + 10
    nodes[0].fy = h / 2
    nodes[nodes.length - 1].fx = w - r
    nodes[nodes.length - 1].fy = h / 2

    const color = d3.scaleOrdinal(d3.schemeCategory10)
    const simulation = d3.forceSimulation()
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('link', d3.forceLink().distance(r / 2).id(function (d) {
        return d.id
      }))
      .force('charge', d3.forceManyBody().strength(-500))

    simulation.nodes(nodes)
    simulation.force('link').links(links)

    const link = svg.selectAll('.link')
      .data(links)
      .enter().append('line')
      .attr('class', 'link')

    const node = svg.selectAll('.node')
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
        .attr('cx', function (d) {
          d.x = Math.max(r, Math.min(w - r, d.x))
          return d.x
        })
        .attr('cy', function (d) {
          d.y = Math.max(r, Math.min(h - r, d.y))
          return d.y
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
    return svg
  }
}
