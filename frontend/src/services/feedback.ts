import Taro from '@tarojs/taro'

/**
 * 音效与震动（PRD F4 反馈表 / UI 方案第 9.3 节）。
 *
 * ⚠️ 音效素材（4 个 mp3）还没提供，文件放在 `src/assets/sounds/` 后即可自动生效：
 *    right.mp3（木琴清脆单音）/ wrong.mp3（柔和「噗」声）/
 *    combo.mp3（音阶上行）/ finish.mp3（欢快旋律）
 * 在素材到位前，播放会静默失败，不影响答题流程。
 */
export type SoundName = 'right' | 'wrong' | 'combo' | 'finish'

const SOUND_FILES: Record<SoundName, string> = {
  right: '/assets/sounds/right.mp3',
  wrong: '/assets/sounds/wrong.mp3',
  combo: '/assets/sounds/combo.mp3',
  finish: '/assets/sounds/finish.mp3'
}

const contexts: Partial<Record<SoundName, Taro.InnerAudioContext>> = {}
let soundEnabled = true

export const feedback = {
  /** 首次用户交互时调用（系统要求：音效必须由用户手势触发才能播放） */
  preloadSounds(): void {
    ;(Object.keys(SOUND_FILES) as SoundName[]).forEach((name) => {
      try {
        const ctx = Taro.createInnerAudioContext()
        ctx.src = SOUND_FILES[name]
        ctx.volume = 0.6 // 学习场景下不应该吓到用户
        contexts[name] = ctx
      } catch {
        /* 忽略：素材缺失或平台不支持 */
      }
    })
  },

  play(name: SoundName): void {
    if (!soundEnabled) return
    try {
      contexts[name]?.play()
    } catch {
      /* 静默失败 */
    }
  },

  setEnabled(enabled: boolean): void {
    soundEnabled = enabled
  },

  /** 答对轻微震动、连对中等震动、答错不震动（原型反馈表） */
  vibrate(kind: 'light' | 'medium' | 'heavy' = 'light'): void {
    try {
      Taro.vibrateShort({ type: kind })
    } catch {
      /* 部分机型不支持 */
    }
  }
}
