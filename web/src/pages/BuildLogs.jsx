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
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import { parse } from 'query-string'

import { fetchBuildIfNeeded } from '../actions/build'
import { fetchLogfileIfNeeded } from '../actions/logfile'
import Refreshable from '../containers/Refreshable'
import Build from '../containers/build/Build'
import Manifest from '../containers/build/Manifest'
import LogFile from '../containers/logfile/LogFile'


class BuildLogsPage extends Refreshable {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    logFile: PropTypes.object,
    tenant: PropTypes.object
  }

  updateData = (force) => {
    this.props.dispatch(fetchBuildIfNeeded(
      this.props.tenant, this.props.match.params.buildId, null, force))
  }

  componentDidMount () {
    document.title = 'Zuul Build'
    super.componentDidMount()
  }

  state = {
    displayedFile: null
  }

  selectLogfile = (build, path) => {
    console.log('fetch', path)
    this.setState({displayedFile: path})
    this.props.dispatch(fetchLogfileIfNeeded(
      this.props.tenant,
      build,
      path,
      false))
  }

  render () {
    const { remoteData, logfile } = this.props
    const build = remoteData.builds[this.props.match.params.buildId]
    const severity = parse(this.props.location.search).severity
    console.log('page props', this.props)
    return (
      <React.Fragment>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        {build && build.manifest &&
         <Build build={build} active='logs'>
           <Manifest select={this.selectLogfile} tenant={this.props.tenant} build={build}/>
         </Build>}
        {logfile.buildLogfiles[this.state.displayedFile] && <LogFile build={build} data={logfile.buildLogfiles[this.state.displayedFile]} severity={severity}/>}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.build,
  logfile: state.logfile,
}))(BuildLogsPage)
