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
import { DomSanitizer } from '@angular/platform-browser'
import { Observable } from 'rxjs/Observable'
import 'rxjs/add/operator/map'

import ZuulService from '../zuul/zuul.service'
import Variant from './variant'

@Component({
  template: require('./job.component.html')
})
export default class JobComponent implements OnInit {
  variants: Variant[]
  job_name: string
  labels_color: Map<string, string>
  tenant: string

  constructor(
    private http: HttpClient, private route: ActivatedRoute,
    private _sanitizer: DomSanitizer,
    private zuul: ZuulService
  ) {}

  ngOnInit() {
    this.tenant = this.route.snapshot.paramMap.get('tenant')

    this.job_name = this.route.snapshot.queryParamMap.get('job_name') || 'base'
    this.labels_color = new Map<string, string>()
    this.variants = undefined

    this.jobFetch()
  }

  getNodeLabelStyle(node) {
    return this._sanitizer.bypassSecurityTrustStyle(
           'margin: 5px; padding-left: 5px; padding-right: 5px; ' +
           'border: 1px solid #cccccc; border-radius: 10px; background: ' +
           this.labels_color[node.label] + ';')
  }

  jobRefresh(job_name) {
    this.job_name = job_name
    this.jobFetch()
  }

  jobFetch(): void {
    this.http.get<Variant[]>(
      this.zuul.getSourceUrl('job/' + this.job_name, this.tenant))
      .subscribe(variants => this.injestResults(variants))
  }

  injestResults(variants: Variant[]): void {
    for (const variant of variants) {
      if (Object.keys(variant.variables).length === 0) {
        variant.variables = undefined
      } else {
        variant.variables = JSON.stringify(
          variant.variables, undefined, 2)
      }
      // Generate color based on node label
      for (const node of variant.nodeset.nodes) {
        let hash = 0
        for (let idx = 0; idx < node.label.length; idx++) {
          const c = node.label.charCodeAt(idx)
          hash = ((hash << 5) - hash) + c
        }
        const r = (0x800000 + (hash - 0x500000)) & 0xFF0000
        const g = (0x005000 + (hash - 0x00a000)) & 0x00FF00
        const b = (0x000080 + (hash - 0x50)) & 0x0000FF
        this.labels_color[node.label] = '#' + (r | g | b).toString(16)
      }
      if (variant.parent === 'None') {
        variant.parent = 'base'
      }
    }
    this.variants = variants
  }
}
