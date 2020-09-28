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

// Use CommonJS require so we can dynamically import during build-time.
if (
  process.env.NODE_ENV === 'production' ||
  // FIXME (felix): This deactivates redux-immutable-state-invariant for tests.
  // Usually, this is not a good idea, but there are some weird state mutations
  // deep within the zuul-web JS code I couldn't track down so far. Both of them
  // make the "render single tenant" test in App.test.js. To still continue
  // development while using redux-immutable-state-invariant, remove it from the
  // test env for now by using the same store configuration as for the
  // production environment.

  // Some details to the state mutation errors:
  // 1. The status page does some weird status mutations between dispatches
  // (so, most probably somewhere within its render method or the render method
  // of its child components).
  // The concrete path where state mutation is detected, is:
  // status.status.pipelines.0.change_queues.0.heads.0.0._tree_branches

  // While we could also ignore the first error by providing an ignore parameter
  // to the reduxImmutableStateInvariant() when applying the middleware in
  // store.dev.js this doesn't "silence" the second error.
  // Just for reference, this would look like:
  // applyMiddleware(thunk, reduxImmutableStateInvariant({ ignore: ['status.status.pipelines']}))

  // 2.RangeError: Maximum call stack size exceeded
  //   at trackProperties (node_modules/redux-immutable-state-invariant/dist/trackForMutations.js:16:25)
  //   at trackProperties (node_modules/redux-immutable-state-invariant/dist/trackForMutations.js:32:31)
  //   at trackProperties (node_modules/redux-immutable-state-invariant/dist/trackForMutations.js:32:31)
  //   ...
  process.env.NODE_ENV === 'test'
) {
  module.exports = require('./store.prod')
} else {
  module.exports = require('./store.dev')
}
