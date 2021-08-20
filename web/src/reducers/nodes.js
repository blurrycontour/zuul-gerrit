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

import {
  NODES_FETCH_FAIL,
  NODES_FETCH_REQUEST,
  NODES_FETCH_SUCCESS,
  NODES_SORT
} from '../actions/nodes'

// This is the order the table should lay out the fields of the "node"
// object
const table_columns = [
  'id',
  'labels',
  'connection_type',
  'external_id',
  'provider',
  'state',
  'state_time',
  'comment'
]
// This is the human-readable name for each column above
const table_column_descriptions = [
  'ID',
  'Labels',
  'Connection Type',
  'Server',
  'Provider',
  'State',
  'Age',
  'Comment'
]

// Sort a list of nodes according to a given index and direction
function sortRows(rows, index, direction) {
  if (index === -1) {
    return rows
  }

  return rows.slice().sort((a, b) => {
    // table_columns[activeSortIndex] is the name of the
    // field to sort on
    const field = table_columns[index]

    if (field === 'labels') {
      const av = a.type ? a.type.join(',') : ''
      const bv = b.type ? b.type.join(',') : ''
      return direction === 'asc' ?
        av.localeCompare(bv) :
        bv.localeCompare(av)
    }
    if (typeof a[field] === 'number') {
      // numeric sort
      return direction === 'asc' ?
        a[field] - b[field] :
        b[field] - a[field]
    } else {
      /* sometimes can be null, make empty to avoid errors */
      const av = a[field] ? a[field] : ''
      const bv = b[field] ? b[field] : ''
      return direction === 'asc' ?
        av.localeCompare(bv) :
        bv.localeCompare(av)
    }
  })

}

export default (state = {
  receivedAt: 0,
  isFetching: false,
  nodes: [],
  activeSortIndex: -1,
  activeSortDirection: 'none',
  table_columns: table_columns,
  table_column_descriptions: table_column_descriptions
}, action) => {
  switch (action.type) {
  case NODES_FETCH_REQUEST:
    return {
      ...state,
      isFetching: true
    }
  case NODES_FETCH_SUCCESS:
    return {
      ...state,
      nodes:  sortRows(
        action.nodes, state.activeSortIndex, state.activeSortDirection),
      isFetching: false,
      receviedAt: action.receviedAt
    }
  case NODES_FETCH_FAIL:
    return {
      ...state,
      isFetching: false
    }
  case NODES_SORT:
    return {
      ...state,
      nodes: sortRows(state.nodes, action.sortIndex, action.sortDirection),
      activeSortIndex: action.sortIndex,
      activeSortDirection: action.sortDirection
    }
  default:
    return state
  }
}
