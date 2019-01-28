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
import { TreeView } from 'patternfly-react'


class JobsList extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    jobs: PropTypes.array,
  }

  render () {
    const { jobs } = this.props

    // Create tree data
    const nodes = []
    const visited = {}
    const linkPrefix = this.props.tenant.linkPrefix + '/job/'
    const getNode = function (job) {
      if (!visited[job.name]) {
        if (job.parent) {
          for (let otherJob of jobs) {
            if (job.parent === otherJob.name) {
              getNode(otherJob)
              break
            }
          }
        }
        visited[job.name] = {
          text: (
            <React.Fragment>
              <Link to={linkPrefix + job.name}>{job.name}</Link>
              {job.description && (
                <span style={{marginLeft: '10px'}}>{job.description}</span>
              )}
            </React.Fragment>),
          icon: 'fa fa-cube',
        }
      }
      return visited[job.name]
    }
    for (let job of jobs) {
      const jobNode = getNode(job)
      if (job.parent) {
        const parentNode = visited[job.parent]
        if (!parentNode.nodes) {
          parentNode.nodes = []
          parentNode.state = {
            expanded: true
          }
        }
        parentNode.nodes.push(jobNode)
      } else {
        nodes.push(jobNode)
      }
    }
    return (
      <div className="tree-view-container">
        <TreeView nodes={nodes} />
      </div>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
}))(JobsList)
