import { getHomepageUrl } from './api'

it('should should return the homepage url', () => {
  const homepage = 'https://my-zuul.com/'
  Object.defineProperty(window, 'location', {
    value: new URL(homepage)
  } )

  // Test some of the known, possible, URLs to verify
  // that the origin is returned.
  const urls = [
      // auth_callback test  as some providers build
      // different callback urls
      'https://my-zuul.com/auth_callback',
      'https://my-zuul.com/auth_callback#state=12345',

      // Regular browser navigation urls
      'https://my-zuul.com/status',
      'https://my-zuul.com/t/zuul-tenant/status',
      'https://my-zuul.com/t/zuul-tenant/jobs',

      // API urls
      'https://my-zuul.com/api/tenant/zuul-tenant/status',
      'https://my-zuul.com/api/tenant/zuul-tenant/authorization',

  ]

  for (let url of urls) {
    window.location.href = url
    expect(getHomepageUrl()).toEqual(homepage)
  }
})

it('should return the subdir homepage url', () => {
   const homepage = 'https://example.com/zuul/'
   Object.defineProperty(window, 'location', {
     value: new URL(homepage)
   } )
   // The build process strips trailing slashes from PUBLIC_URL,
   // so make sure we don't include any in our tests
   Object.defineProperty(process.env, 'PUBLIC_URL', {
     value: '/zuul'
   } )

   // Test some of the known, possible, URLs to verify
   // that the origin is returned.
   const urls = [
       // auth_callback test  as some providers build
       // different callback urls
       'https://example.com/zuul/auth_callback',
       'https://example.com/zuul/auth_callback#state=12345',

       // Regular browser navigation urls
       'https://example.com/zuul/status',
       'https://example.com/zuul/t/zuul-tenant/status',
       'https://example.com/zuul/t/zuul-tenant/jobs',
   ]

   for (let url of urls) {
     window.location.href = url
     expect(getHomepageUrl()).toEqual(homepage)
   }
 })
