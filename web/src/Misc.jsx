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
import { ExternalLinkAltIcon } from '@patternfly/react-icons'

import {
  CheckIcon,
  ExclamationIcon,
  QuestionIcon,
  TimesIcon,
} from '@patternfly/react-icons'

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

// https://github.com/kitze/conditional-wrap
// appears to be the first implementation of this pattern
const ConditionalWrapper = ({ condition, wrapper, children }) =>
  condition ? wrapper(children) : children

// TODO Tentative grouping of known build results. Suggestions welcome!

// Successful results -> green
const BUILD_SUCCESS_CONSTS = {
  // PF green-500
  SUCCESS: {
    icon: CheckIcon,
    color: '#3E8635',
    badgeColor: 'green'
  },
}

// Build discontinuations that may be expected from normal events (PS updated, etc) -> cyan
const BUILD_DISCONTINUED_CONSTS = {
  // PF cyan-100
  SKIPPED: {
    icon: QuestionIcon,
    color: '#A2D9D9',
    badgeColor: 'cyan'
  },
  // PF cyan-200
  ABORTED: {
    icon: QuestionIcon,
    color: '#73C5C5',
    badgeColor: 'cyan'
  },
  // PF cyan-300
  CANCELED: {
    icon: QuestionIcon,
    color: '#009596',
    badgeColor: 'cyan'
  }
}

// Failures caused by the tested PS -> red
const BUILD_FAILURE_CONSTS = {
  // PF red-100
  FAILURE: {
    icon: TimesIcon,
    color: '#C9190B',
    badgeColor: 'red'
  },
}

// Failures caused by retries -> orange 
const BUILD_RETRY_CONSTS = {
  // PF orange-100
  RETRY: {
    icon: TimesIcon,
    color: '#F4B678',
    badgeColor: 'orange'
  },
  // PF orange-300
  RETRY_LIMIT: {
    icon: TimesIcon,
    color: '#EC7A08',
    badgeColor: 'orange'
  },
}

// Failures caused by infrastructure -> purple
const BUILD_INFRA_FAILURE_CONSTS = {
  // PF purple-100
  NODE_FAILURE: {
    icon: ExclamationIcon,
    color: '#CBC1FF',
    badgeColor: 'purple'
  },
  // PF purple-200
  CONFIG_ERROR: {
    icon: ExclamationIcon,
    color: '#B2A3FF',
    badgeColor: 'purple'
  },
  // PF purple-300
  DISK_FULL: {
    icon: ExclamationIcon,
    color: '#A18FFF',
    badgeColor: 'purple',
  },
  // PF purple-400
  TIMED_OUT: {
    icon: ExclamationIcon,
    color: '#8476D1',
    badgeColor: 'purple'
  },
  // PF purple-500
  DISCONNECT: {
    icon: ExclamationIcon,
    color: '#6753AC',
    badgeColor: 'purple',
  },
  // PF purple-600
  MERGER_FAILURE: {
    icon: ExclamationIcon,
    color: '#40199A',
    badgeColor: 'purple'
  }
}

// Failures in jobs configuration -> yellow
const BUILD_JOB_FAILURE_CONSTS = {
  // PF gold-200
  POST_FAILURE: {
    icon: ExclamationIcon,
    color: '#F6D173',
    badgeColor: 'yellow'
  },
  // PF  gold-400
  NO_JOBS: {
    icon: ExclamationIcon,
    color: '#F0AB00',
    badgeColor: 'yellow'
  },
}

// Generic errors -> grey
const BUILD_GENERIC_CONSTS = {
  // PF black-300
  ERROR: {
    icon: QuestionIcon,
    color: '#D2D2D2',
    badgeColor: 'grey'
  },
  // PF black-400
  EXCEPTION: {
    icon: QuestionIcon,
    color: '#B8BBBE',
    badgeColor: 'grey'
  },
  // PF black-500
  LOST: {
    icon: QuestionIcon,
    color: '#8A8D90',
    badgeColor: 'grey'
  },
  // PF black-200
  NO_HANDLE: {
    icon: QuestionIcon,
    color: '#F0F0F0',
    badgeColor: 'grey'
  },
}

const BUILDS_CONSTS = {
  ...BUILD_SUCCESS_CONSTS,
  ...BUILD_FAILURE_CONSTS,
  ...BUILD_RETRY_CONSTS,
  ...BUILD_DISCONTINUED_CONSTS,
  ...BUILD_INFRA_FAILURE_CONSTS,
  ...BUILD_JOB_FAILURE_CONSTS,
  ...BUILD_GENERIC_CONSTS,
}

export { removeHash, ExternalLink, buildExternalLink, buildExternalTableLink, ConditionalWrapper, BUILDS_CONSTS }
