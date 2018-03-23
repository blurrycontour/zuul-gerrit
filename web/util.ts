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

// TODO(mordred) This should be encapsulated in an Angular Service singleton
// that fetches the other things from the info endpoint.

import * as url from 'url'

declare var ZUUL_API_URL: string
declare var ZUUL_BASE_HREF: string

function getSourceUrl (filename: string, tenant?: string): string {
  if (typeof ZUUL_API_URL !== 'undefined') {
    return `${ZUUL_API_URL}/api/${filename}`
  } else {
    const baseHref = getBaseHrefFromPath(window.location.pathname)
    if (tenant) {
      // Multi-tenant deploy. This is at t/a-tenant/x.html
      return `${baseHref}api/tenant/${tenant}/${filename}`
    } else {
      // Whitelabel deploy or tenants list, such as /status.html, /tenants.html
      // or /zuul/status.html or /zuul/tenants.html
      return `${baseHref}api/${filename}`
    }
  }
}
export default getSourceUrl

export function getWebsocketUrl (filename: string, tenant?: string): string {
  let apiBase: string
  if (typeof ZUUL_API_URL !== 'undefined') {
    apiBase = ZUUL_API_URL
  } else {
    apiBase = window.location.href
  }

  return url
    .resolve(apiBase, getSourceUrl(filename, tenant))
    .replace(/(http)(s)?\:\/\//, 'ws$2://')
}

function getBaseHrefFromPath (path: string) {
  if (path.includes('/t/')) {
    return path.slice(0, path.lastIndexOf('/t/') + 1)
  } else {
    return path.split('/').slice(0, -1).join('/') + '/'
  }
}

export function getBaseHref (): string {
  if (typeof ZUUL_BASE_HREF !== 'undefined') {
    return ZUUL_BASE_HREF
  } else {
    return getBaseHrefFromPath(window.location.pathname)
  }
}
