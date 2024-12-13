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

export const PIPELINEPINNING_PIN = 'PIPELINEPINNING_PIN'
export const PIPELINEPINNING_UNPIN = 'PIPELINEPINNING_UNPIN'

const pinPipelineAction = (key) => ({
    type: PIPELINEPINNING_PIN,
    key: key,
})

const unpinPipelineAction = (key) => ({
    type: PIPELINEPINNING_UNPIN,
    key: key,
})

export const pinPipeline = (key) => (dispatch) => {
    dispatch(pinPipelineAction(key))
}

export const unpinPipeline = (key) => (dispatch) => {
    dispatch(unpinPipelineAction(key))
}
