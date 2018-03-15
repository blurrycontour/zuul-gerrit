// @licstart  The following is the entire license notice for the
// JavaScript code in this page.
//
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
//
// @licend  The above is the entire license notice
// for the JavaScript code in this page.

import { Component, OnInit } from '@angular/core';

import zuulStart from './zuulStart'

@Component({
  template: require('./status.html')
})
export default class StatusComponent implements OnInit {
  ngOnInit() {
    zuulStart(jQuery)
  }
}
