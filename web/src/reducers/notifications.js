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

import update from 'immutability-helper'

import {
  ADD_NOTIFICATION,
  CLEAR_NOTIFICATION,
  CLEAR_NOTIFICATIONS,
  addApiError,
} from '../actions/notifications'


export default (state = [], action) => {
  // Intercept API failure
  if (action.notification && action.type.match(/.*_FETCH_FAIL$/)) {
    action = addApiError(action.notification)
  }
  // Intercept Admin API failures
  if (action.notification && action.type.match(/ADMIN_.*_FAIL$/)) {
    action = addApiError(action.notification)
  }
  switch (action.type) {
    case ADD_NOTIFICATION:
      if (state.filter(notification => (
        notification.url === action.notification.url &&
        notification.status === action.notification.status)).length > 0)
        return state
      action.notification.id = action.id
      action.notification.date = Date.now()
      return update(state, { $push: [action.notification] })
    case CLEAR_NOTIFICATION:
      return update(state, {
        $splice: [[state.indexOf(
          state.filter(item => (item.id === action.id))[0]), 1]]
      })
    case CLEAR_NOTIFICATIONS:
      return []
    default:
      return state
  }
}
