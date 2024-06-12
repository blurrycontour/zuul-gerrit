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
import { withRouter } from 'react-router-dom'
import PropTypes from 'prop-types'
import * as moment_tz from 'moment-timezone'

import {
  Bullseye,
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
import { Fetchable, Fetching, ReloadButton } from '../containers/Fetching'
import { useDocumentVisibility } from '../Hooks'


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
        Last reconfigured:{' '}
        {moment_tz.utc(stats.last_reconfigured).tz(timezone).fromNow()}
        {' '}
      </LevelItem>
      <LevelItem>
        Last reconfigured:{' '}
        {moment_tz.utc(stats.last_reconfigured).tz(timezone).fromNow()}
        {' '}
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
  pipelines, stats, isFetching, tenant, darkMode, autoReload, timezone, fetchStatusIfNeeded
}) {

  const [showEmptyPipelines, setShowEmptyPipelines] = useState(false)
  const [isReloading, setIsReloading] = useState(false)

  const isDocumentVisible = useDocumentVisibility()

  const onShowEmptyPipelinesToggle = (isChecked) => {
    setShowEmptyPipelines(isChecked)
  }

  useEffect(() => {
    const updateData = (force) => {
      if (force || (isDocumentVisible && autoReload)) {
        setIsReloading(true)
        fetchStatusIfNeeded(tenant)
          .then(() => {
            //timer = setTimeout(() => updateData(true), 5000)
            setIsReloading(false)
          })
      }
    }

    const delay = 5
    document.title = 'Zuul Status'
    // Initial data fetch
    //updateData(true)
    // Subsequent data fetches via timeout
    let timer = null

    if (tenant.name) {
      timer = setTimeout(() => updateData(), delay * 1000);
    }

    // The "cleanup" code (return statement) is called before the hook is
    // invoked again. So we use this to clear any existing timer. When the
    // hook is invoked again ("setup" code), a new timeout might be created.
    return () => {
      if (timer) {
        clearTimeout(timer)
      }
    }
    // We provide the isReloading flag to the dependency array of useEffect,
    // so we can invoke the useEffect hook simply by changing the flag. This
    // is a lot simpler than explicitly calling the updateData function
    // outside of the useEffect hook.
  }, [tenant, autoReload, isDocumentVisible, fetchStatusIfNeeded, isReloading])


  // Only show the fetching component on the initial data fetch, but
  // not on subsequent reloads, as this would overlay the page data.
  if (!isReloading && isFetching) {
    return <Fetching />
  }

  return (
    <>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <TenantStats stats={stats} timezone={timezone} isReloading={isReloading} reloadCallback={() => setIsReloading(true)} />
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
      <PageSection variant={PageSectionVariants.dark} className="zuul-page-footer">
        <Bullseye>
          Zuul Version: {stats.zuul_version}
        </Bullseye>
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

function mapStateToProps(state, ownProps) {
  // TODO (felix): Check if the old state already contained a valid
  // pipelines array. If so, set the isReloading flag instead of the
  // isFetching flag based on the current isFetching value in the state.
  // This should solve the isFetching/isReloading problem.
  let pipelines = []
  let stats = {}
  if (state.status.status) {
    // TODO (felix): Make filtering optional via a switch (default: on)
    pipelines = state.status.status.pipelines.map(ppl => (
      { ...ppl, _count: countItems(ppl) }
    ))
    stats = {
      trigger_event_queue: state.status.status.trigger_event_queue,
      management_event_queue: state.status.status.management_event_queue,
      last_reconfigured: state.status.status.last_reconfigured,
      zuul_version: state.status.status.zuul_version,
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
