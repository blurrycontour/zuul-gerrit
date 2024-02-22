// Copyright 2018 Red Hat, Inc
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

import { Tooltip } from '@patternfly/react-core'
import {
  BundleIcon,
  CheckIcon,
  CodeBranchIcon,
  ExclamationIcon,
  FlaskIcon,
  OutlinedClockIcon,
  SortAmountDownIcon,
  StreamIcon,
  TimesIcon,
} from '@patternfly/react-icons'

const QUEUE_ITEM_ICON_CONFIGS = {
  SUCCESS: {
    icon: CheckIcon,
    color: 'var(--pf-global--success-color--100)',
    variant: 'success',
  },
  FAILURE: {
    icon: TimesIcon,
    color: 'var(--pf-global--danger-color--100)',
    variant: 'danger',
  },
  MERGE_CONFLICT: {
    icon: ExclamationIcon,
    color: 'var(--pf-global--warning-color--100)',
    variant: 'warning',
  },
  QUEUED: {
    icon: OutlinedClockIcon,
    color: 'var(--pf-global--info-color--100)',
    variant: 'info',
  },
  WAITING: {
    icon: OutlinedClockIcon,
    color: 'var(--pf-global--disabled-color--100)',
    variant: 'pending',
  },
}

/*
  Note: the documentation links are unused at the moment, but kept for
  convenience. We might figure a way to use these at some point.
*/
const PIPELINE_ICON_CONFIGS = {
  dependent: {
    icon: CodeBranchIcon,
    help_title: 'Dependent Pipeline',
    help: 'A dependent pipeline ensures that every change is tested exactly in the order it is going to be merged into the repository.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.dependent',
  },
  independent: {
    icon: FlaskIcon,
    help_title: 'Independent Pipeline',
    help: 'An independent pipeline treats every change as independent of other changes in it.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.independent',
  },
  serial: {
    icon: SortAmountDownIcon,
    help_title: 'Serial Pipeline',
    help: 'A serial pipeline supports shared queues, but only one item in each shared queue is processed at a time.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.serial',
  },
  supercedent: {
    icon: BundleIcon,
    help_title: 'Supercedent Pipeline',
    help: 'A supercedent pipeline groups items by project and ref, and processes only one item per grouping at a time. Only two items (currently processing and latest) can be queued per grouping.',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html#value-pipeline.manager.supercedent',
  },
  unknown: {
    icon: StreamIcon,
    help_title: '?',
    help: 'Unknown pipeline type',
    doc_url: 'https://zuul-ci.org/docs/zuul/reference/pipeline_def.html'
  },
}

const DEFAULT_PIPELINE_ICON_CONFIG = PIPELINE_ICON_CONFIGS['unknown']

const getQueueItemIconConfig = (item) => {
  if (item.failing_reasons && item.failing_reasons.length > 0) {
    let reasons = item.failing_reasons.join(', ')
    if (reasons.match(/merge conflict/)) {
      return QUEUE_ITEM_ICON_CONFIGS['MERGE_CONFLICT']
    }
    return QUEUE_ITEM_ICON_CONFIGS['FAILURE']
  }

  if (item.active !== true) {
    return QUEUE_ITEM_ICON_CONFIGS['QUEUED']
  }

  if (item.live !== true) {
    return QUEUE_ITEM_ICON_CONFIGS['WAITING']
  }

  return QUEUE_ITEM_ICON_CONFIGS['SUCCESS']
}

function PipelineIcon({ pipelineType, size = 'sm' }) {
  const iconConfig = PIPELINE_ICON_CONFIGS[pipelineType] || DEFAULT_PIPELINE_ICON_CONFIG
  const Icon = iconConfig.icon

  // Define the verticalAlign based on the size
  let verticalAlign = '-0.2em'

  if (size === 'md') {
    verticalAlign = '-0.35em'
  }

  return (
    <Tooltip
      position="bottom"
      content={<div><strong>{iconConfig.help_title}</strong><p>{iconConfig.help}</p></div>}
    >
      <Icon
        size={size}
        style={{
          marginRight: 'var(--pf-global--spacer--sm)',
          verticalAlign: verticalAlign,
        }}
      />
    </Tooltip>
  )
}

PipelineIcon.propTypes = {
  pipelineType: PropTypes.string,
  size: PropTypes.string,
}

export { getQueueItemIconConfig, PipelineIcon }
