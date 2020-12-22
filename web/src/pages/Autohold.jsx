// Copyright 2021 Red Hat, Inc
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
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import {
  EmptyState,
  EmptyStateIcon,
  EmptyStateVariant,
  PageSection,
  PageSectionVariants,
  Title,
  Flex,
  FlexItem,
  List,
  ListItem,
} from '@patternfly/react-core'
import { LockIcon,
         BuildIcon,
         CubeIcon,
         CodeIcon,
         BellIcon,
         OutlinedClockIcon,
         OutlinedCommentDotsIcon } from '@patternfly/react-icons'
import { IconProperty } from '../containers/Misc'

import { Link } from 'react-router-dom'
import * as moment from 'moment'

import { fetchAutohold } from '../actions/autoholds'
import { EmptyPage } from '../containers/Errors'
import { Fetching } from '../containers/Fetching'
import HeldBuildList from '../containers/autohold/HeldBuildList'

class AutoholdPage extends React.Component {
  static propTypes = {
    match: PropTypes.object.isRequired,
    tenant: PropTypes.object.isRequired,
    autohold: PropTypes.object,
    isFetching: PropTypes.bool.isRequired,
    fetchAutohold: PropTypes.func.isRequired,
  }

  updateData = () => {
    if (!this.props.autohold) {
      this.props.fetchAutohold(
        this.props.tenant,
        this.props.match.params.requestId
      )
    }
  }

  componentDidMount() {
    document.title = 'Zuul Autohold Request'
    if (this.props.tenant.name) {
      this.updateData()
    }
  }

  componentDidUpdate(prevProps) {
    if (this.props.tenant.name !== prevProps.tenant.name) {
      this.updateData()
    }
  }

  render() {
    const { autohold, isFetching, tenant } = this.props

    // Initial page load
    if (autohold === undefined || isFetching) {
      return <Fetching />
    }

    // Fetching finished, but no autohold found
    if (!autohold) {
      return (
        <EmptyPage
          title="This autohold request does not exist"
          icon={LockIcon}
          linkTarget={`${tenant.linkPrefix}/autoholds`}
          linkText="Show all autohold requests"
        />
      )
    }

    // Return the build list or an empty state if no builds triggered the autohold.
    const buildsContent = autohold.nodes ? (
      <span ><HeldBuildList nodes={autohold.nodes} /></span>
    ) : (
      <>
        {/* Using an hr above the empty state ensures that the space between
            heading (builds) and empty state is filled and the empty state
            doesn't look like it's lost in space. */}
        <hr />
        <EmptyState variant={EmptyStateVariant.small}>
          <EmptyStateIcon icon={BuildIcon} />
          <Title headingLevel="h4" size="lg">
            This autohold request hasn't triggered yet.
          </Title>
        </EmptyState>
      </>
    )

    const node_expiration = moment.duration(autohold.node_expiration, 'seconds').humanize()

    return (
      <>
        <PageSection variant={PageSectionVariants.light}>
          <Title headingLevel="h2">Autohold Request {autohold.id}</Title>

          <Flex className="zuul-autohold-attributes">
            <Flex flex={{ default: 'flex_1' }}>
                <FlexItem>
                  <List style={{ listStyle: 'none' }}>
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<CubeIcon />}
                      value={
                        <>
                          <strong>Project </strong> <Link to={`${tenant.linkPrefix}/project/${autohold.project}`}>{autohold.project}</Link>
                        </>
                      }
                    />
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<CodeIcon />}
                      value={
                        <>
                          <strong>Filter </strong> {autohold.ref_filter}
                        </>
                      }
                    />
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<BuildIcon />}
                      value={
                        <>
                          <strong>Job </strong> <Link to={`${tenant.linkPrefix}/job/${autohold.job}`}>{autohold.job}</Link>
                        </>
                      }
                    />
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<BellIcon />}
                      value={
                        <>
                          <strong>Count </strong> {autohold.current_count} out of {autohold.max_count}
                        </>
                      }
                    />
                    <IconProperty
                      WrapElement={ListItem}
                      icon={<OutlinedClockIcon />}
                      value={
                        <>
                          <strong>Hold Duration </strong> {node_expiration}
                        </>
                      }
                    />
                  </List>
                </FlexItem>
            </Flex>
            <Flex flex={{ default: 'flex_1' }}>
              <FlexItem>
                <List style={{ listStyle: 'none' }}>
                  <IconProperty
                    WrapElement={ListItem}
                    icon={<OutlinedCommentDotsIcon />}
                    value={
                      <>
                        <strong>Reason:</strong>
                        <pre>{autohold.reason}</pre>
                      </>
                    }
                  />
                </List>
              </FlexItem>
            </Flex>
          </Flex>
        </PageSection>
        <PageSection variant={PageSectionVariants.light}>
          <Title headingLevel="h3">
            <BuildIcon
              style={{
                marginRight: 'var(--pf-global--spacer--sm)',
                verticalAlign: '-0.1em',
              }}
            />{' '}
            Held Builds
          </Title>
          {buildsContent}
        </PageSection>
      </>
    )
  }
}

function mapStateToProps(state, ownProps) {
  return {
    autohold: state.autoholds.autohold,
    tenant: state.tenant,
    isFetching: state.autoholds.isFetching,
  }
}

const mapDispatchToProps = { fetchAutohold }

export default connect(mapStateToProps, mapDispatchToProps)(AutoholdPage)
