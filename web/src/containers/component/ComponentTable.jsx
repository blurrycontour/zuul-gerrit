// Copyright 2020 BMW Group
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
import PropTypes from 'prop-types'
import {
  Table,
  TableBody,
  TableHeader,
  TableVariant,
} from '@patternfly/react-table'
import {
  OnRunningIcon,
  OutlinedHddIcon,
  PauseCircleIcon,
  RunningIcon,
  QuestionIcon,
  ServiceIcon,
  StopCircleIcon,
} from '@patternfly/react-icons'

import { IconProperty } from '../build/Misc'

const STATE_ICON_CONFIGS = {
  RUNNING: {
    icon: RunningIcon,
    color: 'var(--pf-global--success-color--100)',
  },
  PAUSED: {
    icon: PauseCircleIcon,
    color: 'var(--pf-global--warning-color--100)',
  },
  STOPPED: {
    icon: StopCircleIcon,
    color: 'var(--pf-global--danger-color--100)',
  },
}

const DEFAULT_STATE_ICON_CONFIG = {
  icon: QuestionIcon,
  color: 'var(--pf-global--info-color--100)',
}

function ComponentStateIcon({ state }) {
  const iconConfig =
    STATE_ICON_CONFIGS[state.toUpperCase()] || DEFAULT_STATE_ICON_CONFIG
  const Icon = iconConfig.icon

  return (
    <span style={{ color: iconConfig.color }}>
      <Icon
        size="sm"
        style={{
          marginRight: 'var(--pf-global--spacer--sm)',
          verticalAlign: '-0.2em',
        }}
      />
    </span>
  )
}

function ComponentState({ state }) {
  const iconConfig =
    STATE_ICON_CONFIGS[state.toUpperCase()] || DEFAULT_STATE_ICON_CONFIG

  return <span style={{ color: iconConfig.color }}>{state.toUpperCase()}</span>
}

// TODO (felix): Group components by kind (like an accordion, but with multiple
// active sections).
function ComponentTable({ components }) {
  // TODO (felix): We could change this to an expandable table and show some
  // details about the component in the expandable row. E.g. similar to what
  // OpenShift shows in for deployments and pods (metrics, performance,
  // additional attributes).
  const columns = [
    {
      title: <IconProperty icon={<ServiceIcon />} value="Component" />,
      dataLabel: 'Component',
    },
    {
      title: <IconProperty icon={<OutlinedHddIcon />} value="Hostname" />,
      dataLabel: 'Hostname',
    },
    {
      title: <IconProperty icon={<OnRunningIcon />} value="State" />,
      dataLabel: 'State',
    },
  ]

  function createComponentRow(kind, component) {
    return {
      cells: [
        {
          title: (
            <>
              <ComponentStateIcon state={component.state} /> {kind}
            </>
          ),
        },
        component.hostname,
        {
          title: <ComponentState state={component.state} />,
        },
      ],
    }
  }

  const rows = []
  for (const [kind, _components] of Object.entries(components)) {
    for (const component of _components) {
      rows.push(createComponentRow(kind, component))
    }
  }

  return (
    <>
      <Table
        aria-label="Components Table"
        variant={TableVariant.compact}
        cells={columns}
        rows={rows}
        className="zuul-build-table"
      >
        <TableHeader />
        <TableBody />
      </Table>
    </>
  )
}

ComponentTable.propTypes = {
  components: PropTypes.object.isRequired,
}

export default ComponentTable
