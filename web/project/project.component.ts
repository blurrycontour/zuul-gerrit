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

import ZuulService from '../zuul/zuul.service'
import Job from '../jobs/job'

interface Pipeline {
  name: string,
  queue_name: string,
  jobs: Job[]
}

interface ProjectDetail {
  project_name: string
  canonical_name: string
  default_branch: string
  merge_mode: string
  pipelines: Pipeline[]
}

@Component({
  template: require('./project.component.html')
})
export default class ProjectComponent implements OnInit {

  project_name: string
  project: ProjectDetail
  tenant?: string

  constructor(
    private http: HttpClient, private route: ActivatedRoute,
    private zuul: ZuulService
  ) {}

  ngOnInit() {
    this.tenant = this.route.snapshot.paramMap.get('tenant')
    this.project_name = this.route.snapshot.queryParamMap.get('project_name')

    this.projectFetch()
  }

  projectFetch(): void {
    this.http.get<ProjectDetail>(
      this.zuul.getSourceUrl('project/' + this.project_name, this.tenant))
      .subscribe(project => { this.project = project })
  }
}
