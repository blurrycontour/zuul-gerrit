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
import { Table } from 'patternfly-react'
import * as moment from 'moment'
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchAutoholdsIfNeeded } from '../actions/autoholds'
import { Fetchable } from '../containers/Fetching'


class AutoholdsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData = (force) => {
    this.props.dispatch(fetchAutoholdsIfNeeded(this.props.tenant, force))
  }

  componentDidMount () {
    document.title = 'Zuul Autoholds'
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
    const autoholds = remoteData.autoholds
    const myAutoholds = []
    autoholds.forEach(autohold => {
      let ah = {...autohold, count_ratio: autohold.current_count + '/' + autohold.max_count}
      myAutoholds.push(ah)
    })

    const headerFormat = value => <Table.Heading>{value}</Table.Heading>
    const cellFormat = value => <Table.Cell>{value}</Table.Cell>
    const nodeExpiryFormat = value => <Table.Cell>{moment.duration(value, "seconds").humanize()}</Table.Cell>

    const columns = []
    const myColumns = [
      'id', 'project', 'job', 'ref filter', 'count', 'reason', 'nodes holding duration'
    ]
    myColumns.forEach(column => {
      let formatter = cellFormat
      let prop = column
      if (column === 'ref filter') {
        prop = 'ref_filter'
    } else if (column === 'count') {
        prop = 'count_ratio'
    } else if (column === 'nodes holding duration') {
        prop = 'node_expiration'
        formatter = nodeExpiryFormat
      }
      columns.push({
        header: {label: column, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
    })
    return (
      <PageSection variant={PageSectionVariants.light}>
        <PageSection style={{paddingRight: '5px'}}>
          <Fetchable
            isFetching={remoteData.isFetching}
            fetchCallback={this.updateData}
          />
        </PageSection>
        <Table.PfProvider
          striped
          bordered
          hover
          columns={columns}
        >
          <Table.Header/>
          <Table.Body
            rows={myAutoholds}
            rowKey="id"
          />
        </Table.PfProvider>
      </PageSection>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.autoholds,
}))(AutoholdsPage)
