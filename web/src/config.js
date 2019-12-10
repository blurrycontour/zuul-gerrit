// TODO: what's the best practice for config in deployments?

const userManagerConfig = {
  client_id: 'zuul',
  redirect_uri: 'https://sfrdotestinstance.org/zuul/auth_callback',
  response_type: 'token id_token',
  scope: 'openid profile',
  authority: 'https://keycloak.sfrdotestinstance.org/auth/realms/sf',
//  silent_redirect_uri: `${window.location.protocol}//${window.location.hostname}${window.location.port ? `:${window.location.port}` : ''}/silent_renew.html`,
  automaticSilentRenew: false,
  filterProtocolClaims: true,
  loadUserInfo: true,
}

export default userManagerConfig
