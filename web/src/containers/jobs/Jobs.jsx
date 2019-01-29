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
import {
  Form,
  FormGroup,
  FormControl,
  Icon,
  TreeView
} from 'patternfly-react'


class JobsList extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    jobs: PropTypes.array,
  }

  state = {
    filter: null
  }

  handleKeyPress = (e) => {
    if (e.charCode === 13) {
      this.setState({filter: e.target.value})
      e.preventDefault()
      e.target.blur()
    }
  }

  render () {
    const { jobs } = this.props
    const { filter } = this.state

    const linkPrefix = this.props.tenant.linkPrefix + '/job/'

    // nodes contains the tree data
    const nodes = []
    // visited contains individual node
    const visited = {}
    // getNode returns the tree node and visit each parents
    const getNode = function (job, filtered) {
      if (!visited[job.name]) {
        // Collect parents
        let parents = []
        if (job.variants) {
          for (let jobVariant of job.variants) {
            if (jobVariant.parent) {
              parents.push(jobVariant.parent)
            }
          }
        }
        // Visit parent recursively
        for (let parent of parents) {
          for (let otherJob of jobs) {
            if (parent === otherJob.name) {
              getNode(otherJob, filtered)
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
          state: {
            expanded: true,
          },
          parents: parents,
          filtered: filtered,
        }
      }
      return visited[job.name]
    }
    // filter job
    let filtered = false
    if (filter) {
      filtered = true
      for (let job of jobs) {
        if (job.name.indexOf(filter) !== -1 ||
            (job.description && job.description.indexOf(filter) !== -1)) {
          getNode(job, !filtered)
        }
      }
    }
    // process job list
    for (let job of jobs) {
      const jobNode = getNode(job, filtered)
      if (!jobNode.filtered) {
        let attached = false
        // add tree node to each parent and expand the parent
        for (let parent of jobNode.parents) {
          const parentNode = visited[parent]
          if (!parentNode) {
            console.log('Job ', job.name, ' parent ', parent, ' does not exist!')
            continue
            let attached = false
            // add tree node to each parent and expand the parent
            for (let parent of jobNode.parents) {
              const parentNode = visited[parent]
              if (!parentNode) {
                console.log(
                  "Job ", job.name, "'s parent ", parent, " doesn't exist!")
                continue
              }
              if (!parentNode.nodes) {
                parentNode.nodes = []
              }
              parentNode.nodes.push(jobNode)
              attached = true
            }
            // else add node at the tree root
            if (!attached || jobNode.parents.length === 0) {
              nodes.push(jobNode)
            }
          }
        }
    }
    return (
      <div className="tree-view-container">
        <Form inline>
          <FormGroup controlId='jobs'>
            <FormControl
              type='text'
              placeholder='job name'
              defaultValue={filter}
              inputRef={i => this.filter = i}
              onKeyPress={this.handleKeyPress} />
            {filter && (
              <FormControl.Feedback>
                <span
                  onClick={() => {this.setState({filter: ''})
                                 this.filter.value = ''}}
                  style={{cursor: 'pointer', zIndex: 10, pointerEvents: 'auto'}}
                >
                  <Icon type='pf' title='Clear filter' name='delete' />
                  &nbsp;
                </span>
              </FormControl.Feedback>
            )}
          </FormGroup>
        </Form>
        <TreeView nodes={nodes} />
      </div>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
}))(JobsList)
