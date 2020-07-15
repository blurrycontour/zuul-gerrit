// Copyright 2019 Red Hat, Inc
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
import { Link } from 'react-router-dom'
import { Table } from 'patternfly-react'
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchBuildsets } from '../api'
import {
  buildQueryString,
  FilterToolbar,
  getFiltersFromUrl,
  writeFiltersToUrl,
} from '../containers/FilterToolbar'


class BuildsetsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    location: PropTypes.object,
    history: PropTypes.object,
  }

  constructor (props) {
    super()
    this.prepareTableHeaders()
    this.filterCategories = [
      {
        key: 'project',
        title: 'Project',
        placeholder: 'Filter by Project...',
        type: 'search',
      },
      {
        key: 'branch',
        title: 'Branch',
        placeholder: 'Filter by Branch...',
        type: 'search',
      },
      {
        key: 'pipeline',
        title: 'Pipeline',
        placeholder: 'Filter by Pipeline...',
        type: 'search',
      },
      {
        key: 'change',
        title: 'Change',
        placeholder: 'Filter by Change...',
        type: 'search',
      },
      // TODO (felix): We could change the result filter to a dropdown later on
      {
        key: 'result',
        title: 'Result',
        placeholder: 'Filter by Result...',
        type: 'search',
      },
      {
        key: 'uuid',
        title: 'Buildset',
        placeholder: 'Filter by Buildset UUID...',
        type: 'search',
      },
    ]

    this.state = {
      buildsets: null,
      filters: getFiltersFromUrl(props.location, this.filterCategories),
    }

  }

  updateData = (filters) => {
    // When building the filter query for the API we can't rely on the location
    // search parameters. Although, we've updated them in the updateUrl() method
    // they always have the same value in here (the values when the page was
    // first loaded). Most probably that's the case because the location is
    // passed as prop and doesn't change since the page itself wasn't
    // re-rendered.
    const queryString = buildQueryString(filters)
    this.setState({buildsets: null})
    fetchBuildsets(this.props.tenant.apiPrefix, queryString).then(response => {
      this.setState({buildsets: response.data})
    })
  }

  componentDidMount () {
    document.title = 'Zuul Buildsets'
    if (this.props.tenant.name) {
      this.updateData(this.state.filters)
    }
  }

  componentDidUpdate (prevProps) {
    const { filters } = this.state
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData(filters)
    }
  }

  handleFilterChange = (filters) => {
    const { location, history } = this.props
    // We must update the URL parameters before the state. Otherwise, the URL
    // will always be one filter selection behind the state. But as the URL
    // reflects our state this should be ok.
    writeFiltersToUrl(filters, location, history)
    this.updateData(filters)
    this.setState(() => {
      return {
        filters: filters,
      }
    })
  }

  prepareTableHeaders() {
    const headerFormat = value => <Table.Heading>{value}</Table.Heading>
    const cellFormat = (value) => <Table.Cell>{value}</Table.Cell>
    const linkChangeFormat = (value, rowdata) => (
      <Table.Cell>
        <a href={rowdata.rowData.ref_url}>
          {value ?
           rowdata.rowData.change + ',' + rowdata.rowData.patchset :
           rowdata.rowData.newrev ?
             rowdata.rowData.newrev.substr(0, 7) :
           rowdata.rowData.branch}
        </a>
      </Table.Cell>
    )
    const linkBuildsetFormat = (value, rowdata) => (
      <Table.Cell>
        <Link
          to={this.props.tenant.linkPrefix +
              '/buildset/' + rowdata.rowData.uuid}>
          {value}
        </Link>
      </Table.Cell>
    )
    this.columns = []
    this.filterTypes = []
    const myColumns = [
      'project',
      'branch',
      'pipeline',
      'change',
      'result']
    myColumns.forEach(column => {
      let prop = column
      let formatter = cellFormat
      if (column === 'change') {
        formatter = linkChangeFormat
      } else if (column === 'result') {
        formatter = linkBuildsetFormat
      }
      const label = column.charAt(0).toUpperCase() + column.slice(1)
      this.columns.push({
        header: {label: label, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
      if (column !== 'builds') {
        this.filterTypes.push({
          id: prop,
          title: label,
          placeholder: 'Filter by ' + label,
          filterType: 'text',
        })
      }
    })
    // Add buildset filter at the end
    this.filterTypes.push({
      id: 'uuid',
      title: 'Buildset',
      placeholder: 'Filter by Buildset UUID',
      filterType: 'text',
    })
  }

  renderTable (buildsets) {
    return (
      <Table.PfProvider
        striped
        bordered
        columns={this.columns}
      >
        <Table.Header/>
        <Table.Body
          rows={buildsets}
          rowKey='uuid'
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
    const { buildsets, filters } = this.state
    return (
      <PageSection variant={PageSectionVariants.light}>
        <FilterToolbar
          filterCategories={this.filterCategories}
          onFilterChange={this.handleFilterChange}
          filters={filters}
        />
        {buildsets ? this.renderTable(buildsets) : <p>Loading...</p>}
      </PageSection>
    )
  }
}

export default connect(state => ({tenant: state.tenant}))(BuildsetsPage)
