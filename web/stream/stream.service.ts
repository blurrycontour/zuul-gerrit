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
declare var BuiltinConfig: object

import { Injectable } from '@angular/core'
import { Observable } from 'rxjs/Observable'
import { Observer } from 'rxjs/Observer'

import { ActivatedRoute } from '@angular/router'

import WebsocketRequest from './websocketRequest'
import { getWebsocketUrl } from '../util'

function escapeLog (text: string): string {
  const pattern = /[<>&"']/g

  return text.replace(pattern, (match) => {
    return '&#' + match.charCodeAt(0) + ';'
  })
}

@Injectable()
class StreamService {

  private websocket: WebSocket
  private params: WebsocketRequest

  constructor(private route: ActivatedRoute) {}

  public initSocket(): void {
    const tenant = this.route.snapshot.paramMap.get('tenant')
    const queryParamMap = this.route.snapshot.queryParamMap
    let url: string

    this.params = new WebsocketRequest(queryParamMap.get('uuid'))

    if (queryParamMap.has('logfile')) {
      this.params.logfile = queryParamMap.get('logfile')
    }

    if (typeof BuiltinConfig !== 'undefined') {
      url = BuiltinConfig['websocket_url']
    } else if (queryParamMap.has('websocket_url')) {
      url = queryParamMap.get('websocket_url')
    } else {
      url = getWebsocketUrl('console-stream', tenant)
    }
    this.websocket = new WebSocket(url)
    this.websocket.addEventListener('open', (event) => {
      console.log('onOpen')
      this.websocket.send(JSON.stringify(this.params))
    })
  }

  public onOpen(event): void {
    console.log('onOpen')
    this.websocket.send(JSON.stringify(this.params))
  }

  public onMessage(): Observable<string> {
    return new Observable<string>(observer => {
      this.websocket.addEventListener('message', (event) => {
        console.log('onMessage')
        observer.next(event.data)
      })
    })
  }

  public onClose(): Observable<string> {
    return new Observable<string>(observer => {
      this.websocket.addEventListener('close', (event) => {
        console.log('onClose')
        observer.next('\n--- END OF STREAM ---\n')
      })
    })
  }
}

export default StreamService
