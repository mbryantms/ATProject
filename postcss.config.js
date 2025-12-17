module.exports = {
  plugins: [
    require('postcss-import'),
    require('postcss-mixins'),
    require('postcss-nested'),
    require('postcss-custom-properties'),
    require('autoprefixer'),
    require('postcss-sorting'),
    require('cssnano')({
      preset: 'default',
    }),
  ],
};