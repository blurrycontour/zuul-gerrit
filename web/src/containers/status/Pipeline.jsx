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
import { Title, Tooltip } from '@patternfly/react-core'

import ChangeQueue from './ChangeQueue'
import { PipelineIcon } from './Misc'

function getRefs(item) {
  // Backwards compat
  return 'refs' in item ? item.refs : [item]
}

class Pipeline extends React.Component {
  static propTypes = {
    expanded: PropTypes.bool.isRequired,
    pipeline: PropTypes.object.isRequired,
    filter: PropTypes.string
  }

  createTree(pipeline) {
    let count = 0
    let pipelineMaxTreeColumns = 1
    pipeline.change_queues.forEach(changeQueue => {
      let tree = []
      let maxTreeColumns = 1
      let changes = []
      let lastTreeLength = 0
      changeQueue.heads.forEach(head => {
        head.forEach((change, changeIndex) => {
          changes[change.id] = change
          change._tree_position = changeIndex
        })
      })
      // Generate a unique identifier for each queues
      changeQueue.uuid = Object.keys(changes).join('-')
      changeQueue.heads.forEach(head => {
        head.forEach(change => {
          if (change.live === true) {
            count += 1
          }
          let idx = tree.indexOf(change.id)
          if (idx > -1) {
            change._tree_index = idx
            // remove...
            tree[idx] = null
            while (tree[tree.length - 1] === null) {
              tree.pop()
            }
          } else {
            change._tree_index = 0
          }
          change._tree_branches = []
          change._tree = []
          if (typeof (change.items_behind) === 'undefined') {
            change.items_behind = []
          }
          change.items_behind.sort(function (a, b) {
            return (changes[b]._tree_position - changes[a]._tree_position)
          })
          change.items_behind.forEach(id => {
            tree.push(id)
            if (tree.length > lastTreeLength && lastTreeLength > 0) {
              change._tree_branches.push(tree.length - 1)
            }
          })
          if (tree.length > maxTreeColumns) {
            maxTreeColumns = tree.length
          }
          if (tree.length > pipelineMaxTreeColumns) {
            pipelineMaxTreeColumns = tree.length
          }
          change._tree = tree.slice(0) // make a copy
          lastTreeLength = tree.length
        })
      })
      changeQueue._tree_columns = maxTreeColumns
    })
    pipeline._tree_columns = pipelineMaxTreeColumns
    return count
  }

  filterQueue(queue, filter) {
    let found = false
    let filters = filter.replace(/ +/g, ',').split(',')
    queue.heads.forEach(itemList => {
      itemList.forEach(item => {
        getRefs(item).forEach(ref => {
          filters.forEach(changeFilter => {
            if (changeFilter && (
              (ref.project && ref.project.indexOf(changeFilter) !== -1) ||
                (ref.id && ref.id.indexOf(changeFilter) !== -1))) {
              found = true
              return
            }
          })
        })
        if (found) {
          return
        }
      })
      if (found) {
        return
      }
    })
    return found
  }

  renderPipelineName() {
    const { pipeline } = this.props
    let pipeline_type = pipeline.manager || 'unknown'

    return (
      <>
        <PipelineIcon pipelineType={pipeline_type} /> {pipeline.name}
      </>
    )
  }

  render() {
    const { pipeline, filter, expanded } = this.props
    const count = this.createTree(pipeline)
    return (
      <div className="zuul-pipeline col-sm-6 col-md-4">
        <div className="zuul-pipeline-header">
          <Title headingLevel="h3">
            {this.renderPipelineName()} <Badge>{count}</Badge>
          </Title>
          {pipeline.description ? (
            <small>
              <p>{pipeline.description.split(/\r?\n\r?\n/)}</p>
            </small>) : ''}
          <Tooltip position="top"
            content={<div>Unprocessed pipeline specific events</div>}>
            <small>
              <em>
                Events:&nbsp;
                {pipeline.trigger_events} trigger events,&nbsp;
                {pipeline.management_events} management events,&nbsp;
                {pipeline.result_events} results.
              </em>
            </small>
          </Tooltip>
        </div>
        {pipeline.change_queues.filter(item => item.heads.length > 0)
          .filter(item => (!filter || (
            filter.indexOf(pipeline.name) !== -1 ||
            this.filterQueue(item, filter)
          )))
          .map(changeQueue => (
            <ChangeQueue
              queue={changeQueue}
              expanded={expanded}
              pipeline={pipeline}
              key={changeQueue.uuid}
            />
          ))}
      </div>
    )
  }
}

export default Pipeline
