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

import React, { useEffect, useState } from 'react'
import { connect } from 'react-redux'
import { withRouter } from 'react-router-dom'
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
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from '@patternfly/react-core'

import PipelineSummary from '../containers/status/PipelineSummary'

import { fetchStatusIfNeeded } from '../actions/status'
import { Fetching } from '../containers/Fetching'


// Define the order of pipeline types in reverse order, so we can
// utilize the -1 return value of the indexOf() method in case the
// pipeline type could not be found. This ensures, that all "unknown"
// pipelines come last to the end.
const PIPELINE_TYPE_SORT_ORDER_REVERSE = [
  'independent', 'supercedent', 'serial', 'dependent'
]

function TenantStats({ stats, timezone }) {

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
        Last reconfigured:{' '}
        {moment_tz.utc(stats.last_reconfigured).tz(timezone).fromNow()}
      </LevelItem>
    </Level>
  )
}

TenantStats.propTypes = {
  stats: PropTypes.object,
  timezone: PropTypes.object,
}

function PipelineGallery({ pipelines, tenant, showEmptyPipelines }) {
  // Filter out empty pipelines if necessary
  if (!showEmptyPipelines) {
    pipelines = pipelines.filter(ppl => ppl._count > 0)
  }

  return (
    <Gallery
      hasGutter
      minWidths={{
        default: '450px',
      }}
    >
      {pipelines.map(pipeline => (
        <GalleryItem key={pipeline.name}>
          <PipelineSummary pipeline={pipeline} tenant={tenant} showEmptyQueues={showEmptyPipelines} />
        </GalleryItem>
      ))}
    </Gallery>
  )
}

PipelineGallery.propTypes = {
  pipelines: PropTypes.array,
  tenant: PropTypes.object,
  showEmptyPipelines: PropTypes.bool,
}

function PipelineOverviewPage({
  pipelines, stats, isFetching, tenant, darkMode, timezone, fetchStatusIfNeeded
}) {
  const [showEmptyPipelines, setShowEmptyPipelines] = useState(false)

  const onShowEmptyPipelinesToggle = (isChecked) => {
    setShowEmptyPipelines(isChecked)
  }

  useEffect(() => {
    document.title = 'Zuul Status'
    if (tenant.name) {
      fetchStatusIfNeeded(tenant)
    }
  }, [tenant, fetchStatusIfNeeded])

  if (isFetching) {
    return <Fetching />
  }

  return (
    <>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <TenantStats stats={stats} timezone={timezone} />
        <Toolbar>
          <ToolbarContent>
            <ToolbarItem>
              <span>Show empty pipelines</span>{' '}
              <Switch
                id="empty-pipeline-switch"
                aria-label="Show empty pipelines"
                isChecked={showEmptyPipelines}
                onChange={onShowEmptyPipelinesToggle}
              />
            </ToolbarItem>
          </ToolbarContent>
        </Toolbar>
      </PageSection>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <PipelineGallery
          pipelines={pipelines}
          tenant={tenant}
          showEmptyPipelines={showEmptyPipelines}
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
  timezone: PropTypes.object,
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

const sortPipelines = (a, b) => {
  const order_a = PIPELINE_TYPE_SORT_ORDER_REVERSE.indexOf(a.manager)
  const order_b = PIPELINE_TYPE_SORT_ORDER_REVERSE.indexOf(b.manager)

  // Sort by pipeline type
  if (order_a > order_b) {
    return -1
  }
  if (order_b > order_a) {
    return 1
  }

  // Same pipeline type, sort by number of items (desc)
  if (a._count > b._count) {
    return -1
  }
  if (b._count > a._count) {
    return 1
  }
  return 0
}

function mapStateToProps(state) {
  let pipelines = []
  let stats = {}
  if (state.status.status) {
    // Count number of items per pipeline/queue and sort the pipelines
    // by number of items (desc).
    pipelines = state.status.status.pipelines.map(ppl => (
      { ...ppl, _count: countItems(ppl) }
    )).sort((a, b) => sortPipelines(a, b))
    stats = {
      trigger_event_queue: state.status.status.trigger_event_queue,
      management_event_queue: state.status.status.management_event_queue,
      last_reconfigured: state.status.status.last_reconfigured,
    }
  }
  return {
    pipelines,
    stats,
    isFetching: state.status.isFetching,
    tenant: state.tenant,
    darkMode: state.preferences.darkMode,
    timezone: state.timezone,
  }
}

const mapDispatchToProps = { fetchStatusIfNeeded }

export default connect(
  mapStateToProps,
  mapDispatchToProps,
)(withRouter(PipelineOverviewPage))
