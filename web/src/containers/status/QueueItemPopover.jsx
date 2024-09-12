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
import { IconProperty, formatTime } from '../../Misc'
import { connect } from 'react-redux'

import {
  Grid,
  GridItem,
  Popover,
} from '@patternfly/react-core'
import {
  OutlinedClockIcon,
  StopwatchIcon,
} from '@patternfly/react-icons'

import {
  calculateQueueItemTimes,
  ChangeLink,
  QueueItemProgressbar,
  getRefs
} from './Misc'

function QueueItemPopover({ item, triggerElement }) {
  // TODO (felix): Move the triggerElement to be used as children
  // instead. This should make the usage of the QueueItemPopover
  // a little nicer.
  const times = calculateQueueItemTimes(item)

  let remainingTime = 'unknown'
  if (times.remaining !== null) {
    remainingTime = formatTime(times.remaining)
  }

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

  return (
    <Popover
      aria-label="QueueItem Popover"
      headerContent={
        getRefs(item).map((change, idx) => (
          <div key={idx}>
            {change.project} <ChangeLink change={change} />
          </div>
        ))
      }
      bodyContent={
        <Grid hasGutter>
          <GridItem span={12}>
            <QueueItemProgressbar item={item} />
          </GridItem>
          <GridItem span={6}>
            {/* TODO (felix): Show the remaining time behind the
                progress bar like PF4 is doing:
                https://v4-archive.patternfly.org/v4/components/progress#outside

                This would also be achieved by converting the
                QueueItemProgressbar to use a PF4 Progress component.
              */}
            <IconProperty icon={<StopwatchIcon />} value={`${remainingTime}`} />
          </GridItem>
          <GridItem span={6}>
            <IconProperty icon={<OutlinedClockIcon />} value={formatEnqueueTime(item.enqueue_time)} />
          </GridItem>
        </Grid>
      }
    >
      {/* The triggerElement must be placed within the Popover to open it */}
      {triggerElement}
    </Popover>
  )
}

QueueItemPopover.propTypes = {
  item: PropTypes.object,
  triggerElement: PropTypes.object,
}

function mapStateToProps(state) {
  return {
    darkMode: state.preferences.darkMode,
  }
}

export default connect(mapStateToProps)(QueueItemPopover)
