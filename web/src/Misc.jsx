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
        {buildish.newrev.slice(0,7)}
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
        {buildish.newrev.slice(0,7)}
      </ExternalLink>
    )
  }

  return null
}

// https://github.com/kitze/conditional-wrap
// appears to be the first implementation of this pattern
const ConditionalWrapper = ({ condition, wrapper, children }) =>
  condition ? wrapper(children) : children

export { removeHash, ExternalLink, buildExternalLink, buildExternalTableLink, ConditionalWrapper }
