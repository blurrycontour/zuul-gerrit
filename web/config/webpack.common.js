const path = require('path');
const webpack = require('webpack');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const CleanWebpackPlugin = require('clean-webpack-plugin');

module.exports = {
  entry: {
    status: './web/status.ts',
    builds: './web/builds.ts',
    stream: './web/stream.ts',
    job: './web/job.ts',
    jobs: './web/jobs.ts',
    tenants: './web/tenants.ts',
    project: './web/project.ts',
    projects: './web/projects.ts'
  },
  resolve: {
    extensions: [ '.tsx', '.ts', '.js' ]
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
  optimization: {
    runtimeChunk: true,
    splitChunks: {
      cacheGroups: {
        commons: {
          test: /node_modules/,
          name: "vendor",
          chunks: "all"
        }
      }
    }
  },
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
      title: 'Zuul Status',
      app: 'zuulStatus',
      template: 'web/config/main.ejs',
      filename: 'status.html',
      chunks: ['status', 'vendor', 'runtime~status']
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Builds',
      app: 'zuulBuilds',
      template: 'web/config/main.ejs',
      filename: 'builds.html',
      chunks: ['builds', 'vendor', 'runtime~builds']
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Job',
      app: 'zuulJob',
      template: 'web/config/main.ejs',
      filename: 'job.html',
      chunks: ['job', 'vendor', 'runtime~job']
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Jobs',
      app: 'zuulJobs',
      template: 'web/config/main.ejs',
      filename: 'jobs.html',
      chunks: ['jobs', 'vendor', 'runtime~jobs']
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Project',
      app: 'zuulProject',
      template: 'web/config/main.ejs',
      filename: 'project.html',
      chunks: ['project', 'vendor', 'runtime~project']
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Projects',
      app: 'zuulProjects',
      template: 'web/config/main.ejs',
      filename: 'projects.html',
      chunks: ['projects', 'vendor', 'runtime~projects']
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Tenants',
      app: 'zuulTenants',
      template: 'web/config/main.ejs',
      filename: 'tenants.html',
      chunks: ['tenants', 'vendor', 'runtime~tenants']
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Console Stream',
      app: 'zuulStream',
      template: 'web/config/main.ejs',
      filename: 'stream.html',
      chunks: ['stream', 'vendor', 'runtime~stream']
    })
  ],
  module: {
    rules: [
      {
        test: /\.ts$/,
        exclude: /node_modules/,
        use: [
          'babel-loader', 'ts-loader'
        ]
      },
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
