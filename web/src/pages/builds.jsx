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
  constructor() {
    super()

    this.state = {
      builds: [],
    }
  }

  componentDidMount() {
    fetchBuilds().then(response => {
      this.setState({builds: response.data})
    })
  }
  render() {
    const { builds } = this.state
    if (builds.length === 0) {
      return (<p>Loading...</p>)
    }
    const headerFormat = value => <Table.Heading>{value}</Table.Heading>
    const cellFormat = (value, { rowData }) => (
        <Table.Cell>{value}</Table.Cell>)
    const columns = []
    const myColumns = ['job', 'project', 'branch', 'pipeline', 'result']
    myColumns.forEach(column => {
      let prop = column
      if (prop === 'job') {
        prop = 'job_name'
      }
      columns.push({
        header: {label: column,
                 formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [cellFormat]},
      })
    })
    return (
      <Table.PfProvider
        striped
        bordered
        hover
        columns={columns}
        >
        <Table.Header/>
        <Table.Body
          rows={builds}
          rowKey="uuid"
          />
      </Table.PfProvider>)
  }
}

export default BuildsPage
