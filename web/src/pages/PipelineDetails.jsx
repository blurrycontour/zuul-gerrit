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
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { withRouter } from 'react-router-dom'

import {
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
import { StreamIcon } from '@patternfly/react-icons'

import ChangeQueue from '../containers/status/ChangeQueue'
import { PipelineIcon } from '../containers/status/Misc'
import { fetchStatusIfNeeded } from '../actions/status'
import { EmptyPage } from '../containers/Errors'
import { Fetching } from '../containers/Fetching'

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

function PipelineDetails({ pipeline }) {

  const pipelineType = pipeline.manager || 'unknown'

  return (
    <>
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
}

function PipelineDetailsPage({ pipeline, isFetching, tenant, darkMode, fetchStatusIfNeeded }) {

  useEffect(() => {
    document.title = 'Zuul Pipeline Details'
    if (tenant.name) {
      fetchStatusIfNeeded(tenant)
    }
  }, [tenant, fetchStatusIfNeeded])

  if (pipeline === undefined || isFetching) {
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
        <PipelineDetails pipeline={pipeline} />
      </PageSection>
      <PageSection variant={darkMode ? PageSectionVariants.dark : PageSectionVariants.light}>
        <Title headingLevel="h3">
          <StreamIcon
            style={{
              marginRight: 'var(--pf-global--spacer--sm)',
              verticalAlign: '-0.1em',
            }}
          />{' '}
          Queues
        </Title>
        <Gallery
          hasGutter
          minWidths={{
            default: '450px',
          }}
        >

          {pipeline.change_queues.map((queue, idx) => (
            <GalleryItem key={idx}>
              <ChangeQueue queue={queue} pipeline={pipeline}/>
            </GalleryItem>
          ))}
        </Gallery>
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
  fetchStatusIfNeeded: PropTypes.func.isRequired,
}

function mapStateToProps(state, ownProps) {
  let pipeline = null
  if (state.status.status) {
    // Filter the state for this specific pipeline
    state.status.status.pipelines.filter(
      ppl => (ppl.name === ownProps.match.params.pipelineName)
    ).map(
      ppl => (pipeline = ppl)
    )
  }

  return {
    pipeline,
    isFetching: state.status.isFetching,
    tenant: state.tenant,
    darkMode: state.preferences.darkMode,
  }
}

const mapDispatchToProps = { fetchStatusIfNeeded }

export default connect(
  mapStateToProps,
  mapDispatchToProps,
)(withRouter(PipelineDetailsPage))
