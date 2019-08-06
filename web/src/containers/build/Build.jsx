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
import { Link } from 'react-router-dom'
import { Panel } from 'react-bootstrap'
import {
  Nav,
  NavItem,
  TabContainer,
  TabPane,
  TabContent,
} from 'patternfly-react'

import ArtifactList from './Artifact'
import BuildOutput from './BuildOutput'
import Manifest from './Manifest'
import Console from './Console'


class Build extends React.Component {
  static propTypes = {
    build: PropTypes.object,
    tenant: PropTypes.object,
  }

  render () {
      const { build } = this.props
    const rows = []
    const myColumns = [
      'job_name', 'result', 'voting',
      'pipeline', 'start_time', 'end_time', 'duration',
      'project', 'branch', 'change', 'patchset', 'oldrev', 'newrev',
      'ref', 'new_rev', 'ref_url', 'log_url']

    const defaultTab = window.location.hash.substring(1) || 'summary'

    myColumns.forEach(column => {
      let label = column
      let value = build[column]
      if (column === 'job_name') {
        label = 'job'
        value = (
          <Link to={this.props.tenant.linkPrefix + '/job/' + value}>
            {value}
          </Link>
        )
      }
      if (column === 'voting') {
        if (value) {
          value = 'true'
        } else {
          value = 'false'
        }
      }
      if (value && (column === 'log_url' || column === 'ref_url')) {
        value = <a href={value}>{value}</a>
      }
      if (column === 'log_url') {
        label = 'log url'
      }
      if (column === 'ref_url') {
        label = 'ref url'
      }
      if (value) {
        rows.push({key: label, value: value})
      }
    })
    return (
      <Panel>
        <Panel.Heading>Build result {build.uuid}</Panel.Heading>
        <Panel.Body>
          <TabContainer id="zuul-project" defaultActiveKey={defaultTab}>
            <div>
              <Nav bsClass="nav nav-tabs nav-tabs-pf">
                <NavItem eventKey={'summary'} href="#summary">
                  Summary
                </NavItem>
                {build.manifest &&
                 <NavItem eventKey={'logs'} href="#logs">
                   Logs
                 </NavItem>}
                {build.output &&
                 <NavItem eventKey={'console'} href="#console">
                   Console
                 </NavItem>}
              </Nav>
              <TabContent>
                <TabPane eventKey={'summary'}>
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
                  <h3>Artifacts</h3>
                  <ArtifactList build={build}/>
                  <h3>Results</h3>
                  {build.hosts && <BuildOutput output={build.hosts}/>}
                </TabPane>
                {build.manifest &&
                 <TabPane eventKey={'logs'}>
                   <Manifest tenant={this.props.tenant} build={build}/>
                 </TabPane>}
                {build.output &&
                 <TabPane eventKey={'console'}>
                   <Console output={build.output}/>
                 </TabPane>}
              </TabContent>
            </div>
          </TabContainer>
        </Panel.Body>
      </Panel>
    )
  }
}


export default connect(state => ({tenant: state.tenant}))(Build)
