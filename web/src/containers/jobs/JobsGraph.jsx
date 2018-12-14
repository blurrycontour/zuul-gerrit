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
import { connect } from 'react-redux'
import { withRouter } from 'react-router'
import { cluster, stratify } from 'd3-hierarchy'
import { select } from 'd3-selection'


class JobsGraph extends React.Component {
  static propTypes = {
    jobs: PropTypes.array,
    tenant: PropTypes.object,
    history: PropTypes.object,
    width: PropTypes.integer,
    height: PropTypes.integer,
  }

  createJobGraph() {
    const node = this.node
    const { jobs } = this.props

    // Adjust height base on job count
    select(node)
      .attr('height', 15 * jobs.length)

    // Prepare tree
    const w = select(this.node).attr('width')
    const h = select(this.node).attr('height')
    const tree = cluster().size([h, w - 250])

    // Create tree
    // TODO: ensure 'root' job doesn't exist
    jobs.push({name: 'root'})
    const root = stratify()
      .id((d) => {
        return d.name
      })
      .parentId((d) => {
        if (d.name != 'root' && !d.parent || d.name == 'noop') {
          return 'root'
        }
        return d.parent
      })(jobs)
    tree(root)

    // Create svg
    const svg = select(this.node)
          .append('g').attr('transform', 'translate(40,0)')

    // Add links
    svg.selectAll('.link')
      .data(root.descendants().slice(1))
      .enter()
      .append('path')
      .attr('class', 'link')
      .attr('d', (d) => {
        return 'M' + d.y + ',' + d.x + 'C' + (d.parent.y + 100) + ',' + d.x +
          ' ' + (d.parent.y + 100) + ',' + d.parent.x + ' ' +
          d.parent.y + ',' + d.parent.x
      })

    // Add nodes
    const n = svg.selectAll('.node')
          .data(root.descendants())
          .enter().append('g')
          .attr('transform', (d) => {
            return 'translate(' + d.y + ',' + d.x + ')'
          })
    n.append('circle').attr('r', 2)

    // Add node text
    const { history, tenant } = this.props
    n.append('svg:a')
      .attr('xlink:href', '#')
      .on('click', (d) => {history.push(tenant.linkPrefix + '/job/' + d.id)})
      .append('text')
      .attr('dy', 3)
      .attr('x', (d) => {return d.children ? -8 : 8})
      .style('text-anchor', (d) => {return d.children ? 'end' : 'start'})
      .text((d) => {return d.id})
  }

  componentDidMount() {
    this.createJobGraph()
  }

  componentDidUpdate() {
    this.createJobGraph()
  }

  render() {
    return (
      <svg
        style={{font: '14px sans-serif'}}
        ref={node => this.node = node}
        width={this.props.width}
        height={this.props.height} />
    )
  }
}

export default withRouter(connect(state => ({
  tenant: state.tenant
}))(JobsGraph))
