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

declare var ZUUL_BASE_HREF: string

function getBaseHrefFromWindowHref () {
  const path = window.location.href
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
    return getBaseHrefFromWindowHref()
  }
}
