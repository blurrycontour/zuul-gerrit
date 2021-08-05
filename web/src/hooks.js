// Copyright 2021 Red Hat, Inc
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

// Custom hooks used in zuul components

import React, {createContext, useContext, useState, useEffect} from 'react'

import { useDispatch } from 'react-redux'

const store = createContext({})
const { Provider } = store

export const StateProvider = (prop) => {
  const value = useState({})
  return <Provider value={value}>{prop.children}</Provider>
}

// Create a new object with arbitrary key value
const addKeyValue = (obj, key, value) => {
  const newObj = {}
  newObj[key] = value
  return {...obj, ...newObj}
}

export const useRemoteData = (title, fetch) => {
  const [state, setState] = useContext(store)
  const dispatch = useDispatch()
  useEffect(() => {
    document.title = 'Zuul ' + title
    fetch()
      .then(response => setState(state => addKeyValue(state, title, response.data)))
      .catch(error => dispatch({type: 'TENANTS_FETCH_FAIL', error}))
  }, [fetch, dispatch, title, setState])
  return state[title] || []
}
