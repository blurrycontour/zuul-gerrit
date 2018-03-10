import * as path from 'path'
import * as webpack from 'webpack'
import * as WebpackMerge from 'webpack-merge'
import * as ArchivePlugin from 'webpack-archive-plugin'

import * as CommonConfig from './webpack.common'

const config: webpack.Configuration = WebpackMerge(CommonConfig, {
  mode: 'production',
  output: {
    filename: '[name].[chunkhash].js',
    // path.resolve(__dirname winds up relative to the config dir
    path: path.resolve(__dirname, '../../zuul/web/static'),
    publicPath: ''
  },
  plugins: [
    new webpack.LoaderOptionsPlugin({
      minimize: true,
      debug: false
    }),
    new webpack.DefinePlugin({
      'process.env': {
        'NODE_ENV': JSON.stringify('production')
      }
    }),
    // Keeps the vendor bundle from changing needlessly.
    new webpack.HashedModuleIdsPlugin(),
    new ArchivePlugin({
      output: path.resolve(__dirname, '../../zuul-web'),
      format: [
        'tar',
      ],
      ext: 'tgz'
    })
  ]
})

export default config
