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

import React from 'react'
import PropTypes from 'prop-types'

import {
  Grid,
  GridItem,
  Title,
  Text,
  TextContent,
  TextVariants,
} from '@patternfly/react-core'

import { PipelineIcon } from './Misc'

function PipelineDetails({ pipeline }) {

  const pipelineType = pipeline.manager || 'unknown'

  const renderPipelineStats = () => {
    return (
      <>
        <Title headingLevel="h4">
          Statistics
        </Title>

        <p>X items enqueued in X change queues</p>

        <b>Events:</b><br /><br />
        Trigger: {pipeline.trigger_events} <br />
        Management: {pipeline.management_events} <br />
        Result: {pipeline.result_events} <br />

      </>
    )

  }

  return (
    <>
      <Title headingLevel="h1">
        <PipelineIcon pipelineType={pipelineType} />
        {pipeline.name}
      </Title>
      <Grid hasGutter>
        <GridItem span={8}>
          <TextContent>
            <Text component={TextVariants.p}>
              {pipeline.description}
            </Text>
          </TextContent>
        </GridItem>
        <GridItem span={4}>
          {renderPipelineStats()}
        </GridItem>
      </Grid>
    </>
  )
}

PipelineDetails.propTypes = {
  pipeline: PropTypes.object.isRequired,
}

export default PipelineDetails
