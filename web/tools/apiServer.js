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

// This file allows us to configure JSON server to our needs. Since we use the
// API mainly to get the data from Zuul, but don't provide full-featured CRUD
// operations, we only tweak a few settings. For a list of possible extras take
// a look at https://github.com/typicode/json-server#extras.

const jsonServer = require('json-server')
const server = jsonServer.create()
const path = require('path')
// Make json-server look up the generated db.json file from the tools directory.
const router = jsonServer.router(path.join(__dirname, 'db.json'))

// Can pass a limited number of options to this to override (some) defaults.
// See https://github.com/typicode/json-server#api
const middlewares = jsonServer.defaults()

// Set default middlewares (logger, static, cors and no-cache)
server.use(middlewares)

// Change this value to simulate delay on all requests (milliseconds)
server.use(function (req, res, next) {
  setTimeout(next, 0)
})

server.use(
  jsonServer.rewriter({
    // This will prefix the path to all JSON server resources with "api", e.g.
    // /api/builds. This is also were Zuul expects the data to be served.
    '/api/*': '/$1',
    // The Zuul API serves single resources under a different path e.g. build/
    // instead of builds/
    '/build/:id': '/builds/:id',
    '/buildset/:id': '/buildsets/:id',
  })
)

// Tell json server to use the uuid field as key for it's database. By default,
// json server requires each object to provide an id field which will be used
// to look up a single resource. Unfortunately, Zuul only provides a uuid field
// for each object.
// NOTE (felix): When using json-server via comment line, this can easly be done
// by specyfing the --id parameter like this:
// $ json-server --id uuid
// Unfortunately, I didn't find a proper way when using the json-server API to
// create a custom server instance and the following line is also what
// json-server does when evaluating the command line argument:
// https://github.com/typicode/json-server/blob/4f315b090f6a504c261bab83894d3eb85eabe686/src/cli/run.js#L73
router.db._.id = 'uuid'
server.use(router)

// By default, JSON server is running on port 3000, which is already used by our
// react app. Thus, change the port to 3001 and start the server.
const port = 3001
server.listen(port, () => {
  console.log(`JSON Server is running on port ${port}`)
})
