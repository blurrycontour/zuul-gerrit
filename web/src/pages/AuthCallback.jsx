// Copyright 2020 Red Hat, Inc
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

import React, { useEffect } from 'react'
import { useHistory } from 'react-router-dom'

import { Fetching } from '../containers/Fetching'

// Several pages use the location hash in a way that would be
// difficult to disentangle from the OIDC callback parameters.  This
// dedicated callback page accepts the OIDC params and then internally
// redirects to the page we saved before redirecting to the IDP.

function AuthCallbackPage() {
  let history = useHistory()

  useEffect(() => {
    const redirect = localStorage.getItem('zuul_auth_redirect')
    history.push(redirect)
  }, [history])

  return (
    <>
      <div>Login successful. You will be redirected shortly...</div>
      <Fetching />
    </>
  )
}

export default AuthCallbackPage
