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
import { Link } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  CardTitle,
  CardBody,
  Flex,
  FlexItem,
  Tooltip,
} from '@patternfly/react-core'
import { SquareIcon } from '@patternfly/react-icons'

import QueueItemPopover from './QueueItemPopover'
import { PipelineIcon, getQueueItemIconConfig } from './Misc'

function QueueItemSquareWithPopover({ item }) {
  return (
    <QueueItemPopover
      item={item}
      triggerElement={<QueueItemSquare item={item} />}
    />
  )
}

QueueItemSquareWithPopover.propTypes = {
  item: PropTypes.object,
}

function QueueItemSquare({ item }) {
  const iconConfig = getQueueItemIconConfig(item)
  return (
    <Button
      variant="plain"
      className={`zuul-item-square zuul-item-square-${iconConfig.variant}`}
    >
      <SquareIcon />
    </Button>
  )
}

QueueItemSquare.propTypes = {
  item: PropTypes.object,
}


function QueueSummary({ pipeline, pipelineType }) {
  // Dependent pipelines usually come with named queues, so we will
  // visualize each queue individually. For other pipeline types, we
  // will consolidate all heads as a single queue to simplify the
  // visualization (e.g. independent pipelines like check where each
  // change/item is enqueued in it's own queue by design).
  if (['dependent'].indexOf(pipelineType) > -1) {
    return (
      pipeline.change_queues.map((queue) => (
        <Flex key={`${queue.name}${queue.branch}`}>
          <FlexItem>
            <Card isPlain className="zuul-compact-card">
              <CardTitle>
                {queue.name}
                {queue.branch ? ` (${queue.branch})` : ''}
              </CardTitle>
              <CardBody style={{ paddingBottom: '0' }}>
                {queue.heads.map((head) => (
                  head.map((item) => <QueueItemSquareWithPopover item={item} key={item.id} />)
                ))}
              </CardBody>
            </Card>
          </FlexItem>
        </Flex>
      ))
    )
  } else {
    return (
      <Flex
        display={{ default: 'inlineFlex' }}
        spaceItems={{ default: 'spaceItemsNone' }}
      >
        {pipeline.change_queues.map((queue) => (
          queue.heads.map((head) => (
            head.map((item) => (
              <FlexItem key={item.id}>
                <QueueItemSquareWithPopover item={item} />
              </FlexItem>
            ))
          ))
        ))}
      </Flex>
    )
  }
}

QueueSummary.propTypes = {
  pipeline: PropTypes.object,
  pipelineType: PropTypes.string,
}

function PipelineSummary({ pipeline, tenant }) {

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

  const pipelineType = pipeline.manager || 'unknown'
  const itemCount = countItems(pipeline)

  return (
    <Card className="zuul-pipeline-summary zuul-compact-card">
      <CardTitle
        style={pipelineType !== 'dependent' ? { paddingBottom: '8px' } : {}}
      >
        <PipelineIcon pipelineType={pipelineType} />
        <Link
          to={`${tenant.linkPrefix}/status/pipeline/${pipeline.name}`}
          className="zuul-pipeline-link"
        >
          {pipeline.name}
        </Link>
        <Tooltip
          content={
            itemCount === 1
              ? <div>{itemCount} item enqueued</div>
              : <div>{itemCount} items enqueued</div>
          }
        >
          <Badge
            isRead
            style={{ marginLeft: 'var(--pf-global--spacer--sm)', verticalAlign: '0.1em' }}
          >
            {itemCount}
          </Badge>
        </Tooltip>
      </CardTitle>
      <CardBody>
        <QueueSummary pipeline={pipeline} pipelineType={pipelineType} />
      </CardBody>

    </Card>
  )
}

PipelineSummary.propTypes = {
  pipeline: PropTypes.object,
  tenant: PropTypes.object,
}

export default PipelineSummary
