import * as path from 'path'
import * as webpack from 'webpack'
import * as WebpackMerge from 'webpack-merge'
import * as CommonConfig from './webpack.common'

const config: webpack.Configuration = WebpackMerge(CommonConfig, {
  // Enable Hot Module Replacement for devServer
  devServer: {
    hot: true,
    contentBase: path.resolve(__dirname, './zuul/web/static'),
    publicPath: '/'
  },
  module: {
    rules: [
      {
        enforce: 'pre',
        test: /\.js$/,
        use: [
          'babel-loader',
          'eslint-loader'
        ],
        exclude: /node_modules/,
      }
    ]
  },
  plugins: [
    new webpack.HotModuleReplacementPlugin(),
    // We only need to bundle the demo files when we're running locally
    // The paths are relative to the file that they're being injected in to.
    new webpack.ProvidePlugin({
        DemoStatusBasic: '../config/status-basic.json',
        DemoStatusOpenStack: '../config/status-openstack.json',
        DemoStatusTree: '../config/status-tree.json'
    }),
  ]
})

export default config
