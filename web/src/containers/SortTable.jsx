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

import React from 'react'
import PropTypes from 'prop-types'
import {SortByDirection, Table, TableBody, TableHeader, TableVariant, sortable} from '@patternfly/react-table'
import {IconProperty} from './build/Misc'
import {Spinner} from '@patternfly/react-core'

class SortTable extends React.Component {
  constructor(props) {
    super(props)
    this.onSort = this.onSort.bind(this)

    this.state = {
      sortBy: {
        index: props.defaultSortIndex || 1,
        direction: props.defaultSort === 'desc' ? SortByDirection.desc : SortByDirection.asc
      },
      columns: this.configToColumns(props.config),
      rows: this.dataToRows(props.config, props.data)
    }
  }

  static propTypes = {
    config: PropTypes.array.isRequired,
    data: PropTypes.array.isRequired,
    defaultSort: PropTypes.oneOf(['asc', 'desc']).isRequired,
    defaultSortIndex: PropTypes.number,
    fetching: PropTypes.bool,
    name: PropTypes.string.isRequired,
  }

  componentDidUpdate(prevProps) {
    if (this.props.data.length === 0 || this.props.data.length === prevProps.data.length)
      return
    this.updateRows()
  }

  updateRows() {
    const i = this.props.defaultSortIndex
    this.setState({
      rows: this.dataToRows(this.props.config, this.props.data)
        .sort((a, b) => (a[i].title < b[i].title ? -1 : a[i].title > b[i].title ? 1 : 0))
    })
  }

  dataToRows(config, data) {
    return data.reduce((acc, d) => {
      const row = []
      config.map(c => row.push({title: d[c.field], formatters: c.formatters}))
      acc.push(row)
      return acc
    }, [])
  }

  configToColumns(config) {
    return config.reduce((acc, c) => {
      acc.push({
        'title': <IconProperty icon={c.icon} value={c.name}/>,
        'transforms': c.sortable ? [sortable] : []
      })
      return acc
    }, [])
  }

  onSort(_event, index, direction) {
    const sortedRows = this.state.rows.sort((a, b) => (a[index].title < b[index].title ? -1 : a[index].title > b[index].title ? 1 : 0))
    this.setState({
      sortBy: {
        index,
        direction
      },
      rows: direction === SortByDirection.asc ? sortedRows : sortedRows.reverse()
    })
  }

  emptyRows() {
    return [
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
    ]
  }

  render() {
    const {name, fetching} = this.props
    const {columns, rows, sortBy} = this.state
    if (fetching) {
      return this.emptyRows()
    }
    return (
      <Table
        aria-label={`Sortable ${name}`}
        variant={TableVariant.compact}
        cells={columns}
        rows={rows}
        sortBy={sortBy}
        onSort={this.onSort}
      >
        <TableHeader/>
        <TableBody/>
      </Table>
    )
  }
}

export default SortTable
