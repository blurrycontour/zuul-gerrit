// Copyright 2024 BMW Group
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

import React, { useCallback, useEffect, useState, useMemo } from 'react'

import { useSelector, useDispatch } from 'react-redux'
import { withRouter, useLocation, useHistory } from 'react-router-dom'
import PropTypes from 'prop-types'
import * as moment_tz from 'moment-timezone'

import {
  Gallery,
  GalleryItem,
  Level,
  LevelItem,
  PageSection,
  PageSectionVariants,
  Switch,
  ToolbarItem,
  Tooltip,
} from '@patternfly/react-core'
import { StreamIcon } from '@patternfly/react-icons'

import PipelineSummary from '../containers/status/PipelineSummary'

import { fetchStatusIfNeeded } from '../actions/status'
import { clearQueue } from '../actions/statusExpansion'
import { Fetching, ReloadButton } from '../containers/Fetching'
import {
  FilterToolbar,
  getFiltersFromUrl,
  isFilterActive,
} from '../containers/FilterToolbar'
import {
  clearFilters,
  filterInputValidation,
  filterPipelines,
  handleFilterChange,
} from '../containers/status/Filters'
import { EmptyBox } from '../containers/Errors'
import { countPipelineItems } from '../containers/status/Misc'
import { useDocumentVisibility, useInterval } from '../Hooks'

const filterCategories = [
  {
    key: 'change',
    title: 'Change',
    placeholder: 'Filter by Change...',
    type: 'fuzzy-search',
  },
  {
    key: 'project',
    title: 'Project',
    placeholder: 'Filter by Project...',
    type: 'fuzzy-search',
  },
  {
    key: 'queue',
    title: 'Queue',
    placeholder: 'Filter by Queue...',
    type: 'fuzzy-search',
  },
  {
    key: 'pipeline',
    title: 'Pipeline',
    placeholder: 'Filter by Pipeline...',
    type: 'fuzzy-search',
  },
]

function TenantStats({ stats, timezone, isReloading, reloadCallback }) {
  return (
    <Level>
      <LevelItem>
        <p>
          Queue lengths:{' '}
          <span>
            {stats.trigger_event_queue ? stats.trigger_event_queue.length : '0'}
          </span> trigger events,{' '}
          <span>
            {stats.management_event_queue ? stats.management_event_queue.length : '0'}
          </span> management events.
        </p>
      </LevelItem>
      <LevelItem>
        <Tooltip
          position="bottom"
          content={moment_tz.utc(stats.last_reconfigured).tz(timezone).format('llll')}
        >
          <span>
            Last reconfigured:{' '}
            {moment_tz.utc(stats.last_reconfigured).tz(timezone).fromNow()}
          </span>
        </Tooltip>
        <ReloadButton
          isReloading={isReloading}
          reloadCallback={reloadCallback}
        />
      </LevelItem>
    </Level>
  )
}

TenantStats.propTypes = {
  stats: PropTypes.object,
  timezone: PropTypes.string,
  isReloading: PropTypes.bool.isRequired,
  reloadCallback: PropTypes.func.isRequired,
}

function PipelineGallery({ pipelines, tenant, showAllPipelines, expandAll, isLoading, filters, onClearFilters }) {
  // Filter out empty pipelines if necessary
  if (!showAllPipelines) {
    pipelines = pipelines.filter(ppl => ppl._count > 0)
  }

  return (
    <>
      <Gallery
        hasGutter
        minWidths={{
          sm: '450px',
        }}
      >
        {pipelines.map(pipeline => (
          <GalleryItem key={pipeline.name}>
            <PipelineSummary pipeline={pipeline} tenant={tenant} showAllQueues={showAllPipelines} areAllJobsExpanded={expandAll} filters={filters} />
          </GalleryItem>
        ))}
      </Gallery>

      {!isLoading && pipelines.length === 0 && (
        <EmptyBox title="No items found"
          icon={StreamIcon}
          action="Clear all filters"
          onAction={onClearFilters}>
          No items match this filter criteria. Remove some filters or
          clear all to show results.
        </EmptyBox>
      )}
    </>
  )
}

PipelineGallery.propTypes = {
  pipelines: PropTypes.array,
  tenant: PropTypes.object,
  showAllPipelines: PropTypes.bool,
  expandAll: PropTypes.bool,
  isLoading: PropTypes.bool,
  filters: PropTypes.object,
  onClearFilters: PropTypes.func,
}

function getPipelines(status, location) {
  let pipelines = []
  let stats = {}
  if (status) {
    const filters = getFiltersFromUrl(location, filterCategories)
    // we need to work on a copy of the state..pipelines, because when mutating
    // the original, we couldn't reset or change the filters without reloading
    // from the backend first.
    pipelines = global.structuredClone(status.pipelines)
    pipelines = filterPipelines(pipelines, filters, filterCategories, true)

    pipelines = pipelines.map(ppl => (
      countPipelineItems(ppl)
    ))
    stats = {
      trigger_event_queue: status.trigger_event_queue,
      management_event_queue: status.management_event_queue,
      last_reconfigured: status.last_reconfigured,
    }
  }
  return {
    pipelines,
    stats,
  }
}

function PipelineOverviewPage() {
  const [showAllPipelines, setShowAllPipelines] = useState(
    localStorage.getItem('zuul_show_all_pipelines') === 'true')
  const [expandAll, setExpandAll] = useState(
    localStorage.getItem('zuul_overview_expand_all') === 'true')

  const [isReloading, setIsReloading] = useState(false)
  const location = useLocation()
  const history = useHistory()
  const filters = getFiltersFromUrl(location, filterCategories)
  const filterActive = isFilterActive(filters)

  const isDocumentVisible = useDocumentVisibility()

  const status = useSelector((state) => state.status.status)
  const {pipelines, stats} = useMemo(() => getPipelines(status, location), [status, location])

  const isFetching = useSelector((state) => state.status.isFetching)
  const tenant = useSelector((state) => state.tenant)
  const darkMode = useSelector((state) => state.preferences.darkMode)
  const autoReload = useSelector((state) => state.preferences.autoReload)
  const timezone = useSelector((state) => state.timezone)
  const dispatch = useDispatch()

  const onShowAllPipelinesToggle = (isChecked) => {
    setShowAllPipelines(isChecked)
    localStorage.setItem('zuul_show_all_pipelines', isChecked.toString())
  }

  const onExpandAllToggle = (isChecked) => {
    setExpandAll(isChecked)
    localStorage.setItem('zuul_overview_expand_all', isChecked.toString())
    dispatch(clearQueue())
  }

  const onFilterChanged = (newFilters) => {
    handleFilterChange(newFilters, location, history)
    // show all pipelines when filtering, hide when not
    setShowAllPipelines(
      isFilterActive(newFilters) || localStorage.getItem('zuul_show_all_pipelines') === 'true')
  }

  const onClearFilters = () => {
    clearFilters(location, history, filterCategories)
    // reset `showAllPipelines` when clearing filters
    setShowAllPipelines(localStorage.getItem('zuul_show_all_pipelines') === 'true')
  }

  const updateData = useCallback((tenant) => {
    if (tenant.name) {
      setIsReloading(true)
      dispatch(fetchStatusIfNeeded(tenant))
        .then(() => {
          setIsReloading(false)
        })
    }
  }, [setIsReloading, dispatch])

  useEffect(() => {
    document.title = 'Zuul Status'
    // Initial data fetch
    updateData(tenant)
  }, [updateData, tenant])

  // Subsequent data fetches every 5 seconds if auto-reload is enabled
  useInterval(() => {
    if (isDocumentVisible && autoReload) {
      updateData(tenant)
    }
    // Reset the interval on a manual refresh
  }, isReloading ? null : 5000)

  // Only show the fetching component on the initial data fetch, but
  // not on subsequent reloads, as this would overlay the page data.
  if (!isReloading && isFetching) {
    return <Fetching />
  }

  const allPipelinesSwitch = (
    <Switch
      className="zuul-show-all-switch"
      id="all-pipeline-switch"
      aria-label="Show all pipelines"
      label="Show all pipelines"
      isReversed
      isChecked={showAllPipelines}
      isDisabled={filterActive}
      onChange={onShowAllPipelinesToggle}
    />
  )

  return (
    <>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <TenantStats
          stats={stats}
          timezone={timezone}
          isReloading={isReloading}
          reloadCallback={() => updateData(tenant)}
        />
        <FilterToolbar
          filterCategories={filterCategories}
          onFilterChange={onFilterChanged}
          filters={filters}
          filterInputValidation={filterInputValidation}
        >
          <ToolbarItem>
            {filterActive ?
              <Tooltip content="Disabled when filtering">{allPipelinesSwitch}</Tooltip> :
              allPipelinesSwitch}
          </ToolbarItem>
          <ToolbarItem>
            <Switch
              className="zuul-show-all-switch"
              aria-label="Expand all"
              label="Expand all"
              isReversed
              onChange={onExpandAllToggle}
              isChecked={expandAll}
            />
          </ToolbarItem>
        </FilterToolbar>
      </PageSection>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <PipelineGallery
          pipelines={pipelines}
          tenant={tenant}
          showAllPipelines={showAllPipelines}
          expandAll={expandAll}
          isLoading={isFetching}
          filters={filters}
          onClearFilters={onClearFilters}
        />
      </PageSection>
    </>
  )
}

export default withRouter(PipelineOverviewPage)
