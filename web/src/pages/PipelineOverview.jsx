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

import React, { useCallback, useEffect, useState } from 'react'

import { connect } from 'react-redux'
import { withRouter, useLocation, useHistory } from 'react-router-dom'
import PropTypes from 'prop-types'
import * as moment_tz from 'moment-timezone'

import {
  Button,
  EmptyState,
  EmptyStateBody,
  EmptyStateIcon,
  EmptyStateSecondaryActions,
  Gallery,
  GalleryItem,
  Level,
  LevelItem,
  PageSection,
  PageSectionVariants,
  Switch,
  Title,
  ToolbarItem,
  Tooltip,
} from '@patternfly/react-core'
import { BuildIcon } from '@patternfly/react-icons'

import PipelineSummary from '../containers/status/PipelineSummary'

import { fetchStatusIfNeeded } from '../actions/status'
import { Fetching, ReloadButton } from '../containers/Fetching'
import { useDocumentVisibility, useInterval } from '../Hooks'

import {
  FilterToolbar,
  getFiltersFromUrl,
} from '../containers/FilterToolbar'
import {
  filterPipelines,
  handleFilterChange,
  onClearFilters,
  filterInputValidation,
} from '../containers/status/Misc'

const filterCategories = [
  {
    key: 'pipeline',
    title: 'Pipeline',
    placeholder: 'Filter by pipeline...',
    type: 'fuzzy-search',
  },
  {
    key: 'project',
    title: 'Project',
    placeholder: 'Filter by Project...',
    type: 'fuzzy-search',
  },
  {
    key: 'change',
    title: 'Change',
    placeholder: 'Filter by Change...',
    type: 'search',
  },
  {
    key: 'queue',
    title: 'Queue',
    placeholder: 'Filter by Queue...',
    type: 'fuzzy-search',
  }
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

function PipelineGallery({ pipelines, tenant, showAllPipelines, isFetching, filters }) {
  // Filter out empty pipelines if necessary
  if (!showAllPipelines) {
    pipelines = pipelines.filter(ppl => ppl._count > 0)
  }

  const location = useLocation()
  const history = useHistory()

  return (
    <>
    <Gallery
      hasGutter
      minWidths={{
        default: '450px',
      }}
    >
      {pipelines.map(pipeline => (
        <GalleryItem key={pipeline.name}>
          <PipelineSummary pipeline={pipeline} tenant={tenant} showAllQueues={showAllPipelines} filters={filters} />
        </GalleryItem>
      ))}
    </Gallery>

    {!isFetching && pipelines.length === 0 && (
      <EmptyState>
        <EmptyStateIcon icon={BuildIcon} />
        <Title headingLevel="h1">No items found</Title>
        <EmptyStateBody>
          No items match this filter criteria. Remove some filters or
          clear all to show results.
        </EmptyStateBody>
        <EmptyStateSecondaryActions>
          <Button variant="link" onClick={() => onClearFilters(location, history, filterCategories)}>
            Clear all filters
          </Button>
        </EmptyStateSecondaryActions>
      </EmptyState>
    )}
    </>
  )
}

PipelineGallery.propTypes = {
  pipelines: PropTypes.array,
  tenant: PropTypes.object,
  showAllPipelines: PropTypes.bool,
  isFetching: PropTypes.bool,
  filters: PropTypes.object,
}

function PipelineOverviewPage({
  pipelines, stats, isFetching, tenant, darkMode, autoReload, timezone, fetchStatusIfNeeded
}) {
  const [showAllPipelines, setShowAllPipelines] = useState(false)
  const [isReloading, setIsReloading] = useState(false)
  const location = useLocation()
  const history = useHistory()
  const filters = getFiltersFromUrl(location, filterCategories)

  const isDocumentVisible = useDocumentVisibility()

  const onShowAllPipelinesToggle = (isChecked) => {
    setShowAllPipelines(isChecked)
  }

  const updateData = useCallback((tenant) => {
    if (tenant.name) {
      setIsReloading(true)
      fetchStatusIfNeeded(tenant)
        .then(() => {
          setIsReloading(false)
        })
    }
  }, [setIsReloading, fetchStatusIfNeeded])

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
          onFilterChange={(newFilters) => {handleFilterChange(newFilters, location, history)}}
          filters={filters}
          filterInputValidation={filterInputValidation}
        >
            <ToolbarItem>
              <span>Show all pipelines</span>{' '}
              <Switch
                className="zuul-show-pipeline-switch"
                id="all-pipeline-switch"
                aria-label="Show all pipelines"
                isChecked={showAllPipelines}
                onChange={onShowAllPipelinesToggle}
              />
            </ToolbarItem>
        </FilterToolbar>
      </PageSection>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <PipelineGallery
          pipelines={pipelines}
          tenant={tenant}
          showAllPipelines={showAllPipelines}
          isFetching={isFetching}
          filters={filters}
        />
      </PageSection>
    </>
  )

}

PipelineOverviewPage.propTypes = {
  pipelines: PropTypes.array,
  stats: PropTypes.object,
  isFetching: PropTypes.bool,
  tenant: PropTypes.object,
  preferences: PropTypes.object,
  darkMode: PropTypes.bool,
  autoReload: PropTypes.bool.isRequired,
  timezone: PropTypes.string,
  fetchStatusIfNeeded: PropTypes.func,
}

const countItems = (pipeline) => {
  let count = 0
  pipeline.change_queues.map(queue => (
    queue.heads.map(head => (
      head.map(() => (
        count++
      ))
    ))
  ))
  return count
}

function mapStateToProps(state, ownProps) {
  let pipelines = []
  let stats = {}
  if (state.status.status) {
    const filters = getFiltersFromUrl(ownProps.location, filterCategories)
    // we need to work on a copy of the state..pipelines, because when mutating
    // the original, we couldn't reset or change the filters without reloading
    // from the backend first.
    pipelines = global.structuredClone(state.status.status.pipelines)
    pipelines = filterPipelines(pipelines, filters, filterCategories)
    // TODO (felix): Make filtering optional via a switch (default: on)
    pipelines = pipelines.map(ppl => (
      { ...ppl, _count: countItems(ppl) }
    ))
    stats = {
      trigger_event_queue: state.status.status.trigger_event_queue,
      management_event_queue: state.status.status.management_event_queue,
      last_reconfigured: state.status.status.last_reconfigured,
    }
  }

  // TODO (felix): Here we could also order the pipelines by any
  // criteria (e.g. the pipeline_type) in case we want that. Currently
  // they are ordered in the way they are defined in the zuul config.
  // The sorting could also be done via the filter toolbar.
  return {
    pipelines,
    stats,
    isFetching: state.status.isFetching,
    tenant: state.tenant,
    darkMode: state.preferences.darkMode,
    autoReload: state.preferences.autoReload,
    timezone: state.timezone,
  }
}

const mapDispatchToProps = { fetchStatusIfNeeded }

export default connect(
  mapStateToProps,
  mapDispatchToProps,
)(withRouter(PipelineOverviewPage))
