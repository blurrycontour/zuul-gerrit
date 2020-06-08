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

// The App is the parent component of every pages. Each page content is
// rendered by the Route object according to the current location.

import PropTypes from 'prop-types'
import React from 'react'
import { connect } from 'react-redux'


class Logout extends React.Component {
   static propTypes = {
       userManager: PropTypes.object,
       userInfo: PropTypes.object,
   }

   render() {
       const { userManager, userInfo } = this.props
       console.log('userManager:', userManager)
       console.log('userInfo:', userInfo)
       return (
           <div>
             Hello {userInfo.user ? userInfo.user.profile.name : "Anonymous Coward"}
             <button onClick={() => {userManager.removeUser()}}>Sign out</button>
           </div>)
   }
}

export default connect(state =>({
    userManager: state.auth.userManager,
    userInfo: state.userInfo,
}))(Logout)
