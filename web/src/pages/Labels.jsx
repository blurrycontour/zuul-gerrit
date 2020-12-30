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

import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
} from '@patternfly/react-table'

import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchLabelsIfNeeded } from '../actions/labels'
import { Fetchable, Fetching } from '../containers/Fetching'


class LabelsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData (force) {
    this.props.dispatch(fetchLabelsIfNeeded(this.props.tenant, force))
  }

  componentDidMount () {
    document.title = 'Zuul Labels'
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
    const { remoteData } = this.props
    const labels = remoteData.labels[this.props.tenant.name] || []

    if (!labels) {
      return <Fetching />
    }

    const columns = [{title: 'Name'}]
    const rows = labels.map(l => [l.name])

    return (
      <PageSection variant={PageSectionVariants.light}>
        <PageSection style={{paddingRight: '5px'}}>
          <Fetchable
            isFetching={remoteData.isFetching}
            fetchCallback={this.updateData}
          />
        </PageSection>
        <Table
          aria-label="Labels Table"
          variant={TableVariant.compact}
          cells={columns}
          rows={rows}
        >
          <TableHeader />
          <TableBody />
        </Table>
      </PageSection>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.labels,
}))(LabelsPage)
