// Copyright 2024 Acme Gating, LLC
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
  STATUSEXPANSION_EXPAND_JOBS,
  STATUSEXPANSION_COLLAPSE_JOBS,
  STATUSEXPANSION_CLEANUP_JOBS,
} from '../actions/statusExpansion'

export default (state = {
  expandedJobs: {},
}, action) => {
  switch (action.type) {
    case STATUSEXPANSION_EXPAND_JOBS:
      return {
        ...state,
        expandedJobs: {...state.expanded_Jobs, [action.key]: true}
      }
    case STATUSEXPANSION_COLLAPSE_JOBS:
      return {
        ...state,
        expandedJobs: {...state.expanded_Jobs, [action.key]: false}
      }
    case STATUSEXPANSION_CLEANUP_JOBS:
      // eslint-disable-next-line
      const {[action.key]:undefined, ...newJobs } = state.expandedJobs
      return {
        ...state,
        expandedJobs: newJobs,
      }
    default:
      return state
  }
}
