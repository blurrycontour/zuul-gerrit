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

import { Component, OnInit } from '@angular/core'
import { HttpClient } from '@angular/common/http'

import getSourceUrl from '../util'

export class JobDetails {
  source_context: string
}

export class Job {
  expanded: boolean
  details: JobDetails
  name: string

  constructor() {
    this.expanded = false
  }
}

@Component({
  template: require('./jobs.html')
})
export default class JobsComponent implements OnInit {

  jobs: Array<Job>

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.jobsFetch()
  }

  jobsFetch(): void {
    console.log("blert")
    this.http.get<Array<Job>>(getSourceUrl('jobs')).subscribe(
      jobs => this.injestJobs(jobs))
  }

  injestJobs(jobs: Array<Job>): void {
    for (let job of jobs) {
      job.expanded = false
    }
    this.jobs = jobs
  }

  jobToggleExpanded(job: Job) {
    if (!job.details) {
      this.http.get<JobDetails>(getSourceUrl('jobs/' + job.name))
        .subscribe(details => {job.details = details})
    }
    job.expanded = !job.expanded
  }
}
