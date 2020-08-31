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
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchBuildIfNeeded } from '../actions/build'
import { Fetchable } from '../containers/Fetching'
import Build from '../containers/build/Build'


class BuildPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object,
    dispatch: PropTypes.func,
    activeTab: PropTypes.string.isRequired,
    location: PropTypes.object,
  }

  updateData = (force) => {
    this.props.dispatch(fetchBuildIfNeeded(
      this.props.tenant, this.props.match.params.buildId, null, force))
  }

  componentDidMount () {
    document.title = 'Zuul Build'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  render () {
    const { remoteData, activeTab, location } = this.props
    const build = remoteData.builds[this.props.match.params.buildId]
    const hash = location.hash.substring(1).split('/')
    return (
      <PageSection variant={PageSectionVariants.light}>
        <PageSection style={{paddingRight: '5px'}}>
          <Fetchable
            isFetching={remoteData.isFetching}
            fetchCallback={this.updateData}
          />
        </PageSection>
        {build && <Build build={build} active={activeTab} hash={hash}/>}
      </PageSection>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.build,
}))(BuildPage)
