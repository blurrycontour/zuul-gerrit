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

import ChangeQueue from './ChangeQueue'

import {
  CodeBranchIcon,
  OutlinedCalendarAltIcon,
  FlaskIcon,
  SortAmountDownIcon,
  BundleIcon,
  StreamIcon,
} from '@patternfly/react-icons'

const PIPELINE_ICONS = {
  periodic: {
    icon: OutlinedCalendarAltIcon,
    help: 'A periodic pipeline runs jobs on a regular basis.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/drivers/timer.html',
  },
  dependent: {
    icon: CodeBranchIcon,
    help: 'A dependent pipeline ensures that every change is tested exactly in the order it is going to be merged into the repository.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.dependent',
  },
  independent: {
    icon: FlaskIcon,
    help: 'An independent pipeline treats every change as independent of other changes in it.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.independent',
  },
  serial: {
    icon: SortAmountDownIcon,
    help: 'A serial pipeline supports shared queues, but only one item in each shared queue is processed at a time.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.serial',
  },
  supercedent: {
    icon: BundleIcon,
    help: 'A supercedent pipeline groups items by project and ref, and processes only one item per grouping at a time. Only two items (currently processing and latest) can be queued per grouping.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.supercedent',
  },
  unknown: {
    icon: StreamIcon,
    help: 'Unknown pipeline type',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html'
  },
}

const DEFAULT_PIPELINE_ICON = PIPELINE_ICONS['unknown']

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
    queue.heads.forEach(changes => {
      changes.forEach(change => {
        filters.forEach(changeFilter => {
          if (changeFilter && (
            (change.project && change.project.indexOf(changeFilter) !== -1) ||
            (change.id && change.id.indexOf(changeFilter) !== -1))) {
            found = true
            return
          }
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

  renderPipelineIcon() {
    const { pipeline } = this.props
    let pipeline_type = pipeline.manager || 'unknown'
    // override if periodic
    if (pipeline.triggers) {
      pipeline.triggers.forEach(trigger => {
        if (trigger.driver === 'timer') {
          pipeline_type = 'periodic'
        }
      })
    }
    const pl_config = PIPELINE_ICONS[pipeline_type] || DEFAULT_PIPELINE_ICON
    const Icon = pl_config.icon
    return (
      <a href={pl_config.doc_url} style={{ text_decoration: 'none', color: 'inherit' }}>
        <Icon title={pl_config.help} />
      </a>
    )
  }

  render() {
    const { pipeline, filter, expanded } = this.props
    const count = this.createTree(pipeline)
    return (
      <div className="pf-c-content zuul-pipeline col-sm-6 col-md-4">
        <div className="zuul-pipeline-header">
          <h3>
            {this.renderPipelineIcon()} {pipeline.name} <Badge>{count}</Badge>
          </h3>
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
              pipeline={pipeline.name}
              key={changeQueue.uuid}
            />
          ))}
      </div>
    )
  }
}

export default Pipeline
