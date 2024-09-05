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
  Tooltip,
} from '@patternfly/react-core'

import {
  OutlinedClockIcon,
  StopwatchIcon,
} from '@patternfly/react-icons'

import { IconProperty, formatTime } from '../../Misc'
import { QueueItemProgressbar } from './Misc'


function QueueItemProgress({ item, times }) {

  const formatEnqueueTime = (ms) => {
    let hours = 60 * 60 * 1000
    let now = Date.now()
    let delta = now - ms
    let text = formatTime(delta)
    let color = 'var(--pf-global--success-color--100)'

    // TODO (felix): Those color "thresholds" are currently the same for
    // each job. Maybe we could define those based on the average job
    // run time (which would be the remaining time, right?).
    if (delta > (4 * hours)) {
      color = 'var(--pf-global--danger-color--100)'
    } else if (delta > (2 * hours)) {
      color = 'var(--pf-global--warning-color--100)'
    }

    return <span style={{ color: color }}>{text}</span>
  }

  let remainingTime = '-'
  if (times.remaining !== null) {
    remainingTime = formatTime(times.remaining)
  }

  return (
    <Grid className="zuul-compact-grid">
      <GridItem>
        <QueueItemProgressbar item={item} />
      </GridItem>
      <GridItem span={6}>
        <Tooltip content="Elapsed Time" position="right">
          <IconProperty icon={<StopwatchIcon />} value={formatEnqueueTime(item.enqueue_time)} />
        </Tooltip>
      </GridItem>
      <GridItem
        span={6}
        className={
          item.remaining_time !== null ? 'zuul-remaining-time' : 'zuul-unknown-remaining-time'
        }
      >
        <Tooltip content="Remaining Time" position="right">
          <IconProperty icon={<OutlinedClockIcon />} value={`${remainingTime}`} />
        </Tooltip>
      </GridItem>
    </Grid>
  )
}


QueueItemProgress.propTypes = {
  item: PropTypes.object,
  times: PropTypes.object,
}

export default QueueItemProgress
