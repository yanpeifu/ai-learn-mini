import { Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import { ClayButton, TipBar, Yanbao } from '@/components'
import { starSvg } from '@/assets/star'
import { COPY } from '@/constants/copy'
import { useNavMetrics } from '@/hooks/useNavMetrics'
import { api } from '@/services/api'
import { ApiError } from '@/services/request'
import { svgToDataUri } from '@/utils/svg'
import type { Settlement } from '@/types/api'

import './result.scss'

const STAR_COUNT = 3
const WEAK_THRESHOLD = 60

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/** P4 通关结算：三星通关（P4-1）/ 低分鼓励（P4-2），也是学习记录的只读回看页。 */
export default function Result() {
  const { safeTop } = useNavMetrics()
  const [settlement, setSettlement] = useState<Settlement | null>(null)
  const [title, setTitle] = useState('')
  const [litStars, setLitStars] = useState(0)
  const [error, setError] = useState('')

  useLoad((params) => {
    const attemptId = Number(params?.attemptId ?? 0)
    if (!attemptId) {
      setError('没有找到这次学习记录')
      return
    }
    api
      .attemptDetail(attemptId)
      .then((detail) => {
        setSettlement(detail.settlement)
        setTitle(detail.attempt.title)
      })
      .catch((caught: unknown) => {
        setError(caught instanceof ApiError ? caught.message : '结算数据加载失败')
      })
  })

  // 星星依次弹出（原型：间隔 120ms）
  useEffect(() => {
    if (!settlement) return
    const timers: ReturnType<typeof setTimeout>[] = []
    for (let index = 0; index < settlement.star; index += 1) {
      timers.push(setTimeout(() => setLitStars(index + 1), 120 * (index + 1)))
    }
    return () => timers.forEach(clearTimeout)
  }, [settlement])

  if (error) {
    return (
      <View className='page-result result-center' style={{ paddingTop: `${safeTop}px` }}>
        <Yanbao mood='sad' size='lg' />
        <Text className='result-error'>{error}</Text>
        <ClayButton variant='primary' onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>
          {COPY.playAgain}
        </ClayButton>
      </View>
    )
  }

  if (!settlement) {
    return (
      <View className='page-result result-center' style={{ paddingTop: `${safeTop}px` }}>
        <Yanbao mood='happy' size='md' />
        <Text className='cap'>正在算分…</Text>
      </View>
    )
  }

  const isLowScore = settlement.accuracy < 50
  const weakCount = settlement.weak_points.length

  return (
    <View className='page-result'>
      <View
        className='content content-center'
        // 注意：本页是纯居中、竖向堆叠的页面，右上角没有任何内容，
        // 所以只需要状态栏留白；加右侧避让反而会把整块内容挤偏（BUG 回归修复）。
        style={{ paddingTop: `${safeTop + 13}px` }}
      >
        <Yanbao mood={isLowScore ? 'go' : 'cheer'} size='lg' />

        <View className='stars'>
          {Array.from({ length: STAR_COUNT }).map((_item, index) => (
            <View
              key={index}
              className={`star ${index < litStars || index < settlement.star ? 'star-on' : ''}`}
              style={{
                backgroundImage: `url("${svgToDataUri(
                  starSvg(index < Math.max(litStars, settlement.star))
                )}")`
              }}
            />
          ))}
        </View>

        <Text className={`big ${isLowScore ? 'big-small' : ''}`}>{Math.round(settlement.accuracy)}%</Text>
        <Text className='cap'>{COPY.accurateRate.replace('{n}', String(settlement.total_count))}</Text>
        {title ? <Text className='result-title'>{title}</Text> : null}

        {isLowScore ? (
          <TipBar>{settlement.advice}</TipBar>
        ) : (
          <View className='kpi'>
            <View className='kpi-cell'>
              <Text className='kpi-value'>{formatDuration(settlement.duration_ms)}</Text>
              <Text className='kpi-label'>{COPY.timeUsed}</Text>
            </View>
            <View className='kpi-cell'>
              <Text className='kpi-value'>
                {settlement.correct_count}/{settlement.total_count}
              </Text>
              <Text className='kpi-label'>{COPY.correctCount}</Text>
            </View>
          </View>
        )}

        {isLowScore ? (
          <View className='kpi'>
            <View className='kpi-cell'>
              <Text className='kpi-value'>{settlement.total_count - settlement.correct_count}</Text>
              <Text className='kpi-label'>待复习错题</Text>
            </View>
            <View className='kpi-cell'>
              <Text className='kpi-value'>{weakCount}</Text>
              <Text className='kpi-label'>薄弱知识点</Text>
            </View>
          </View>
        ) : (
          <>
            <Text className='sec'>各知识点表现</Text>
            <View className='kplist'>
              {settlement.points.map((point) => (
                <View className='kp-row' key={point.level_seq}>
                  <Text className='kp-name'>{point.knowledge_point}</Text>
                  <View className='kp-bar'>
                    <View
                      className={`kp-fill ${point.accuracy < WEAK_THRESHOLD ? 'kp-fill-weak' : ''}`}
                      style={{ width: `${Math.max(4, Math.round(point.accuracy))}%` }}
                    />
                  </View>
                  <Text className={`kp-accuracy ${point.accuracy < WEAK_THRESHOLD ? 'warn' : ''}`}>
                    {Math.round(point.accuracy)}%
                  </Text>
                </View>
              ))}
            </View>
            <TipBar>{settlement.advice}</TipBar>
          </>
        )}

        <View className='btnrow btnrow-full'>
          {isLowScore ? (
            <>
              <ClayButton onClick={() => Taro.showToast({ title: COPY.mistakesSoon, icon: 'none' })}>
                {COPY.viewMistakes}
              </ClayButton>
              <ClayButton variant='primary' onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>
                {COPY.learnAgain}
              </ClayButton>
            </>
          ) : (
            <>
              <ClayButton onClick={() => Taro.switchTab({ url: '/pages/index/index' })}>
                {COPY.playAgain}
              </ClayButton>
              <ClayButton variant='primary' onClick={() => Taro.switchTab({ url: '/pages/mine/mine' })}>
                {COPY.viewRecords}
              </ClayButton>
            </>
          )}
        </View>
      </View>
    </View>
  )
}
