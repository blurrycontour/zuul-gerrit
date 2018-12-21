/* global clearTimeout, setTimeout, JSON, URLSearchParams */
// Copyright 2018 Red Hat, Inc
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

import * as React from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { Checkbox, Form, FormGroup } from 'patternfly-react'
import Sockette from 'sockette'
import Ansi from 'ansi-to-react'

import { getStreamUrl } from '../api'


class StreamPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    location: PropTypes.object.isRequired,
    tenant: PropTypes.object
  }

  state = {
    autoscroll: true,
    lines: [],
  }

  constructor() {
    super()
    this.receiveBuffer = ''
    this.messagesEnd = React.createRef()
  }


  componentWillUnmount () {
    if (this.timer) {
      clearTimeout(this.timer)
      this.timer = null
    }
    if (this.ws) {
      console.log('Remove ws')
      this.ws.close()
    }
  }

  onLine = (line) => {
    this.setState(prevState => ({
      lines: [...prevState.lines, line]
    }))
  }

  onMessage = (message) => {
    this.receiveBuffer += message
    const lines = this.receiveBuffer.split('\n')
    const lastLine = lines.slice(-1)[0]
    // Append all completed lines
    lines.slice(0, -1).forEach(line => {
      this.onLine(line)
    })
    // Check if last chunk is completed
    if (lastLine && this.receiveBuffer.slice(-1) === '\n') {
      this.onLine(lastLine)
      this.receiveBuffer = ''
    } else {
      this.receiveBuffer = lastLine
    }
  }

  componentDidMount() {
    const params = {
      uuid: this.props.match.params.buildId
    }
    const urlParams = new URLSearchParams(this.props.location.search)
    const logfile = urlParams.get('logfile')
    if (logfile) {
      params.logfile = logfile
    }
    document.title = 'Zuul Stream | ' + params.uuid.slice(0, 7)
    this.ws = new Sockette(getStreamUrl(this.props.tenant.apiPrefix), {
      timeout: 5e3,
      maxAttempts: 3,
      onopen: () => {
        console.log('onopen')
        this.ws.send(JSON.stringify(params))
      },
      onmessage: e => {
        this.onMessage(e.data)
      },
      onreconnect: e => {
        console.log('Reconnecting...', e)
      },
      onmaximum: e => {
        console.log('Stop Attempting!', e)
      },
      onclose: e => {
       console.log('onclose', e)
       this.onMessage('\n--- END OF STREAM ---\n')
      },
      onerror: e => {
       console.log('onerror:', e)
      }
    })
  }

  handleCheckBox = (e) => {
    this.setState({autoscroll: e.target.checked})
  }

  render () {
    const lines = this.state.lines.map((line) => {
      return(<Ansi className='zuulstreamcontent'>{line + '\n'}</Ansi>)
    })
    return (
      <React.Fragment>
        <Form inline id='zuulstreamoverlay'>
          <FormGroup controlId='stream'>
            <Checkbox
              checked={this.state.autoscroll}
              onChange={this.handleCheckBox}>
              autoscroll
            </Checkbox>
          </FormGroup>
        </Form>
        <div className='zuulstreamcontent'>
          <div className='zuulstreamline'>
              {lines}
          </div>
          <div ref={this.messagesEnd} />
        </div>
      </React.Fragment>
    )
  }

  componentDidUpdate() {
    if (this.state.autoscroll) {
      this.messagesEnd.current.scrollIntoView({ behavior: 'instant' })
    }
  }
}

export default connect(state => ({tenant: state.tenant}))(StreamPage)
