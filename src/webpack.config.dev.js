var path = require('path');
var webpack = require('webpack');

var BundleTracker  = require('webpack-bundle-tracker');
var ExtractTextPlugin = require('extract-text-webpack-plugin');

var autoprefixer = require('autoprefixer');

require('es6-promise').polyfill();

module.exports = {
  entry: {
    main:[
      'webpack/hot/dev-server',
      'webpack-dev-server/client?http://localhost:8080',
      path.resolve(__dirname, 'static/src/main.js'),
    ],
    forum: path.resolve(__dirname, 'static/src/forum.js'),
  },
  output: {
    path: path.resolve(__dirname, 'static/build'),
    filename: '[name].bundle.js',
    publicPath: 'http://localhost:8080/static/',
  },
  plugins: [
    new BundleTracker({
      path: path.resolve(__dirname, 'static/build'),
      filename: 'stats.json',
    }),
    new webpack.optimize.DedupePlugin(),
    new webpack.optimize.OccurenceOrderPlugin(),
    new webpack.optimize.UglifyJsPlugin({
      compressor: {
        drop_debugger: false,
        warnings: false,
      },
    }),
  ],
  module: {
    loaders: [

      // FONTS
      {
        test: /\.woff(\?v=\d+\.\d+\.\d+)?$/,
        loader: 'url-loader?limit=8192&mimetype=application/font-woff',
      }, {
        test: /\.woff2(\?v=\d+\.\d+\.\d+)?$/,
        loader: 'url-loader?limit=8192&mimetype=application/font-woff',
      }, {
        test: /\.ttf(\?v=\d+\.\d+\.\d+)?$/,
        loader: 'url-loader?limit=8192&mimetype=application/octet-stream',
      }, {
        test: /\.eot(\?v=\d+\.\d+\.\d+)?$/,
        loader: 'url-loader?limit=8192&mimetype=application/vnd.ms-fontobject',
      }, {
        test: /\.otf(\?v=\d+\.\d+\.\d+)?$/,
        loader: 'url-loader?limit=8192&mimetype=image/font-otf',
      }, {
        test: /\.svg(\?v=\d+\.\d+\.\d+)?$/,
        loader: 'url-loader?limit=8192&mimetype=image/svg+xml',
      },

      // IMAGES
      {
        test: /\.(ico|jpe?g|png|gif|svg)$/i,
        loaders: [
            'file?hash=sha512&digest=hex&name=images/assets/[name].[ext]?[hash:5]',
            'image-webpack?bypassOnDebug&optimizationLevel=7&interlaced=false&progressive=true',
        ],
        include: [
          path.resolve(__dirname, 'static/src/images/assets/'),
        ],
      },
      {
        test: /\.(ico|jpe?g|png|gif|svg)$/i,
        loader: 'url?limit=8192&name=images/includes/[name].[ext]',
        include: [
          path.resolve(__dirname, 'static/src/images/includes'),
        ],
      },

      // STYLES
      {
        test: /\.css$/,
        loader: 'style!css!postcss',
      },
      {
        test: /\.scss$/,
        loader: 'style!css!postcss!sass',
      },

      // MISC
      {
        test: /\.xml$/,
        loader: 'file?hash=sha512&digest=hex&name=[name].[ext]?[hash:5]',
      },
    ]
  },
  postcss: [
    autoprefixer({ browsers: ['last 2 versions'] }),
  ],
};
