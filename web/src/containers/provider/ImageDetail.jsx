// Copyright 2024 Acme Gating, LLC
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

import React from 'react'
import {
  DescriptionList,
  DescriptionListTerm,
  DescriptionListGroup,
  DescriptionListDescription,
} from '@patternfly/react-core'

function ProviderDetail(props) {
  const {image} = props
  return (
    <>
      <DescriptionList isHorizontal
                       style={{'--pf-c-description-list--RowGap': '0rem'}}
                       className='pf-u-m-xl'>
        <DescriptionListGroup>
          <DescriptionListTerm>
            Name
          </DescriptionListTerm>
          <DescriptionListDescription>
            {image.name}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>
            Canonical Name
          </DescriptionListTerm>
          <DescriptionListDescription>
            {image.canonical_name}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>
            Type
          </DescriptionListTerm>
          <DescriptionListDescription>
            {image.type}
          </DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    </>
  )
}

export default ProviderDetail
