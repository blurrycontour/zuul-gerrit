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

import { Injectable } from '@angular/core'
import { ActivatedRoute } from '@angular/router'

import { getBaseHref } from '../util'

declare var ZUUL_API_URL: string

@Injectable()
class ZuulService {
  public baseHref: string

  constructor() {
    this.baseHref = getBaseHref()
  }

  getApiUrl (): string {
    if (typeof ZUUL_API_URL !== 'undefined') {
      return ZUUL_API_URL
    } else {
      return this.baseHref
    }
  }

  getSourceUrl (filename: string, tenant?: string): string {
    let apiUrl: string = this.getApiUrl()
    if (tenant) {
      // Multi-tenant deploy. This is at t/a-tenant/x.html
      return `${apiUrl}/api/tenant/${tenant}/${filename}`
    } else {
      // Whitelabel deploy or tenants list, such as /status.html,
      // /tenants.html or /zuul/status.html or /zuul/tenants.html
      return `${apiUrl}/api/${filename}`
    }
  }

  getWebsocketUrl (filename: string, tenant?: string): string {
    return this.getSourceUrl(filename, tenant)
      .replace(/(http)(s)?\:\/\//, 'ws$2://')
  }

}

export default ZuulService
