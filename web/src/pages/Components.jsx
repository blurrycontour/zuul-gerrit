// Copyright 2021 BMW Group
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

import React, { useEffect, useState } from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import {
  EmptyState,
  EmptyStateVariant,
  EmptyStateIcon,
  PageSection,
  PageSectionVariants,
  Pagination,
  Text,
  TextContent,
  Title,
} from '@patternfly/react-core'
import { ServiceIcon } from '@patternfly/react-icons'

import { fetchComponents } from '../actions/component'
import { Fetching } from '../containers/Fetching'
import ComponentTable from '../containers/component/ComponentTable'
import ComponentFilterToolbar from '../containers/component/ComponentFilter'

function ComponentsPage({ components, isFetching, fetchComponents }) {
  const [filteredComponents, setFilteredComponents] = useState([])
  const [filters, setFilters] = useState({ component: [], state: [] })
  const [perPage, setPerPage] = useState(50)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(500)

  useEffect(() => {
    document.title = 'Zuul Components'
    // Fetch the components once on initial page load
    console.log("fetch components")
    fetchComponents()
    console.log("components fetched")
    console.log(components)
  }, [fetchComponents])

  useEffect(() => {
    function filterComponents() {
      console.log("Filtering components...")
      console.log(components)
      const filteredComponents = {}
      for (const [kind, _components] in Object.entries(components)) {
        console.log(kind)
        console.log(_components)
        filteredComponents[kind] = _components.filter((component) => {
          return (
            // Return true for each component that should be included in the result.
            // This means either a filter is empty (=== 0) or some of the filter
            // values matches the component's attribute.
            (filters.component.length === 0 ||
              filters.component.some(
                (filterKind) => component.kind === filterKind
              )) &&
            (filters.state.length === 0 ||
              filters.state.some(
                (filterState) => component.state === filterState
              ))
          )
        })
      }
      console.log(filteredComponents)
      return filteredComponents
    }

    // Filter and page the components whenever any of the relevant data changes.
    // This includes the original components array, the filters and the
    // pagination variables.
    const filteredComponents = filterComponents()
    const filteredAndPagedComponents = filteredComponents.slice(
      (page - 1) * perPage,
      page * perPage
    )

    // The total value must be set to the length of the filtered components
    // without the pagination applied.
    setTotal(filteredComponents.length)
    // The filtered components list will only contain the current page to be
    // shown in the table.
    setFilteredComponents(filteredAndPagedComponents)
  }, [filters, components, page, perPage])

  function handleFilterChange(filters) {
    setFilters(filters)
  }

  function handleClearFilters() {
    const newFilters = {
      component: [],
      state: [],
    }
    handleFilterChange(newFilters)
  }

  function handlePageChange(pageNumber, perPage) {
    // "Normalized" callback function that handles various onClick handlers of
    // the Pagination component.
    setPage(pageNumber)
    setPerPage(perPage)
  }

  // TODO (felix): Let the table handle the empty state and the fetching,
  // similar to the builds table.
  const content =
    components === undefined || isFetching ? (
      <Fetching />
    ) : Object.keys(components).length === 0 ? (
      <EmptyState variant={EmptyStateVariant.small}>
        <EmptyStateIcon icon={ServiceIcon} />
        <Title headingLevel="h4" size="lg">
          It looks like no components are connected to ZooKeeper
        </Title>
      </EmptyState>
    ) : (
      <>
        <ComponentFilterToolbar
          // The FilterToolbar doesn't need to know this is actually a set, so
          // convert it to an array for simpler usage inside this component.
          // There seems to be also no PropTypes to differentiate between array
          // and set although the iterator methods are different.
          components={[...Object.keys(components)]}
          filters={filters}
          onFilterChange={handleFilterChange}
          pagination={
            // We define the pagination directly in here and pass it to the
            // FilterToolbar to avoid passing all the necessary callbacks and
            // props through both components.
            <Pagination
              itemCount={total}
              page={page}
              perPage={perPage}
              isCompact
              onSetPage={(_, pageNumber, perPage) =>
                handlePageChange(pageNumber, perPage)
              }
              onPerPageSelect={(_, perPage, pageNumber) =>
                handlePageChange(pageNumber, perPage)
              }
            />
          }
        />
        <ComponentTable
          components={filteredComponents}
          onClearFilters={handleClearFilters}
        />
      </>
    )

  return (
    <>
      <PageSection variant={PageSectionVariants.light}>
        <TextContent>
          <Text component="h1">Components</Text>
          <Text component="p">
            This page shows all Zuul components and their current state.
          </Text>
        </TextContent>
        {content}
      </PageSection>
    </>
  )
}

ComponentsPage.propTypes = {
  components: PropTypes.object.isRequired,
  isFetching: PropTypes.bool.isRequired,
  fetchComponents: PropTypes.func.isRequired,
}

function mapStateToProps(state) {
  return {
    components: state.component.components,
    isFetching: state.component.isFetching,
  }
}

const mapDispatchToProps = { fetchComponents }

export default connect(mapStateToProps, mapDispatchToProps)(ComponentsPage)
