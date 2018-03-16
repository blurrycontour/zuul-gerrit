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
import { HttpClient } from '@angular/common/http'

import getSourceUrl from '../util'

class Variant {
  variables: Object
  nodeset: [string, string]
  parent: string
}

@Component({
  template: require('./job.html')
})
export default class JobController implements OnInit {

  job_name: string
  job_url: string
  labels_color: Map<string, string>
  variants: Array<Variant>

  constructor(private http: HttpClient, private route: ActivatedRoute) {}

  ngOnInit() {
    this.job_name = this.route.snapshot.queryParamMap.get('job_name') || 'base'
    this.job_url = getSourceUrl('jobs/' + this.job_name)
    this.labels_color = new Map<string, string>()
    this.variants = undefined
    this.jobFetch()
  }

  jobFetch(): void {
    this.http.get<Array<Variant>>(this.job_url)
      .subscribe(variants => this.injestResults(variants))
  }

  injestResults(variants: Array<Variant>): void {
    for (let variant of variants) {
      if (Object.keys(variant.variables).length === 0) {
        variant.variables = undefined
      } else {
        variant.variables = JSON.stringify(
          variant.variables, undefined, 2)
      }
      if (variant.nodeset.length >= 0) {
        // Generate color based on node label
        for (let node of variant.nodeset) {
          let hash = 0
          for (let idx = 0; idx < node[0].length; idx++) {
            let c = node[0].charCodeAt(idx)
            hash = ((hash << 5) - hash) + c
          }
          let r = (0x800000 + (hash - 0x500000)) & 0xFF0000
          let g = (0x005000 + (hash - 0x00a000)) & 0x00FF00
          let b = (0x000080 + (hash - 0x50)) & 0x0000FF
          this.labels_color[node[0]] = '#' + (r | g | b).toString(16)
        }
      }
      if (variant.parent === 'None') {
        variant.parent = 'base'
      }
    }
    this.variants = variants
  }
}
