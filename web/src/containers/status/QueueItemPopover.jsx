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
import { connect } from 'react-redux'

import {
  Popover,
} from '@patternfly/react-core'

import {
  calculateQueueItemTimes,
  ChangeLink,
  getRefs
} from './Misc'

import QueueItemProgress from './QueueItemProgress'

function QueueItemPopover({ item, triggerElement }) {
  // TODO (felix): Move the triggerElement to be used as children
  // instead. This should make the usage of the QueueItemPopover
  // a little nicer.
  const times = calculateQueueItemTimes(item)

  return (
    <Popover
      className="zuul-queue-item-popover"
      aria-label="QueueItem Popover"
      headerContent={
        getRefs(item).map((change, idx) => (
          <div key={idx}>
            {change.project} <ChangeLink change={change} />
          </div>
        ))
      }
      bodyContent={
        <QueueItemProgress item={item} times={times} />
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
