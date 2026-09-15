// ESM config: cssnano 9, postcss-nested 8 and postcss-import 17 are ESM-only,
// so this file must be a module (package.json has no "type": "module", hence
// the .mjs extension). postcss-cli / postcss-load-config pick it up by name.
import autoprefixer from 'autoprefixer';
import cssnano from 'cssnano';
import postcssCustomProperties from 'postcss-custom-properties';
import postcssImport from 'postcss-import';
import postcssMixins from 'postcss-mixins';
import postcssNested from 'postcss-nested';
import postcssSorting from 'postcss-sorting';

export default {
  plugins: [
    postcssImport,
    postcssMixins,
    postcssNested,
    postcssCustomProperties,
    autoprefixer,
    postcssSorting,
    cssnano({ preset: 'default' }),
  ],
};
