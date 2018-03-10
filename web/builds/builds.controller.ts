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

import getSourceUrl from '../util'

interface IBuild {
  node_name: string
  log_url: string
  job_name: string
  result: string
}

export default class BuildsController {
  $http: ng.IHttpService
  builds: Array<IBuild>
  pipeline: string
  job_name: string
  project: string
  tenant: string

  constructor($http: ng.IHttpService, $location: ng.ILocationService) {
    this.$http = $http

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

    this.buildsFetch()
  }

  rowClass (build: IBuild): string {
    if (build.result === 'SUCCESS') {
      return 'success'
    } else {
      return 'warning'
    }
  }

  buildsFetch(): void  {
    let queryString = ''
    if (this.tenant) { queryString += '&tenant=' + this.tenant }
    if (this.pipeline) { queryString += '&pipeline=' + this.pipeline }
    if (this.job_name) { queryString += '&job_name=' + this.job_name }
    if (this.project) { queryString += '&project=' + this.project }
    if (queryString !== '') { queryString = '?' + queryString.substr(1) }
    let remoteLocation = getSourceUrl('builds') + queryString
    this.$http.get(remoteLocation).then(result => {
      let builds = <Array<IBuild>>result.data
      for (let build of builds) {
        if (!build.node_name) {
          build.node_name = 'master'
        }
        /* Fix incorect url for post_failure job */
        if (build.log_url === build.job_name) {
          build.log_url = undefined
        }
      }
      this.builds = builds
    })
  }
}
