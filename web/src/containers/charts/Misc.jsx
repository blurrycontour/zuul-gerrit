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

import { BUILDS_CONSTS } from '../../Misc'

const buildResultLegendData = Object.keys(BUILDS_CONSTS).map(result => (
    {
        name: result,
        symbol: {
            fill: BUILDS_CONSTS[result].color
        }
    })
)

const buildsBarStyleMap = buildResultLegendData.reduce(
    (final, x) => ({ ...final, [x.name]: x.symbol.fill }), {}
)

const buildsBarStyle = {
    data: {
        fill: ({ datum }) => buildsBarStyleMap[datum.result]
    }
}

export { buildResultLegendData, buildsBarStyleMap, buildsBarStyle }