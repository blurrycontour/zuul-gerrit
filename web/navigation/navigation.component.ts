// Copyright 2018 Red Hat, Inc.
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

import { OnInit, Component } from '@angular/core'
import { Router, ResolveEnd, ActivatedRoute } from '@angular/router'
import { Observable } from 'rxjs/Observable'
import { filter } from 'rxjs/operators'

@Component({
  selector: 'navigation',
  template: require('./navigation.component.html')
})
export default class NavigationComponent implements OnInit {
  navbarRoutes = ['status', 'jobs', 'builds']
  showNavbar = true
  resolveEnd: Observable<ResolveEnd>

  constructor(private router: Router, private route: ActivatedRoute) {
    this.resolveEnd = this.router.events.pipe(
      filter(evt => evt instanceof ResolveEnd)
    ) as Observable<ResolveEnd>
  }

  ngOnInit() {
    this.resolveEnd.subscribe(evt => {
      this.showNavbar = (evt.url !== '/tenants.html')
    })
  }

  getRouteTitle(target: string): string {
    return target.charAt(0).toUpperCase() + target.slice(1)
  }

  getRouterLink(target: string): string[] {
    const htmlTarget = target + '.html'
    if (this.route.snapshot.paramMap.has('tenant')) {
      return ['/t', this.route.snapshot.paramMap.get('tenant'), htmlTarget]
    } else {
      return ['/' + htmlTarget]
    }
  }
}
