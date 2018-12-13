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
import { Panel } from 'react-bootstrap'
import {
  Icon,
  ListView,
} from 'patternfly-react'

class JobOutput extends React.Component {
  static propTypes = {
    output: PropTypes.array,
  }

  componentDidMount () {
    // Expand host with failed tasks
    Object.values(this.hosts).forEach(values => {
      if (values.failed.length > 0) {
        values.ref.setState({expanded: true})
      }
    })
  }

  renderFailedTask (task) {
    return (
      <Panel key={task.zuul_log_id}>
        <Panel.Heading>{task.name}</Panel.Heading>
        <Panel.Body>
          {task.invocation && task.invocation.module_args &&
           task.invocation.module_args._raw_params && (
             <strong key="cmd">
               {task.invocation.module_args._raw_params} <br />
             </strong>
           )}
          {task.stdout_lines && task.stdout_lines.length > 0 && (
            <span key="stdout" style={{whiteSpace: 'pre'}} title="stdout">
              {task.stdout_lines.slice(-42).map((line, idx) => (
                <span key={idx}>{line}<br/></span>))}
              <br />
            </span>
          )}
          {task.stderr_lines && task.stderr_lines.length > 0 && (
            <span key="stderr" style={{whiteSpace: 'pre'}} title="stderr">
              {task.stderr_lines.slice(-42).map((line, idx) => (
                <span key={idx}>{line}<br/></span>))}
              <br />
            </span>
          )}
        </Panel.Body>
      </Panel>
    )
  }

  render () {
    const { output } = this.props
    const hosts = {}
    // Compute stats
    output.forEach(phase => {
      Object.entries(phase.stats).forEach(([host, stats]) => {
         if (!hosts[host]) {
           hosts[host] = stats
           hosts[host].failed = []
         } else {
           hosts[host].changed += stats.changed
           hosts[host].failures += stats.failures
           hosts[host].ok += stats.ok
         }
        if (stats.failures > 0) {
          phase.plays.forEach(play => {
            play.tasks.forEach(task => {
              if (task.hosts[host]) {
                if (task.hosts[host].results) {
                  task.hosts[host].results.forEach(result => {
                    if (result.failed) {
                      result.name = task.task.name
                      hosts[host].failed.push(result)
                    }
                  })
                } else if (task.hosts[host].rc || task.hosts[host].failed) {
                  let result = task.hosts[host]
                  result.name = task.task.name
                  hosts[host].failed.push(result)
                }
              }
            })
          })
        }
      })
    })
    this.hosts = hosts
    return (
      <ListView>
        {Object.entries(hosts).map(([host, values]) => (
          <ListView.Item
            key={host}
            heading={host}
            hideCloseIcon={true}
            ref={ref => {this.hosts[host].ref = ref}}
            additionalInfo={[
              <ListView.InfoItem key="ok" title="Task OK">
                <Icon type='pf' name='info' />
                <strong>{values.ok}</strong>
              </ListView.InfoItem>,
              <ListView.InfoItem key="changed" title="Task changed">
                <Icon type='pf' name='ok' />
                <strong>{values.changed}</strong>
              </ListView.InfoItem>,
              <ListView.InfoItem key="fail" title="Task failure">
                <Icon type='pf' name='error-circle-o' />
                <strong>{values.failures}</strong>
              </ListView.InfoItem>
            ]}
          >
            {values.failed.map(failed => (
              this.renderFailedTask(failed)
            ))}
          </ListView.Item>
        ))}
      </ListView>
    )
  }
}


export default JobOutput
