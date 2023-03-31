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

import * as React from 'react'
import PropTypes from 'prop-types'
import { 
  ExternalLinkAltIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  TimesCircleIcon, } from '@patternfly/react-icons'

function removeHash() {
  // Remove location hash from url
  window.history.pushState('', document.title, window.location.pathname)
}

function ExternalLink(props) {
  const { target } = props

  return (
    <a href={target}>
      <span>
        {props.children}
        {/* As we want the icon to be smaller than "sm", we have to specify the
            font-size directly */}
        <ExternalLinkAltIcon
          style={{
            marginLeft: 'var(--pf-global--spacer--xs)',
            color: 'var(--pf-global--Color--400)',
            fontSize: 'var(--pf-global--icon--FontSize--sm)',
            verticalAlign: 'super',
          }}
        />
      </span>
    </a>
  )
}

ExternalLink.propTypes = {
  target: PropTypes.string,
  children: PropTypes.node,
}

function buildExternalLink(buildish) {
  /* TODO (felix): What should we show for periodic builds
      here? They don't provide a change, but the ref_url is
      also not usable */
  if (buildish.ref_url && buildish.change) {
    return (
      <ExternalLink target={buildish.ref_url}>
        <strong>Change </strong>
        {buildish.change},{buildish.patchset}
      </ExternalLink>
    )
  } else if (buildish.ref_url && buildish.newrev) {
    return (
      <ExternalLink target={buildish.ref_url}>
        <strong>Revision </strong>
        {buildish.newrev.slice(0, 7)}
      </ExternalLink>
    )
  }

  return null
}

function buildExternalTableLink(buildish) {
  /* TODO (felix): What should we show for periodic builds
      here? They don't provide a change, but the ref_url is
      also not usable */
  if (buildish.ref_url && buildish.change) {
    return (
      <ExternalLink target={buildish.ref_url}>
        {buildish.change},{buildish.patchset}
      </ExternalLink>
    )
  } else if (buildish.ref_url && buildish.newrev) {
    return (
      <ExternalLink target={buildish.ref_url}>
        {buildish.newrev.slice(0, 7)}
      </ExternalLink>
    )
  }

  return null
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

IconProperty.propTypes = {
  icon: PropTypes.node,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.node]),
  WrapElement: PropTypes.func,
}

// https://github.com/kitze/conditional-wrap
// appears to be the first implementation of this pattern
const ConditionalWrapper = ({ condition, wrapper, children }) =>
  condition ? wrapper(children) : children

// Tentative grouping of known build results. TODO this could be provided by Zuul REST API

// Color consts
const SUCCESS_COLOR = 'var(--pf-global--success-color--100)' // green
const ERROR_COLOR = 'var(--pf-global--danger-color--100)' // red
const INFO_COLOR = 'var(--pf-global--info-color--100)' // blue
const WARNING_COLOR = 'var(--pf-global--warning-color--100)' // gold
// const MISC_COLOR = 'var(--pf-global--disabled-color--100)' // gray

const BUILD_SUCCESS_CONSTS = {
  SUCCESS: {
    icon: CheckIcon,
    color: SUCCESS_COLOR,
    badgeColor: 'green'
  },
}

// build discontinuations that may be the result of normal events (PS updated, etc) -> info
const BUILD_DISCONTINUED_CONSTS = {
  SKIPPED: {
    icon: ExclamationTriangleIcon,
    color: INFO_COLOR,
    badgeColor: 'cyan'
  },
  ABORTED: {
    icon: ExclamationTriangleIcon,
    color: INFO_COLOR,
    badgeColor:'cyan'
  },
  CANCELED: {
    icon: ExclamationTriangleIcon,
    color: INFO_COLOR,
    badgeColor:'cyan'
  },
  RETRY: {
    icon: ExclamationTriangleIcon,
    color: WARNING_COLOR,
    badgeColor:'orange'
  },
  NO_JOBS: {
    icon: ExclamationTriangleIcon,
    color: WARNING_COLOR,
    badgeColor: 'orange'
  },
}

// We attempt a distinction between pure job-related failures (unit tests failing, for example)
// and the rest, typically errors triggered by infrastructure failures or configuration mistakes.
// This isn't as clear-cut in real life however, so the color codes are really just a preliminary
// suggestion at what might have gone wrong.

// Correct execution to completion, failure is change-related
const BUILD_JOB_FAILURE_CONSTS = {
  FAILURE: {
    icon: TimesCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
}

const BUILD_MISC_FAILURE_CONSTS = {
  NODE_FAILURE: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  CONFIG_ERROR: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  DISK_FULL: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  TIMED_OUT: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  MERGE_CONFLICT: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  MERGE_FAILURE: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  RETRY_LIMIT: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  POST_FAILURE: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
  ERROR: {
    icon: ExclamationCircleIcon,
    color: ERROR_COLOR,
    badgeColor: 'red'
  },
}

const BUILD_CONSTS = {
  ...BUILD_SUCCESS_CONSTS,
  ...BUILD_DISCONTINUED_CONSTS,
  ...BUILD_JOB_FAILURE_CONSTS,
  ...BUILD_MISC_FAILURE_CONSTS,
}

export { IconProperty, removeHash, ExternalLink, buildExternalLink, buildExternalTableLink, ConditionalWrapper, BUILD_CONSTS, SUCCESS_COLOR, INFO_COLOR, WARNING_COLOR, ERROR_COLOR }
