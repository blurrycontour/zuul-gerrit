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
import * as moment from 'moment'

import {
  Flex,
  FlexItem,
  Label,
  PageSection,
  PageSectionVariants,
  Title
} from '@patternfly/react-core'

import {
  TableComposable,
  Thead,
  Tbody,
  Tr,
  Th,
  Td
} from '@patternfly/react-table'

import { fetchNodesIfNeeded, sortNodes } from '../actions/nodes'
import { Fetchable } from '../containers/Fetching'

class NodesPage extends React.PureComponent {
  static propTypes = {
    tenant: PropTypes.object,
    nodes: PropTypes.array,
    isFetching: PropTypes.bool,
    activeSortIndex: PropTypes.number,
    activeSortDirection: PropTypes.string,
    table_columns: PropTypes.array,
    table_column_descriptions: PropTypes.array,
    dispatch: PropTypes.func
  }

  updateData = (force) => {
    this.props.dispatch(fetchNodesIfNeeded(this.props.tenant, force))
  }

  componentDidMount () {
    document.title = 'Zuul Nodes'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate (prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  onSort = (event, index, direction) => {
    this.props.dispatch(sortNodes(index, direction))
  }

  cellFormat = (field, node) => {
    if (field === 'id') {
      return (<tt>{node.id}</tt>)
    }
    if (field === 'external_id') {
      return (<tt>{node.external_id}</tt>)
    }
    if (field === 'labels') {
      if (node.type && node.type.length > 0) {
        return (<React.Fragment>
                  {node.type.map((x,idx) => (
                    <Label key={idx} variant='outline'>{x}</Label>
                  ))}
                </React.Fragment>)
      } else {
        return null
      }
    }
    else if (field === 'state_time') {
      return moment.unix(node['state_time']).fromNow()
    }
    else if (field === 'state') {
      const value = node.state
      if (value === 'in-use') {
        return (<Label color="green">in-use</Label>)
      }
      else if (value === 'deleting') {
        return (<Label color="orange">deleting</Label>)
      }
      else if (value === 'ready') {
        return (<Label color="cyan">ready</Label>)
      }
      else if (value === 'hold') {
        return (<Label color="purple">hold</Label>)
      }
      else {
        return (<Label color="grey">{value}</Label>)
      }
    }
    else {
      return node[field]
    }
  }

  render () {
    return (
      <React.Fragment>
        <PageSection>
          <Flex>
            <FlexItem>
              <Title headingLevel="h2">Node overview</Title>
            </FlexItem>
            <FlexItem align={{ default: 'alignRight' }}>
              <Fetchable
                isFetching={this.props.isFetching}
                fetchCallback={this.updateData}
              />
            </FlexItem>
          </Flex>
        </PageSection>
        <PageSection variant={PageSectionVariants.light}>
          <TableComposable variant='compact'>
            <Thead>
              <Tr>
                {this.props.table_column_descriptions.map((column, idx) => {
                  const sortParams = {
                    sort: {
                      sortBy: {
                        index: this.props.activeSortIndex,
                        direction: this.props.activeSortDirection
                      },
                      onSort: this.onSort,
                      columnIndex: idx
                    }
                  }
                  return(
                    <Th key={idx} {...sortParams}>{column}</Th>
                  ) })
                }
              </Tr>
            </Thead>
            <Tbody>
              {this.props.nodes.map((row, rowIdx) => (
                <Tr key={rowIdx}>
                  {this.props.table_columns.map((colName, cellIdx) => (
                    <Td key={`${rowIdx}_${cellIdx}`}
                        dataLabel={this.props.table_column_descriptions[cellIdx]}>
                      {this.cellFormat(colName, row)}
                    </Td>)
                                               )}
                </Tr>))}
            </Tbody>
          </TableComposable>
        </PageSection>
      </React.Fragment>
    )
  }
}

function mapStateToProps(state) {
  return {
    tenant: state.tenant,
    isFetching: state.nodes.isFetching,
    nodes: state.nodes.nodes,
    activeSortDirection: state.nodes.activeSortDirection,
    activeSortIndex: state.nodes.activeSortIndex,
    table_columns: state.nodes.table_columns,
    table_column_descriptions: state.nodes.table_column_descriptions
  }
}

export default connect(mapStateToProps)(NodesPage)
