// Copyright 2019 Red Hat, Inc
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
  TreeView,
} from 'patternfly-react'

const renderTree = (select, tenant, build, path, obj) => {
  const node = {}
  let name = obj.name

  if ('children' in obj && obj.children) {
    node.nodes = obj.children.map(n => renderTree(select, tenant, build, path+obj.name+'/', n))
  }
  if (obj.mimetype === 'application/directory') {
    name = obj.name + '/'
  } else {
    node.icon = 'fa fa-file-o'
  }

  let log_url = build.log_url
  if (log_url.endsWith('/')) {
    log_url = log_url.slice(0, -1)
  }

  if (obj.mimetype === 'text/plain') {
    node.text = (
      <span>
        <span onClick={() => {select(
        build.uuid,
        (path+name).slice(1),
          false)}}> {obj.name} </span>
        &nbsp;&nbsp;
        (<a href={log_url + path + name}>raw</a>
        &nbsp;<span className="fa fa-external-link"/>)
      </span>)
  } else {
    node.text = (
      <span>
        <a href={log_url + path + name}>{obj.name}</a>
        &nbsp;<span className="fa fa-external-link"/>
      </span>
    )
  }
  return node
}

class Manifest extends React.Component {
  static propTypes = {
    tenant: PropTypes.object.isRequired,
    build: PropTypes.object.isRequired,
    select: PropTypes.object
  }

  render() {
    const { tenant, build, select } = this.props

    const nodes = build.manifest.tree.map(n => renderTree(select, tenant, build, '/', n))

    return (
      <React.Fragment>
        <br/>
        <div className="tree-view-container">
          <TreeView
            nodes={nodes}
          />
        </div>
      </React.Fragment>
    )
  }
}

export default Manifest
