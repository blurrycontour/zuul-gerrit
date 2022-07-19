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
import { connect } from 'react-redux'
import PropTypes from 'prop-types'
import { withRouter } from 'react-router'

import {
    Button,
    PageSection,
    EmptyState,
    EmptyStateVariant,
    Title,
    Text,
    TextVariants
} from '@patternfly/react-core'
import { apiErrorReset } from '../actions/apiErrors'

import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faScrewdriverWrench, faFaceDizzy, faFaceFrown } from '@fortawesome/free-solid-svg-icons'

class ApiErrorPage extends React.Component {
    static propTypes = {
        apiErrors: PropTypes.object,
        history: PropTypes.object,
        tenant: PropTypes.object,
        dispatch: PropTypes.func
    }

    renderError(errorIcon, title, code, description, log_id) {
        const { tenant } = this.props
        const backUrl = tenant.name ? tenant.defaultRoute : '/'
        const goBack = () => {
            this.props.dispatch(apiErrorReset())
            this.props.history.push(backUrl)
        }
        return (
            <EmptyState variant={EmptyStateVariant.large}>
                <Title headingLevel="h1" size="lg">
                    {title} &nbsp;
                    <FontAwesomeIcon size="lg" icon={errorIcon} title={'HTTP Error Code: ' + code} />
                </Title>
                <Text component={TextVariants.h3}>{description}</Text>
                {log_id
                    ? <Text component={TextVariants.p}>Forward the following code to an administrator for further debugging: {log_id}</Text>
                    : <Text></Text>}
                <Button variant="link" onClick={goBack}>Go back to where it is safe</Button>
            </EmptyState>)
    }

    renderUserError(error) {
        let title = 'Zuul encountered an error'
        return this.renderError(faFaceFrown, title, error.error, error.description)
    }

    renderServerError(error) {
        let title = 'Zuul encountered an internal error'
        return this.renderError(faScrewdriverWrench, title, error.error, error.description, error.zuul_request_id)
    }

    renderUnknownError(error) {
        let title = 'Zuul encountered ... something?'
        return this.renderError(faFaceDizzy, title, error.error, 'We do not know what happened. Check your browser console for details.')
    }

    render() {
        const { apiErrors } = this.props
        let errorSection
        switch (apiErrors.type) {
            case 'server':
                errorSection = this.renderServerError(apiErrors)
                break
            case 'user':
                errorSection = this.renderUserError(apiErrors)
                break
            default:
                errorSection = this.renderUnknownError(apiErrors)
        }
        return <PageSection isCenterAligned isWidthLimited>
            {errorSection}
        </PageSection>
    }
}

export default withRouter(connect(state => ({
    apiErrors: state.apiErrors,
    tenant: state.tenant,
}))(ApiErrorPage))