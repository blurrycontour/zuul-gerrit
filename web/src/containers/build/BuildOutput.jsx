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
import PropTypes from 'prop-types'
import {
  Card,
  CardBody,
  CardHeader,
  DataList,
  DataListItem,
  DataListItemRow,
  DataListItemCells,
  DataListCell,
  Label,
  Flex,
  FlexItem,
} from '@patternfly/react-core'

import {
  CheckCircleIcon,
  InfoCircleIcon,
  TimesIcon,
  TimesCircleIcon,
} from '@patternfly/react-icons'

class BuildOutput extends React.Component {
  static propTypes = {
    output: PropTypes.object,
  }

  renderHosts (hosts) {
    return (
      <Card>
        <CardHeader>
          <strong>Task run summary</strong>
        </CardHeader>
        <CardBody>
          <DataList aria-label="Build Results">
            {Object.entries(hosts).map(([host, values]) => (
              <DataListItem key={host} aria-label="Host">
                <DataListItemRow>
                  <DataListItemCells
                    dataListCells={[
                      <DataListCell key={host + '.name'}>{host} </DataListCell>,
                      <DataListCell key={host + '.data'}>
                        <Flex>
                          <FlexItem>
                            <Label color="green" icon={<CheckCircleIcon />}>{values.ok} OK</Label>
                          </FlexItem>
                          <FlexItem>
                            <Label color="orange" icon={<InfoCircleIcon />}>{values.changed} changed</Label>
                          </FlexItem>
                          <FlexItem>
                            <Label color="red" icon={<TimesCircleIcon />}>{values.failures} failed</Label>
                          </FlexItem>
                        </Flex>
                      </DataListCell>
                    ]}
                  />
                </DataListItemRow>
              </DataListItem>
            ))}
          </DataList>
        </CardBody>
      </Card>
    )
  }

  renderFailedTask (host, task) {
    const max_lines = 42
    return (
      <Card key={host + task.zuul_log_id}>
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
                    {task.stdout_lines.slice(0, -max_lines).join('\n')}
                  </pre>
                </details>)}
              <pre key="stdout" title="stdout">
                {task.stdout_lines.slice(-max_lines).join('\n')}
              </pre>
            </Fragment>
          )}
          {task.stderr_lines && task.stderr_lines.length > 0 && (
            <Fragment>
              {task.stderr_lines.length > max_lines && (
                <details className={`${'foldable'} ${'stderr'}`}><summary></summary>
                  <pre key="stderr" title="stderr">
                    {task.stderr_lines.slice(0, -max_lines).join('\n')}
                  </pre>
                </details>
              )}
              <pre key="stderr" title="stderr">
                {task.stderr_lines.slice(-max_lines).join('\n')}
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
        {Object.entries(output)
          .filter(([, values]) => values.failed.length > 0)
          .map(([host, values]) => (values.failed.map(failed => (
            this.renderFailedTask(host, failed)))))}
      </React.Fragment>
    )
  }
}


export default BuildOutput
