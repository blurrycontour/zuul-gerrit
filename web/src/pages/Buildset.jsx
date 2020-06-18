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
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import { MessageDialog, Icon } from 'patternfly-react'

import { fetchBuildsetIfNeeded } from '../actions/build'
import Refreshable from '../containers/Refreshable'
import Buildset from '../containers/build/Buildset'
import { enqueue, enqueue_ref } from '../api'
import { addEnqueueError } from '../actions/adminActions'


class BuildsetPage extends Refreshable {
  static propTypes = {
    match: PropTypes.object.isRequired,
    remoteData: PropTypes.object,
    tenant: PropTypes.object,
    user: PropTypes.object,
  }
  state = {
    showEnqueueModal: false,
  }

  updateData = (force) => {
    this.props.dispatch(fetchBuildsetIfNeeded(
      this.props.tenant, this.props.match.params.buildsetId, force))
  }

  componentDidMount () {
    document.title = 'Zuul Buildset'
    super.componentDidMount()
  }

  enqueueConfirm = () => {
    const { remoteData, tenant, user } = this.props
    const buildset = remoteData.buildsets[this.props.match.params.buildsetId]
    let changeId = buildset.change ? buildset.change + ',' + buildset.patchset : buildset.newrev
    this.setState(() => ({showEnqueueModal: false}))
    if (/^[0-9a-f]{40}$/.test(changeId)) {
      const oldrev = '0000000000000000000000000000000000000000'
      enqueue_ref(tenant.apiPrefix, buildset.project, buildset.pipeline, buildset.ref, oldrev, changeId, user.user.access_token)
        .then(() => {
          alert('Change queued successfully.')
        })
        .catch(error => {
          this.props.dispatch(addEnqueueError(error))
        })
    } else {
      enqueue(tenant.apiPrefix, buildset.project, buildset.pipeline, changeId, user.user.access_token)
      .then(() => {
        alert('Change queued successfully.')
      })
      .catch(error => {
        this.props.dispatch(addEnqueueError(error))
      })
    }
  }

  enqueueCancel = () => {
    this.setState(() => ({showEnqueueModal: false}))
  }

  renderEnqueueButton () {
    return (
      <div style={{float: 'right'}}>
      <button className='btn btn-default' onClick={() => {
        this.setState(() => ({showEnqueueModal: true}))
          }}>
        <Icon type='pf' name='restart' title='Enqueue'/>&nbsp;Re-enqueue
      </button>
      </div>
    )
  }

  renderEnqueueMessageDialog() {
    const { remoteData } = this.props
    const buildset = remoteData.buildsets[this.props.match.params.buildsetId]
    console.log(buildset)
    const changeId = buildset.change ? buildset.change + ',' + buildset.patchset : buildset.newrev.substr(0, 7)
    const primaryContent = <p>You are about to re-enqueue change <strong>{ changeId }</strong> on pipeline <strong>{ buildset.pipeline }</strong>.</p>
    const secondaryContent = <p>Please confirm that you want to trigger a re-enqueue.</p>
    const icon = <Icon type='pf' name='warning-triangle-o' />
    return (
        <MessageDialog
          show={this.state.showEnqueueModal}
          onHide={this.enqueueCancel}
          primaryAction={this.enqueueConfirm}
          secondaryAction={this.enqueueCancel}
          primaryActionButtonContent="Confirm"
          secondaryActionButtonContent="Cancel"
          title="Re-enqueue Change?"
          icon={icon}
          primaryContent={primaryContent}
          secondaryContent={secondaryContent}
          accessibleName="enqueueWarningDialog"
          accessibleDescription="enqueueWarningDialogContent"
        />
    )
  }

  render () {
    const { remoteData, user, tenant } = this.props
    const buildset = remoteData.buildsets[this.props.match.params.buildsetId]
    const enqueueButton = (user.adminTenants && user.adminTenants.indexOf(tenant.name) !== -1) ? this.renderEnqueueButton() : ''
    return (
      <React.Fragment>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        { enqueueButton }
        {buildset && <Buildset buildset={buildset}/>}
        {buildset && this.renderEnqueueMessageDialog()}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.build,
  user: state.user,
}))(BuildsetPage)
