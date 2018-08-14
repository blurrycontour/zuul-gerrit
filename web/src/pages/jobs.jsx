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
import { Link } from 'react-router-dom'
import { store } from '../reducers'

import { fetchJobs } from '../api'

class JobsPage extends React.Component {
  constructor () {
    super()

    this.state = {
      jobs: []
    }
  }

  componentDidMount () {
    fetchJobs().then(response => {
      this.setState({jobs: response.data})
    })
  }

  render () {
    const { jobs } = this.state
    if (jobs.length === 0) {
      return (<p>Loading...</p>)
    }
    let to
    const state = store.getState()
    if (state.info.tenant) {
      to = '/builds'
    } else {
      to = '/t/' + state.tenant + '/builds'
    }

    const headerFormat = value => <Table.Heading>{value}</Table.Heading>
    const cellFormat = (value) => (
      <Table.Cell>{value}</Table.Cell>)
    const cellBuildFormat = (value) => (
      <Table.Cell>
        <Link to={to + '?job_name=' + value}>builds</Link>
      </Table.Cell>)
    const columns = []
    const myColumns = ['name', 'description', 'Last builds']
    myColumns.forEach(column => {
      let formatter = cellFormat
      let prop = column
      if (column === 'Last builds') {
        prop = 'name'
        formatter = cellBuildFormat
      }
      columns.push({
        header: {label: column,
          formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
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
          rows={jobs}
          rowKey="name"
        />
      </Table.PfProvider>)
  }
}

export default JobsPage
