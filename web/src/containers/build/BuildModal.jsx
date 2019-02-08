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
import { withRouter } from 'react-router-dom'
import { connect } from 'react-redux'
import {
  Button,
  Checkbox,
  Col,
  Form,
  FormControl,
  FormGroup,
  HelpBlock,
  Icon,
  Modal,
} from 'patternfly-react'

import { fetchJobIfNeeded } from '../../actions/job'
import * as API from '../../api'


class BuildModal extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    projectName: PropTypes.string,
    job: PropTypes.object,
    onRef: PropTypes.func,
    dispatch: PropTypes.func,
    history: PropTypes.object.isRequired,
  }

  state = {
    show: false,
    jobsNames: [],
  }

  fetchJobAndParentsIfNeeded = (jobName) => {
    this.props.dispatch(fetchJobIfNeeded(this.props.tenant, jobName))
      .then(() => {
        const jobs = this.props.job.jobs[this.props.tenant.name][jobName]
        if (!jobs) {
          return
        }
        for (let job of jobs) {
          if (job.branches && job.branches.length > 0) {
            // No need to continue
            return
          }
        }
        for (let job of jobs) {
          if (job.parent) {
            this.fetchJobAndParentsIfNeeded(job.parent)
          }
        }
      })
  }

  show = (pipeline, jobs) => {
    for (let job of jobs) {
      this.fetchJobAndParentsIfNeeded(job)
    }
    this.setState({show: true, pipeline: pipeline, jobsNames: jobs})
  }

  componentDidMount() {
    this.props.onRef(this)
  }

  componentWillUnmount() {
    this.props.onRef(undefined)
  }

  assignVariable = (variables, name, value) => {
    if (name.indexOf('.') !== -1) {
      const components = name.split('.')
      name = components[0]
      if (!variables[name]) {
        variables[name] = {}
      }
      value = this.assignVariable(
        variables[name], components.slice(1).join('.'), value)
    }
    try {
      variables[name] = value
    } catch (TypeError) {
      console.error('Couldn\'t assign variable', name)
    }
    return variables
  }

  submit = () => {
    const { pipeline, jobsNames } = this.state
    const { tenant, projectName } = this.props
    const jobs = []
    for (let jobName of jobsNames) {
      jobs.push('^' + jobName + '$')
    }
    const variables = {}
    if (this.jobsVariables) {
      for (let variable of this.jobsVariables) {
        let value
        if (variable['type'] === 'bool') {
          value = this.inputs[variable.name].checked
        } else {
          value = this.inputs[variable.name].value
        }
        if (value !== '') {
          this.assignVariable(variables, variable.name, value)
        }
      }
    }
    let branch = this.branch
    if (this.branchRef && this.branchRef.value) {
      branch = this.branchRef.value
    }
    API.triggerJobs(
      tenant.apiPrefix, projectName, {
        job_filters: jobs,
        branch: branch,
        pipeline: pipeline,
        variables: variables})
      .then(() => this.props.history.push(tenant.linkPrefix + '/status'))
      .catch(error => console.error('oops', error))
  }

  getVariables(jobs, job) {
    if (!jobs || !jobs[job] || !jobs[job][0].description) {
      return []
    }
    const variables = []
    let v = undefined
    for (let line of jobs[job][0].description.split('\n')) {
      if (new RegExp('^.. zuul:jobvar').test(line)) {
        if (v) {
          variables.push(v)
        }
        v = {name: line.split(':: ')[1], jobs: [job]}
      }
      if (v && !v['defaults'] && new RegExp('^ {3}:default: ').test(line)) {
        v['defaults'] = line.split(':default: ')[1]
      }
      if (v && !v['doc'] && new RegExp('^ {3}:doc-link: ').test(line)) {
        v['doc'] = line.split(':doc-link: ')[1]
      }
      if (v && !v['type'] && new RegExp('^ {3}:type: ').test(line)) {
        v['type'] = line.split(':type: ')[1]
      }
      if (v && v['type'] && v['type'] === 'choice' && !v['value'] &&
          new RegExp('^ {3}:value: ').test(line)) {
        let val = line.split(':value: ')[1]
        v['value'] = val.substr(1, val.length - 2).split(',').map(
          item => item.trim())
      }
      if (v && !v['description'] && new RegExp('^ {3}[a-zA-Z]').test(line)) {
        v['description'] = line.trim()
      }
    }
    if (v) {
      variables.push(v)
    }
    return variables
  }

  getJobsVariables(jobs, jobsNames) {
    const variables = []
    const getVariable = function (variableName) {
      for (let variable of variables) {
        if (variable.name === variableName) {
          return variable
        }
      }
    }
    for (let job of jobsNames) {
      const jobVariables = this.getVariables(jobs, job)

      for (let jobVariable of jobVariables) {
        let variable = getVariable(jobVariable.name)
        if (!variable) {
          variables.push(jobVariable)
        } else {
          variable.jobs.push(job)
        }
      }
    }
    return variables
  }

  getJobsBranch(jobsNames) {
    // Return the first branch matcher found, otherwise return master
    const allJobs = this.props.job.jobs[this.props.tenant.name]
    if (!allJobs) {
      return 'master'
    }
    for (let jobName of jobsNames) {
      const jobs = allJobs[jobName]
      if (!jobs) {
        continue
      }
      for (let job of jobs) {
        if (job.branches && job.branches.length > 0) {
          return job.branches[0]
        }
        if (job.parent) {
          if (allJobs[job.parent]) {
            const parentBranch = this.getJobsBranch([job.parent])
            if (parentBranch !== 'master') {
              return parentBranch
            }
          }
        }
      }
    }
    return 'master'
  }

  render () {
    const { jobsNames } = this.state
    const { projectName, job } = this.props
    this.branch = this.getJobsBranch(jobsNames)
    this.jobsVariables = this.getJobsVariables(
      job.jobs[this.props.tenant.name], jobsNames)
    this.inputs = {}
    this.branchRef = null
    return (
      <Modal
        show={this.state.show}
        onHide={() => {this.setState({show: false})}}>
        <Modal.Header>
          <button
            className='close'
            onClick={() => {this.setState({show: false})}}
            aria-hidden='true'
            aria-label='Close'
          >
            <Icon type='pf' name='close' />
          </button>
          <Modal.Title>
            Run {jobsNames.join(' ')} for project {projectName}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form horizontal>
            <FormGroup controlId='project-branch' key='project-branch'>
              <Col sm={3}>
                branch
              </Col>
              <Col sm={9}>
                <FormControl
                  type='text'
                  placeholder={this.branch}
                  inputRef={(ref) => {this.branchRef = ref}} />
                <HelpBlock>
                  The project branch name
                </HelpBlock>
              </Col>
            </FormGroup>
            {this.jobsVariables.map(item => {
              let formControl
              if (item['type'] === 'bool') {
                formControl = (
                  <Checkbox
                    style={{'marginTop': '0'}}
                    inputRef={(ref) => {this.inputs[item.name]= ref}} />
                )
              } else if (item['type'] === 'choice') {
                formControl = (
                  <FormControl
                    componentClass='select'
                    inputRef={(ref) => {this.inputs[item.name]= ref}}>
                    <React.Fragment>
                      {item['value'].map(itemValue => (
                        <option value={itemValue} key={itemValue}>{itemValue}</option>
                      ))}
                    </React.Fragment>
                  </FormControl>
                )
              } else {
                formControl = (
                  <FormControl
                    type='text'
                    inputRef={(ref) => {this.inputs[item.name]= ref}} />
                )
              }
              return (
                <FormGroup controlId={item.name} key={item.name}>
                  <Col sm={3}>
                    {item.name} {item.doc && (
                      <a href={item.doc}
                         rel='noopener noreferrer'
                         title='Parameter documentation'
                         target='_blank'><Icon type='pf' name='help' /></a>)}
                  </Col>
                  <Col sm={9}>
                    {formControl}
                    <HelpBlock>
                      {item.description}
                      {item.defaults && ' (' + item.defaults + ')'}
                      {item.jobs.length !== jobsNames.length && (
                        <React.Fragment>
                          {item.description && <br />}
                          <strong>Affects:</strong> {item.jobs.join(',')}
                        </React.Fragment>
                      )}
                    </HelpBlock>
                  </Col>
                </FormGroup>
              )
            })}
          </Form>
        </Modal.Body>
        <Modal.Footer>
          <Button bsStyle='primary' onClick={this.submit}>
            Execute
          </Button>
          <Button onClick={() => {this.setState({show: false})}}>
            Cancel
          </Button>
        </Modal.Footer>
      </Modal>
    )
  }
}

export default withRouter(connect(state => ({
  tenant: state.tenant,
  job: state.job,
}))(BuildModal))
