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

import React, { useState } from 'react'
import PropTypes from 'prop-types'
import {
  Select,
  SelectOption,
  SelectVariant,
  Toolbar,
  ToolbarContent,
  ToolbarFilter,
  ToolbarGroup,
  ToolbarItem,
} from '@patternfly/react-core'

function ComponentFilterToolbar({
  components,
  filters,
  onFilterChange,
  pagination,
}) {
  const [componentIsExpanded, setComponentIsExpanded] = useState(false)
  const [stateIsExpanded, setStateIsExpanded] = useState(false)

  function handleComponentToggle(isExpanded) {
    setComponentIsExpanded(isExpanded)
  }

  function handleComponentSelect(event, selection) {
    handleSelect('component', event, selection)
  }

  function handleStateToggle(isExpanded) {
    setStateIsExpanded(isExpanded)
  }

  function handleStateSelect(event, selection) {
    handleSelect('state', event, selection)
  }

  function handleSelect(type, event, selection) {
    const checked = event.target.checked
    const prevFilters = filters
    const prevSelections = filters[type]
    const newFilters = {
      ...prevFilters,
      [type]: checked
        ? [...prevSelections, selection]
        : prevSelections.filter((value) => value !== selection),
    }

    // Notify the parent component about the filter change
    onFilterChange(newFilters)
  }

  function handleDelete(type = '', id = '') {
    let newFilters = {}
    if (type) {
      newFilters = { ...filters }
      // Copy the old filter values for the given type, but ignore the value
      // that matches the given id.
      newFilters[type.toLowerCase()] = filters[type.toLowerCase()].filter(
        (s) => s !== id
      )
    } else {
      // Clear all filters
      newFilters = {
        component: [],
        state: [],
      }
    }

    // Notify the parent component about the filter change
    onFilterChange(newFilters)
  }

  function handleDeleteGroup(type) {
    const newFilters = { ...filters, [type.toLowerCase()]: [] }

    // Notify the parent component about the filter change
    onFilterChange(newFilters)
  }

  const componentOptions = components.map((component) => (
    <SelectOption key={`component${component}`} value={component} />
  ))

  const stateOptions = [
    <SelectOption key="stateRunning" value="RUNNING" />,
    <SelectOption key="statePaused" value="PAUSED" />,
    <SelectOption key="stateStopped" value="STOPPED" />,
  ]

  return (
    <Toolbar
      id="component-toolbar"
      clearAllFilters={handleDelete}
      collapseListedFiltersBreakpoint="md"
    >
      <ToolbarContent>
        <ToolbarGroup variant="filter-group">
          <ToolbarFilter
            chips={filters.component}
            deleteChip={handleDelete}
            deleteChipGroup={handleDeleteGroup}
            categoryName="Component"
          >
            <Select
              variant={SelectVariant.checkbox}
              aria-label="Select Component"
              onToggle={handleComponentToggle}
              onSelect={handleComponentSelect}
              selections={filters.component}
              isOpen={componentIsExpanded}
              placeholderText="Component"
            >
              {componentOptions}
            </Select>
          </ToolbarFilter>
          <ToolbarFilter
            chips={filters.state}
            deleteChip={handleDelete}
            deleteChipGroup={handleDeleteGroup}
            categoryName="State"
          >
            <Select
              variant={SelectVariant.checkbox}
              aria-label="Select State"
              onToggle={handleStateToggle}
              onSelect={handleStateSelect}
              selections={filters.state}
              isOpen={stateIsExpanded}
              placeholderText="State"
            >
              {stateOptions}
            </Select>
          </ToolbarFilter>
        </ToolbarGroup>
        <ToolbarItem variant="pagination">{pagination}</ToolbarItem>
      </ToolbarContent>
    </Toolbar>
  )
}

ComponentFilterToolbar.propTypes = {
  components: PropTypes.array.isRequired,
  filters: PropTypes.object.isRequired,
}

export default ComponentFilterToolbar
