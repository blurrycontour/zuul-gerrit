const path = require('path');
const webpack = require('webpack');
const Merge = require('webpack-merge');
const DevConfig = require('./webpack.dev.js');
const ArchivePlugin = require('webpack-archive-plugin');

module.exports = Merge(DevConfig, {
  plugins: [
    new webpack.ProvidePlugin({
        BuiltinConfig: './gate.config.json',
    })
  ]
})
