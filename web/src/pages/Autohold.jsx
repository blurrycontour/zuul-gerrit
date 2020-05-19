// Copyright 2020 Red Hat, Inc
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
import { ThumbTackIcon } from '@patternfly/react-icons'

import { EmptyPage } from '../containers/Errors'
import { fetchAutoholdRequestIfNeeded } from '../actions/autohold'
import { Fetchable, Fetching } from '../containers/Fetching'
import AutoholdRequest from '../containers/autohold/autoholdRequest'


class AutoholdRequestPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object
  }

  updateData = (force) => {
    this.props.dispatch(fetchAutoholdRequestIfNeeded(
      this.props.tenant, this.props.match.params.autoholdRequestId, force))
  }

  componentDidMount () {
    document.title = 'Autohold Request'
    super.componentDidMount()
  }

  render () {
    const { remoteData } = this.props
    const autoholdRequest = remoteData.autoholdRequests[this.props.match.params.autoholdRequestId]
    const tenant = this.props.tenant

    if (!autoholdRequest && remoteData.isFetching) {
      return <Fetching />
    }

    if (!autoholdRequest) {
      return (
        <EmptyPage
          title="Request not found"
          icon={ThumbTackIcon}
          linkTarget={`${tenant.linkPrefix}/autoholds`}
          linkText="Show all autohold requests"
        />
      )
    }

    const fetchable = (
      <Fetchable
        isFetching={remoteData.isFetching}
        fetchCallback={this.updateData}
      />
    )

    return (
      <React.Fragment>
        {autoholdRequest && <AutoholdRequest autoholdRequest={autoholdRequest}/>}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
    tenant: state.tenant,
    remoteData: state.autohold,
}))(AutoholdRequestPage)
