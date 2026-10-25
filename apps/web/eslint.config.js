/** 新 Vue/JavaScript 代码的增量检查，不扫描尚未迁移的旧客户端。 */
import js from '@eslint/js';
import vue from 'eslint-plugin-vue';
import prettier from 'eslint-config-prettier';
import { methodComments } from './eslint-rules.js';

export default [
  {
    // 线上原版兼容资源按摘要保留；新Vue源码继续严格检查，不重排已发布旧模块。
    ignores: [
      'dist/**',
      'dist-trial/**',
      'node_modules/**',
      'src/shared/http/generated.d.ts',
      'public/legacy-runtime/**',
      'public/assets/**',
    ],
  },
  js.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['src/**/*.js', 'src/**/*.vue'],
    languageOptions: {
      globals: {
        fetch: 'readonly',
        AbortController: 'readonly',
        AbortSignal: 'readonly',
        Headers: 'readonly',
        Response: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        FileReader: 'readonly',
        crypto: 'readonly',
        TextEncoder: 'readonly',
        TextDecoder: 'readonly',
        ReadableStream: 'readonly',
        DOMException: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        setTimeout: 'readonly',
      },
    },
  },
  {
    files: ['src/**/*.js', 'src/**/*.vue'],
    plugins: { huali: { rules: { 'method-comments': methodComments } } },
    rules: { 'huali/method-comments': 'error' },
  },
  { files: ['vite.config.js'], languageOptions: { globals: { process: 'readonly' } } },
  prettier,
];
