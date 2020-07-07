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
import { BuildIcon } from '@patternfly/react-icons'

import { fetchBuildIfNeeded } from '../actions/build'
import { EmptyPage } from '../containers/Errors'
import { Fetchable, Fetching } from '../containers/Fetching'
import Build from '../containers/build/Build'
import Console from '../containers/build/Console'

class BuildConsolePage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object,
    dispatch: PropTypes.func,
    location: PropTypes.object,
  }

  updateData = (force) => {
    this.props.dispatch(
      fetchBuildIfNeeded(
        this.props.tenant,
        this.props.match.params.buildId,
        null,
        force
      )
    )
  }

  componentDidMount() {
    document.title = 'Zuul Build'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate(prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  render() {
    const { remoteData, tenant } = this.props
    const build = remoteData.builds[this.props.match.params.buildId]
    const hash = this.props.location.hash.substring(1).split('/')

    if (!build && remoteData.isFetching) {
      return <Fetching />
    }

    if (build && build.output) {
      const fetchable = (
        <Fetchable
          isFetching={remoteData.isFetching}
          fetchCallback={this.updateData}
        />
      )

      return (
        <Build build={build} active="console" fetchable={fetchable}>
          <Console
            output={build.output}
            errorIds={build.errorIds}
            displayPath={hash.length > 0 ? hash : undefined}
          />
        </Build>
      )
    }

    return (
      <EmptyPage
        title="This build does not exist"
        icon={BuildIcon}
        linkTarget={`${tenant.linkPrefix}/builds`}
        linkText="Show all builds"
      />
    )
  }
}

export default connect((state) => ({
  tenant: state.tenant,
  remoteData: state.build,
}))(BuildConsolePage)
