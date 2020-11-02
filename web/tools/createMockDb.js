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

const fs = require('fs')
const path = require('path')
const mockData = require('./mockData')

const { builds, buildsets, configErrors, info, tenants } = mockData
const data = JSON.stringify({
  builds,
  buildsets,
  'config-errors': configErrors,
  info,
  tenants,
})
const filepath = path.join(__dirname, 'db.json')

fs.writeFile(filepath, data, function (err) {
  err ? console.log(err) : console.log('Mock DB created.')
})
