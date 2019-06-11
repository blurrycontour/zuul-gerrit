// TODO: what's the best practice for config in deployments?

const userManagerConfig = {
  client_id: 'zuul-web',
  redirect_uri: `http://localhost:9000/auth_callback`,
  response_type: 'token id_token',
  scope: 'openid profile',
  authority: 'http://localhost:8282/auth/realms/zuul-demo/',
//  silent_redirect_uri: `${window.location.protocol}//${window.location.hostname}${window.location.port ? `:${window.location.port}` : ''}/silent_renew.html`,
  automaticSilentRenew: false,
  filterProtocolClaims: true,
  loadUserInfo: true,
}

export default userManagerConfig
