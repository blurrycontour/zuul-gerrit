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

import React, { useState } from 'react'
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
import {
  SquareIcon,
  AngleRightIcon,
  AngleDownIcon,
} from '@patternfly/react-icons'

import QueueItemPopover from './QueueItemPopover'
import {
  PipelineIcon,
  getQueueItemIconConfig,
} from './Misc'
import { makeQueryString } from '../FilterToolbar'
import ChangeQueue from './ChangeQueue'

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

function QueueCard({ pipeline, queue, allQueuesExpanded }) {
  const [isQueueExpanded, setIsQueueExpanded] = useState(undefined)
  const [areAllQueuesExpanded, setAreAllQueuesExpanded] = useState(undefined)

  // If the pipeline toggle is changed, update the queue toggles to match.
  if (allQueuesExpanded !== areAllQueuesExpanded) {
    setAreAllQueuesExpanded(allQueuesExpanded)
    setIsQueueExpanded(allQueuesExpanded)
  }

  const onQueueToggle = () => {
    setIsQueueExpanded(!isQueueExpanded)
  }

  return (
    <Card isPlain className="zuul-compact-card">
      <CardTitle>
        {queue.name}
        {queue.branch ? ` (${queue.branch})` : ''}
        <Tooltip
          content={
            <div style={{ textAlign: 'left' }}>
              Queue length: {queue._itemCount}<br />Window size: {queue.window}
            </div>
          }
        >
          <Badge
            isRead
            style={{ marginLeft: 'var(--pf-global--spacer--sm)', verticalAlign: '0.1em' }}
          >
            {queue._itemCount} / {queue.window}
          </Badge>
        </Tooltip>
        {isQueueExpanded ?
          <AngleDownIcon className="zuul-expand-icon" onClick={onQueueToggle} />
          :
          <AngleRightIcon className="zuul-expand-icon" onClick={onQueueToggle} />
        }
      </CardTitle>
      {isQueueExpanded ? null :
        <CardBody style={{ paddingBottom: '0' }}>
          {queue.heads.map((head) => (
            head.map((item) => <QueueItemSquareWithPopover item={item} key={item.id} />)
          ))}
        </CardBody>
      }
      {isQueueExpanded ?
        <ChangeQueue queue={queue} pipeline={pipeline} showTitle={false} />
        : null
      }
    </Card>
  )
}

QueueCard.propTypes = {
  pipeline: PropTypes.object,
  queue: PropTypes.object,
  allQueuesExpanded: PropTypes.bool,
}

function QueueSummary({ pipeline, showAllQueues, allQueuesExpanded }) {
  let changeQueues = pipeline.change_queues

  if (!showAllQueues) {
    changeQueues = changeQueues.filter(queue => queue.heads.length > 0)
  }

  return (
    changeQueues.map((queue, idx) => {
      if (queue.name) {
        // Visualize named queues individually
        return (
          <QueueCard
            key={`${queue.name}${queue.branch}`}
            pipeline={pipeline}
            queue={queue}
            allQueuesExpanded={allQueuesExpanded}
          />
        )
      } else {
        // For queues without a name, all heads will be consolidated
        // into a single queue to simplify the visualization.
        // This is the case for e.g. independent pipelines like check
        // where each change is enqueued in it's own queue by design.
        return (
          allQueuesExpanded ?
            <ChangeQueue key={idx} queue={queue} pipeline={pipeline} showTitle={false} />
            :
            <Flex
              display={{ default: 'inlineFlex' }}
              spaceItems={{ default: 'spaceItemsNone' }}
            >
              {queue.heads.map((head) => (
                head.map((item) => (
                  <FlexItem key={item.id}>
                    <QueueItemSquareWithPopover item={item} />
                  </FlexItem>
                ))
              ))}
            </Flex>
        )
      }
    })
  )
}

QueueSummary.propTypes = {
  pipeline: PropTypes.object,
  showAllQueues: PropTypes.bool,
  allQueuesExpanded: PropTypes.bool,
}

function PipelineSummary({ pipeline, tenant, showAllQueues, filters }) {

  const pipelineType = pipeline.manager || 'unknown'
  const itemCount = pipeline._itemCount
  const [areAllQueuesExpanded, setAreAllQueuesExpanded] = useState(undefined)
  const onQueueToggle = () => {
    setAreAllQueuesExpanded(!areAllQueuesExpanded)
  }

  return (
    <Card className="zuul-pipeline-summary zuul-compact-card">
      <CardTitle style={{ paddingBottom: '8px' }} >
        <Tooltip content={pipeline.description ? pipeline.description : ''}>
          <PipelineIcon pipelineType={pipelineType} />
        </Tooltip>
        <Link
          to={{
            pathname: `${tenant.linkPrefix}/status/pipeline/${pipeline.name}`,
            search: encodeURI(makeQueryString(filters)),
          }}
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
        {areAllQueuesExpanded ?
          <AngleDownIcon className="zuul-expand-icon" onClick={onQueueToggle} />
          :
          <AngleRightIcon className="zuul-expand-icon" onClick={onQueueToggle} />
        }
      </CardTitle>
      <CardBody>
        <QueueSummary
          pipeline={pipeline}
          showAllQueues={showAllQueues}
          allQueuesExpanded={areAllQueuesExpanded}
        />
      </CardBody>

    </Card>
  )
}

PipelineSummary.propTypes = {
  pipeline: PropTypes.object,
  tenant: PropTypes.object,
  showAllQueues: PropTypes.bool,
  filters: PropTypes.object,
}

export default PipelineSummary
