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
import { Table } from 'patternfly-react'

import { fetchBuilds } from '../api'
import FilterComponent from './filterComponent'

class BuildsPage extends FilterComponent {
  constructor () {
    super()

    this.prepareTableHeaders()
    this.state = {
      builds: [],
      currentFilterType: this.filterTypes[0],
      activeFilters: [],
      currentValue: ''
    }
  }

  updateData = (filters) => {
    let queryString = ""
    if (filters) {
      filters.forEach(item => queryString += "&" + item.key + "=" + item.value)
    }
    fetchBuilds(queryString).then(response => {
      this.setState({builds: response.data})
    })
  }

  componentDidMount () {
    this.updateData()
  }

  prepareTableHeaders() {
    const headerFormat = value => <Table.Heading>{value}</Table.Heading>
    const cellFormat = (value) => (
      <Table.Cell>{value}</Table.Cell>)
    /*
     * For info about noopener noreferrer, see
     * https://mathiasbynens.github.io/rel-noopener/
     */
    const linkCellFormat = (value) => (
      <Table.Cell>
        <a href={value} target="_blank" rel="noopener noreferrer">link</a>
      </Table.Cell>
    )
    this.columns = []
    this.filterTypes = []
    const myColumns = [
      'job',
      'project',
      'branch',
      'pipeline',
      'change',
      'duration',
      'log',
      'start time',
      'result']
    myColumns.forEach(column => {
      let prop = column
      let formatter = cellFormat
      // Adapt column name and property name
      if (prop === 'job') {
        prop = 'job_name'
      } else if (prop === 'start time') {
        prop = 'start_time'
      } else if (prop === 'change') {
        prop = 'ref_url'
        formatter = linkCellFormat
      } else if (prop === 'log') {
        prop = 'log_url'
        formatter = linkCellFormat
      }
      const label = column.charAt(0).toUpperCase() + column.slice(1)
      this.columns.push({
        header: {label: label, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
      if (prop !== 'start_time' && prop !== 'ref_url' && prop !== 'duration'
          && prop !== 'log_url') {
        this.filterTypes.push({
          id: prop,
          title: label,
          placeholder: 'Filter by ' + label,
          filterType: 'text',
        })
      }
    })
  }

  renderTable (builds) {
    return (
      <Table.PfProvider
        striped
        bordered
        columns={this.columns}
      >
        <Table.Header/>
        <Table.Body
          rows={builds}
          rowKey="uuid"
          onRow={(row) => {
            switch (row.result) {
              case 'SUCCESS':
                return { className: 'success' }
              default:
                return { className: 'warning' }
            }
          }} />
      </Table.PfProvider>)
  }
  render() {
    const { builds } = this.state
    if (builds.length === 0) {
      return (<p>Loading...</p>)
    }
    return (
      <React.Fragment>
        {this.renderFilter()}
        {this.renderTable(builds)}
      </React.Fragment>
    )
  }
}

export default BuildsPage
