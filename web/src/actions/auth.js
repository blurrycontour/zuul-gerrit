import { fetchUserAuthZ } from '../api'

export const USER_EXPIRED = 'redux-oidc/USER_EXPIRED'
export const SILENT_RENEW_ERROR = 'redux-oidc/SILENT_RENEW_ERROR'
export const SESSION_TERMINATED = 'redux-oidc/SESSION_TERMINATED'
export const USER_EXPIRING = 'redux-oidc/USER_EXPIRING'
export const USER_FOUND = 'redux-oidc/USER_FOUND'
export const LOADING_USER = 'redux-oidc/LOADING_USER'
export const USER_SIGNED_OUT = 'redux-oidc/USER_SIGNED_OUT'
export const LOAD_USER_ERROR = 'redux-oidc/LOAD_USER_ERROR'
export const LOADING_USER_AUTHORIZATIONS = 'LOADING_USER_AUTHORIZATIONS'
export const USER_AUTHORIZATIONS_LOADED = 'USER_AUTHORIZATIONS_LOADED'

const loadingUserAuthz = () => ({
    type: LOADING_USER_AUTHORIZATIONS
})

const userAuthzLoaded = (data) => ({
    type: USER_AUTHORIZATIONS_LOADED,
    adminTenants: data,
})

export const fetchUserAuthorizations = (user) => dispatch => {
    dispatch(loadingUserAuthz())
    return fetchUserAuthZ(user.access_token)
        .then(response => {
            dispatch(userAuthzLoaded(response.data))
        })
}
