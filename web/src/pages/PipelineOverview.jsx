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

import React, { useEffect } from 'react'
import { connect } from 'react-redux'
import { withRouter } from 'react-router-dom'
import PropTypes from 'prop-types'

import {
  Gallery,
  GalleryItem,
  PageSection,
  PageSectionVariants,
} from '@patternfly/react-core'

import PipelineSummary from '../containers/status/PipelineSummary'

import { fetchStatusIfNeeded } from '../actions/status'
import { Fetching } from '../containers/Fetching'


function TenantStats({ stats }) {
  return (
    <>
      <p>
        Queue lengths:{' '}
        <span>
          {stats.trigger_event_queue ? stats.trigger_event_queue.length : '0'}
        </span> trigger events,{' '}
        <span>
          {stats.management_event_queue ? stats.management_event_queue.length : '0'}
        </span> management events.
      </p>
    </>
  )
}

TenantStats.propTypes = {
  stats: PropTypes.object,
}

function PipelineOverviewPage({ pipelines, stats, isFetching, tenant, darkMode, fetchStatusIfNeeded }) {

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
        <TenantStats stats={stats} />
      </PageSection>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <Gallery
          hasGutter
          minWidths={{
            default: '450px',
          }}
        >
          {pipelines.map(pipeline => (
            <GalleryItem key={pipeline.name}>
              <PipelineSummary pipeline={pipeline} tenant={tenant} />
            </GalleryItem>
          ))}
        </Gallery>
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
  fetchStatusIfNeeded: PropTypes.func,
}

function mapStateToProps(state) {
  let pipelines = []
  let stats = {}
  if (state.status.status) {
    // TODO (felix): Here we could filter out the pipeline data from
    // the status.json and if necessary "reformat" it to only contain
    // the relevant information for this component (e.g. drop all
    // job related information which isn't shown).
    pipelines = state.status.status.pipelines
    stats = {
      trigger_event_queue: state.status.status.trigger_event_queue,
      management_event_queue: state.status.status.management_event_queue,
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
  }
}

const mapDispatchToProps = { fetchStatusIfNeeded }

export default connect(
  mapStateToProps,
  mapDispatchToProps,
)(withRouter(PipelineOverviewPage))
