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
import ReactJson from 'react-json-view'
import {
  Icon,
  ListView,
  Row,
  Col,
  Modal,
  Button
} from 'patternfly-react'


function hostTaskStats (state, host) {
  if (host.failed) { state.failed += 1}
  else if (host.changed) { state.changed += 1}
  else if (host.skip_reason) { state.skipped += 1}
  else { state.ok += 1}
}

class Task extends React.Component {
  static propTypes = {
    task: PropTypes.object,
  }

  state = {
    failed: 0,
    changed: 0,
    skipped: 0,
    ok: 0
  }

  constructor (props) {
    super(props)

    Object.entries(props.task.hosts).forEach(([hostname, host]) => {
      hostTaskStats(this.state, host)
    })
  }

  render () {
    const { task } = this.props

    const ai = []
    if (this.state.skipped) {
      ai.push(
        <ListView.InfoItem key="skipped" title="Skipped hosts">
          <span className="task-skipped">SKIPPED</span>
        </ListView.InfoItem>)
    }
    if (this.state.changed) {
      ai.push(
        <ListView.InfoItem key="changed" title="Changed hosts">
          <span className="task-changed">CHANGED</span>
        </ListView.InfoItem>)
    }
    if (this.state.failed) {
      ai.push(
        <ListView.InfoItem key="failed" title="Failed hosts">
          <span className="task-failed">FAILED</span>
        </ListView.InfoItem>)
    }
    if (this.state.ok) {
      ai.push(
        <ListView.InfoItem key="ok" title="OK hosts">
          <span className="task-ok">OK</span>
        </ListView.InfoItem>)
    }

    //        key={idx}
    return (
      <ListView.Item
        heading={task.task.name}
        additionalInfo={ai}
      >
        <Row>
          <Col sm={12}>
            {Object.entries(task.hosts).map(([hostname, host]) => (
              <HostTask key={hostname} hostname={hostname} host={host}/>
            ))}
          </Col>
        </Row>
      </ListView.Item>
    )
  }
}

class HostTask extends React.Component {
  static propTypes = {
    hostname: PropTypes.string,
    host: PropTypes.object,
  }

  state = {
    showModal: false,
    lines: [],
    failed: 0,
    changed: 0,
    skipped: 0,
    ok: 0
  }

  open = () => {
    this.setState({ showModal: true})
  }

  close = () => {
    this.setState({ showModal: false})
  }

  constructor (props) {
    super(props)

    const { hostname, host } = this.props

    hostTaskStats(this.state, host)

    let lines = []

    if (host.results) {
      host.results.forEach((r) => {
        lines = lines.concat(this.getLinesForItem(hostname, r))
      })
    } else {
      lines = lines.concat(this.getLinesForItem(hostname, host))
    }
    this.state.lines = lines
  }

  getLinesForItem(hostname, item) {
    let lines = []
    if (item.msg) {
      lines = lines.concat(item.msg.split('\n'))
    } else if (item.skip_reason) {
      lines.push(item.skip_reason)
    } else if (item.changed) {
      lines.push('changed')
    }
    return lines
  }

  render () {
    const { hostname, host } = this.props

    const ai = []
    if (this.state.skipped) {
      ai.push(
        <ListView.InfoItem key="skipped" title="Skipped hosts">
          <span className="task-skipped">SKIPPED</span>
        </ListView.InfoItem>)
    }
    if (this.state.changed) {
      ai.push(
        <ListView.InfoItem key="changed" title="Changed hosts">
          <span className="task-changed">CHANGED</span>
        </ListView.InfoItem>)
    }
    if (this.state.failed) {
      ai.push(
        <ListView.InfoItem key="failed" title="Failed hosts">
          <span className="task-failed">FAILED</span>
        </ListView.InfoItem>)
    }
    if (this.state.ok) {
      ai.push(
        <ListView.InfoItem key="ok" title="OK hosts">
          <span className="task-ok">OK</span>
        </ListView.InfoItem>)
    }
    ai.push(
      <Button key='button' bsStyle="primary" bsSize="small" onClick={this.open}>
        Details
      </Button>
    )

    return (
      <React.Fragment>
        <ListView.Item
          key='header'
          heading={hostname}
          initExpanded={this.state.lines.length>0}
          additionalInfo={ai}
        >
         <Row>
           <Col sm={11}>
             <pre>
               {this.state.lines.join('\n')}
             </pre>
           </Col>
         </Row>
        </ListView.Item>
        <Modal key='modal' show={this.state.showModal} onHide={this.close}
               dialogClassName="task-detail">
          <Modal.Header>
            <button
              className="close"
              onClick={this.close}
              aria-hidden="true"
              aria-label="Close"
            >
              <Icon type="pf" name="close" />
            </button>
            <Modal.Title>{hostname}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {Object.entries(host).map(([key, value]) => (
              this.renderData(key, value)
            ))}
          </Modal.Body>
        </Modal>
      </React.Fragment>
    )
  }

  renderData(key, value) {
    let ret
    if (typeof(value) === 'string') {
      ret = (
        <pre>
          {value}
        </pre>
      )
    } else if (typeof(value) === 'object') {
      ret = (
        <pre>
          <ReactJson
            src={value}
            name={null}
            sortKeys={true}
            enableClipboard={false}
            displayDataTypes={false}/>
        </pre>
      )
    } else {
      ret = (
        <pre>
          {value.toString()}
        </pre>
      )
    }

    return (
      <div key={key}>
        {ret && <h3>{key}</h3>}
        {ret && ret}
      </div>
    )
  }
}

class Console extends React.Component {
  static propTypes = {
    output: PropTypes.array,
  }

  renderPlaybook (playbook, idx) {
    const ai = []
    if (playbook.trusted) {
      ai.push(
        <ListView.InfoItem key="trusted" title="Trusted">
          <Icon type='pf' name='info' /> Trusted
        </ListView.InfoItem>
      )
    }
    return (
      <ListView.Item
        key={idx}
        additionalInfo={ai}
        heading={playbook.phase[0].toUpperCase() + playbook.phase.slice(1) +
                 ' playbook: '+ playbook.playbook}
      >
        <Row>
          <Col sm={12}>
            {playbook.plays.map((play, idx) => this.renderPlay(play, idx))}
          </Col>
        </Row>
      </ListView.Item>
    )}

  renderPlay (play, idx) {
    return (
      <ListView.Item
        key={idx}
        heading={'Play: ' + play.play.name}
      >
        <Row>
          <Col sm={12}>
            {play.tasks.map((task, idx) => (
              <Task key={idx} task={task}/>
            ))}
          </Col>
        </Row>
      </ListView.Item>
  )}

  render () {
    const { output } = this.props
    return (
      <React.Fragment>
        <ListView key="playbooks" className="zuul-console">
          {output.map((playbook, idx) => this.renderPlaybook(playbook, idx))}
        </ListView>
      </React.Fragment>
    )
  }
}


export default Console
