import { fetchUserAuthZ } from '../api'

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
