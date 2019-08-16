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

import {
  Spinner
} from 'patternfly-react'


class BuildLogsPage extends Refreshable {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    logFile: PropTypes.object,
    tenant: PropTypes.object
  }

  state = {
    displayedFile: null,
    lines: [],
    initialScroll: false,
    initialLogfileHeaderScroll: true,
  }

  updateData = (force) => {
    if (this.props.match.params.file) {
      this.setState({displayedFile: this.props.match.params.file})
      this.props.dispatch(fetchLogfileIfNeeded(
        this.props.tenant,
        this.props.match.params.buildId,
        this.props.match.params.file,
        force))
    } else {
      this.props.dispatch(fetchBuildIfNeeded(
        this.props.tenant, this.props.match.params.buildId, null, force))
    }
  }

  componentDidMount () {
    document.title = 'Zuul Build'
    super.componentDidMount()
  }

  highlightDidUpdate = (lines) => {
    const getLine = (nr) => {
      return document.getElementsByClassName('ln-' + nr)[0]
    }
    const getEnd = (lines) => {
      if (lines.length > 1 && lines[1] > lines[0]) {
        return lines[1]
      } else {
        return lines[0]
      }
    }
    const dehighlight = (lines) => {
      const end = getEnd(lines)
      for (let idx = lines[0]; idx <= end; idx++) {
        getLine(idx).classList.remove('highlight')
      }
    }
    const highlight = (lines) => {
      const end = getEnd(lines)
      for (let idx = lines[0]; idx <= end; idx++) {
        getLine(idx).classList.add('highlight')
      }
    }
    if (this.state.lines.length === 0 ||
        this.state.lines[0] !== lines[0] ||
        this.state.lines[1] !== lines[1]) {
      if (this.state.lines.length > 0) {
        // Reset previous selection
        dehighlight(this.state.lines)
      }
      // Store the current lines selection, this trigger highlight update
      this.setState({lines: lines, initialScroll: true})
    } else {
      // Add highlight to the selected line
      highlight(this.state.lines)
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.match.params.file !== prevProps.match.params.file) {
      this.updateData()
      this.setState({initialLogFileHeaderScroll: false})
    } else if (!this.state.initialLogFileHeaderScroll) {
      const element = document.getElementsByClassName('zuul-logfile-header')
      if (element.length) {
        const header = document.getElementsByClassName('navbar')
        if (header.length) {
          element[0].scrollIntoView()
          window.scroll(0, window.scrollY - header[0].offsetHeight - 8)
          this.setState({initialLogFileHeaderScroll: true})
        }
      }
    }
    const lines = this.props.location.hash.substring(1).split('-').map(Number)
    if (lines.length > 0) {
      const element = document.getElementsByClassName('ln-' + lines[0])
      // Lines are loaded
      if (element.length > 0) {
        if (!this.state.initialScroll) {
          // Move line into view
          const header = document.getElementsByClassName('navbar')
          if (header.length) {
            element[0].scrollIntoView()
            window.scroll(0, window.scrollY - header[0].offsetHeight - 8)
          }
        }
        // Add highlight to the selection range
        this.highlightDidUpdate(lines)
      }
    }
  }

  renderSpinner () {
    const { remoteData, logfile } = this.props
    return (
      <Spinner loading={ remoteData.isFetching || logfile.isFetching }>
      </Spinner>
    )
  }

  render () {
    const { remoteData, logfile } = this.props
    const build = remoteData.builds[this.props.match.params.buildId]
    const severity = parse(this.props.location.search).severity
    return (
      <React.Fragment>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        {build && build.manifest &&
         <Build build={build} active='logs'>
           <Manifest tenant={this.props.tenant} build={build}/>
         </Build>}
        {logfile.buildLogfiles[this.state.displayedFile] &&
         <LogFile build={build}
                  data={logfile.buildLogfiles[this.state.displayedFile]}
                  filename={this.state.displayedFile}
                  severity={severity}/>}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.build,
  logfile: state.logfile,
}))(BuildLogsPage)
