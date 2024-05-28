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
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { withRouter, useLocation, useHistory } from 'react-router-dom'

import {
  Button,
  EmptyState,
  EmptyStateBody,
  EmptyStateIcon,
  EmptyStateSecondaryActions,
  Gallery,
  GalleryItem,
  Grid,
  GridItem,
  PageSection,
  PageSectionVariants,
  Title,
  Text,
  TextContent,
  TextVariants,
} from '@patternfly/react-core'
import { BuildIcon, StreamIcon } from '@patternfly/react-icons'

import ChangeQueue from '../containers/status/ChangeQueue'
import { PipelineIcon } from '../containers/status/Misc'
import { fetchStatusIfNeeded } from '../actions/status'
import { EmptyPage } from '../containers/Errors'
import { Fetching, ReloadButton } from '../containers/Fetching'
import { useDocumentVisibility, useInterval } from '../Hooks'
import {
  FilterToolbar,
  getFiltersFromUrl,
} from '../containers/FilterToolbar'
import {
  filterPipelines,
  handleFilterChange,
  filterInputValidation,
  onClearFilters,
} from '../containers/status/Misc'

const filterCategories = [
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

function PipelineStats({ pipeline }) {
  return (
    <>
      <Title headingLevel="h4" style={{ margin: 0 }}>Events</Title>
      Trigger: {pipeline.trigger_events} <br />
      Management: {pipeline.management_events} <br />
      Result: {pipeline.result_events} <br />
    </>
  )
}

PipelineStats.propTypes = {
  pipeline: PropTypes.object.isRequired,
}

function PipelineDetails({ pipeline, isReloading, reloadCallback }) {

  const pipelineType = pipeline.manager || 'unknown'

  return (
    <>
      <span className="zuul-reload-button-floating">
        <ReloadButton
          isReloading={isReloading}
          reloadCallback={reloadCallback}
        />
      </span>
      <Title headingLevel="h1">
        <PipelineIcon pipelineType={pipelineType} />
        {pipeline.name}
      </Title>
      <Grid hasGutter>
        <GridItem span={10}>
          <TextContent>
            <Text component={TextVariants.p}>
              {pipeline.description}
            </Text>
          </TextContent>
        </GridItem>
        <GridItem span={2}>
          <PipelineStats pipeline={pipeline} />
        </GridItem>
      </Grid>
    </>
  )
}

PipelineDetails.propTypes = {
  pipeline: PropTypes.object.isRequired,
  isReloading: PropTypes.bool.isRequired,
  reloadCallback: PropTypes.func.isRequired,
}

function PipelineDetailsPage({
  pipeline, isFetching, tenant, darkMode, autoReload, fetchStatusIfNeeded, isEmpty
}) {
  const [isReloading, setIsReloading] = useState(false)

  const isDocumentVisible = useDocumentVisibility()

  const location = useLocation()
  const history = useHistory()
  const filters = getFiltersFromUrl(location, filterCategories)

  const updateData = (tenant) => {
    if (tenant.name) {
      setIsReloading(true)
      fetchStatusIfNeeded(tenant)
        .then(() => {
          setIsReloading(false)
        })
    }
  }

  useEffect(() => {
    document.title = 'Zuul Pipeline Details'
    // Initial data fetch
    updateData(tenant)
  }, [tenant])


  // Subsequent data fetches every 5 seconds if auto-reload is enabled
  useInterval(() => {
    if (isDocumentVisible && autoReload) {
      updateData(tenant)
    }
    // Reset the interval on a manual refresh
  }, isReloading ? null : 5000)

  if (pipeline === undefined || (!isReloading && isFetching)) {
    return <Fetching />
  }

  if (!pipeline) {
    return (
      <EmptyPage
        title="This pipeline does not exist"
        icon={StreamIcon}
        linkTarget={`${tenant.linkPrefix}/status`}
        linkText="Back to status page"
      />
    )
  }

  return (
    <>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <FilterToolbar
          filterCategories={filterCategories}
          onFilterChange={(newFilters) => {handleFilterChange(newFilters, location, history)}}
          filters={filters}
          filterInputValidation={filterInputValidation}
        />
        <PipelineDetails pipeline={pipeline} isReloading={isReloading} reloadCallback={() => updateData(tenant)} />
      </PageSection>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        {!isEmpty &&
        <Title headingLevel="h3">
          <StreamIcon
            style={{
              marginRight: 'var(--pf-global--spacer--sm)',
              verticalAlign: '-0.1em',
            }}
          />{' '}
          Queues
        </Title>
        }
        <Gallery
          hasGutter
          minWidths={{
            default: '450px',
          }}
        >

          {
            pipeline.change_queues.filter(
              queue => queue.heads.length > 0
            ).map((queue, idx) => (
              <GalleryItem key={idx}>
                <ChangeQueue queue={queue} pipeline={pipeline} />
              </GalleryItem>
            ))
          }
        </Gallery>
        {isEmpty &&
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
        }
      </PageSection>
    </>
  )
}

PipelineDetailsPage.propTypes = {
  match: PropTypes.object.isRequired,
  pipeline: PropTypes.object,
  isFetching: PropTypes.bool,
  tenant: PropTypes.object,
  darkMode: PropTypes.bool,
  autoReload: PropTypes.bool.isRequired,
  fetchStatusIfNeeded: PropTypes.func.isRequired,
  isEmpty: PropTypes.bool,
}

function mapStateToProps(state, ownProps) {
  let pipeline = null
  if (state.status.status) {
    const filters = getFiltersFromUrl(ownProps.location, filterCategories)
    // we need to work on a copy of the state..pipelines, because when mutating
    // the original, we couldn't reset or change the filters without reloading
    // from the backend first.
    let pipelines = global.structuredClone(state.status.status.pipelines)
    pipelines = filterPipelines(pipelines, filters, filterCategories)
    // Filter the state for this specific pipeline
    pipelines.filter(
      ppl => (ppl.name === ownProps.match.params.pipelineName)
    ).map(
      ppl => (pipeline = ppl)
    )
  }

  const isEmpty = pipeline && pipeline.change_queues.map(q => q.heads.length).reduce((a, len) => a + len) === 0

  return {
    pipeline,
    isFetching: state.status.isFetching,
    tenant: state.tenant,
    darkMode: state.preferences.darkMode,
    autoReload: state.preferences.autoReload,
    isEmpty,
  }
}

const mapDispatchToProps = { fetchStatusIfNeeded }

export default connect(
  mapStateToProps,
  mapDispatchToProps,
)(withRouter(PipelineDetailsPage))
