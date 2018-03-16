import * as path from 'path'
import * as webpack from 'webpack'
import * as HtmlWebpackPlugin from 'html-webpack-plugin'
import * as CleanWebpackPlugin from 'clean-webpack-plugin'

// Workaround issue in the published typescript definition of
// webpack.Options.SplitChunksOptions in @types/webpack. The published
// definition says:
//   cacheGroups?: false | string | ((...args: any[]) => any) | RegExp | CacheGroupsOptions;
// but what webpack ACTUALLY wants, rather than a CacheGroupsOptions is a
// Map<string, CacheGroupsOptions>.
// A PR has been submitted upstream:
//    https://github.com/DefinitelyTyped/DefinitelyTyped/pull/24221
// For now, just extend with any
interface Configuration extends webpack.Configuration {
  optimization?: any
}

const config: Configuration = {
  // Default to development, the prod config will override
  mode: 'development',
  entry: {
    main: './web/main.ts',
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
      template: 'web/config/main.ejs',
      filename: 'status.html',
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Builds',
      template: 'web/config/main.ejs',
      filename: 'builds.html',
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Job',
      template: 'web/config/main.ejs',
      filename: 'job.html',
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Jobs',
      template: 'web/config/main.ejs',
      filename: 'jobs.html',
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Project',
      template: 'web/config/main.ejs',
      filename: 'project.html',
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Projects',
      template: 'web/config/main.ejs',
      filename: 'projects.html',
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Tenants',
      template: 'web/config/main.ejs',
      filename: 'tenants.html',
    }),
    new HtmlWebpackPlugin({
      title: 'Zuul Console Stream',
      template: 'web/config/main.ejs',
      filename: 'stream.html',
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
}

export default config
