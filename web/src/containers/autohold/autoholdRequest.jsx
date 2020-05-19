// Copyright 2020 Red Hat, Inc
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
import { Link } from 'react-router-dom'
import { Panel } from 'react-bootstrap'
import * as moment from 'moment'
import 'moment-duration-format'


class AutoholdRequest extends React.Component {
  static propTypes = {
    autoholdRequest: PropTypes.object,
    tenant: PropTypes.object,
  }

  render () {
    const { autoholdRequest } = this.props
    const rows = []
    const myColumns = [
      'project', 'job', 'ref_filter', 'current_count', 'node_expiration', 'reason'
    ]
    const buildRows = []
    const buildColumns = [
      'build'
    ]

    myColumns.forEach(column => {
      let label = column
      let value = autoholdRequest[column]
      if (column === 'current_count') {
        label = 'count'
        value = (
            autoholdRequest['current_count'] + '/' + autoholdRequest['max_count']
        )
      }
      if (column === 'ref_filter') {
        label = 'ref filter'
      }
      if (column === 'node_expiration') {
        label = 'node expiration'
        value = moment.duration(autoholdRequest['node_expiration'], 'seconds').format('h [hr] m [min] s [sec]')
      }
      if (value) {
        rows.push({key: label, value: value})
      }
    })

    if (autoholdRequest.nodes) {
      autoholdRequest.nodes.forEach(nodeset => {
        const row = []
        buildColumns.forEach(column => {
          if (column === 'build') {
            row.push(<Link
                        to={this.props.tenant.linkPrefix + '/build/' + nodeset.build}>
                        {nodeset.build}
                     </Link>)
          }
        })
        buildRows.push(row)
      })
    }
    return (
      <React.Fragment>
        <Panel>
          <Panel.Heading>Autohold Request {autoholdRequest.id}</Panel.Heading>
          <Panel.Body>
            <table className="table table-striped table-bordered">
              <tbody>
                {rows.map(item => (
                    <tr key={item.key}>
                      <td>{item.key}</td>
                      <td>{item.value}</td>
                    </tr>
                ))}
              </tbody>
            </table>
          </Panel.Body>
        </Panel>
        {autoholdRequest.nodes.length > 0 &&
          <Panel>
            <Panel.Heading>Held Builds</Panel.Heading>
            <Panel.Body>
              <table className="table table-striped table-bordered">
                <thead>
                </thead>
                <tbody>
                  {autoholdRequest.nodes.map((item, idx) => (
                    <tr key={idx}>
                        {buildRows[idx].map((item, idx) => (
                          <td key={idx}>{item}</td>
                        ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel.Body>
          </Panel>
        }
      </React.Fragment>
    )
  }
}


export default connect(state => ({tenant: state.tenant}))(AutoholdRequest)
