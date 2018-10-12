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

import { ForceGraph3D } from 'react-force-graph'

class PipelinesGraph extends React.Component {
  static propTypes = {
    pipelines: PropTypes.array.isRequired,
    filter: PropTypes.string,
  }

  render () {
    let filters = []
    if (this.props.filter) {
      filters = this.props.filter.replace(' ', ',').split(',')
    }
    const graphData = {
      nodes: [{
        id: 'root',
        name: 'Zuul',
        color: 'orange',
      }],
      links: [],
    }
    let add_pipeline_node
    this.props.pipelines.forEach((pipeline, idx) => {
      add_pipeline_node = false
      pipeline.change_queues.forEach((changeQueue, cidx) => {
        let found = false
        if (filters.length === 0) {
          found = true
        }
        const cid = idx + '-' + cidx
        changeQueue.heads.forEach((head, hidx) => {
          const hid = cid + '-' + hidx
          let prevchid = cid
          head.forEach((change, chidx) => {
            filters.forEach(changeFilter => {
              if (changeFilter && (
                (change.project &&
                 change.project.indexOf(changeFilter) !== -1) ||
                (change.id &&
                 change.id.indexOf(changeFilter) !== -1))) {
                found = true
                return
              }
            })
            if (!found) {
              return
            }
            const chid = hid + '-' + chidx
            let jobRunning = 0
            let jobFailed = 0
            change.jobs.forEach((job) => {
              if (job.start_time > 0) {
                jobRunning += 1
              }
              if (job.result && job.result !== 'SUCCESS') {
                jobFailed += 1
              }
            })
            if (!found) {
              return
            }
            let color = 'grey'
            if (jobRunning > 0) {
              color = 'green'
            }
            if (jobFailed > 0) {
              color = 'red'
            }
            graphData.nodes.push({
              id: chid,
              name: change.project_canonical + '/' + change.id,
              color: color,
              size: 1,
              resolution: 2
            })
            graphData.links.push({
              source: chid,
              target: prevchid,
            })
            prevchid = chid
          })

        })
        if (!found || changeQueue.heads.length === 0) {
          return
        }
        add_pipeline_node = true
        graphData.nodes.push({
          id: cid,
          name: changeQueue.name,
          color: 'yellow',
          size: 2,
        })
        graphData.links.push({
          source: idx,
          target: cid
        })
      })
      if (!add_pipeline_node) {
        return
      }
      graphData.nodes.push({
        id: idx,
        name: pipeline.name,
        color: 'purple',
        size: 3,
      })
      graphData.links.push({
        source: 'root',
        target: idx,
      })
    })
    return (
        <ForceGraph3D
          graphData={graphData}
          d3Force='charge'
          />
    )
  }
}

export default PipelinesGraph
