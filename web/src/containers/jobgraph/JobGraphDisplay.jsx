// Copyright 2022 Acme Gating, LLC
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

import React, { useState, useEffect} from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import * as d3 from 'd3'

import { makeJobGraphKey, fetchJobGraphIfNeeded } from '../../actions/jobgraph'
import { graphviz } from 'd3-graphviz'

import { getHomepageUrl } from '../../api'

function makeDot(tenant, pipeline, project, branch, jobGraph) {
  let ret = 'digraph job_graph {\n'
  ret += '  rankdir=LR;\n'
  ret += '  node [shape=box];\n'
  jobGraph.forEach((job) => {
    const searchParams = new URLSearchParams('')
    searchParams.append('pipeline', pipeline)
    searchParams.append('project', project.name)
    searchParams.append('job', job.name)
    searchParams.append('branch', branch)
    const url = (getHomepageUrl() + tenant.linkPrefix +
                 'freeze-job?' + searchParams.toString())
    // Escape ampersands to get it through graphviz and d3; these will
    // appear unescaped in the DOM.
    const escaped_url = url.replace(/&/g, '&amp;')
    ret += '  "' + job.name + '" [URL="' + escaped_url + '"];\n'
    if (job.dependencies.length) {
      job.dependencies.forEach((dep) => {
        let soft = ''
        if (dep.soft) {
          soft = ' [style=dashed]'
        }
        ret += '  "' + dep.name + '" -> "' + job.name + '"' + soft + ';\n'
      })
    }
  })
  ret += '}\n'
  console.log(ret)
  return ret
}

function GraphViz(props) {
  useEffect(() => {
    const gv = graphviz('#graphviz')
          .options({
            fit: false,
            zoom: true,
            tweenPaths: false,
            scale: 0.75,
          }).renderDot(props.dot)

    // Fix up the initial values of the internal transform data;
    // without this the first time we pan the graph jumps.
    const element = d3.select('.zuul-job-graph > svg')
    const transform = element[0][0].firstElementChild.attributes.transform.value
    const match = transform.match(/translate\(\d+,(\d+)\).*/)
    if (match && match.length > 0) {
      const val = parseInt(match[1])
      gv._translation.y = val
      gv._originalTransform.y = val
    }
  }, [props.dot])

  return (
    <div className="zuul-job-graph" id="graphviz"/>
  )
}

GraphViz.propTypes = {
  dot: PropTypes.string.isRequired,
}

function JobGraphDisplay(props) {
  const [dot, setDot] = useState()
  const {fetchJobGraphIfNeeded, tenant, project, pipeline, branch} = props

  useEffect(() => {
    fetchJobGraphIfNeeded(tenant, project.name, pipeline, branch)
  }, [fetchJobGraphIfNeeded, tenant, project, pipeline, branch])

  const tenantJobGraph = props.jobgraph.jobGraphs[tenant.name]
  const jobGraphKey = makeJobGraphKey(props.project.name,
                                      props.pipeline,
                                      props.branch)
  const jobGraph = tenantJobGraph ? tenantJobGraph[jobGraphKey] : undefined
  useEffect(() => {
    if (jobGraph) {
      setDot(makeDot(tenant, pipeline, project, branch, jobGraph))
    }
  }, [tenant, pipeline, project, branch, jobGraph])
  return (
    <>
      {dot && <GraphViz dot={dot}/>}
    </>
  )
}

JobGraphDisplay.propTypes = {
  fetchJobGraphIfNeeded: PropTypes.func,
  tenant: PropTypes.object,
  project: PropTypes.object.isRequired,
  pipeline: PropTypes.string.isRequired,
  branch: PropTypes.string.isRequired,
  jobgraph: PropTypes.object,
  dispatch: PropTypes.func,
  state: PropTypes.object,
}
function mapStateToProps(state) {
  return {
    tenant: state.tenant,
    jobgraph: state.jobgraph,
    state: state,
  }
}

const mapDispatchToProps = { fetchJobGraphIfNeeded }

export default connect(mapStateToProps, mapDispatchToProps)(JobGraphDisplay)
