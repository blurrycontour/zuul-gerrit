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

import { FilterSelect } from './filters/Select'
import { FilterTernarySelect } from './filters/TernarySelect'
import { FilterCheckbox } from './filters/Checkbox'


function FilterToolbar(props) {
  const [isCategoryDropdownOpen, setIsCategoryDropdownOpen] = useState(false)
  const [currentCategory, setCurrentCategory] = useState(
    props.filterCategories[0].title
  )
  const [inputValue, setInputValue] = useState('')

  function handleCategoryToggle(isOpen) {
    setIsCategoryDropdownOpen(isOpen)
  }

  function handleCategorySelect(event) {
    setCurrentCategory(event.target.innerText)
    setIsCategoryDropdownOpen(!isCategoryDropdownOpen)
  }

  function handleInputChange(newValue) {
    setInputValue(newValue)
  }

  function handleInputSend(event, category) {
    const { onFilterChange, filters } = props

    // In case the event comes from a key press, only accept "Enter"
    if (event.key && event.key !== 'Enter') {
      return
    }

    // Ignore empty values
    if (!inputValue) {
      return
    }

    const prevFilters = filters[category.key]
    const newFilters = {
      ...filters,
      [category.key]: prevFilters.includes(inputValue)
        ? prevFilters
        : [...prevFilters, inputValue],
    }

    // Clear the input field
    setInputValue('')
    // Notify the parent component about the filter change
    onFilterChange(newFilters)
  }

  function handleDelete(type = '', id = '', category) {
    const { filterCategories, filters, onFilterChange } = props

    // Usually the type contains the category for which a chip should be deleted
    // If the type is set, we got a delete() call for a single chip. The type
    // reflects the name of the Chip group which does not necessarily go in hand
    // with our category keys. Thus, we use the category to identify the correct
    // filter to be updated/removed.
    let newFilters = {}
    if (type) {
      if (category.type === 'ternary') {
        newFilters = {
          ...filters,
          [category.key]: [],
        }
      } else {
        newFilters = {
          ...filters,
          [category.key]: filters[category.key].filter((s) => s !== id),
        }
      }
    } else {
      // Delete the values for each filter category
      newFilters = filterCategories.reduce((filterDict, category) => {
        filterDict[category.key] = []
        return filterDict
      }, {})
    }

    // Notify the parent component about the filter change
    onFilterChange(newFilters)
  }

  function renderCategoryDropdown() {
    const { filterCategories } = props

    return (
      <ToolbarItem>
        <Dropdown
          onSelect={handleCategorySelect}
          position={DropdownPosition.left}
          toggle={
            <DropdownToggle
              onToggle={handleCategoryToggle}
              style={{ width: '100%' }}
            >
              <FilterIcon /> {currentCategory}
            </DropdownToggle>
          }
          isOpen={isCategoryDropdownOpen}
          dropdownItems={filterCategories.filter(
            (category) => (category.type === 'search' ||
              category.type === 'select' ||
              category.type === 'ternary' ||
              category.type === 'checkbox')
          ).map((category) => (
            <DropdownItem key={category.key}>{category.title}</DropdownItem>
          ))}
          style={{ width: '100%' }}
        />
      </ToolbarItem>
    )
  }

  function renderFilterInput(category, filters) {
    const { onFilterChange } = props
    if (category.type === 'search') {
      return (
        <InputGroup>
          <TextInput
            name={`${category.key}-input`}
            id={`${category.key}-input`}
            type="search"
            aria-label={`${category.key} filter`}
            onChange={handleInputChange}
            value={inputValue}
            placeholder={category.placeholder}
            onKeyDown={(event) => handleInputSend(event, category)}
          />
          <Button
            variant={ButtonVariant.control}
            aria-label="search button for search input"
            onClick={(event) => handleInputSend(event, category)}
          >
            <SearchIcon />
          </Button>
        </InputGroup>
      )
    } else if (category.type === 'select') {
      return (
        <InputGroup>
          <FilterSelect
            onFilterChange={onFilterChange}
            filters={filters}
            category={category}
          />
        </InputGroup>
      )
    } else if (category.type === 'ternary') {
      return (
        <InputGroup>
          <FilterTernarySelect
            onFilterChange={onFilterChange}
            filters={filters}
            category={category}
          />
        </InputGroup>
      )
    } else if (category.type === 'checkbox') {
      return (
        <InputGroup>
          <br />
          <FilterCheckbox
            onFilterChange={onFilterChange}
            filters={filters}
            category={category}
          />
        </InputGroup>
      )
    }
  }

  function renderFilterDropdown() {
    const { filterCategories, filters } = props

    return (
      <>
        {filterCategories.map((category) => (
          <ToolbarFilter
            key={category.key}
            chips={getChipsFromFilters(filters, category)}
            deleteChip={(type, id) => handleDelete(type, id, category)}
            categoryName={category.title}
            showToolbarItem={currentCategory === category.title}
          >
            {renderFilterInput(category, filters)}
          </ToolbarFilter>
        ))}
      </>
    )
  }

  return (
    <>
      <Toolbar
        id="toolbar-with-chip-groups"
        clearAllFilters={handleDelete}
        collapseListedFiltersBreakpoint="md"
      >
        <ToolbarContent>
          <ToolbarToggleGroup toggleIcon={<FilterIcon />} breakpoint="md">
            <ToolbarGroup variant="filter-group">
              {renderCategoryDropdown()}
              {renderFilterDropdown()}
            </ToolbarGroup>
          </ToolbarToggleGroup>
        </ToolbarContent>
      </Toolbar>
    </>
  )
}

FilterToolbar.propTypes = {
  onFilterChange: PropTypes.func.isRequired,
  filters: PropTypes.object.isRequired,
  filterCategories: PropTypes.array.isRequired,
}

function getChipsFromFilters(filters, category) {
  if (category.type === 'ternary') {
    switch ([...filters[category.key]].pop()) {
      case 1:
      case '1':
        return ['True',]
      case 0:
      case '0':
        return ['False',]
      default:
        return []
    }
  } else {
    return filters[category.key]
  }
}

function getFiltersFromUrl(location, filterCategories) {
  const urlParams = new URLSearchParams(location.search)
  const filters = filterCategories.reduce((filterDict, item) => {
    // Initialize each filter category with an empty list
    filterDict[item.key] = []

    // And update the list with each matching element from the URL query
    urlParams.getAll(item.key).forEach((param) => {
      if (item.type === 'checkbox') {
        switch (param) {
          case '1':
            filterDict[item.key].push(1)
            break
          case '0':
            filterDict[item.key].push(0)
            break
          default:
            break
        }
      } else {
        filterDict[item.key].push(param)
      }
    })
    return filterDict
  }, {})
  return filters
}

function writeFiltersToUrl(filters, location, history) {
  // Build new URL parameters from the filters in state
  const searchParams = new URLSearchParams('')
  Object.keys(filters).map((key) => {
    filters[key].forEach((value) => {
      searchParams.append(key, value)
    })
    return searchParams
  })
  history.push({
    pathname: location.pathname,
    search: searchParams.toString(),
  })
}

function buildQueryString(filters) {
  let queryString = '&complete=true'
  if (filters) {
    Object.keys(filters).map((key) => {
      filters[key].forEach((value) => {
        queryString += '&' + key + '=' + value
      })
      return queryString
    })
  }
  return queryString
}

export { buildQueryString, FilterToolbar, getFiltersFromUrl, writeFiltersToUrl }
