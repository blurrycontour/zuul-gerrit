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
import {
  Icon
} from 'patternfly-react'
import {
  PageSection,
  PageSectionVariants,
} from '@patternfly/react-core'

import {
  FilterToolbar,
  getFiltersFromUrl,
  writeFiltersToUrl,
} from '../containers/FilterToolbar'
import { fetchConfigErrorsAction } from '../actions/configErrors'
import ConfigErrorTable from '../containers/configerrors/ConfigErrorTable'

class ConfigErrorsPage extends React.Component {
  static propTypes = {
    configErrors: PropTypes.array,
    configErrorsReady: PropTypes.bool,
    tenant: PropTypes.object,
    dispatch: PropTypes.func,
    preferences: PropTypes.object,
    history: PropTypes.object,
    location: PropTypes.object,
  }

  constructor(props) {
    super()
    this.filterCategories = [
      {
        key: 'project',
        title: 'Project',
        placeholder: 'Filter by project...',
        type: 'search',
      },
      {
        key: 'branch',
        title: 'Branch',
        placeholder: 'Filter by branch...',
        type: 'search',
      },
      {
        key: 'severity',
        title: 'Severity',
        placeholder: 'Filter by severity...',
        type: 'search',
      },
      {
        key: 'name',
        title: 'Name',
        placeholder: 'Filter by name...',
        type: 'search',
      },
    ]

    const _filters = getFiltersFromUrl(props.location, this.filterCategories)
    this.state = {
      filters: _filters,
    }
  }

  componentDidMount () {
    document.title = 'Zuul Configuration Errors'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  updateData = () => {
    this.props.dispatch(fetchConfigErrorsAction(this.props.tenant))
  }

  filterInputValidation = (filterKey, filterValue) => {
    // Input value should not be empty for all cases
    if (!filterValue) {
      return {
        success: false,
        message: 'Input should not be empty'
      }
    }

    return {
      success: true
    }
  }

  handleFilterChange = (newFilters) => {
    const { location, history } = this.props

    // We must update the URL parameters before the state. Otherwise, the URL
    // will always be one filter selection behind the state. But as the URL
    // reflects our state this should be ok.
    writeFiltersToUrl(newFilters, location, history)
    this.setState({filters: newFilters})
  }

  handleClearFilters = () => {
    // Delete the values for each filter category
    const filters = this.filterCategories.reduce((filterDict, category) => {
      filterDict[category.key] = []
      return filterDict
    }, {})
    this.handleFilterChange(filters)
  }

  filterErrors = (errors, filters) => {
    return errors.filter((error) => {
      if (filters.project.length &&
          !filters.project.includes(error.source_context.project)) {
        return false
      }
      if (filters.branch.length &&
          !filters.branch.includes(error.source_context.branch)) {
        return false
      }
      if (filters.severity.length &&
          !filters.severity.includes(error.severity)) {
        return false
      }
      if (filters.name.length &&
          !filters.name.includes(error.name)) {
        return false
      }
      return true
    })
  }

  render () {
    const { configErrors, configErrorsReady, history } = this.props
    return (
      <PageSection variant={this.props.preferences.darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <div className="pull-right">
          {/* Lint warning jsx-a11y/anchor-is-valid */}
          {/* eslint-disable-next-line */}
          <a className="refresh" onClick={() => {this.updateData()}}>
            <Icon type="fa" name="refresh" /> refresh&nbsp;&nbsp;
          </a>
        </div>
        <FilterToolbar
          filterCategories={this.filterCategories}
          onFilterChange={this.handleFilterChange}
          filters={this.state.filters}
          filterInputValidation={this.filterInputValidation}
        />
        <ConfigErrorTable
          errors={this.filterErrors(configErrors, this.state.filters)}
          fetching={!configErrorsReady}
          onClearFilters={this.handleClearFilters}
          history={history}
        />
      </PageSection>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  configErrors: state.configErrors.errors,
  configErrorsReady: state.configErrors.ready,
  preferences: state.preferences,
}))(ConfigErrorsPage)
