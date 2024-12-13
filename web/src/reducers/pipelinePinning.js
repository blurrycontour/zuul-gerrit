// Copyright 2024 BMW Group
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

import {
    PIPELINEPINNING_PIN,
    PIPELINEPINNING_UNPIN,
} from '../actions/pipelinePinning'

export default(state = {
    pinnedPipelines: {},
}, action) => {
    switch (action.type) {
        case PIPELINEPINNING_PIN:
            return {
                ...state,
                pinnedPipelines: {...state.pinnedPipelines, [action.key]: true},
            }
        case PIPELINEPINNING_UNPIN:
            return {
                ...state,
                pinnedPipelines: {...state.pinnedPipelines, [action.key]: false},
            }
        default:
            return state
    }
}
