import path from 'node:path'

import { defineConfig, type UserConfigExport } from '@tarojs/cli'
import TsconfigPathsPlugin from 'tsconfig-paths-webpack-plugin'
import devConfig from './dev'
import prodConfig from './prod'

/**
 * designWidth 取 375：UI 原型是按 375 逻辑像素的 iPhone 稿画的
 * （正文 14.5px、卡片圆角 24px、描边 2.5px、硬投影 0 2px 0），
 * 这样原型里的 px 数值可以原样搬进样式，是 1:1 还原的前提。
 * 模板自带的 deviceRatio 已包含 375: 2，无需改动。
 */
/**
 * 后端地址在构建期写死（H5 运行时没有 process 对象，必须静态替换，
 * 否则会白屏并报 `process is not defined` —— 这是视觉验收时真实踩到的坑）。
 */
const API_BASE = process.env.TARO_APP_API_BASE || 'http://127.0.0.1:8000'
/** 本地联调开关：true 时前端直接发 dev_ 开头的假 code（无需 AppID/Secret）。 */
const DEV_LOGIN = process.env.TARO_APP_DEV_LOGIN || ''

// https://taro-docs.jd.com/docs/next/config#defineconfig-辅助函数
export default defineConfig<'webpack5'>(async (merge) => {
  const baseConfig: UserConfigExport<'webpack5'> = {
    projectName: 'ai-learn-mini',
    date: '2026-9-17',
    designWidth: 375,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      375: 2,
      828: 1.81 / 2
    },
    sourceRoot: 'src',
    // 关键：小程序与 H5 的产物必须分开放。
    // 两者共用 dist 时，后编译的会覆盖前一个，进而让开发者工具缓存失效
    // （典型报错：ENOENT ... dist\js\app.<hash>.js —— 那是 H5 的文件，已被小程序产物覆盖）。
    // 注意：CLI 的 --output-root 参数在当前 Taro 版本上不生效，所以在这里按平台判断。
    outputRoot: process.env.TARO_ENV === 'h5' ? 'dist-h5' : 'dist',
    plugins: [
      "@tarojs/plugin-generator"
    ],
    defineConstants: {
      'process.env.TARO_APP_API_BASE': JSON.stringify(API_BASE),
      'process.env.TARO_APP_DEV_LOGIN': JSON.stringify(DEV_LOGIN)
    },
    copy: {
      patterns: [
        // 音效素材按「包内路径」被代码引用（见 src/services/feedback.ts），
        // 所以必须显式拷贝进产物；把 mp3 放进 src/assets/sounds/ 即可自动生效。
        { from: 'src/assets/sounds', to: 'dist/assets/sounds' }
      ],
      options: {
      }
    },
    framework: 'react',
    compiler: 'webpack5',
    cache: {
      enable: false // Webpack 持久化缓存配置，建议开启。默认配置请参考：https://docs.taro.zone/docs/config-detail#cache
    },
    sass: {
      // 每个 .scss 自动注入设计令牌（src/styles/tokens.scss），页面里直接用 $paper / $ink 等变量
      resource: [path.resolve(__dirname, '..', 'src', 'styles', 'tokens.scss')],
      projectDirectory: path.resolve(__dirname, '..')
    },
    mini: {
      postcss: {
        pxtransform: {
          enable: true,
          config: {

          }
        },
        cssModules: {
          enable: false, // 默认为 false，如需使用 css modules 功能，则设为 true
          config: {
            namingPattern: 'module', // 转换模式，取值为 global/module
            generateScopedName: '[name]__[local]___[hash:base64:5]'
          }
        }
      },
      webpackChain(chain) {
        chain.resolve.plugin('tsconfig-paths').use(TsconfigPathsPlugin)
      }
    },
    h5: {
      publicPath: '/',
      staticDirectory: 'static',
      output: {
        filename: 'js/[name].[hash:8].js',
        chunkFilename: 'js/[name].[chunkhash:8].js'
      },
      miniCssExtractPluginOption: {
        ignoreOrder: true,
        filename: 'css/[name].[hash].css',
        chunkFilename: 'css/[name].[chunkhash].css'
      },
      postcss: {
        autoprefixer: {
          enable: true,
          config: {}
        },
        cssModules: {
          enable: false, // 默认为 false，如需使用 css modules 功能，则设为 true
          config: {
            namingPattern: 'module', // 转换模式，取值为 global/module
            generateScopedName: '[name]__[local]___[hash:base64:5]'
          }
        }
      },
      webpackChain(chain) {
        chain.resolve.plugin('tsconfig-paths').use(TsconfigPathsPlugin)
      }
    },
    rn: {
      appName: 'taroDemo',
      postcss: {
        cssModules: {
          enable: false, // 默认为 false，如需使用 css modules 功能，则设为 true
        }
      }
    }
  }


  if (process.env.NODE_ENV === 'development') {
    // 本地开发构建配置（不混淆压缩）
    return merge({}, baseConfig, devConfig)
  }
  // 生产构建配置（默认开启压缩混淆等）
  return merge({}, baseConfig, prodConfig)
})
