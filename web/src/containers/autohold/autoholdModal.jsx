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

import React from 'react'

import {
    Button,
    Modal,
    ModalVariant,
    Form,
    FormGroup,
    TextInput
} from '@patternfly/react-core'
// import {
//     LockIcon,
// } from '@patternfly/react-icons'

import { autohold } from '../../api'
import { addAutoholdError } from '../../actions/adminActions'
import { addNotification } from '../../actions/notifications'
import { fetchAutoholdsIfNeeded } from '../../actions/autoholds'

function renderAutoholdModal(
    tenant,
    user,
    showAutoholdModal,
    setShowAutoholdModal,
    change,
    setChange,
    ref,
    setRef,
    project,
    setProject,
    job_name,
    setJob_name,
    reason,
    setReason,
    count,
    setCount,
    nodeHoldExpiration,
    setNodeHoldExpiration,
    dispatch,
) {

    function handleConfirm() {
        let ah_change = change === '' ? null : change
        let ah_ref = ref === '' ? null : ref
        let ah_owner = user.data ? user.data.profile.preferred_username : '[unknown]'
        let reason_prefix = 'Requested by ' + ah_owner + ': '

        autohold(tenant.apiPrefix, project, job_name, ah_change, ah_ref, reason_prefix + reason, parseInt(count), parseInt(nodeHoldExpiration), user.token)
            .then(() => {
                /* TODO it looks like there is a delay in the update of the API, meaning we sometimes 
                   do not get the newly created request after the dispatch. A solution could be to 
                   make this page auto-refreshing like the status page.*/
                dispatch(fetchAutoholdsIfNeeded(tenant, true))
                dispatch(addNotification(
                    {
                        text: 'Autohold request set successfully.',
                        type: 'success',
                        status: '',
                        url: '',
                    }))
            })
            .catch(error => {
                dispatch(addAutoholdError(error))
            })
        setShowAutoholdModal(false)
    }

    return (
        <Modal
            variant={ModalVariant.small}
            // titleIconVariant={LockIcon}
            isOpen={showAutoholdModal}
            title='Create an Autohold Request'
            onClose={() => { setShowAutoholdModal(false) }}
            actions={[
                <Button
                    key="autohold_confirm"
                    variant="primary"
                    onClick={() => handleConfirm()}>Create</Button>,
                <Button
                    key="autohold_cancel"
                    variant="link"
                    onClick={() => { setShowAutoholdModal(false) }}>Cancel</Button>
            ]}>
            <Form isHorizontal>
                <FormGroup
                    label="Project"
                    isRequired
                    fieldId="ah-form-project"
                    helperText="The project for which to hold the next failing build">
                    <TextInput
                        value={project}
                        isRequired
                        type="text"
                        id="ah-form-ref"
                        name="project"
                        onChange={(value) => { setProject(value) }} />
                </FormGroup>
                <FormGroup
                    label="Job"
                    isRequired
                    fieldId="ah-form-job-name"
                    helperText="The job for which to hold the next failing build">
                    <TextInput
                        value={job_name}
                        isRequired
                        type="text"
                        id="ah-form-job-name"
                        name="job_name"
                        onChange={(value) => { setJob_name(value) }} />
                </FormGroup>
                <FormGroup
                    label="Change"
                    fieldId="ah-form-change"
                    helperText="The change for which to hold the next failing build">
                    <TextInput
                        value={change}
                        type="text"
                        id="ah-form-change"
                        name="change"
                        onChange={(value) => { setChange(value) }} />
                </FormGroup>
                <FormGroup
                    label="Ref"
                    fieldId="ah-form-ref"
                    helperText="The ref for which to hold the next failing build">
                    <TextInput
                        value={ref}
                        type="text"
                        id="ah-form-ref"
                        name="change"
                        onChange={(value) => { setRef(value) }} />
                </FormGroup>
                <FormGroup
                    label="Reason"
                    isRequired
                    fieldId="ah-form-reason"
                    helperText="A descriptive reason for holding the next failing build">
                    <TextInput
                        value={reason}
                        isRequired
                        type="text"
                        id="ah-form-reason"
                        name="reason"
                        onChange={(value) => { setReason(value) }} />
                </FormGroup>
                <FormGroup
                    label="Count"
                    isRequired
                    fieldId="ah-form-count"
                    helperText="How many times a failing build should be held">
                    <TextInput
                        value={count}
                        isRequired
                        type="number"
                        id="ah-form-count"
                        name="count"
                        onChange={(value) => { setCount(value) }} />
                </FormGroup>
                <FormGroup
                    label="Node Hold Expires in (s)"
                    isRequired
                    fieldId="ah-form-nhe"
                    helperText="How long nodes should be kept in HELD state (seconds)">
                    <TextInput
                        value={nodeHoldExpiration}
                        isRequired
                        type="number"
                        id="ah-form-count"
                        name="nodeHoldExpiration"
                        onChange={(value) => { setNodeHoldExpiration(value) }} />
                </FormGroup>
            </Form>
        </Modal>
    )
}

export default renderAutoholdModal
