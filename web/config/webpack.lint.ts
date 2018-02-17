import * as path from 'path'
import * as webpack from 'webpack'
import * as WebpackMerge from 'webpack-merge'
import { BundleAnalyzerPlugin } from 'webpack-bundle-analyzer'

import * as CommonConfig from './webpack.common'

const config: webpack.Configuration = WebpackMerge(CommonConfig, {

  mode: 'development',
  module: {
    rules: [
      {
        enforce: 'pre',
        test: /\.ts$/,
        use: [
          'tslint-loader'
        ],
        exclude: /node_modules/,
      },
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
    new BundleAnalyzerPlugin({
      analyzerMode: 'static',
      reportFilename: '../../../reports/bundle.html',
      generateStatsFile: true,
      openAnalyzer: false,
      statsFilename: '../../../reports/stats.json',
    }),
  ]
})

export default config
