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

import { fetchNodes } from '../api'
import Refreshable from '../containers/TableFilters'


class NodesPage extends Refreshable {
  static propTypes = {
    tenant: PropTypes.object,
    dispatch: PropTypes.func
  }

  constructor () {
    super()
    this.prepareTableHeaders()
    this.state = {
      nodes: null,
      currentFilterType: this.filterTypes[0],
      activeFilters: [],
      currentValue: ''
    }
  }

  transformParamValueToFilterValue (key, value) {
    if (key === 'in_state_less_than' || key === 'in_state_more_than') {
      return value + ' seconds'
    } else {
      return value
    }
  }

  transformFilterValueToParamValue (key, value) {
    if (key === 'in_state_less_than' || key === 'in_state_more_than') {
      let durationValue = {}
      if (/(\d+\s*\w+)/.test(value)) {
        let durationMatch = value.match(/(\d+\s*\w+)/g)
        durationMatch.forEach(item => {
          let chunk = Array.from(item.matchAll(/(\d+)\s*(\w+)/g))[0]
          let unit = chunk[2].toLowerCase()
          if (unit === 'seconds' || unit === 'second') {
            durationValue.seconds = chunk[1]
          } else if (unit === 'minutes' || unit === 'minute') {
            durationValue.minutes = chunk[1]
          } else if (unit === 'hours' || unit === 'hour') {
            durationValue.hours = chunk[1]
          } else if (unit === 'days' || unit === 'day') {
            durationValue.days = chunk[1]
          } else {
            alert('Valid time units are "days", "hours", "minutes", "seconds"')
          }
        })
      } else {
        // assume seconds
        durationValue.seconds = value
      }
      let val = moment.duration(durationValue).asSeconds()
      return val
    } else {
      return value
    }
  }

  updateData = (filters) => {
    let queryString = ''
    if (filters) {
      filters.forEach(item =>
        queryString += '&' + item.key + '=' + this.transformFilterValueToParamValue(item.key, item.value))
    }
    this.setState({nodes: null})
    fetchNodes(this.props.tenant.apiPrefix, queryString).then(response => {
      this.setState({nodes: response.data})
    })
  }

  componentDidMount () {
    document.title = 'Zuul Nodes'
    if (this.props.tenant.name) {
      this.updateData(this.getFilterFromUrl())
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData(this.getFilterFromUrl())
    }
  }

  prepareTableHeaders() {
    const headerFormat = value => <Table.Heading>{value}</Table.Heading>
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
    this.columns = []
    this.filterTypes = []
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
      const label = column.charAt(0).toUpperCase() + column.slice(1)
      this.columns.push({
        header: {label: label, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
      if (['type', 'provider', 'state'].includes(prop)) {
        this.filterTypes.push({
          id: prop,
          title: label,
          placeholder: 'Filter by ' + label,
          filterType: 'text',
        })
      }
    })
    this.filterTypes.push({
      id: 'in_state_less_than',
      title: 'in state for less than',
      placeholder: 'seconds',
      filterType: 'text',
    })
    this.filterTypes.push({
      id: 'in_state_more_than',
      title: 'in state for more than',
      placeholder: 'seconds',
      filterType: 'text',
    })
  }

  renderTable (nodes) {
    return (
        <Table.PfProvider
          striped
          bordered
          hover
          columns={this.columns}
        >
          <Table.Header/>
          <Table.Body
            rows={nodes}
            rowKey="id"
          />
        </Table.PfProvider>
    )
  }

  render () {
    const { nodes } = this.state
    return (
      <React.Fragment>
        {this.renderFilter()}
        {nodes ? this.renderTable(nodes) : <p>Loading...</p>}
      </React.Fragment>
    )

  }

}

export default connect(state => ({
  tenant: state.tenant
}))(NodesPage)
