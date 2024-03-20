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


function PipelineOverviewPage({ pipelines, tenant, darkMode, fetchStatusIfNeeded }) {

  useEffect(() => {
    document.title = 'Zuul Status'
    if (tenant.name) {
      fetchStatusIfNeeded(tenant)
    }
  }, [tenant, fetchStatusIfNeeded])

  return (
    <>
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
  tenant: PropTypes.object,
  preferences: PropTypes.object,
  darkMode: PropTypes.bool,
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
  if (state.status.status) {
    // Count number of items per pipeline/queue and sort the pipelines
    // by number of items (desc).
    // TODO (felix): Make filtering optional via a switch (default: on)
    pipelines = state.status.status.pipelines.map(ppl => (
      { ...ppl, _count: countItems(ppl) }
    )).sort((a, b) => sortPipelines(a, b)).filter(ppl => ppl._count > 0)
  }
  return {
    pipelines,
    tenant: state.tenant,
    darkMode: state.preferences.darkMode,
  }
}

const mapDispatchToProps = { fetchStatusIfNeeded }

export default connect(
  mapStateToProps,
  mapDispatchToProps,
)(withRouter(PipelineOverviewPage))
