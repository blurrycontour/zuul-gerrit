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
import { Link } from 'react-router-dom'

import { fetchAutoholds } from '../api'
import TableFilters from '../containers/TableFilters'


class AutoholdsPage extends TableFilters {
  static propTypes = {
    tenant: PropTypes.object
  }

  constructor () {
    super()

    this.prepareTableHeaders()
    this.state = {
      autoholds: null,
      currentFilterType: this.filterTypes[0],
      activeFilters: [],
      currentValue: ''
    }
  }

  updateData = (filters) => {
    let queryString = ''
    if (filters) {
      filters.forEach(item => queryString += '&' + item.key + '=' + item.value)
    }
    this.setState({autoholds: null})
    fetchAutoholds(this.props.tenant.apiPrefix, queryString).then(response => {
      this.setState({autoholds: response.data})
    })
  }

  componentDidMount () {
    document.title = 'Autohold Requests'
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
    const cellFormat = (value) => (
      <Table.Cell>{value}</Table.Cell>)
    const linkAutoholdRequestFormat = (value, rowdata) => (
        <Table.Cell>
            <Link to={this.props.tenant.linkPrefix + '/autohold/' + rowdata.rowData.id}>{value}</Link>
        </Table.Cell>
    )
    const countFormat = (value, rowdata) => (
        <Table.Cell>
            {value + '/' + rowdata.rowData.max_count}
        </Table.Cell>
    )
    this.columns = []
    this.filterTypes = []
    const myColumns = [
      'id',
      'project',
      'job',
      'filter',
      'count',
      'reason']
    myColumns.forEach(column => {
      let prop = column
      let formatter = cellFormat
      // Adapt column name and property name
      if (column === 'id') {
        formatter = linkAutoholdRequestFormat
      }else if (column === 'filter') {
        prop = 'ref_filter'
      } else if (column === 'count') {
        prop = 'current_count'
        formatter = countFormat
      // } else if (column === 'max count') {
      //   prop = 'max_count'
      }
      const label = column.charAt(0).toUpperCase() + column.slice(1)
      this.columns.push({
        header: {label: label, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
    })
    // Only one filter available so far
    this.filterTypes.push({
      id: 'project',
      title: 'Project',
      placeholder: 'Filter by project',
      filterType: 'text',
    })
  }

  renderTable (autoholds) {
    return (
      <Table.PfProvider
        striped
        bordered
        columns={this.columns}
      >
        <Table.Header/>
        <Table.Body
          rows={autoholds}
          rowKey='id'
          onRow={(row) => {
            switch (row.current_count < row.max_count) {
              case false:
                return { className: 'danger' }
              default:
                return { className: 'success' }
            }
          }} />
      </Table.PfProvider>)
  }

  render() {
    const { autoholds } = this.state
    return (
      <React.Fragment>
        {this.renderFilter()}
        {autoholds ? this.renderTable(autoholds) : <p>Loading...</p>}
      </React.Fragment>
    )
  }
}

export default connect(state => ({tenant: state.tenant}))(AutoholdsPage)
