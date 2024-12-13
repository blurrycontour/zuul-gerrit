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
import { useDispatch, useSelector } from 'react-redux'

import {
  Badge,
  Button,
  Card,
  CardHeader,
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
  StarIcon,
} from '@patternfly/react-icons'

import QueueItemPopover from './QueueItemPopover'
import { PipelineIcon, getQueueItemIconConfig } from './Misc'
import { makeQueryString } from '../FilterToolbar'
import ChangeQueue from './ChangeQueue'
import { expandQueue, collapseQueue } from '../../actions/statusExpansion'
import { pinPipeline, unpinPipeline } from '../../actions/pipelinePinning'

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

function QueueCard({ pipeline, queue, jobsExpanded }) {
  const expansionKey = `${pipeline.name}/${queue.name}`
  const expandedQueue = useSelector(state => state.statusExpansion.expandedQueue[expansionKey])
  const isQueueExpanded = expandedQueue === undefined ? jobsExpanded : expandedQueue
  const dispatch = useDispatch()

  const onQueueToggle = (isExpanded) => {
    if (isExpanded) {
      dispatch(expandQueue(expansionKey))
    } else {
      dispatch(collapseQueue(expansionKey))
    }
  }

  return (
    <Card isPlain className="zuul-compact-card">
      <CardHeader style={{ padding: '0' }}>
        <CardTitle>
          {queue.name}
          {queue.branch ? ` (${queue.branch})` : ''}
          <Tooltip
            content={
              <div style={{ textAlign: 'left' }}>
                Queue length: {queue._count}<br />Window size: {queue.window}
              </div>
            }
          >
            <Badge
              isRead
              style={{ marginLeft: 'var(--pf-global--spacer--sm)', verticalAlign: '0.1em' }}
            >
              {queue._count} / {queue.window}
            </Badge>
          </Tooltip>
          {isQueueExpanded ?
            <AngleDownIcon className="zuul-expand-icon" onClick={() => onQueueToggle(false)} />
            :
            <AngleRightIcon className="zuul-expand-icon" onClick={() => onQueueToggle(true)} />
          }
        </CardTitle>
      </CardHeader>
      {isQueueExpanded ? null :
        <CardBody style={{ padding: '0' }}>
          {queue.heads.map((head) => (
            head.map((item) => <QueueItemSquareWithPopover item={item} key={item.id} />)
          ))}
        </CardBody>
      }
      {isQueueExpanded ?
        <ChangeQueue queue={queue} pipeline={pipeline} showTitle={false} jobsExpanded={jobsExpanded} />
        : null
      }
    </Card>
  )
}

QueueCard.propTypes = {
  pipeline: PropTypes.object,
  queue: PropTypes.object,
  jobsExpanded: PropTypes.bool,
}

function QueueSummary({ pipeline, showAllQueues, allQueuesExpanded, jobsExpanded }) {
  let changeQueues = pipeline.change_queues

  if (!showAllQueues) {
    changeQueues = changeQueues.filter(queue => queue.heads.length > 0)
  }

  return (
    changeQueues.map((queue, idx) => {
      if (allQueuesExpanded) {
        // When a pipeline is expanded, we differentiate between named
        // and unnamed queues. Named queues are visualized independently
        // and can also be expanded individually.
        // Unnamed queues on the other hand will still be consolidated
        // as a single queue to simplify the visualization. This is the
        // case for e.g. independen pipelines like check where each
        // change is enqueued in it's own queue by design.
        return queue.name ?
          <QueueCard
            key={`${queue.name}${queue.branch}`}
            pipeline={pipeline}
            queue={queue}
            allQueuesExpanded={allQueuesExpanded}
            jobsExpanded={jobsExpanded}
          />
          :
          <ChangeQueue
            key={idx}
            queue={queue}
            pipeline={pipeline}
            showTitle={false}
            jobsExpanded={jobsExpanded}
          />
      }
      return (
        // In the collapsed view, the heads of all queues will be consolidated
        // into a single queue to simplify the visualization. This is done for
        // all queues (no matter if they are named or not) to keep the size of
        // the individual queues aligned and not break the gallery layout.
        <Flex
          key={idx}
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
    })
  )
}

QueueSummary.propTypes = {
  pipeline: PropTypes.object,
  showAllQueues: PropTypes.bool,
  allQueuesExpanded: PropTypes.bool,
  jobsExpanded: PropTypes.bool,
}

function PipelineSummary({ pipeline, tenant, showAllQueues, areAllJobsExpanded, filters }) {
  const pipelineType = pipeline.manager || 'unknown'
  const itemCount = pipeline._count
  const expansionKey = `${pipeline.name}`
  const expandedQueue = useSelector(state => state.statusExpansion.expandedQueue[expansionKey])
  const dispatch = useDispatch()

  const isQueueExpanded = expandedQueue === undefined ? areAllJobsExpanded : expandedQueue

  const pinKey = `${tenant.name}/${pipeline.name}`
  const isPipelinePinned = useSelector(state => state.pipelinePinning.pinnedPipelines[pinKey] === true)

  const onQueueToggle = (isExpanded) => {
    if (isExpanded) {
      dispatch(expandQueue(expansionKey))
    } else {
      dispatch(collapseQueue(expansionKey))
    }
  }

  const onPipelinePinToggle = (isPinned) => {
    if (isPinned) {
      dispatch(pinPipeline(pinKey))
    } else {
      dispatch(unpinPipeline(pinKey))
    }
  }

  return (
    <Card className="zuul-pipeline-summary zuul-compact-card">
      <CardHeader>
        <CardTitle>
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
          {isQueueExpanded ?
            <AngleDownIcon className="zuul-expand-icon" onClick={() => onQueueToggle(false)} />
            :
            <AngleRightIcon className="zuul-expand-icon" onClick={() => onQueueToggle(true)} />
          }
          <Button className="zuul-pipeline-fav" position="right" onClick={() => onPipelinePinToggle(!isPipelinePinned)}>
            <StarIcon className={isPipelinePinned? 'zuul-pipeline-fav-icon-enabled' : 'zuul-pipeline-fav-icon-disabled'} />
          </Button>
        </CardTitle>
      </CardHeader>
      <CardBody>
        <QueueSummary
          pipeline={pipeline}
          showAllQueues={showAllQueues}
          allQueuesExpanded={isQueueExpanded}
          jobsExpanded={areAllJobsExpanded}
        />
      </CardBody>

    </Card>
  )
}

PipelineSummary.propTypes = {
  pipeline: PropTypes.object,
  tenant: PropTypes.object,
  showAllQueues: PropTypes.bool,
  areAllJobsExpanded: PropTypes.bool,
  filters: PropTypes.object,
}

export default PipelineSummary
