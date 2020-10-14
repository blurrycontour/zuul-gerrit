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
  BUILD_FETCH_FAIL,
  BUILD_FETCH_REQUEST,
  BUILD_FETCH_SUCCESS,
  BUILDSET_FETCH_FAIL,
  BUILDSET_FETCH_REQUEST,
  BUILDSET_FETCH_SUCCESS,
  BUILD_OUTPUT_FAIL,
  BUILD_OUTPUT_REQUEST,
  BUILD_OUTPUT_SUCCESS,
  BUILD_MANIFEST_FAIL,
  BUILD_MANIFEST_REQUEST,
  BUILD_MANIFEST_SUCCESS,
} from '../actions/build'

export default (
  state = {
    isFetching: false,
    isFetchingOutput: false,
    isFetchingManifest: false,
    builds: {},
    buildsets: {},
  },
  action
) => {
  switch (action.type) {
    case BUILD_FETCH_REQUEST:
    case BUILDSET_FETCH_REQUEST:
      return { ...state, isFetching: true }
    case BUILD_FETCH_SUCCESS:
      return {
        ...state,
        builds: { ...state.builds, [action.buildId]: action.build },
        isFetching: false,
      }
    case BUILDSET_FETCH_SUCCESS:
      return {
        ...state,
        buildsets: { ...state.buildsets, [action.buildsetId]: action.buildset },
        isFetching: false,
      }
    case BUILD_FETCH_FAIL:
    case BUILDSET_FETCH_FAIL:
      return { ...state, isFetching: false }
    case BUILD_OUTPUT_REQUEST:
      return { ...state, isFetchingOutput: true }
    case BUILD_OUTPUT_SUCCESS: {
      const buildsWithOutput = {
        ...state.builds,
        [action.buildId]: {
          ...state.builds[action.buildId],
          errorIds: action.errorIds,
          hosts: action.hosts,
          output: action.output,
        },
      }
      return { ...state, builds: buildsWithOutput, isFetchingOutput: false }
    }
    case BUILD_OUTPUT_FAIL:
      return { ...state, isFetchingOutput: false }
    case BUILD_MANIFEST_REQUEST:
      return { ...state, isFetchingManifest: true }
    case BUILD_MANIFEST_SUCCESS: {
      const buildsWithManifest = {
        ...state.builds,
        [action.buildId]: {
          ...state.builds[action.buildId],
          manifest: action.manifest,
        },
      }
      return { ...state, builds: buildsWithManifest, isFetchingManifest: false }
    }
    case BUILD_MANIFEST_FAIL:
      return { ...state, isFetchingManifest: false }
    default:
      return state
  }
}
