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

import { Component, OnInit } from '@angular/core'
import { ActivatedRoute } from '@angular/router'

import zuulStartStream from './zuulStartStream'

@Component({
  styles: [require('./stream.component.css').toString()],
  template: require('./stream.component.html')
})
export default class StreamComponent implements OnInit {

  constructor(private route: ActivatedRoute) {}

  ngOnInit() {
    zuulStartStream(this.route.snapshot.paramMap.get('tenant'), this.route)
  }
}
