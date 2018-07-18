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

import ZuulService from '../zuul/zuul.service'

interface Project {
  name: string
  type: string
}

@Component({
  template: require('./projects.component.html')
})
export default class ProjectsComponent implements OnInit {

  projects: Project[]

  constructor(
    private http: HttpClient, private route: ActivatedRoute,
    private zuul: ZuulService
  ) {}

  async ngOnInit() {
    await this.zuul.setTenant(this.route.snapshot.paramMap.get('tenant'))

    this.projectsFetch()
  }

  projectsFetch(): void {
    const remoteLocation = this.zuul.getSourceUrl('projects')
    if (remoteLocation) {
      this.http.get<Project[]>(remoteLocation)
        .subscribe(projects => { this.projects = projects})
    }
  }
}
