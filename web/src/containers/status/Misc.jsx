// Copyright 2018 Red Hat, Inc
// Copyright 2020 BMW Group
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

import { ExternalLink } from '../../Misc'

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

function ChangeLink({ change }) {
  let changeId = change.id || 'NA'
  let changeTitle = changeId
  // Fall back to display the ref if there is no change id
  if (changeId === 'NA' && change.ref) {
    changeTitle = change.ref
  }
  let changeText = ''
  if (change.url !== null) {
    let githubId = changeId.match(/^([0-9]+),([0-9a-f]{40})$/)
    if (githubId) {
      changeTitle = githubId
      changeText = '#' + githubId[1]
    } else if (/^[0-9a-f]{40}$/.test(changeId)) {
      changeText = changeId.slice(0, 7)
    }
  } else if (changeId.length === 40) {
    changeText = changeId.slice(0, 7)
  }
  return (
    <ExternalLink target={change.url}>
      {changeText !== '' ? changeText : changeTitle}
    </ExternalLink>
  )
}

ChangeLink.propTypes = {
  change: PropTypes.object,
}

const getJobStrResult = (job) => {
  let result = job.result ? job.result.toLowerCase() : null
  if (result === null) {
    if (job.url === null) {
      if (job.queued === false) {
        result = 'waiting'
      } else {
        result = 'queued'
      }
    } else if (job.paused !== null && job.paused) {
      result = 'paused'
    } else {
      result = 'in progress'
    }
  }
  return result
}

const calculateQueueItemTimes = (item) => {
  let maxRemaining = 0
  let jobs = {}
  const now = Date.now()

  for (const job of item.jobs) {
    let jobElapsed = null
    let jobRemaining = null
    if (job.start_time) {
      let jobStart = parseInt(job.start_time * 1000)

      if (job.end_time) {
        let jobEnd = parseInt(job.end_time * 1000)
        jobElapsed = jobEnd - jobStart
      } else {
        jobElapsed = Math.max(now - jobStart, 0)
        if (job.estimated_time) {
          jobRemaining = Math.max(parseInt(job.estimated_time * 1000) - jobElapsed, 0)
        }
      }
    }
    if (jobRemaining && jobRemaining > maxRemaining) {
      maxRemaining = jobRemaining
    }
    jobs[job.name] = {
      elapsed: jobElapsed,
      remaining: jobRemaining,
    }
  }
  // If not all the jobs have started, this will be null, so only
  // use our value if it's oky to calculate it.
  if (item.remaininging_time === null) {
    maxRemaining = null
  }
  return {
    remaining: maxRemaining,
    jobs: jobs,
  }
}

function QueueItemProgressbar({ item, darkMode }) {
  // TODO (felix): Use a PF4 progress bar instead
  const interesting_jobs = item.jobs.filter(j => getJobStrResult(j) !== 'skipped')
  let jobPercent = (100 / interesting_jobs.length).toFixed(2)
  return (
    <div className={`progress zuul-change-total-result${darkMode ? ' progress-dark' : ''}`}>
      {item.jobs.map((job, idx) => {
        let result = getJobStrResult(job)
        if (['queued', 'waiting', 'skipped'].includes(result)) {
          return ''
        }
        let className = ''
        switch (result) {
          case 'success':
            className = ' progress-bar-success'
            break
          case 'lost':
          case 'failure':
            className = ' progress-bar-danger'
            break
          case 'unstable':
          case 'retry_limit':
          case 'post_failure':
          case 'node_failure':
            className = ' progress-bar-warning'
            break
          case 'paused':
            className = ' progress-bar-info'
            break
          default:
            if (job.pre_fail) {
              className = ' progress-bar-danger'
            }
            break
        }
        return <div className={'progress-bar' + className}
          key={idx}
          title={job.name}
          style={{ width: jobPercent + '%' }} />
      })}
    </div>
  )
}

QueueItemProgressbar.propTypes = {
  item: PropTypes.object,
  darkMode: PropTypes.bool,
}

function getRefs(item) {
  // For backwards compat: get a list of this items refs.
  return 'refs' in item ? item.refs : [item]
}

export {
  calculateQueueItemTimes,
  ChangeLink,
  getJobStrResult,
  getQueueItemIconConfig,
  getRefs,
  QueueItemProgressbar,
  PipelineIcon,
}
