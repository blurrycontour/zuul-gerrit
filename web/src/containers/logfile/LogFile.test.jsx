// Copyright 2021 Red Hat, Inc
//
// Licensed under the Apache License, Version 2.0 (the 'License'); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an 'AS IS' BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

import React from 'react'
import ReactDOM from 'react-dom'
import LogFile from './LogFile'

const fakeFile = (width, height) =>
  Array(height).fill({severity: 42, text: 'x'.repeat(width) }).map((x, index) => Object.assign({index}, x))

it('LogFile renders big file', () => {
  const div = document.createElement('div')
  const logfile = fakeFile(1024 * 10, 1024)
  const fakeClick = () => {}
  const begin = performance.now()
  ReactDOM.render(
    <LogFile
      logfileName='fake'
      logfileContent={logfile}
      isFetching={false}
      handleBreadcrumbItemClick={fakeClick}
      location={{}}
      history={{}}
    />,
    div,
    () => {
      const end = performance.now()
      console.log('Render took ' + (end - begin) + ' milliseconds.')
    }
  )
})
