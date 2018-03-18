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
import { ActivatedRoute }     from '@angular/router'
import { HttpClient, HttpParams } from '@angular/common/http'
import { Observable }         from 'rxjs/Observable'
import 'rxjs/add/operator/map'

import getSourceUrl from '../util'

export class Build {

  public rowClass: string

  constructor(
    public job_name: string,
    public result: string,
    public project: string,
    public pipeline: string,
    public ref_url: string,
    public duration: number,
    public start_time: string,
    public log_url?: string,
  ) {
    if (this.result === 'SUCCESS') {
      this.rowClass = 'success'
    } else {
      this.rowClass = 'warning'
    }
  }

}

@Component({
  template: require('./builds.html')
})
export default class BuildsComponent implements OnInit {
  builds: Array<Build>
  pipeline: string
  job_name: string
  project: string
  tenant: string

  constructor(private http: HttpClient, private route: ActivatedRoute) {}

  ngOnInit() {

    this.tenant = this.route.snapshot.paramMap.get('tenant')

    this.pipeline = this.route.snapshot.queryParamMap.get('pipeline')
    this.job_name = this.route.snapshot.queryParamMap.get('job_name')
    this.project = this.route.snapshot.queryParamMap.get('project')

    this.buildsFetch()
  }

  buildsFetch(): void  {
    let params = new HttpParams()
    if (this.tenant) { params = params.set('tenant', this.tenant) }
    if (this.pipeline) { params = params.set('pipeline', this.pipeline) }
    if (this.job_name) { params = params.set('job_name', this.job_name) }
    if (this.project) { params = params.set('project', this.project) }

    let remoteLocation = getSourceUrl('builds')
    this.http.get<Array<Build>>(remoteLocation, {params: params})
      .subscribe(builds => { this.builds = builds })
  }
}
