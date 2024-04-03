// Copyright 2018 Red Hat, Inc
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

import * as React from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { Link } from 'react-router-dom'
import * as moment from 'moment'
import 'moment-duration-format'
import { Button } from '@patternfly/react-core'

function getRefs(item) {
  // For backwards compat: get a list of this items refs.
  return 'refs' in item ? item.refs : [item]
}

class ItemPanel extends React.Component {
  static propTypes = {
    globalExpanded: PropTypes.bool.isRequired,
    item: PropTypes.object.isRequired,
    tenant: PropTypes.object,
    preferences: PropTypes.object
  }

  constructor () {
    super()
    this.state = {
      expanded: false,
      showSkipped: false,
    }
    this.onClick = this.onClick.bind(this)
    this.toggleSkippedJobs = this.toggleSkippedJobs.bind(this)
    this.clicked = false
  }

  onClick (e) {
    // Skip middle mouse button
    if (e.button === 1) {
      return
    }
    let expanded = this.state.expanded
    if (!this.clicked) {
      expanded = this.props.globalExpanded
    }
    this.clicked = true
    this.setState({ expanded: !expanded })
  }

  time (ms) {
    return moment.duration(ms).format({
      template: 'h [hr] m [min]',
      largest: 2,
      minValue: 1,
      usePlural: false,
    })
  }

  enqueueTime (ms) {
    // Special format case for enqueue time to add style
    let hours = 60 * 60 * 1000
    let now = Date.now()
    let delta = now - ms
    let status = 'text-success'
    let text = this.time(delta)
    if (delta > (4 * hours)) {
      status = 'text-danger'
    } else if (delta > (2 * hours)) {
      status = 'text-warning'
    }
    return <span className={status}>{text}</span>
  }

  jobStrResult (job) {
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

  renderChangeLink (change) {
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
      <small>
        <a href={change.url} onClick={(e) => e.stopPropagation()}>
          {changeText !== '' ? (
            <abbr title={changeTitle}>{changeText}</abbr>) : changeTitle}
        </a>
      </small>)
  }

  renderProgressBar (change) {
    const interesting_jobs = change.jobs.filter(j => this.jobStrResult(j) !== 'skipped')
    let jobPercent = (100 / interesting_jobs.length).toFixed(2)
    return (
      <div className={`progress zuul-change-total-result${this.props.preferences.darkMode ? ' progress-dark' : ''}`}>
        {change.jobs.map((job, idx) => {
          let result = this.jobStrResult(job)
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
            style={{width: jobPercent + '%'}}/>
        })}
      </div>
    )
  }

  renderTimer (change, times) {
    let remainingTime
    if (times.remaining === null) {
      remainingTime = 'unknown'
    } else {
      remainingTime = this.time(times.remaining)
    }
    return (
      <React.Fragment>
        <small title='Elapsed Time' className='time' style={{display: 'inline'}}>
          {this.enqueueTime(change.enqueue_time)}
        </small>
        <small> | </small>
        <small title='Remaining Time' className='time' style={{display: 'inline'}}>
          {remainingTime}
        </small>
      </React.Fragment>
    )
  }

  renderJobProgressBar (job, elapsedTime, remainingTime) {
    let progressPercent = 100 * (elapsedTime / (elapsedTime +
                                                remainingTime))
    // Show animation in preparation phase
    let className = ''
    let progressWidth = progressPercent
    let title = ''
    let remaining = remainingTime
    if (Number.isNaN(progressPercent)) {
      progressWidth = 100
      progressPercent = 0
      className = 'progress-bar-striped progress-bar-animated'
    } else if (job.pre_fail) {
      className = 'progress-bar-danger'
      title += 'Early failure detected.\n'
    }
    if (remaining !== null) {
      title += 'Estimated time remaining: ' + moment.duration(remaining).format({
        template: 'd [days] h [hours] m [minutes] s [seconds]',
        largest: 2,
        minValue: 30,
      })
    }

    return (
      <div className={`progress zuul-job-result${this.props.preferences.darkMode ? ' progress-dark' : ''}`}
        title={title}>
        <div className={'progress-bar ' + className}
          role='progressbar'
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          style={{'width': progressWidth + '%'}}
        />
      </div>
    )
  }

  renderJobStatusLabel (job, result) {
    let className, title
    switch (result) {
      case 'success':
        className = 'label-success'
        break
      case 'failure':
        className = 'label-danger'
        break
      case 'unstable':
      case 'retry_limit':
      case 'post_failure':
      case 'node_failure':
        className = 'label-warning'
        break
      case 'paused':
      case 'skipped':
        className = 'label-info'
        break
      case 'waiting':
        className = 'label-default'
        if (job.waiting_status !== null) {
          title = 'Waiting on ' + job.waiting_status
        }
        break
      case 'queued':
        className = 'label-default'
        if (job.waiting_status !== null) {
          title = 'Waiting on ' + job.waiting_status
        }
        break
      // 'in progress' 'lost' 'aborted' ...
      default:
        className = 'label-default'
    }

    return (
      <span className={'zuul-job-result label ' + className} title={title}>{result}</span>
    )
  }

  renderJob (job, job_times) {
    const { tenant } = this.props
    let job_name = job.name
    let ordinal_rules = new Intl.PluralRules('en', {type: 'ordinal'})
    const suffixes = {
      one: 'st',
      two: 'nd',
      few: 'rd',
      other: 'th'
    }
    if (job.tries > 1) {
        job_name = job_name + ' (' + job.tries + suffixes[ordinal_rules.select(job.tries)] + ' attempt)'
    }
    let name = ''
    if (job.result !== null) {
      name = <a className='zuul-job-name' href={job.report_url}>{job_name}</a>
    } else if (job.url !== null) {
      let url = job.url
      if (job.url.match('stream/')) {
        const to = (
          tenant.linkPrefix + '/' + job.url
        )
        name = <Link className='zuul-job-name' to={to}>{job_name}</Link>
      } else {
        name = <a className='zuul-job-name' href={url}>{job_name}</a>
      }
    } else {
      name = <span className='zuul-job-name'>{job_name}</span>
    }
    let resultBar
    let result = this.jobStrResult(job)
    if (result === 'in progress') {
      resultBar = this.renderJobProgressBar(job, job_times.elapsed, job_times.remaining)
    } else {
      resultBar = this.renderJobStatusLabel(job, result)
    }

    return (
      <span>
        {name}
        {resultBar}
        {job.voting === false ? (
          <small className='zuul-non-voting-desc'> (non-voting)</small>) : ''}
        <div style={{clear: 'both'}} />
      </span>)
  }

  toggleSkippedJobs (e) {
    // Skip middle mouse button
    if (e.button === 1) {
      return
    }
    this.setState({ showSkipped: !this.state.showSkipped })
  }

  renderJobList (jobs, times) {
    const [buttonText, interestingJobs] = this.state.showSkipped ?
          ['Hide', jobs] :
          ['Show', jobs.filter(j => this.jobStrResult(j) !== 'skipped')]
    const skippedJobCount = jobs.length - interestingJobs.length

    return (
      <>
        <ul className={`list-group ${this.props.preferences.darkMode ? 'zuul-patchset-body-dark' : 'zuul-patchset-body'}`}>
          {interestingJobs.map((job, idx) => (
            <li key={idx} className={`list-group-item ${this.props.preferences.darkMode ? 'zuul-change-job-dark' : 'zuul-change-job'}`}>
              {this.renderJob(job, times.jobs[job.name])}
            </li>
          ))}
          {(this.state.showSkipped || skippedJobCount) ? (
            <li key='last' className='list-group-item zuul-change-job'>
              <Button variant="link" className='zuul-skipped-jobs-button'
                      onClick={this.toggleSkippedJobs}>
                {buttonText} {skippedJobCount ? skippedJobCount : ''} skipped job{skippedJobCount === 1 ? '' : 's'}
              </Button>
            </li>
          ) : ''}
        </ul>
      </>
    )
  }

  calculateTimes (item) {
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

  render () {
    const { expanded } = this.state
    const { item, globalExpanded } = this.props
    let expand = globalExpanded
    if (this.clicked) {
      expand = expanded
    }
    const times = this.calculateTimes(item)
    const header = (
      <div className={`panel panel-default ${this.props.preferences.darkMode ? 'zuul-change-dark' : 'zuul-change'}`}>
        <div className={`panel-heading ${this.props.preferences.darkMode ? 'zuul-patchset-header-dark' : 'zuul-patchset-header'}`}
          onClick={this.onClick}>
          <div>
            {item.live === true ? (
              <div className='row'>
                <div className='col-xs-6'>
                  {this.renderProgressBar(item)}
                </div>
                <div className='col-xs-6 text-right'>
                  {this.renderTimer(item, times)}
                </div>
              </div>
            ) : ''}
            {getRefs(item).map((change, idx) => (
              <div key={idx} className='row'>
                <div className='col-xs-8'>
                  <span className='change_project'>{change.project}</span>
                </div>
                <div className='col-xs-4 text-right'>
                  {this.renderChangeLink(change)}
                </div>
              </div>
            ))}
          </div>
        </div>
        {expand ? this.renderJobList(item.jobs, times) : ''}
      </div >
    )
    return (
      <React.Fragment>
        {header}
      </React.Fragment>
    )
  }
}

export default connect(state => ({
  tenant: state.tenant,
  preferences: state.preferences,
}))(ItemPanel)
