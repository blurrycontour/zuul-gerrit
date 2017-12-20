const webpack = require('webpack');
const Merge = require('webpack-merge');
const ProdConfig = require('./webpack.prod.js');

module.exports = Merge(ProdConfig, {
  plugins: [
    new webpack.ProvidePlugin({
        BuiltinConfig: './gate.config.json',
    })
  ]
})
