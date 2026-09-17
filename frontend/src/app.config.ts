export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/outline/outline',
    'pages/quiz/quiz',
    'pages/result/result',
    'pages/mine/mine',
    // 组件状态预览页（对照《原型-3-状态与规范.html》做视觉验收用）——发布前删除
    'pages/dev/components'
  ],
  window: {
    backgroundTextStyle: 'light',
    // 原型的每个页面都自带页头（含返回箭头与标题），所以全局用自定义导航栏，
    // 由页面自己绘制 AppBar + 状态栏安全区（见 M4 的 SafeArea/AppBar 组件）。
    navigationStyle: 'custom',
    navigationBarBackgroundColor: '#FFFCF7',
    navigationBarTitleText: 'AI 闯关学习',
    navigationBarTextStyle: 'black',
    backgroundColor: '#FFFCF7'
  },
  // 原型底部 tab 是「圆角方块图标 + 文字」，原生 tabBar 画不出这个手感。
  // src/custom-tab-bar/ 已经写好，在微信开发者工具里验证过一次后把 custom 改成 true 即可。
  tabBar: {
    custom: false,
    color: '#8A8078',
    selectedColor: '#33302E',
    backgroundColor: '#FFFFFF',
    borderStyle: 'black',
    list: [
      {
        pagePath: 'pages/index/index',
        text: '首页'
      },
      {
        pagePath: 'pages/mine/mine',
        text: '我的'
      }
    ]
  }
})
