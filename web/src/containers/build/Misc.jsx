// Copyright 2019 Red Hat, Inc
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
import { Label } from '@patternfly/react-core'
import {
  CheckIcon,
  ExclamationIcon,
  QuestionIcon,
  TimesIcon,
} from '@patternfly/react-icons'

const RESULT_ICON_CONFIGS = {
  SUCCESS: {
    icon: CheckIcon,
    color: 'var(--pf-global--success-color--100)',
    badgeColor: 'green',
  },
  FAILURE: {
    icon: TimesIcon,
    color: 'var(--pf-global--danger-color--100)',
    badgeColor: 'red',
  },
  RETRY_LIMIT: {
    icon: TimesIcon,
    color: 'var(--pf-global--danger-color--100)',
    badgeColor: 'red',
  },
  SKIPPED: {
    icon: QuestionIcon,
    color: 'var(--pf-global--info-color--100)',
    badgeColor: 'blue',
  },
  ABORTED: {
    icon: QuestionIcon,
    color: 'var(--pf-global--info-color--100)',
    badgeColor: 'yellow',
  },
  NODE_FAILURE: {
    icon: ExclamationIcon,
    color: 'var(--pf-global--warning-color--100)',
    badgeColor: 'orange',
  },
  TIMED_OUT: {
    icon: ExclamationIcon,
    color: 'var(--pf-global--warning-color--100)',
    badgeColor: 'orange',
  },
  POST_FAILURE: {
    icon: ExclamationIcon,
    color: 'var(--pf-global--warning-color--100)',
    badgeColor: 'orange',
  },
  CONFIG_ERROR: {
    icon: ExclamationIcon,
    color: 'var(--pf-global--warning-color--100)',
    badgeColor: 'orange',
  },
}

function BuildResult(props) {
  const { result, colored = true } = props
  const color = colored
    ? RESULT_ICON_CONFIGS[result].color
    : 'inherit'

  return <span style={{ color: color }}>{result}</span>
}

function BuildResultBadge(props) {
  const { result } = props
  const color = RESULT_ICON_CONFIGS[result].badgeColor

  return (
    <Label
      color={color}
      style={{
        marginLeft: 'var(--pf-global--spacer--sm)',
        verticalAlign: '0.15em',
      }}
    >
      {result}
    </Label>
  )
}

function BuildResultWithIcon(props) {
  // TODO (felix): Instead of "voting" provide "colored" and only specify a
  // color if color is set. Otherwise, no color should be set and the color of
  // the (disabled) list item should apply.
  const { result, colored = true, size = 'sm' } = props
  const iconConfig = RESULT_ICON_CONFIGS[result]

  // Define the verticalAlign based on the size
  let verticalAlign = '-0.2em'

  if (size === 'md') {
    verticalAlign = '-0.35em'
  }

  const Icon = iconConfig.icon
  const color = colored
    ? iconConfig.color
    : 'inherit'

  return (
    <span style={{ color: color }}>
      <Icon
        size={size}
        style={{
          marginRight: 'var(--pf-global--spacer--sm)',
          verticalAlign: verticalAlign,
        }}
      />
      {props.children}
    </span>
  )
}

function IconProperty(props) {
  const { icon, value, WrapElement = 'span' } = props
  return (
    <WrapElement style={{ marginLeft: '25px' }}>
      <span
        style={{
          marginRight: 'var(--pf-global--spacer--sm)',
          marginLeft: '-25px',
        }}
      >
        {icon}
      </span>
      <span>{value}</span>
    </WrapElement>
  )
}

export { BuildResult, BuildResultBadge, BuildResultWithIcon, IconProperty }
