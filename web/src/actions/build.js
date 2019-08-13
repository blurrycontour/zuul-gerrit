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

import Axios from 'axios'
import yaml from 'js-yaml'

import * as API from '../api'

export const BUILD_FETCH_REQUEST = 'BUILD_FETCH_REQUEST'
export const BUILD_FETCH_SUCCESS = 'BUILD_FETCH_SUCCESS'
export const BUILD_FETCH_FAIL = 'BUILD_FETCH_FAIL'

export const BUILD_OUTPUT_REQUEST = 'BUILD_OUTPUT_REQUEST'
export const BUILD_OUTPUT_SUCCESS = 'BUILD_OUTPUT_SUCCESS'
export const BUILD_OUTPUT_FAIL = 'BUILD_OUTPUT_FAIL'

export const BUILD_MANIFEST_REQUEST = 'BUILD_MANIFEST_REQUEST'
export const BUILD_MANIFEST_SUCCESS = 'BUILD_MANIFEST_SUCCESS'
export const BUILD_MANIFEST_FAIL = 'BUILD_MANIFEST_FAIL'

export const requestBuild = () => ({
  type: BUILD_FETCH_REQUEST
})

export const receiveBuild = (buildId, build) => ({
  type: BUILD_FETCH_SUCCESS,
  buildId: buildId,
  build: build,
  receivedAt: Date.now()
})

const failedBuild = error => ({
  type: BUILD_FETCH_FAIL,
  error
})

export const requestBuildOutput = () => ({
  type: BUILD_OUTPUT_REQUEST
})

const receiveBuildOutput = (buildId, output) => {
  const hosts = {}
  // Compute stats
  output.forEach(phase => {
    Object.entries(phase.stats).forEach(([host, stats]) => {
      if (!hosts[host]) {
        hosts[host] = stats
        hosts[host].failed = []
      } else {
        hosts[host].changed += stats.changed
        hosts[host].failures += stats.failures
        hosts[host].ok += stats.ok
      }
      if (stats.failures > 0) {
        // Look for failed tasks
        phase.plays.forEach(play => {
          play.tasks.forEach(task => {
            if (task.hosts[host]) {
              if (task.hosts[host].results &&
                  task.hosts[host].results.length > 0) {
                task.hosts[host].results.forEach(result => {
                  if (result.failed) {
                    result.name = task.task.name
                    hosts[host].failed.push(result)
                  }
                })
              } else if (task.hosts[host].rc || task.hosts[host].failed) {
                let result = task.hosts[host]
                result.name = task.task.name
                hosts[host].failed.push(result)
              }
            }
          })
        })
      }
    })
  })
  return {
    type: BUILD_OUTPUT_SUCCESS,
    buildId: buildId,
    output: hosts,
    receivedAt: Date.now()
  }
}

const failedBuildOutput = error => ({
  type: BUILD_OUTPUT_FAIL,
  error
})

export const requestBuildManifest = () => ({
  type: BUILD_MANIFEST_REQUEST
})

const receiveBuildManifest = (buildId, manifest) => {
  const index = {}

  const renderNode = (root, object) => {
    const path = root + '/' + object.name

    if ('children' in object && object.children) {
      object.children.map(n => renderNode(path, n))
    } else {
      index[path] = object
    }
  }

  manifest.tree.map(n => renderNode('', n))
  return {
    type: BUILD_MANIFEST_SUCCESS,
    buildId: buildId,
    manifest: {tree: manifest.tree, index: index},
    receivedAt: Date.now()
  }
}

const failedBuildManifest = error => ({
  type: BUILD_MANIFEST_FAIL,
  error
})

export const fetchBuild = (tenant, buildId, state, force) => dispatch => {
  const build = state.build.builds[buildId]
  if (!force && build) {
    return Promise.resolve()
  }
  dispatch(requestBuild())
  return API.fetchBuild(tenant.apiPrefix, buildId)
    .then(response => {
      dispatch(receiveBuild(buildId, response.data))
    })
    .catch(error => dispatch(failedBuild(error)))
}

const fetchBuildOutput = (buildId, state, force) => dispatch => {
  const build = state.build.builds[buildId]
  const url = build.log_url.substr(0, build.log_url.lastIndexOf('/') + 1)
  if (!force && build.output) {
    return Promise.resolve()
  }
  dispatch(requestBuildOutput())
  // Try compressed yaml
  return Axios.get(url + 'job-output.yaml.gz', {
    transformResponse: (data) => {return yaml.load(data)}
  })
    .then(response => dispatch(receiveBuildOutput(buildId, response.data)))
    .catch(error => {
      if (!error.request) {
        throw error
      }
      // Try without compression
      Axios.get(url + 'job-output.yaml', {
        transformResponse: (data) => {return yaml.load(data)}
      })
        .then(response => dispatch(receiveBuildOutput(
          buildId, response.data)))
        .catch(error => {
          if (!error.request) {
            throw error
          }
          Axios.get(url + 'job-output.json.gz')
            .then(response => dispatch(receiveBuildOutput(buildId, response.data)))
            .catch(error => {
              if (!error.request) {
                throw error
              }
              // Try without compression
              Axios.get(url + 'job-output.json')
                .then(response => dispatch(receiveBuildOutput(
                  buildId, response.data)))
                .catch(error => dispatch(failedBuildOutput(error)))
            })
        })
     })
}

export const fetchBuildManifest = (buildId, state, force) => dispatch => {
  const build = state.build.builds[buildId]
  if (!force && build.manifest) {
    return Promise.resolve()
  }

  dispatch(requestBuildManifest())
  for (let artifact of build.artifacts) {
    if ('metadata' in artifact &&
        'type' in artifact.metadata &&
        artifact.metadata.type === 'zuul_manifest') {
      return Axios.get(artifact.url)
        .then(manifest => {
          dispatch(receiveBuildManifest(buildId, manifest.data))
        })
        .catch(error => dispatch(failedBuildManifest(error)))
    }
  }
  dispatch(failedBuildManifest('no manifest found'))
}

export const fetchBuildIfNeeded = (tenant, buildId, force) => (dispatch, getState) => {
  dispatch(fetchBuild(tenant, buildId, getState(), force))
    .then(() => {
      dispatch(fetchBuildOutput(buildId, getState(), force))
      dispatch(fetchBuildManifest(buildId, getState(), force))
    })
}
