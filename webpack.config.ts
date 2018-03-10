export default function config(env) {
  return require(`./web/config/webpack.${env}.ts`)
}
