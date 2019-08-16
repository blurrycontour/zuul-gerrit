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

import { fetchLogfileIfNeeded } from '../actions/logfile'
import Refreshable from '../containers/Refreshable'
import LogFile from '../containers/logfile/LogFile'


class LogFilePage extends Refreshable {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object,
  }

  state = {
    lines: []
  }

  updateData = (force) => {
    this.props.dispatch(fetchLogfileIfNeeded(
      this.props.tenant,
      this.props.match.params.buildId,
      this.props.match.params.file,
      force))
  }

  componentDidMount () {
    document.title = 'Zuul Build Logfile'
    super.componentDidMount()
  }

  saveSelection = (lines) => {
    this.setState({lines: lines})
  }

  componentDidUpdate () {
    const lines = this.props.location.hash.substring(1).split('-').map(Number)
    const getLine = (nr) => {
      return document.getElementsByName(nr)[0].parentNode.parentNode
    }
    const dehighlight = (lines) => {
      let end = lines[0] + 1
      if (lines.length > 1) {
        end = lines[1]
      }
      for (let idx = lines[0]; idx <= end; idx++) {
        getLine(idx).classList.remove('highlight')
      }
    }
    if (lines.length > 0) {
      const element = document.getElementsByName(lines[0])
      // Lines are loaded
      if (element.length > 0) {
        if (this.state.lines.length === 0) {
          // Take note of the selected line
          this.saveSelection(lines)
        } else {
          if (this.state.lines[0] !== lines[0] ||
              this.state.lines[1] !== lines[1]) {
            // Reset selection
            dehighlight(this.state.lines)
            this.saveSelection(lines)
          } else {
            // Add highlight to the selected line
            const lineElem = getLine(lines[0])
            lineElem.classList.add('highlight')

            // Move line into view
            const header = document.getElementsByClassName('navbar')
            if (header.length) {
              element[0].scrollIntoView()
              window.scroll(0, window.scrollY - header[0].offsetHeight)
            }

            // Add highlight to the selection range
            if (lines.length > 1 && lines[1] > lines[0]) {
              for (let idx = lines[0]; idx <= lines[1]; idx++) {
                getLine(idx).classList.add('highlight')
              }
            }
          }
        }
      }
    }
  }

  render () {
    const { remoteData } = this.props
    const build = this.props.build.builds[this.props.match.params.buildId]
    const severity = parse(this.props.location.search).severity
    return (
      <React.Fragment>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        {remoteData.data && <LogFile build={build} data={remoteData.data} severity={severity}/>}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.logfile,
  build: state.build
}))(LogFilePage)
