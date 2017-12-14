const path = require('path');
const webpack = require('webpack');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const CleanWebpackPlugin = require('clean-webpack-plugin');

module.exports = {
  // This splits the output into three different files, which may not be
  // what we want long term. Just emitting one file is likely a better choice,
  // but it's three here so that we have the complex thing.
  entry: {
    'dashboard': './web/dashboard.js',
    'status': './web/status.js',
    'stream': './web/stream.js'
  },
  output: {
    filename: '[name].bundle.js',
    // path.resolve(__dirname winds up relative to the config dir
    path: path.resolve(__dirname, '../../zuul/web/static'),
    publicPath: ''
  },
  // Some folks prefer "cheaper" source-map for dev and one that is more
  // expensive to build for prod. Debugging without the full source-map sucks,
  // so define it here in common.
  devtool: 'source-map',
  plugins: [
    new webpack.ProvidePlugin({
        $: 'jquery/dist/jquery',
        jQuery: 'jquery/dist/jquery',
    }),
    new CleanWebpackPlugin(
        ['zuul/web/static'], { root: path.resolve(__dirname, '../..')}),
    // Each of the entries below lists a specific 'chunk' which is one of the
    // entry items from above. We can collapse this to just do one single
    // output file.
    new HtmlWebpackPlugin({
      chunks: ['status'],
      filename: 'status.html',
      template: 'web/templates/status.ejs',
      title: 'Zuul Status'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Builds',
      chunks: ['dashboard'],
      template: 'web/templates/builds.ejs',
      filename: 'builds.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Jobs',
      chunks: ['dashboard'],
      template: 'web/templates/jobs.ejs',
      filename: 'jobs.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Tenants',
      chunks: ['dashboard'],
      template: 'web/templates/index.ejs',
      filename: 'index.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Console Stream',
      chunks: ['stream'],
      template: 'web/templates/stream.ejs',
      filename: 'stream.html'
    })
  ],
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: [
          'babel-loader'
        ]
      },
      {
        test: /.css$/,
        use: [
          'style-loader',
          'css-loader'
        ]
      },
      {
        test: /\.(png|svg|jpg|gif)$/,
        use: ['file-loader'],
      },
      // The majority of the rules below are all about getting bootstrap copied
      // appropriately.
      {
        test: /\.woff(\?v=\d+\.\d+\.\d+)?$/,
        use: {
          loader: "url-loader",
          options: {
            limit: 10000,
            mimetype: 'application/font-woff'
          }
        }
      },
      {
        test: /\.ttf(\?v=\d+\.\d+\.\d+)?$/,
        use: {
          loader: "url-loader",
          options: {
            limit: 10000,
            mimetype: 'application/octet-stream'
          }
        }
      },
      {
        test: /\.eot(\?v=\d+\.\d+\.\d+)?$/,
        use: ['file-loader'],
      },
      {
        test: /\.svg(\?v=\d+\.\d+\.\d+)?$/,
        use: {
          loader: "url-loader",
          options: {
            limit: 10000,
            mimetype: 'image/svg+xml'
          }
        }
      },
      {
        test: /\.html$/,
        use: ['raw-loader'],
        exclude: /node_modules/
      },
      {
        test: /\.(ttf|eot|svg|woff(2)?)(\?[a-z0-9=&.]+)?$/,
        use: ['file-loader']
      }
    ]
  }
};
