// Copyright 2020 BMW Group
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

import { applyMiddleware, compose, createStore } from 'redux'
import appReducer from './reducers'
import reduxImmutableStateInvariant from 'redux-immutable-state-invariant'
import thunk from 'redux-thunk'

export default function configureStore(initialState) {
  // Add support for Redux devtools
  const composeEnhancers =
    window.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__ || compose
  return createStore(
    appReducer,
    initialState,
    // Warn us if we accidentially mutate state directly in the Redux store
    // (only during development).
    composeEnhancers(
      applyMiddleware(
        thunk,
        reduxImmutableStateInvariant({
          // TODO (felix): The status page does some weird status mutations
          // between dispatches (so, most probably somewhere within its render
          // method or the render method of its child components). As I couldn't
          // find and fix this so far, let's ignore it for now. Otherwise it
          // makes the "single tenant" test in App.test.js fail.
          // The concrete path where state mutation is detected, is:
          // status.status.pipelines.0.change_queues.0.heads.0.0._tree_branches
          ignore: [
            'status.status.pipelines',
          ],
        })
      )
    )
  )
}
