export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/outline/outline',
    'pages/quiz/quiz',
    'pages/result/result',
    'pages/mine/mine'
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
  // TODO(M4): 原型底部 tab 是「圆角方块图标 + 文字」，微信原生 tabBar 无法 1:1 还原，
  // M4 会切换为 custom tabBar（custom: true + src/custom-tab-bar/）。
  tabBar: {
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
