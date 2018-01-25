// Copyright 2018 Red Hat, Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this filcense at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

import { OnInit, Component } from '@angular/core'
import { Router, ResolveEnd } from '@angular/router'
import { Observable } from 'rxjs/Observable'
import { filter } from 'rxjs/operators'

import ZuulService from '../zuul/zuul.service'

@Component({
  selector: 'navigation',
  template: require('./navigation.component.html')
})
export default class NavigationComponent implements OnInit {
  dashboardLink: string

  constructor(private router: Router, private zuul: ZuulService) {}

  async ngOnInit() {
    this.dashboardLink = '/t/tenants.html'
  }
}
