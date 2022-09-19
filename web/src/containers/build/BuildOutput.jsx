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
import { Fragment } from 'react'
import ReAnsi from '@softwarefactory-project/re-ansi'
import PropTypes from 'prop-types'
import {
  Card,
  CardBody,
  CardHeader,
  Chip,
  DataList,
  DataListItem,
  DataListItemRow,
  DataListItemCells,
  DataListCell,
  Divider,
  Label,
  Flex,
  FlexItem,
} from '@patternfly/react-core'

import {
  CheckCircleIcon,
  ContainerNodeIcon,
  TimesIcon,
  TimesCircleIcon,
} from '@patternfly/react-icons'

class BuildOutputLabel extends React.Component {
  static propTypes = {
    ok: PropTypes.number,
    changed: PropTypes.number,
    failures: PropTypes.number,
  }

  render() {
    let color = this.props.failures ? 'red' : 'green'
    let icon = this.props.failures ? <TimesCircleIcon /> : <CheckCircleIcon />
    let failures = this.props.failures ? (
      <>
        <Divider orientation={{default: 'vertical'}} />
        <FlexItem><strong>{this.props.failures}</strong> Failure{this.props.failures > 1 ? 's' : ''}</FlexItem>
      </>
    ) : null

    return (
      <Label color={color} icon={icon}>
        <Flex>
          <FlexItem><strong>{this.props.ok}</strong> OK</FlexItem>
          <Divider orientation={{default: 'vertical'}} />
          <FlexItem><strong>{this.props.changed}</strong> Changed</FlexItem>
          { failures }
        </Flex>
      </Label>
    )
  }
}


class BuildOutput extends React.Component {
  static propTypes = {
    output: PropTypes.object,
  }

  renderHosts (hosts) {
    return (
      <>
        <br />
        <div className={'zuul-task-summary'}>
          <DataList aria-label="Build Results" isCompact={true}>
            {Object.entries(hosts).map(([host, values]) => (
              <DataListItem key={host} aria-label="Host">
                <DataListItemRow>
                  <DataListItemCells
                    dataListCells={[
                      <DataListCell key={host + '.name'}>
                        <Chip isReadOnly={true} textMaxWidth='50ch'>
                          <span style={{ fontSize: 'var(--pf-global--FontSize--md)' }}>
                            <ContainerNodeIcon />&nbsp;{host}
                          </span>
                        </Chip>
                      </DataListCell>,
                      <DataListCell key={host + '.data'} >
                        <BuildOutputLabel ok={values.ok} changed={values.changed} failures={values.failures} />
                      </DataListCell>
                    ]}
                  />
                </DataListItemRow>
              </DataListItem>
            ))}
          </DataList>
        </div>
      </>
    )
  }

  renderFailedTask (host, task) {
    const max_lines = 42
    return (
      <Card key={host + task.zuul_log_id} className="zuul-task-summary-failed">
        <CardHeader>
          <TimesIcon style={{ color: 'var(--pf-global--danger-color--100)' }}/>
            &nbsp;Task&nbsp;<strong>{task.name}</strong>&nbsp;
            failed running on host&nbsp;<strong>{host}</strong>
        </CardHeader>
        <CardBody>
          {task.invocation && task.invocation.module_args &&
           task.invocation.module_args._raw_params && (
            <pre key="cmd" title="cmd" className={`${'cmd'}`}>
              {task.invocation.module_args._raw_params}
            </pre>
          )}
          {task.msg && (
            <pre key="msg" title="msg">{task.msg}</pre>
          )}
          {task.exception && (
            <pre key="exc" style={{ color: 'red' }} title="exc">{task.exception}</pre>
          )}
          {task.stdout_lines && task.stdout_lines.length > 0 && (
            <Fragment>
              {task.stdout_lines.length > max_lines && (
                <details className={`${'foldable'} ${'stdout'}`}><summary></summary>
                  <pre key="stdout" title="stdout">
                    <ReAnsi log={task.stdout_lines.slice(0, -max_lines).join('\n')} />
                  </pre>
                </details>)}
              <pre key="stdout" title="stdout">
                <ReAnsi log={task.stdout_lines.slice(-max_lines).join('\n')} />
              </pre>
            </Fragment>
          )}
          {task.stderr_lines && task.stderr_lines.length > 0 && (
            <Fragment>
              {task.stderr_lines.length > max_lines && (
                <details className={`${'foldable'} ${'stderr'}`}><summary></summary>
                  <pre key="stderr" title="stderr">
                    <ReAnsi log={task.stderr_lines.slice(0, -max_lines).join('\n')} />
                  </pre>
                </details>
              )}
              <pre key="stderr" title="stderr">
                <ReAnsi log={task.stderr_lines.slice(-max_lines).join('\n')} />
              </pre>
            </Fragment>
          )}
        </CardBody>
      </Card>
    )
  }

  render () {
    const { output } = this.props
    return (
      <React.Fragment>
        {this.renderHosts(output)}
        <br />
        {Object.entries(output)
          .filter(([, values]) => values.failed.length > 0)
          .map(([host, values]) => (values.failed.map(failed => (
            this.renderFailedTask(host, failed)))))}
      </React.Fragment>
    )
  }
}


export default BuildOutput
