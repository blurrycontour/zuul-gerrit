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
import { Table } from 'patternfly-react'
import * as moment from 'moment'
import { Translate, I18n } from 'react-redux-i18n'

import { fetchNodesIfNeeded } from '../actions/nodes'
import Refreshable from '../containers/Refreshable'


class NodesPage extends Refreshable {
  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData (force) {
    this.props.dispatch(fetchNodesIfNeeded(this.props.tenant, force))
  }

  componentDidMount () {
    document.title = I18n.t('nodesPage.title')
    super.componentDidMount()
  }

  render () {
    const { remoteData } = this.props
    const nodes = remoteData.nodes

    const headerFormat = value => <Table.Heading><Translate value={'nodesPage.' + value} /></Table.Heading>
    const cellFormat = value => <Table.Cell>{value}</Table.Cell>
    const cellLabelsFormat = value => <Table.Cell>{value.join(',')}</Table.Cell>
    const cellPreFormat = value => (
      <Table.Cell style={{fontFamily: 'Menlo,Monaco,Consolas,monospace'}}>
        {value}
      </Table.Cell>)
    const cellAgeFormat = value => (
      <Table.Cell style={{fontFamily: 'Menlo,Monaco,Consolas,monospace'}}>
        {moment.unix(value).fromNow()}
      </Table.Cell>)
    const cellStateFormat = value => {
      let transValue = 'nodesPage.state_'
      if (value === 'in-use') {
        transValue += 'in_use'
      } else {
        transValue += value
      }
      // Do not translate the values to make it easier for users to someday filter by state
      // Instead show the translation when hovering on the cell
      return (
        <Table.Cell title={I18n.t(transValue)}>{value}</Table.Cell>
      )
    }

    const columns = []
    const myColumns = [
      'id', 'labels', 'connection', 'server', 'provider', 'state',
      'age', 'comment'
    ]
    myColumns.forEach(column => {
      let formatter = cellFormat
      let prop = column
      if (column === 'labels') {
        prop = 'type'
        formatter = cellLabelsFormat
      } else if (column === 'connection') {
        prop = 'connection_type'
      } else if (column === 'server') {
        prop = 'external_id'
        formatter = cellPreFormat
      } else if (column === 'age') {
        prop = 'state_time'
        formatter = cellAgeFormat
      }
      else if (column === 'state') {
        formatter = cellStateFormat
      }
      columns.push({
        header: {label: column, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
    })
    return (
      <React.Fragment>
        <div style={{float: 'right'}}>
          {this.renderSpinner()}
        </div>
        <Table.PfProvider
          striped
          bordered
          hover
          columns={columns}
        >
          <Table.Header/>
          <Table.Body
            rows={nodes}
            rowKey="id"
          />
        </Table.PfProvider>
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.nodes,
}))(NodesPage)
