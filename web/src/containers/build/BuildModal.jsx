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
  Col,
  Form,
  FormControl,
  FormGroup,
  HelpBlock,
  Icon,
  Modal,
  Row,
} from 'patternfly-react'

import { fetchJobIfNeeded } from '../../actions/job'
import * as API from '../../api'


class BuildModal extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    projectName: PropTypes.string,
    jobName: PropTypes.string,
    job: PropTypes.object,
    onRef: PropTypes.func,
    dispatch: PropTypes.func,
    history: PropTypes.object.isRequired,
  }

  state = {
    show: false,
  }

  show = () => {
    this.props.dispatch(
      fetchJobIfNeeded(this.props.tenant, this.props.jobName)
    )
    this.setState({show: true})
  }

  componentDidMount() {
    this.props.onRef(this)
  }

  componentWillUnmount() {
    this.props.onRef(undefined)
  }

  submit = () => {
    const { tenant, projectName, jobName } = this.props
    const variables = {}
    if (this.jobVariables) {
      for (let variable of this.jobVariables) {
        const value = this.inputs[variable.name].value
        if (value) {
          variables[variable.name] = value
        }
      }
    }
    API.triggerJobs(tenant.apiPrefix, projectName, [jobName], variables)
      .then(() => this.props.history.push(tenant.linkPrefix + '/status'))
      .catch(error => console.error('oops', error))
  }

  getVariables(jobs, job) {
    if (!jobs || !jobs[job]) {
      return []
    }
    const variables = []
    let v = undefined
    for (let line of jobs[job][0].description.split('\n')) {
      if (new RegExp('^.. zuul:jobvar').test(line)) {
        if (v) {
          variables.push(v)
        }
        v = {name: line.split(':: ')[1]}
      }
      if (v && !v['defaults'] && new RegExp('^ {3}:default: ').test(line)) {
        v['defaults'] = line.split(':default: ')[1]
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

  render () {
    const { projectName, job, jobName } = this.props
    this.jobVariables = this.getVariables(
      job.jobs[this.props.tenant.name], jobName)
    this.inputs = {}
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
            Run {jobName} for project {projectName}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form horizontal>
            {this.jobVariables.map(item => (
              <FormGroup controlId={item.name} key={item.name}>
                <Col sm={3}>
                  {item.name}
                </Col>
                <Col sm={9}>
                  <FormControl
                    type='text'
                    inputRef={(ref) => {this.inputs[item.name]= ref}} />
                  <HelpBlock>
                    {item.description}
                    {item.defaults && ' (' + item.defaults + ')'}
                  </HelpBlock>
                </Col>
              </FormGroup>
            ))}
            <Row style={{paddingTop: '10px',paddingBottom: '10px'}}>
              <Col smOffset={3} sm={9}>
                <span>
                  <Button bsStyle='primary' onClick={this.submit}>
                    Execute
                  </Button>
                </span>&nbsp;
                <span>
                  <Button onClick={() => {this.setState({show: false})}}>
                    Cancel
                  </Button>
                </span>
              </Col>
            </Row>
          </Form>
        </Modal.Body>
      </Modal>
    )
  }
}

export default withRouter(connect(state => ({
  tenant: state.tenant,
  job: state.job,
}))(BuildModal))
