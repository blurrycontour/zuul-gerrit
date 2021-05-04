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
import { PageSection, PageSectionVariants } from '@patternfly/react-core'

import { fetchBuildsets } from '../api'
import {
  buildQueryString,
  FilterToolbar,
  getFiltersFromUrl,
  writeFiltersToUrl,
} from '../containers/FilterToolbar'
import BuildsetTable from '../containers/build/BuildsetTable'

class BuildsetsPage extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    location: PropTypes.object,
    history: PropTypes.object,
  }

  constructor(props) {
    super()
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
      {
        key: 'result',
        title: 'Result',
        placeholder: 'Filter by Result...',
        type: 'select',
        // are there more?
        options: [
          'SUCCESS',
          'FAILURE',
          'MERGER_FAILURE',
        ]
      },
      {
        key: 'uuid',
        title: 'Buildset',
        placeholder: 'Filter by Buildset UUID...',
        type: 'search',
      },
    ]

    this.state = {
      buildsets: [],
      fetching: false,
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
    this.setState({ fetching: true })
    fetchBuildsets(this.props.tenant.apiPrefix, queryString).then(
      (response) => {
        this.setState({
          buildsets: response.data,
          fetching: false,
        })
      }
    )
  }

  componentDidMount() {
    document.title = 'Zuul Buildsets'
    if (this.props.tenant.name) {
      this.updateData(this.state.filters)
    }
  }

  componentDidUpdate(prevProps) {
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
    const { buildsets, fetching, filters } = this.state
    return (
      <PageSection variant={PageSectionVariants.light}>
        <FilterToolbar
          filterCategories={this.filterCategories}
          onFilterChange={this.handleFilterChange}
          filters={filters}
        />
        <BuildsetTable
          buildsets={buildsets}
          fetching={fetching}
          onClearFilters={this.handleClearFilters}
          history={history}
        />
      </PageSection>
    )
  }
}

export default connect((state) => ({ tenant: state.tenant }))(BuildsetsPage)
