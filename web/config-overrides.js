const rewiredEsbuild = require("react-app-rewired-esbuild");

module.exports = function override(config, env) {
  // No additional config just want esbuild instead of babel
  return rewiredEsbuild()(config, env);
};

// use `customize-cra`
function supportMJS(config) {
   config.module.rules.push({
     test: /\.mjs$/,
     include: /node_modules/,
     type: "javascript/auto"
   });
   return config;
}

const { override } = require("customize-cra");

module.exports = override(supportMJS, rewiredEsbuild());
