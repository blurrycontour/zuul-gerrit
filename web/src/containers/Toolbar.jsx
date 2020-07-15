// Copyright 2020 BMW Group
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
import {
  Button,
  ButtonVariant,
  Dropdown,
  DropdownItem,
  DropdownPosition,
  DropdownToggle,
  InputGroup,
  TextInput,
  Toolbar,
  ToolbarContent,
  ToolbarFilter,
  ToolbarGroup,
  ToolbarItem,
  ToolbarToggleGroup,
} from '@patternfly/react-core'
import { FilterIcon, SearchIcon } from '@patternfly/react-icons'

class FilterToolbar extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
      isCategoryDropdownOpen: false,
      currentCategory: 'Job',
      inputValue: '',
      filters: {
        job: [],
        project: [],
        branch: [],
        pipeline: [],
        change: [],
        result: [],
        uuid: [],
      },
    }
  }

  // TODO (felix):
  // https://www.patternfly.org/v4/documentation/react/demos/filtertabledemo

  onCategoryToggle = (isOpen) => {
    this.setState({
      isCategoryDropdownOpen: isOpen,
    })
  }

  onCategorySelect = (event) => {
    this.setState({
      currentCategory: event.target.innerText,
      isCategoryDropdownOpen: !this.state.isCategoryDropdownOpen,
    })
  }

  onInputChange = (newValue) => {
    this.setState({ inputValue: newValue })
  }

  onDelete = (type = '', id = '') => {
    if (type) {
      this.setState((prevState) => {
        prevState.filters[type.toLowerCase()] = prevState.filters[
          type.toLowerCase()
        ].filter((s) => s !== id)
        return {
          filters: prevState.filters,
        }
      })
    } else {
      this.setState({
        filters: {
          job: [],
          project: [],
          branch: [],
          pipeline: [],
          change: [],
          result: [],
          uuid: [],
        },
      })
    }
  }

  onJobInput = (event, selection) => {
    if (event.key && event.key !== 'Enter') {
      return
    }

    const { inputValue } = this.state
    this.setState((prevState) => {
      const prevFilters = prevState.filters['job']
      return {
        filters: {
          ...prevState.filters,
          ['job']: prevFilters.includes(inputValue)
            ? prevFilters
            : [...prevFilters, inputValue],
        },
        inputValue: '',
      }
    })
  }

  renderCategoryDropdown = () => {
    const { isCategoryDropdownOpen, currentCategory } = this.state

    return (
      <ToolbarItem>
        <Dropdown
          onSelect={this.onCategorySelect}
          position={DropdownPosition.left}
          toggle={
            <DropdownToggle
              onToggle={this.onCategoryToggle}
              style={{ width: '100%' }}
            >
              <FilterIcon /> {currentCategory}
            </DropdownToggle>
          }
          isOpen={isCategoryDropdownOpen}
          dropdownItems={[
            <DropdownItem key="job">Job</DropdownItem>,
            <DropdownItem key="project">Project</DropdownItem>,
            <DropdownItem key="branch">Branch</DropdownItem>,
            <DropdownItem key="pipeline">Pipeline</DropdownItem>,
            <DropdownItem key="change">Change</DropdownItem>,
            <DropdownItem key="result">Result</DropdownItem>,
            <DropdownItem key="uuid">UUID</DropdownItem>,
          ]}
          style={{ width: '100%' }}
        />
      </ToolbarItem>
    )
  }

  renderFilterDropdown = () => {
    const { currentCategory, filters, inputValue } = this.state

    return (
      <ToolbarFilter
        chips={filters.job}
        deleteChip={this.onDelete}
        categoryName="Job"
        showToolbarItem={currentCategory === 'Job'}
      >
        <InputGroup>
          <TextInput
            name="jobInput"
            id="jobInput1"
            type="search"
            aria-label="job filter"
            onChange={this.onInputChange}
            value={inputValue}
            placeholder="Filter by Job..."
            onKeyDown={this.onJobInput}
          />
          <Button
            variant={ButtonVariant.control}
            aria-label="search button for search input"
            onClick={this.onJobInput}
          >
            <SearchIcon />
          </Button>
        </InputGroup>
      </ToolbarFilter>
    )
  }

  render() {
    return (
      <>
        <Toolbar
          id="toolbar-with-chip-groups"
          clearAllFilters={this.onDelete}
          collapseListedFiltersBreakpoint="xl"
        >
          <ToolbarContent>
            <ToolbarToggleGroup toggleIcon={<FilterIcon />} breakpoint="xl">
              <ToolbarGroup variant="filter-group">
                {this.renderCategoryDropdown()}
                {this.renderFilterDropdown()}
              </ToolbarGroup>
            </ToolbarToggleGroup>
          </ToolbarContent>
        </Toolbar>
      </>
    )
  }
}

export default FilterToolbar
