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
import 'moment-duration-format'
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchBuilds } from '../api'
import {
  buildQueryString,
  FilterToolbar,
  getFiltersFromUrl,
  writeFiltersToUrl,
} from '../containers/FilterToolbar'
import BuildTable from '../containers/build/BuildTable'

class BuildsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    timezone: PropTypes.string,
    location: PropTypes.object,
    history: PropTypes.object,
  }

  constructor(props) {
    super()
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
      {
        key: 'result',
        title: 'Result',
        placeholder: 'Any result',
        type: 'select',
        // TODO there should be a single source of truth for this
        options: [
          'SUCCESS',
          'FAILURE',
          'RETRY_LIMIT',
          'POST_FAILURE',
          'SKIPPED',
          'NODE_FAILURE',
          'MERGER_FAILURE',
          'CONFIG_ERROR',
          'TIMED_OUT',
          'CANCELED',
          'ERROR',
          'RETRY',
          'DISK_FULL',
          'NO_JOBS',
          'DISCONNECT',
          'ABORTED',
          'LOST',
          'EXCEPTION',
          'NO_HANDLE'],
      },
      {
        key: 'uuid',
        title: 'Build',
        placeholder: 'Filter by Build UUID...',
        type: 'search',
      },
      {
        key: 'held',
        title: 'Held',
        placeholder: 'Choose Hold Status...',
        type: 'ternary',
        options: [
          'All',
          'Held Builds Only',
          'Non Held Builds Only',
        ]
      },
      {
        key: 'voting',
        title: 'Voting',
        placeholder: 'Choose Voting Status...',
        type: 'ternary',
        options: [
          'All',
          'Voting Only',
          'Non-Voting Only',
        ]
      },
    ]

    this.state = {
      builds: [],
      fetching: false,
      filters: getFiltersFromUrl(props.location, this.filterCategories),
    }
  }

  updateData = (filters) => {
    // When building the filter query for the API we can't rely on the location
    // search parameters. Although, we've updated them in theu URL directly
    // they always have the same value in here (the values when the page was
    // first loaded). Most probably that's the case because the location is
    // passed as prop and doesn't change since the page itself wasn't
    // re-rendered.
    const queryString = buildQueryString(filters)
    this.setState({ fetching: true })
    // TODO (felix): What happens in case of a broken network connection? Is the
    // fetching shows infinitely or can we catch this and show an erro state in
    // the table instead?
    fetchBuilds(this.props.tenant.apiPrefix, queryString).then((response) => {
      this.setState({
        builds: response.data,
        fetching: false,
      })
    })
  }

  componentDidMount() {
    document.title = 'Zuul Builds'
    if (this.props.tenant.name) {
      this.updateData(this.state.filters)
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

  handleClearFilters = () => {
    // Delete the values for each filter category
    const filters = this.filterCategories.reduce((filterDict, category) => {
      filterDict[category.key] = []
      return filterDict
    }, {})
    this.handleFilterChange(filters)
  }

  render() {
    const { history } = this.props
    const { builds, fetching, filters } = this.state
    return (
      <PageSection variant={PageSectionVariants.light}>
        <FilterToolbar
          filterCategories={this.filterCategories}
          onFilterChange={this.handleFilterChange}
          filters={filters}
        />
        <BuildTable
          builds={builds}
          fetching={fetching}
          onClearFilters={this.handleClearFilters}
          history={history}
        />
      </PageSection>
    )
  }
}

export default connect((state) => ({
  tenant: state.tenant,
  timezone: state.timezone,
}))(BuildsPage)
