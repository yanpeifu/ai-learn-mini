import { Text, View } from '@tarojs/components'
import Taro, { useDidShow, useReachBottom } from '@tarojs/taro'
import { useCallback, useState } from 'react'

import { Chip, EmptyState, Yanbao } from '@/components'
import { COPY } from '@/constants/copy'
import { api } from '@/services/api'
import { storage } from '@/services/storage'
import { useUser } from '@/store/UserContext'
import type { AttemptHistoryItem, UserStats } from '@/types/api'

import './mine.scss'

const PAGE_SIZE = 20

/** P5 我的：有记录（P5-1）/ 空状态（P5-2）。 */
export default function Mine() {
  const { user, login } = useUser()
  const [stats, setStats] = useState<UserStats | null>(null)
  const [records, setRecords] = useState<AttemptHistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    try {
      if (!storage.getToken()) await login()
      const [statResult, history] = await Promise.all([api.userStats(), api.attempts(1, PAGE_SIZE)])
      setStats(statResult)
      setRecords(history.list)
      setTotal(history.total)
      setPage(1)
    } catch {
      setStats(null)
      setRecords([])
    } finally {
      setLoaded(true)
    }
  }, [login])

  useDidShow(() => {
    void load()
  })

  useReachBottom(() => {
    if (loadingMore || records.length >= total || total === 0) return
    setLoadingMore(true)
    api
      .attempts(page + 1, PAGE_SIZE)
      .then((history) => {
        setRecords((current) => [...current, ...history.list])
        setPage((current) => current + 1)
      })
      .catch(() => undefined)
      .finally(() => setLoadingMore(false))
  })

  const scoreClass = (accuracy: number) =>
    accuracy >= 90 ? 'score-good' : accuracy >= 70 ? 'score-mid' : 'score-bad'

  const hasRecords = records.length > 0

  return (
    <View className='page-mine'>
      <View className='profile'>
        <View className='avatar'>
          <Yanbao mood={hasRecords ? 'happy' : 'peek'} size='sm' />
        </View>
        <View className='profile-text'>
          <Text className='profile-name'>{user?.nickname ?? COPY.learner}</Text>
          <Text className='cap'>
            {stats && stats.study_days > 0
              ? COPY.studyDays
                  .replace('{d}', String(stats.study_days))
                  .replace('{s}', String(stats.streak_days))
              : COPY.notStarted}
          </Text>
        </View>
        <Chip tone='lav'>{COPY.memberBadge}</Chip>
      </View>

      <View className='kpi'>
        <View className='kpi-cell'>
          <Text className='kpi-value'>{stats?.study_count ?? 0}</Text>
          <Text className='kpi-label'>{COPY.studyCount}</Text>
        </View>
        <View className='kpi-cell'>
          <Text className='kpi-value'>{stats?.answered_count ?? 0}</Text>
          <Text className='kpi-label'>{COPY.answeredCount}</Text>
        </View>
        <View className='kpi-cell'>
          <Text className='kpi-value'>{stats && stats.study_count > 0 ? `${Math.round(stats.avg_accuracy)}%` : '—'}</Text>
          <Text className='kpi-label'>{COPY.avgAccuracy}</Text>
        </View>
      </View>

      <Text className='sec'>学习记录</Text>

      {hasRecords ? (
        <View className='record-list'>
          {records.map((record) => (
            <View
              className='rec'
              key={record.attempt_id}
              onClick={() => Taro.navigateTo({ url: `/pages/result/result?attemptId=${record.attempt_id}` })}
            >
              <Text className='rec-title'>{record.title}</Text>
              <Text className={`score ${scoreClass(record.accuracy)}`}>{Math.round(record.accuracy)}%</Text>
            </View>
          ))}
          <Text className='cap record-footer'>
            {records.length < total
              ? COPY.loadMore.replace('{n}', String(total))
              : `已全部加载 · 共 ${total} 条`}
          </Text>
        </View>
      ) : loaded ? (
        <View className='mine-empty'>
          <EmptyState
            yanbao='peek'
            title={COPY.emptyMineTitle}
            description={COPY.emptyMineHint}
            actionText={COPY.goStudy}
            onAction={() => Taro.switchTab({ url: '/pages/index/index' })}
          />
        </View>
      ) : null}

      <Text className='agreements'>{COPY.agreements}</Text>
    </View>
  )
}
