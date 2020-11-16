export default {
  build: {
    builds: {},
    buildsets: {},
    isFetching: false,
    isFetchingOutput: false,
    isFetchingManifest: false,
  },
  logfile: {
    // Store files by buildId->filename->content
    files: {},
    isFetching: false,
    url: null,
  },
}
