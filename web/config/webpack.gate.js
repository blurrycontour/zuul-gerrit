const webpack = require('webpack');
const Merge = require('webpack-merge');
const DevConfig = require('./webpack.dev.js');

module.exports = Merge(DevConfig, {
  plugins: [
    new webpack.ProvidePlugin({
        BuiltinConfig: './gate.config.json',
    })
  ]
})
