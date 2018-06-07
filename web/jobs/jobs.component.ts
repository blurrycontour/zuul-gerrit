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

import { Component, OnInit } from '@angular/core'
import { ActivatedRoute } from '@angular/router'
import { HttpClient, HttpParams } from '@angular/common/http'
import { Observable } from 'rxjs/Observable'
import 'rxjs/add/operator/map'
import * as d3 from 'd3'

import ZuulService from '../zuul/zuul.service'
import JobDetails from './details'
import Job from './job'

@Component({
  template: require('./jobs.component.html')
})
export default class JobsComponent implements OnInit {

  jobs: Job[]
  tenant?: string
  graph: Object

  constructor(
    private http: HttpClient, private route: ActivatedRoute,
    private zuul: ZuulService
  ) {}

  ngOnInit() {
    this.tenant = this.route.snapshot.paramMap.get('tenant')
    this.graph = undefined

    this.jobsFetch()
  }

  jobsFetch(): void {
    console.log('blert')
    this.http.get<Job[]>(this.zuul.getSourceUrl('jobs', this.tenant))
      .subscribe(jobs => this.injestJobs(jobs))
  }

  injestJobs(jobs: Job[]): void {
    for (const job of jobs) {
      job.expanded = false
    }
    this.jobs = jobs
  }

  jobToggleExpanded(job: Job) {
    if (!job.details) {
      this.http.get<JobDetails>(
        this.zuul.getSourceUrl('job/' + job.name, this.tenant))
        .subscribe(details => {job.details = details})
    }
    job.expanded = !job.expanded
  }

  toggleGraph() {
    jQuery('#jobTable').toggle()
    jQuery('#jobGraph').toggle()
    if (!this.graph) {
      this.graph = this.jobsGraph(this.jobs)
    }
  }

  jobsGraph(jobs) {
    const w = d3.select('#jobGraph').attr('width')
    const h = d3.select('#jobGraph').attr('height')
    const svg = d3.select('#jobGraph').append('g').attr(
      'transform', 'translate(40,0)')

    const stratify = d3.stratify()
      .id(function (d) {
        return d.name
      })
      .parentId(function (d) {
        if (d.name === 'base') {
          return ''
        }
        return d.parent
      })

    const tree = d3.cluster().size([h, w - 250])

    const root = stratify(jobs)

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

    const node = svg.selectAll('.node')
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
}
