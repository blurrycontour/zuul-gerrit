// Copyright 2019 Red Hat, Inc
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
import { Panel } from 'react-bootstrap'

import Build from './Build'


class Buildset extends React.Component {
  static propTypes = {
    buildset: PropTypes.object,
    tenant: PropTypes.object,
  }

  render () {
    const { buildset } = this.props
    const rows = []
    const myColumns = [
      'change', 'project', 'branch', 'pipeline', 'result', 'message'
    ]

    myColumns.forEach(column => {
      let label = column
      let value = buildset[column]
      if (column === 'change') {
        value = (
          <a href={buildset.ref_url}>
            {buildset.change},{buildset.patchset}
          </a>
        )
      }
      if (value) {
        rows.push({key: label, value: value})
      }
    })
    return (
      <Panel>
        <Panel.Heading>Buildset result {buildset.uuid}</Panel.Heading>
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
          {buildset.builds.map(build => (
            <Build build={build} key={build.uuid} />
          ))}
        </Panel.Body>
      </Panel>
    )
  }
}


export default connect(state => ({tenant: state.tenant}))(Buildset)
