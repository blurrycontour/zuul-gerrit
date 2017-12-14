const path = require('path');
const webpack = require('webpack');
const Merge = require('webpack-merge');
const CommonConfig = require('./webpack.common.js');

module.exports = Merge(CommonConfig, {

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
        loader: 'standard-loader',
        exclude: /node_modules/,
        options: {
          globals: [
            'DemoStatusBasic',
            'DemoStatusOpenStack',
            'DemoStatusTree',
            'Image',
            'URL',
            'WebSocket',
            'jQuery'
          ],
          error: false,
          parser: 'babel-eslint'
        }
      }
    ]
  },
  plugins: [
    new webpack.HotModuleReplacementPlugin(),
    new webpack.NamedModulesPlugin(),
    // We only need to bundle the demo files when we're running locally
    new webpack.ProvidePlugin({
        DemoStatusBasic: './status-basic.json',
        DemoStatusOpenStack: './status-openstack.json',
        DemoStatusTree: './status-tree.json'
    }),
  ]
})
