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
  Spinner,
} from '@patternfly/react-core'

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

import {
  Table,
  TableHeader,
  TableBody,
  TableVariant,
  sortable,
  SortByDirection,
} from '@patternfly/react-table'

import * as moment from 'moment'

import {fetchNodesIfNeeded} from '../actions/nodes'
import {PageSection, PageSectionVariants} from "@patternfly/react-core";
import {IconProperty} from "../containers/build/Misc";

class NodesPage extends React.Component {
  constructor(props) {
    super(props);
    const nodes = props.remoteData.nodes

    this.state = {
      sortBy: {index: 1, direction: SortByDirection.asc},
      columns: [
        {
          title: <IconProperty icon={<KeyIcon />} value="Id" />,
        },
        {
          title: <IconProperty icon={<TagIcon />} value="Label" />,
          transforms: [sortable]
        },
        {
          title: <IconProperty icon={<NetworkIcon />} value="Connection" />,
        },
        {
          title: <IconProperty icon={<ClusterIcon />} value="Server" />,
          transforms: [sortable]
        },
        {
          title: <IconProperty icon={<InfrastructureIcon />} value="Provider" />,
          transforms: [sortable]
        },
        {
          title: <IconProperty icon={<RunningIcon />} value="State" />,
          transforms: [sortable]
        },
        {
          title: <IconProperty icon={<OutlinedCalendarAltIcon />} value="Age" />,
          transforms: [sortable]
        },
        {
          title: <IconProperty icon={<OutlinedCommentsIcon />} value="Comment" />,
        },
      ],
      rows: this.parseRows(nodes),
      fetching: false,
    }
    this.onSort = this.onSort.bind(this);
  }

  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
    dispatch: PropTypes.func
  }

  updateData = (force) => {
    this.props.dispatch(fetchNodesIfNeeded(this.props.tenant, force))
  }

  parseRows = nodes => nodes.map(n => [
    {title: n.id},
    {title: n.type[0]},
    {title: n.connection_type},
    {title: n.external_id},
    {title: n.provider},
    {title: n.state},
    {title: n.state_time, formatters: [date => (moment.unix(date).fromNow())]},
    {title: n.comment}
  ])


  emptyRows = () => ([
    {
      heightAuto: true,
      cells: [
        {
          props: {colSpan: 8},
          title: (
            <center>
              <Spinner size="xl"/>
            </center>
          ),
        },
      ],
    },
  ])

  componentDidMount() {
    document.title = 'Zuul Nodes'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate(prevProps) {
    const {nodes, isFetching} = this.props.remoteData
    const {isFetching: wasFetching} = prevProps.remoteData
    if (isFetching !== wasFetching) {
      if (isFetching) {
        this.setState({rows: this.emptyRows()})
      } else {
        this.setState({
          rows: this.parseRows(nodes).sort((a, b) => (a[1].title < b[1].title ? -1 : a[1].title > b[1].title ? 1 : 0))
        })
      }
    }
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  onSort(_event, index, direction) {
    const sortedRows = this.state.rows.sort((a, b) => (a[index].title < b[index].title ? -1 : a[index].title > b[index].title ? 1 : 0));
    this.setState({
      sortBy: {
        index,
        direction
      },
      rows: direction === SortByDirection.asc ? sortedRows : sortedRows.reverse()
    });
  }

  render() {
    const {sortBy, rows, columns} = this.state
    const {nodes} = this.props.remoteData
    const building = nodes.filter(n => n.state === "building").length;
    const ready = nodes.filter(n => n.state === "ready").length;
    const inUse = nodes.filter(n => n.state === "in-use").length;
    const deleting = nodes.filter(n => n.state === "deleting").length;

    return (
      <PageSection variant={PageSectionVariants.light}>
        <div style={{marginBottom: 10}}>
          <div>
            <b>Summary
              : </b>{rows.length} total, {building} building, {ready} ready, {inUse} in-use, {deleting} deleting
          </div>
        </div>
        <PageSection style={{paddingRight: '5px'}}>
        </PageSection>
        <Table
          aria-label="Sortable Table"
          variant={TableVariant.compact}
          cells={columns}
          rows={rows}
          sortBy={sortBy}
          onSort={this.onSort}
        >
          <TableHeader/>
          <TableBody/>
        </Table>
      </PageSection>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  remoteData: state.nodes,
}))(NodesPage)
