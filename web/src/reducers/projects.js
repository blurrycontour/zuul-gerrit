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
  PROJECTS_FETCH_FAIL,
  PROJECTS_FETCH_REQUEST,
  PROJECTS_FETCH_SUCCESS,
  PROJECTS_SORT,
  PROJECTS_FILTER
} from '../actions/projects'

/*
 * List of fields returned from API to show
 * as columns
 */
const table_columns = [
  'name',
  'connection_name',
  'type',
  'builds'
]

/*
 * Pretty name of table_columns entry,
 * and if this column is sortable
 */
const table_columns_descriptions = [
  ['Project', true ],
  ['Connection Type', true],
  ['Project Type', true],
  ['Recent Builds', false]
]

function sortRows(rows, index, direction) {
  if (index === -1) {
    return rows
  }

  return rows.slice().sort((a, b) => {
    // table_columns[index] is the name of the field
    // to sort on
    const field = table_columns[index]

    let av = a[field] ? a[field] : ''
    let bv = b[field] ? b[field] : ''

    return direction === 'asc' ?
      av.localeCompare(bv) :
      bv.localeCompare(av)
  })
}

export default (state = {
  isFetching: false,
  projects: [],
  sortIndex: -1,
  sortDirection: 'none',
  filterTerms: {},
  filterString: '',
  table_columns: table_columns,
  table_columns_descriptions: table_columns_descriptions
}, action) => {
  switch (action.type) {
    case PROJECTS_FETCH_REQUEST:
    return {
      ...state,
      isFetching: true,
    }
  case PROJECTS_FETCH_SUCCESS:
    return {
      ...state,
      isFetching: false,
      projects: sortRows(action.projects,
                         state.sortIndex,
                         state.sortDirection)
    }
  case PROJECTS_FETCH_FAIL:
    return {
      ...state,
      isFetching: false
    }
  case PROJECTS_SORT:
    return {
      ...state,
      projects: sortRows(state.projects,
                         action.sortIndex,
                         action.sortDirection),
      sortIndex: action.sortIndex,
      sortDirection: action.sortDirection
    }
  case PROJECTS_FILTER:
    return {
      ...state,
      filterTerms: action.filterTerms,
      filterString: action.filterString,
    }
  default:
    return state
  }
}
