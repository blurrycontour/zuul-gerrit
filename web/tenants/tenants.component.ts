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

class Tenant {
  name: string
  projects: number
}

@Component({
  template: require('./tenants.html')
})
export default class TenantsComponent implements OnInit {

  tenants: Array<Tenant>

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.tenantsFetch()
  }

  tenantsFetch(): void {
    this.http.get<Array<Tenant>>(getSourceUrl('tenants'))
      .subscribe(tenants => { this.tenants = tenants })
  }
}
