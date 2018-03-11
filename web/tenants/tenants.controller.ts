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

interface ITenant {
  name: string
  projects: number
}

export default class TenantsController {

  $http: ng.IHttpService
  tenants: Array<ITenant>

  constructor($http: ng.IHttpService) {
    this.$http = $http
    this.tenantsFetch()
  }

  tenantsFetch(): void {
    this.$http.get(getSourceUrl('tenants'))
        .then(result => {
          this.tenants = <Array<ITenant>>result.data
        })
  }
}
