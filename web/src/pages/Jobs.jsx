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
import { Button } from 'react-bootstrap'

import { fetchJobsIfNeeded } from '../actions/jobs'
import Refreshable from '../containers/Refreshable'
import Jobs from '../containers/jobs/Jobs'
import JobsGraph from '../containers/jobs/JobsGraph'


class JobsPage extends Refreshable {
  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  state = {
    showGraph: false
  }

  updateData (force) {
    this.props.dispatch(fetchJobsIfNeeded(this.props.tenant, force))
  }

  componentDidMount () {
    document.title = 'Zuul Jobs'
    super.componentDidMount()
  }

  renderJobs (jobs) {
    if (this.state.showGraph) {
      return <JobsGraph jobs={jobs} width={1600} height={1060} />
    } else {
      return <Jobs jobs={jobs} />
    }
  }

  render () {
    const { remoteData } = this.props
    const jobs = remoteData.jobs[this.props.tenant.name]
    return (
      <React.Fragment>
        <Button
          onClick={() => this.setState({showGraph: !this.state.showGraph})}>
          Show graph
        </Button>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        {jobs && jobs.length > 0 && this.renderJobs(jobs)}
      </React.Fragment>)
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.jobs,
}))(JobsPage)
