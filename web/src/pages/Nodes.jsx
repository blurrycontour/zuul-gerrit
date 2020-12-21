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

import {
  ClusterIcon,
  InfrastructureIcon,
  KeyIcon,
  NetworkIcon,
  OutlinedCalendarAltIcon,
  OutlinedCommentsIcon,
  RunningIcon,
  TagIcon
} from '@patternfly/react-icons'

import * as moment from 'moment'

import { fetchNodesIfNeeded } from '../actions/nodes'
import {PageSection, PageSectionVariants} from '@patternfly/react-core'
import SortTable from '../containers/SortTable'

class NodesPage extends React.Component {
  constructor(props) {
    super(props)

    this.state = {
      fetching: false
    }
  }

  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData = (force) => {
    this.props.dispatch(fetchNodesIfNeeded(this.props.tenant, force))
  }

  componentDidMount() {
    document.title = 'Zuul Nodes'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate(prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  render() {
    const nodes = this.props.remoteData.nodes
    const building = nodes.filter(n => n.state === 'building').length
    const ready = nodes.filter(n => n.state === 'ready').length
    const inUse = nodes.filter(n => n.state === 'in-use').length
    const deleting = nodes.filter(n => n.state === 'deleting').length

    return (
      <PageSection variant={PageSectionVariants.light}>
        <div style={{marginBottom: 10}}>
          <div>
            <b>Summary
              : </b>{nodes.length} total, {building} building, {ready} ready, {inUse} in-use, {deleting} deleting
          </div>
        </div>
        <SortTable
          defaultSort={'asc'}
          defaultSortIndex={1}
          config={[
            {
              name: 'Id',
              sortable: false,
              icon: <KeyIcon/>,
              field: 'id',
              formatters: []
            },
            {
              name: 'Label',
              sortable: true,
              icon: <TagIcon/>,
              field: 'type',
              formatters: []
            },
            {
              name: 'Connection',
              sortable: false,
              icon: <NetworkIcon/>,
              field: 'connection_type',
              formatters: []
            },
            {
              name: 'Server',
              sortable: true,
              icon: <ClusterIcon/>,
              field: 'external_id',
              formatters: []
            },
            {
              name: 'Provider',
              sortable: true,
              icon: <InfrastructureIcon/>,
              field: 'provider',
              formatters: []
            },
            {
              name: 'State',
              sortable: true,
              icon: <RunningIcon/>,
              field: 'state',
              formatters: []
            },
            {
              name: 'Age',
              sortable: true,
              icon: <OutlinedCalendarAltIcon/>,
              field: 'state_time',
              formatters: [date => (moment.unix(date).fromNow())]
            },
            {
              name: 'Comment',
              sortable: false,
              icon: <OutlinedCommentsIcon/>,
              field: 'comment',
              formatters: []
            }
          ]}
          data={nodes}
          name={'Nodes Table'}/>
      </PageSection>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.nodes,
}))(NodesPage)
