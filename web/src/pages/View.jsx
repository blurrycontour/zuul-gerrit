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

import { fetchBuildIfNeeded, fetchViewIfNeeded } from '../actions/build'
import Refreshable from '../containers/Refreshable'
import View from '../containers/build/View'


class ViewPage extends Refreshable {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object,
  }

  updateData = (force) => {
    this.props.dispatch(fetchViewIfNeeded(
      this.props.tenant,
      this.props.match.params.buildId,
      this.props.match.params.file,
      force))
  }

  componentDidMount () {
    document.title = 'Zuul Build Viewer'
    super.componentDidMount()
  }

  render () {
    const { remoteData } = this.props
    console.log('render', remoteData)
    const build = remoteData.builds[this.props.match.params.buildId]
    return (
      <React.Fragment>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        {remoteData.viewdata && <View build={build} data={remoteData.viewdata}/>}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.build,
}))(ViewPage)
