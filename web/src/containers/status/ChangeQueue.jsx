// Copyright 2018 Red Hat, Inc
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
  Card,
  CardTitle,
  CardBody,
  Panel,
  ProgressStep,
  ProgressStepper,
  Title,
} from '@patternfly/react-core'

import QueueItem from './QueueItem'
import { getQueueItemIconConfig } from './Misc'


function ChangeQueue({ queue }) {
  return (
    <>
      <Card isPlain className="zuul-change-queue">
        {queue.name ?
          <CardTitle>
            <Title headingLevel="h3" style={{ padding: 0, margin: 0 }}>
              {queue.name}
              {queue.branch ? ` (${queue.branch})` : ''}
            </Title>
          </CardTitle>
          : ''}
        <CardBody>
          <Panel>
            <ProgressStepper isVertical>
              {queue.heads.map(head => (
                head.map(item => {
                  const iconConfig = getQueueItemIconConfig(item)
                  const Icon = iconConfig.icon
                  return (
                    <ProgressStep
                      variant={iconConfig.variant}
                      id={item.id}
                      titleId={item.id}
                      icon={<Icon />}
                      style={{ marginBottom: '16px' }}
                      key={item.id}
                    >
                      <QueueItem item={item} />
                    </ProgressStep>
                  )
                })
              ))}
            </ProgressStepper>
          </Panel>
        </CardBody>
      </Card >
    </>
  )
}

ChangeQueue.propTypes = {
  queue: PropTypes.object,
  tenant: PropTypes.object,
}

export default ChangeQueue
