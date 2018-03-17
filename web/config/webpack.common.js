const path = require('path');
const webpack = require('webpack');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const CleanWebpackPlugin = require('clean-webpack-plugin');

module.exports = {
  entry: {
    main: './web/main.js',
    // Tell webpack to extract 3rd party depdenencies which change less
    // frequently.
    vendor: [
      'angular',
      'bootstrap/dist/css/bootstrap.css',
      'jquery-visibility/jquery-visibility',
      'graphitejs/jquery.graphite.js'
    ]
  },
  output: {
    filename: '[name].js',
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
    new webpack.optimize.CommonsChunkPlugin({
      name: 'vendor',
    }),
    new webpack.optimize.CommonsChunkPlugin({
      name: 'manifest',
    }),
    new CleanWebpackPlugin(
        ['zuul/web/static'], { root: path.resolve(__dirname, '../..')}),
    // Each of the entries below lists a specific 'chunk' which is one of the
    // entry items from above. We can collapse this to just do one single
    // output file.
    new HtmlWebpackPlugin({
      title: 'Zuul Status',
      app: 'zuulStatus',
      template: 'web/main.ejs',
      filename: 'status.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Builds',
      app: 'zuulBuilds',
      template: 'web/main.ejs',
      filename: 'builds.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Job',
      app: 'zuulJob',
      template: 'web/main.ejs',
      filename: 'job.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Jobs',
      app: 'zuulJobs',
      template: 'web/main.ejs',
      filename: 'jobs.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Project',
      app: 'zuulProject',
      template: 'web/main.ejs',
      filename: 'project.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Projects',
      app: 'zuulProjects',
      template: 'web/main.ejs',
      filename: 'projects.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Labels',
      app: 'zuulLabels',
      template: 'web/main.ejs',
      filename: 'labels.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Tenants',
      app: 'zuulTenants',
      template: 'web/main.ejs',
      filename: 'tenants.html'
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Console Stream',
      app: 'zuulStream',
      template: 'web/main.ejs',
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
        test: /\.woff(2)?(\?v=\d+\.\d+\.\d+)?$/,
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
        use: ['html-loader'],
        exclude: /node_modules/
      }
    ]
  }
};
