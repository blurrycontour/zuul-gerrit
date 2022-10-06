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

function getHomepageUrl(url) {
  //
  // Discover serving location from href.
  //
  // This is only needed for sub-directory serving.
  // Serving the application from '/' may simply default to '/'
  //
  // Note that this is not enough for sub-directory serving,
  // The static files location also needs to be adapted with the 'homepage'
  // settings of the package.json file.
  //
  // This homepage url is used for the Router and Link resolution logic
  //
  let baseUrl
  if (url) {
    baseUrl = url
  } else {
    baseUrl = window.location.href
  }
  // Get dirname of the current url
  baseUrl = baseUrl.replace(/\\/g, '/').replace(/\/[^/]*$/, '/')

  // Remove any query strings
  if (baseUrl.includes('?')) {
    baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf('?'))
  }
  // Remove any hash anchor
  if (baseUrl.includes('/#')) {
    baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf('/#') + 1)
  }

  // Remove known sub-path
  const subDir = [
    '/autohold/',
    '/build/',
    '/buildset/',
    '/job/',
    '/project/',
    '/stream/',
    '/status/',
  ]
  subDir.forEach(path => {
    if (baseUrl.includes(path)) {
      baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf(path) + 1)
    }
  })

  // Remove tenant scope
  if (baseUrl.includes('/t/')) {
    baseUrl = baseUrl.slice(0, baseUrl.lastIndexOf('/t/') + 1)
  }
  if (!baseUrl.endsWith('/')) {
    baseUrl = baseUrl + '/'
  }
  // console.log('Homepage url is ', baseUrl)
  return baseUrl
}

function getZuulUrl() {
  // Return the zuul root api absolute url
  const ZUUL_API = process.env.REACT_APP_ZUUL_API
  let apiUrl

  if (ZUUL_API) {
    // Api url set at build time, use it
    apiUrl = ZUUL_API
  } else {
    // Api url is relative to homepage path
    apiUrl = getHomepageUrl() + 'api/'
  }
  if (!apiUrl.endsWith('/')) {
    apiUrl = apiUrl + '/'
  }
  if (!apiUrl.endsWith('/api/')) {
    apiUrl = apiUrl + 'api/'
  }
  // console.log('Api url is ', apiUrl)
  return apiUrl
}
const apiUrl = getZuulUrl()


function getStreamUrl(apiPrefix) {
  const streamUrl = (apiUrl + apiPrefix)
    .replace(/(http)(s)?:\/\//, 'ws$2://') + 'console-stream'
  // console.log('Stream url is ', streamUrl)
  return streamUrl
}

function getWithCorsHandling(url) {
  // This performs a simple GET and tries to detect if CORS errors are
  // due to proxy authentication errors.
  const instance = Axios.create({
    baseURL: apiUrl
  })
  // First try the request as normal
  let res = instance.get(url).catch(err => {
    if (err.response === undefined) {
      // This is either a Network, DNS, or CORS error, but we can't tell which.
      // If we're behind an authz proxy, it's possible our creds have timed out
      // and the CORS error is because we're getting a redirect.
      // Apache mod_auth_mellon (and possibly other authz proxies) will avoid
      // issuing a redirect if X-Requested-With is set to 'XMLHttpRequest' and
      // will instead issue a 403.  We can use this to detect that case.
      instance.defaults.headers.common['X-Requested-With'] = 'XMLHttpRequest'
      let res2 = instance.get(url).catch(err2 => {
        if (err2.response && err2.response.status === 403) {
          // We might be getting a redirect or something else,
          // so reload the page.
          console.log('Received 403 after unknown error; reloading')
          window.location.reload()
        }
        // If we're still getting an error, we don't know the cause,
        // it could be a transient network error, so we won't reload, we'll just
        // wait for it to clear.
        throw (err2)
      })
      return res2
    }
  })
  return res
}

// Direct APIs
function fetchInfo() {
  return getWithCorsHandling('info')
}

function fetchComponents() {
  return getWithCorsHandling('components')
}

function fetchTenantInfo(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'info')
}
function fetchOpenApi() {
  return Axios.get(getHomepageUrl() + 'openapi.yaml')
}
function fetchTenants() {
  return getWithCorsHandling(apiUrl + 'tenants')
}
function fetchConfigErrors(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'config-errors')
}
function fetchStatus(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'status')
}
function fetchChangeStatus(apiPrefix, changeId) {
  return getWithCorsHandling(apiPrefix + 'status/change/' + changeId)
}
function fetchFreezeJob(apiPrefix, pipelineName, projectName, branchName, jobName) {
  return getWithCorsHandling(apiPrefix +
                   'pipeline/' + pipelineName +
                   '/project/' + projectName +
                   '/branch/' + branchName +
                   '/freeze-job/' + jobName)
}
function fetchBuild(apiPrefix, buildId) {
  return getWithCorsHandling(apiPrefix + 'build/' + buildId)
}
function fetchBuilds(apiPrefix, queryString) {
  let path = 'builds'
  if (queryString) {
    path += '?' + queryString.slice(1)
  }
  return getWithCorsHandling(apiPrefix + path)
}
function fetchBuildset(apiPrefix, buildsetId) {
  return getWithCorsHandling(apiPrefix + 'buildset/' + buildsetId)
}
function fetchBuildsets(apiPrefix, queryString) {
  let path = 'buildsets'
  if (queryString) {
    path += '?' + queryString.slice(1)
  }
  return getWithCorsHandling(apiPrefix + path)
}
function fetchPipelines(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'pipelines')
}
function fetchProject(apiPrefix, projectName) {
  return getWithCorsHandling(apiPrefix + 'project/' + projectName)
}
function fetchProjects(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'projects')
}
function fetchJob(apiPrefix, jobName) {
  return getWithCorsHandling(apiPrefix + 'job/' + jobName)
}
function fetchJobGraph(apiPrefix, projectName, pipelineName, branchName) {
  return getWithCorsHandling(apiPrefix +
                   'pipeline/' + pipelineName +
                   '/project/' + projectName +
                   '/branch/' + branchName +
                   '/freeze-jobs')
}
function fetchJobs(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'jobs')
}
function fetchLabels(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'labels')
}
function fetchNodes(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'nodes')
}
function fetchSemaphores(apiPrefix) {
  return Axios.get(apiUrl + apiPrefix + 'semaphores')
}
function fetchAutoholds(apiPrefix) {
  return getWithCorsHandling(apiPrefix + 'autohold')
}
function fetchAutohold(apiPrefix, requestId) {
  return getWithCorsHandling(apiPrefix + 'autohold/' + requestId)
}

// token-protected API
function fetchUserAuthorizations(apiPrefix, token) {
  // Axios.defaults.headers.common['Authorization'] = 'Bearer ' + token
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.get(apiPrefix + 'authorizations')
    .catch(err => { console.log('An error occurred', err) })
  // Axios.defaults.headers.common['Authorization'] = ''
  return res
}

function dequeue(apiPrefix, projectName, pipeline, change, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/dequeue',
    {
      pipeline: pipeline,
      change: change,
    }
  )
  return res
}
function dequeue_ref(apiPrefix, projectName, pipeline, ref, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/dequeue',
    {
      pipeline: pipeline,
      ref: ref,
    }
  )
  return res
}

function enqueue(apiPrefix, projectName, pipeline, change, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/enqueue',
    {
      pipeline: pipeline,
      change: change,
    }
  )
  return res
}
function enqueue_ref(apiPrefix, projectName, pipeline, ref, oldrev, newrev, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/enqueue',
    {
      pipeline: pipeline,
      ref: ref,
      oldrev: oldrev,
      newrev: newrev,
    }
  )
  return res
}
function autohold(apiPrefix, projectName, job, change, ref,
  reason, count, node_hold_expiration, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + 'project/' + projectName + '/autohold',
    {
      change: change,
      job: job,
      ref: ref,
      reason: reason,
      count: count,
      node_hold_expiration: node_hold_expiration,
    }
  )
  return res
}

function autohold_delete(apiPrefix, requestId, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.delete(
    apiPrefix + '/autohold/' + requestId
  )
  return res
}

function promote(apiPrefix, pipeline, changes, token) {
  const instance = Axios.create({
    baseURL: apiUrl
  })
  instance.defaults.headers.common['Authorization'] = 'Bearer ' + token
  let res = instance.post(
    apiPrefix + '/promote',
    {
      pipeline: pipeline,
      changes: changes,
    }
  )
  return res
}


export {
  apiUrl,
  getHomepageUrl,
  getStreamUrl,
  fetchChangeStatus,
  fetchConfigErrors,
  fetchStatus,
  fetchBuild,
  fetchBuilds,
  fetchBuildset,
  fetchBuildsets,
  fetchFreezeJob,
  fetchPipelines,
  fetchProject,
  fetchProjects,
  fetchJob,
  fetchJobGraph,
  fetchJobs,
  fetchLabels,
  fetchNodes,
  fetchOpenApi,
  fetchSemaphores,
  fetchTenants,
  fetchInfo,
  fetchComponents,
  fetchTenantInfo,
  fetchUserAuthorizations,
  fetchAutoholds,
  fetchAutohold,
  autohold,
  autohold_delete,
  dequeue,
  dequeue_ref,
  enqueue,
  enqueue_ref,
  promote,
}
