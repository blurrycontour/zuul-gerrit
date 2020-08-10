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
import { Link } from 'react-router-dom'
import { Table } from 'patternfly-react'
import * as moment from 'moment-timezone'
import 'moment-duration-format'
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchBuilds } from '../api'
import {
  buildQueryString,
  FilterToolbar,
  getFiltersFromUrl,
  writeFiltersToUrl,
} from '../containers/FilterToolbar'

class BuildsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    timezone: PropTypes.string
  }

  constructor() {
    super()
    this.prepareTableHeaders()
    this.state = {
      builds: null,
      filters: {},
    }

    this.filterCategories = [
      {
        key: 'job_name',
        title: 'Job',
        placeholder: 'Filter by Job...',
        type: 'search',
      },
      {
        key: 'project',
        title: 'Project',
        placeholder: 'Filter by Project...',
        type: 'search',
      },
      {
        key: 'branch',
        title: 'Branch',
        placeholder: 'Filter by Brach...',
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
        title: 'Build',
        placeholder: 'Filter by Build UUID...',
        type: 'search',
      },
    ]
  }

  updateData = (filters) => {
    // When building the filter query for the API we can't rely on the location
    // search parameters. Although, we've updated them in theu URL directly
    // they always have the same value in here (the values when the page was
    // first loaded). Most probably that's the case because the location is
    // passed as prop and doesn't change since the page itself wasn't
    // re-rendered.
    const queryString = buildQueryString(filters)
    this.setState({builds: null})
    fetchBuilds(this.props.tenant.apiPrefix, queryString).then(response => {
      this.setState({builds: response.data})
    })
  }

  componentDidMount() {
    const { location } = this.props
    document.title = 'Zuul Builds'
    const filters = getFiltersFromUrl(location, this.filterCategories)
    this.setState({
      filters: filters,
    })
    if (this.props.tenant.name) {
      this.updateData(filters)
    }
  }

  componentDidUpdate(prevProps) {
    const { filters } = this.state
    if (
      this.props.tenant.name !== prevProps.tenant.name ||
      this.props.timezone !== prevProps.timezone
    ) {
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
    const cellFormat = (value) => (
      <Table.Cell>{value}</Table.Cell>)
    const linkBuildFormat = (value, rowdata) => (
      <Table.Cell>
        <Link to={this.props.tenant.linkPrefix + '/build/' + rowdata.rowData.uuid}>{value}</Link>
      </Table.Cell>
    )
    const linkChangeFormat = (value, rowdata) => (
      <Table.Cell>
        <a href={rowdata.rowData.ref_url}>{value ? rowdata.rowData.change+','+rowdata.rowData.patchset : rowdata.rowData.newrev ? rowdata.rowData.newrev.substr(0, 7) : rowdata.rowData.branch}</a>
      </Table.Cell>
    )
    const durationFormat = (value) => (
      <Table.Cell>
        {moment.duration(value, 'seconds').format('h [hr] m [min] s [sec]')}
      </Table.Cell>
    )
    const timeFormat = (value) => (
      <Table.Cell>
        {moment.utc(value).tz(this.props.timezone).format('YYYY-MM-DD HH:mm:ss')}
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
      'start time',
      'result']
    myColumns.forEach(column => {
      let prop = column
      let formatter = cellFormat
      // Adapt column name and property name
      if (column === 'job') {
        prop = 'job_name'
      } else if (column === 'start time') {
        prop = 'start_time'
        formatter = timeFormat
      } else if (column === 'change') {
        prop = 'change'
        formatter = linkChangeFormat
      } else if (column === 'result') {
        formatter = linkBuildFormat
      } else if (column === 'duration') {
        formatter = durationFormat
      }
      const label = column.charAt(0).toUpperCase() + column.slice(1)
      this.columns.push({
        header: {label: label, formatters: [headerFormat]},
        property: prop,
        cell: {formatters: [formatter]}
      })
      if (prop !== 'start_time' && prop !== 'ref_url' && prop !== 'duration'
          && prop !== 'log_url' && prop !== 'uuid') {
        this.filterTypes.push({
          id: prop,
          title: label,
          placeholder: 'Filter by ' + label,
          filterType: 'text',
        })
      }
    })
    // Add build filter at the end
    this.filterTypes.push({
      id: 'uuid',
      title: 'Build',
      placeholder: 'Filter by Build UUID',
      filterType: 'text',
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
    const { builds, filters } = this.state
    return (
      <PageSection variant={PageSectionVariants.light}>
        <FilterToolbar
          filterCategories={this.filterCategories}
          onFilterChange={this.handleFilterChange}
          filters={filters}
        />
        {builds ? this.renderTable(builds) : <p>Loading...</p>}
      </PageSection>
    )
  }
}

export default connect((state) => ({
  tenant: state.tenant,
  timezone: state.timezone,
}))(BuildsPage)
