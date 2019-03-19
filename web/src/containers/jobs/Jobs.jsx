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
import { withRouter } from 'react-router'
import { connect } from 'react-redux'
import { Link } from 'react-router-dom'
import {
  Checkbox,
  Badge,
  Form,
  FormGroup,
  FormControl,
  Icon,
  TreeView
} from 'patternfly-react'

import TableFilters from '../TableFilters'


class JobsList extends TableFilters {
  static propTypes = {
    tenant: PropTypes.object,
    jobs: PropTypes.array,
    location: PropTypes.object
  }

  constructor() {
    super()
    this.filterTypes = [{
      id: 'tag',
      title: 'tag',
      placeHolder: 'Filter by tag',
      filterType: 'select',
    }]
    this.state = {
      filter: null,
      flatten: false,
      activeFilters: [],
      currentValue: '',
      currentFilterType: this.filterTypes[0]
    }
  }

  handleKeyPress = (e) => {
    if (e.charCode === 13) {
      this.setState({filter: e.target.value})
      e.preventDefault()
      e.target.blur()
    }
  }

  componentDidMount() {
    this.getFilterFromUrl()
  }

  // Jobs list data is updated on render
  updateData () {}

  render () {
    const { jobs } = this.props
    const { filter, flatten, activeFilters } = this.state

    const linkPrefix = this.props.tenant.linkPrefix + '/job/'

    // job index map
    const jobMap = {}
    // tag list
    const tagList = []
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
            if (jobVariant.parent &&
                parents.indexOf(jobVariant.parent) === -1) {
              parents.push(jobVariant.parent)
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
              {job.tags && job.tags.map((tag, idx) => (
                <Badge
                  key={idx}
                  pullRight>
                  {tag}
                </Badge>))}
            </React.Fragment>),
          icon: 'fa fa-cube',
          state: {
            expanded: true,
          },
          parents: parents,
          filtered: filtered,
        }
        // Visit parent recursively
        if (!flatten) {
          for (let parent of parents) {
            getNode(jobMap[parent], filtered)
          }
        }
      }
      return visited[job.name]
    }

    // index job list
    for (let job of jobs) {
      jobMap[job.name] = job
      if (job.tags) {
        for (let tag of job.tags) {
          if (tagList.indexOf(tag) === -1) {
            tagList.push(tag)
          }
        }
      }
    }

    const tagFilter = function (tagName) {
      for (let filter of activeFilters) {
        if (filter.value === tagName) {
          return true
        }
      }
      return false
    }

    // filter job
    let filtered = false
    if (filter || activeFilters.length > 0) {
      filtered = true
      let filters
      if (filter) {
        filters = filter.replace(/ +/, ',').split(',')
      }
      for (let job of jobs) {
        if (filters) {
          filters.forEach(jobFilter => {
            if (jobFilter && (
              (job.name.indexOf(jobFilter) !== -1) ||
              (job.description && job.description.indexOf(jobFilter) !== -1))) {
              getNode(job, !filtered)
            }
          })
        }
        if (job.tags && job.tags.filter(tagFilter).length > 0) {
          getNode(job, !filtered)
        }
      }
    }

    // process job list
    for (let job of jobs) {
      const jobNode = getNode(job, filtered)
      if (!jobNode.filtered) {
        let attached = false
        if (!flatten) {
          // add tree node to each parent and expand the parent
          for (let parent of jobNode.parents) {
            const parentNode = visited[parent]
            if (!parentNode) {
              console.log(
                'Job ', job.name, ' parent ', parent, ' does not exist!')
              continue
            }
            if (!parentNode.nodes) {
              parentNode.nodes = []
            }
            parentNode.nodes.push(jobNode)
            attached = true
          }
        }
        // else add node at the tree root
        if (!attached || jobNode.parents.length === 0) {
          nodes.push(jobNode)
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
          <FormGroup controlId='jobs-tag'>
            {this.renderFilterInput(tagList)}
          </FormGroup>
          <FormGroup controlId='jobs-flatten'>
            &nbsp; Flatten list &nbsp;
            <Checkbox
              defaultChecked={flatten}
              onChange={(e) => this.setState({flatten: e.target.checked})} />
          </FormGroup>
        </Form>
        {this.renderActiveFilters()}
        <TreeView nodes={nodes} />
      </div>
    )
  }
}

export default withRouter(connect(state => ({
  tenant: state.tenant,
}))(JobsList))
