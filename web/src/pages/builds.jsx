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

class BuildsPage extends React.Component {
  constructor () {
    super()

    this.state = {
      builds: []
    }
  }

  componentDidMount () {
    fetchBuilds().then(response => {
      this.setState({builds: response.data})
    })
  }
  render () {
    const { builds } = this.state
    if (builds.length === 0) {
      return (<p>Loading...</p>)
    }
    const headerFormat = value => <Table.Heading>{value}</Table.Heading>
    const cellFormat = (value, { rowData }) => (
      <Table.Cell>{value}</Table.Cell>)
    const linkCellFormat = (value, { rowData }) => (
      <Table.Cell><a href={value} target="_blank">link</a></Table.Cell>
    )
    const columns = []
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
      columns.push({
        header: {label: column.charAt(0).toUpperCase() + column.slice(1),
          formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
    })
    return (
      <Table.PfProvider
        striped
        bordered
        columns={columns}
      >
        <Table.Header/>
        <Table.Body
          rows={builds}
          rowKey="uuid"
          onRow={(row, { rowIndex }) => {
            switch (row.result) {
              case 'SUCCESS':
                return { className: 'success' }
              default:
                return { className: 'warning' }
            }
          }} />
      </Table.PfProvider>)
  }
}

export default BuildsPage
