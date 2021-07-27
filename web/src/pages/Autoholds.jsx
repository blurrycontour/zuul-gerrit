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
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { Flex, FlexItem, PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchAutoholdsIfNeeded } from '../actions/autoholds'
import AutoholdTable from '../containers/autohold/AutoholdTable'

import {
  AddCircleOIcon,
} from '@patternfly/react-icons'
import renderAutoholdModal from '../containers/autohold/autoholdModal'
import { IconProperty } from '../Misc'


class AutoholdsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    user: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  constructor() {
    super()
    this.state = {
      showAutoholdModal: false,
      change: '',
      ref: '',
      project: 'some project',
      job_name: 'some job',
      reason: 'some reason',
      count: 1,
      // TODO there should be a check against the max hold age defined in nodepool's config.
      // But we don't have access to it ...
      nodeHoldExpiration: 86400,
    }
  }

  setShowAutoholdModal = (value) => {
    this.setState(() => ({ showAutoholdModal: value }))
  }

  setChange = (value) => {
    this.setState(() => ({ change: value }))
  }

  setRef = (value) => {
    this.setState(() => ({ ref: value }))
  }

  setProject = (value) => {
    this.setState(() => ({ project: value }))
  }

  setJob_name = (value) => {
    this.setState(() => ({ job_name: value }))
  }

  setReason = (value) => {
    this.setState(() => ({ reason: value }))
  }

  setCount = (value) => {
    this.setState(() => ({ count: value }))
  }

  setNodeHoldExpiration = (value) => {
    this.setState(() => ({ nodeHoldExpiration: value }))
  }

  renderAutoholdButton() {
    const value = (<span style={{
      cursor: 'pointer',
      color: 'var(--pf-global--primary-color--100)'
    }}
      title="Create a new autohold request to hold nodes in case of a build failure"
      onClick={(event) => {
        event.preventDefault()
        this.setShowAutoholdModal(true)
      }}
    >
      Create Request
    </span>)
    return (
      <IconProperty
        icon={<AddCircleOIcon />}
        value={value}
      />

    )
  }

  updateData = (force) => {
    this.props.dispatch(fetchAutoholdsIfNeeded(this.props.tenant, force))
  }

  componentDidMount() {
    document.title = 'Zuul Autoholds'
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
    const { tenant, user, remoteData } = this.props
    const autoholds = remoteData.autoholds
    const { showAutoholdModal, change, ref, project, job_name, reason, count, nodeHoldExpiration } = this.state

    return (
      <>
        {(user.isAdmin && user.scope.indexOf(tenant.name) !== -1) && (
          <PageSection>
            <Flex flex={{ default: 'flex_1' }}>
              <FlexItem>
                {this.renderAutoholdButton()}
              </FlexItem>
            </Flex>
          </PageSection>
        )}
        <PageSection variant={PageSectionVariants.light}>
          <AutoholdTable
            autoholds={autoholds}
            fetching={remoteData.isFetching} />
        </PageSection>
        {renderAutoholdModal(
          tenant,
          user,
          showAutoholdModal,
          this.setShowAutoholdModal,
          change,
          this.setChange,
          ref,
          this.setRef,
          project,
          this.setProject,
          job_name,
          this.setJob_name,
          reason,
          this.setReason,
          count,
          this.setCount,
          nodeHoldExpiration,
          this.setNodeHoldExpiration,
          this.props.dispatch,
        )}
      </>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.autoholds,
  user: state.user,
}))(AutoholdsPage)
