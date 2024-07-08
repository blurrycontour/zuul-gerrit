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

function QueueItemPopover({ item, triggerElement, tenant }) {
  // TODO (felix): Move the triggerElement to be used as children
  // instead. This should make the usage of the QueueItemPopover
  // a little nicer.

  const [isVisible, setIsVisible] = useState(false)
  const times = calculateQueueItemTimes(item)

  return (
    <Popover
      className="zuul-queue-item-popover"
      aria-label="QueueItem Popover"
      position="top"
      isVisible={isVisible}
      // Set minimal distance to target element, so we are able to move
      // the cursor to the popover without closing it (this is only
      // needed when the popover was opened via hover and not via a
      // click).
      // TODO (felix): The Popover is larger in light mode than in dark
      // mode, which makes it overlapping with the trigger/target element.
      distance={1}
      // Custom open/close handlers to allow opening the popover via
      // a mouse hover over the triggerElement. The "click listeners"
      // (shouldOpen, shouldClose) are still used to allow closing the
      // popover with a click when it was opened via a hover. This is
      // useful if you want to switch to another QueueItemSqwuare
      // (triggerElelemt) that is overlapped by the active popover.
      shouldOpen={() => setIsVisible(true)}
      shouldClose={() => setIsVisible(false)}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
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
      footerContent={
        <Link to={tenant.linkPrefix + '/status/change/' + getRefs(item)[0].id}>Show details</Link>
      }
    >
      {/* The triggerElement must be placed within the Popover to open it */}
      <span
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
      >
        {triggerElement}
      </span>
    </Popover>
  )
}

QueueItemPopover.propTypes = {
  item: PropTypes.object,
  triggerElement: PropTypes.object,
  tenant: PropTypes.object,
}

function mapStateToProps(state) {
  return {
    tenant: state.tenant,
    darkMode: state.preferences.darkMode,
  }
}

export default connect(mapStateToProps)(QueueItemPopover)
