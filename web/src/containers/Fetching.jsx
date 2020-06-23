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

import * as React from 'react'
import PropTypes from 'prop-types'

import {
  Title,
  EmptyState,
  EmptyStateVariant,
  Spinner,
} from '@patternfly/react-core'

class Fetching extends React.Component {
  static propTypes = {
    tenant: PropTypes.object,
    remoteData: PropTypes.object,
  }

  render() {
    return (
      <EmptyState variant={EmptyStateVariant.small}>
        <Spinner />
        <Title headingLevel="h4" size="lg">
          Fetching info...
        </Title>
      </EmptyState>
    )
  }
}

export default Fetching
