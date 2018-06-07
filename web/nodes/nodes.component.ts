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

interface ZuulNode {
  name: string,
  state_time: number,
  age: string
}

@Component({
  template: require('./nodes.component.html')
})
export default class NodesComponent implements OnInit {

  nodes: ZuulNode[]

  constructor(
    private http: HttpClient, private route: ActivatedRoute,
    private zuul: ZuulService
  ) {}

  async ngOnInit() {
    await this.zuul.setTenant(this.route.snapshot.paramMap.get('tenant'))

    this.nodesFetch()
  }

  nodesFetch(): void {
    const remoteLocation = this.zuul.getSourceUrl('nodes')
    if (remoteLocation) {
      this.http.get<ZuulNode[]>(remoteLocation)
        .subscribe(nodes => {
          const now = new Date().getTime() / 1000
          for (const node of nodes) {
            const age = now - node.state_time
            const hours = Math.floor(age / 3600)
            const minutes = Math.floor((age - (hours * 3600)) / 60)
            const seconds = Math.floor(age - (hours * 3600) - (minutes * 60))
            let hoursStr = hours.toString()
            let minutesStr = minutes.toString()
            let secondsStr = seconds.toString()
            if (hours < 10) {
              hoursStr = '0' + hoursStr
            }
            if (minutes < 10) {
              minutesStr = '0' + minutesStr
            }
            if (seconds < 10) {
              secondsStr = '0' + secondsStr
            }
            node.age = hoursStr + ':' + minutesStr + ':' + secondsStr
          }
          this.nodes = nodes
        })
    }
  }
}
