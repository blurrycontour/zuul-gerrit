const path = require('path');
const webpack = require('webpack');
const Merge = require('webpack-merge');
const CommonConfig = require('./webpack.common.js');
const ArchivePlugin = require('webpack-archive-plugin');

module.exports = Merge(CommonConfig, {
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
    // For development, NamedModulesPlugin keeps the vendor bundle from
    // changing needlessly. HashedModuleIdsPlugin is for production.
    new webpack.HashedModuleIdsPlugin(),
    new webpack.optimize.UglifyJsPlugin({
      warningsFilter: function(filename) {
        return ! /node_modules/.test(filename);
      },
      beautify: false,
      mangle: {
        screw_ie8: true,
        keep_fnames: true
      },
      compress: {
        screw_ie8: true
      },
      sourceMap: true,
      comments: false
    }),
    new ArchivePlugin({
      output: path.resolve(__dirname, '../../zuul-web'),
      format: [
        'tar',
      ],
      ext: 'tgz'
    })
  ]
})
