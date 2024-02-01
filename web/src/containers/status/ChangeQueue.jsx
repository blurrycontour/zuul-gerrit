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

import * as React from 'react'
import PropTypes from 'prop-types'
import { Badge } from 'patternfly-react'
import { Tooltip } from '@patternfly/react-core'

import Item from './Item'


class ChangeQueue extends React.Component {
  static propTypes = {
    pipeline: PropTypes.object.isRequired,
    queue: PropTypes.object.isRequired,
    expanded: PropTypes.bool.isRequired
  }

  render() {
    const { queue, pipeline, expanded } = this.props
    let fullName = queue.name
    if (queue.branch) {
      fullName = `${fullName} (${queue.branch})`
    }
    let shortName = fullName
    if (shortName.length > 32) {
      shortName = shortName.substr(0, 32) + '...'
    }
    let changesList = []
    queue.heads.forEach((items, itemIdx) => {
      items.forEach((item, idx) => {
        changesList.push(
          <Item
            item={item}
            queue={queue}
            expanded={expanded}
            pipeline={pipeline}
            key={itemIdx.toString() + idx}
          />)
      })
    })
    const window = queue.window || '\u221e'  // infinity
    const is_dependent = pipeline.manager === 'dependent'
    return (
      <div className="change-queue" data-zuul-pipeline={pipeline.name}>
        <p>
          Queue: <abbr title={fullName}>{shortName}</abbr>
          <Tooltip position="bottom"
                   content={
                     <div>
                       <p>Queue length: {changesList.length}</p>
                       {is_dependent && <p>Window size: {window}</p>}
                     </div>
                   }>
            <Badge>{changesList.length} {is_dependent && `/ ${window}`}</Badge>
          </Tooltip>
        </p>
        {changesList}
      </div>)
  }
}

export default ChangeQueue
