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

import StreamService from './stream.service'
import ZuulService from '../zuul/zuul.service'

function escapeLog (text) {
  const pattern = /[<>&"']/g

  return text.replace(pattern, function (match) {
    return '&#' + match.charCodeAt(0) + ';'
  })
}

@Component({
  styles: [require('./stream.component.css').toString()],
  template: require('./stream.component.html')
})
export default class StreamComponent implements OnInit {

  autoscroll = true
  logLines: string[] = []

  constructor(
    private route: ActivatedRoute,
    private zuul: ZuulService,
    private stream: StreamService) {}

  ngOnInit() {
    this.startStream()
  }

  startStream () {
    const pageUpdateInMS = 250
    let receiveBuffer = ''

  ngOnInit(): void {
    this.stream.initSocket()

    this.stream.onMessage()
      .subscribe((message: string) => this.injestMessage(message))
    this.stream.onClose()
      .subscribe((message: string) => this.injestMessage(message))
  }

  injestMessage(message: string): void {
    this.logLines.push(message)
    if (this.autoscroll) {
      window.scrollTo(0, document.body.scrollHeight)
    }
  }
}
