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
import {
  Icon,
  ListView,
  Row,
  Col,
} from 'patternfly-react'


class Console extends React.Component {
  static propTypes = {
    output: PropTypes.object,
  }

  renderPlaybook (playbook, idx) {
    return (
      <ListView.Item
        key={idx}
        actions={<div />}
        leftContent={<ListView.Icon />}
        additionalInfo={[
          <ListView.InfoItem key="ok" title="Task OK">
            <Icon type='pf' name='info' />
            <strong>Trusted: {playbook.trusted?'true':'false'}</strong>
          </ListView.InfoItem>
        ]}
        heading={playbook.phase + ' playbook '+ playbook.playbook}
      >
        <Row>
          <Col sm={11}>
            <pre>
              {playbook.plays.map((play, idx) => this.renderPlay(play, idx))}
            </pre>
          </Col>
        </Row>
      </ListView.Item>
    )}

  renderPlay (play, idx) {
    return 'PLAY '+ play.play.name + '\n' +
      play.tasks.map((task, idx) => this.renderTask(task, idx)).join('')
  }

  renderTask (task, idx) {
    return 'TASK '+ task.task.name + '\n' +
      Object.entries(task.hosts).map(([hostname, host]) => this.renderTaskHost(hostname, host)).join('')
  }

  renderTaskHost (hostname, host) {
    let lines = []

    if (host.msg) {
      lines = lines.concat(host.msg.split('\n'))
    } else if (host.skip_reason) {
      lines.push(host.skip_reason)
    }

    console.log(lines)
    return lines.map((l) => hostname + ' | ' + l + '\n').join('')
  }

  render () {
    const { output } = this.props
    return (
      <React.Fragment>
        <ListView key="playbooks">
          {output.map((playbook, idx) => this.renderPlaybook(playbook, idx))}
        </ListView>
      </React.Fragment>
    )
  }
}


export default Console
