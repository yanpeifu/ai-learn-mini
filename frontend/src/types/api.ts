/** 与后端约定的数据结构（统一信封 {code, message, data}）。 */

export interface UserPublic {
  id: number
  nickname: string
  avatar_url?: string | null
  is_member: boolean
}

export interface OutlinePoint {
  id: string
  title: string
  summary: string
}

export interface PublicOption {
  key: string
  text: string
}

export type QuestionType = 'single' | 'multiple' | 'judge'

export interface PublicQuestion {
  id: number
  seq: number
  type: QuestionType
  difficulty: number
  stem: string
  options: PublicOption[]
}

export interface PublicLevel {
  id: number
  seq: number
  title: string
  knowledge_point: string
  question_count: number
  questions: PublicQuestion[]
}

export interface OutlineGenerateResult {
  outline_id: number
  source_id: number
  title: string
  points: OutlinePoint[]
}

export interface OutlineDetail extends OutlineGenerateResult {
  id: number
  status: string
  levels: PublicLevel[]
}

export interface LevelsGenerateResult {
  outline_id: number
  levels: PublicLevel[]
  stats: { regenerated: number; dropped: number; backfilled: number; warnings: number }
}

export interface AttemptStartResult {
  attempt_id: number
  status: string
  total_count: number
  levels: PublicLevel[]
}

export interface AnswerResult {
  is_correct: boolean
  correct_answer: string[]
  explanation: string
  correct_count: number
  answered_count: number
  combo: number
  already_answered: boolean
}

export interface LevelScore {
  level_seq: number
  title: string
  knowledge_point: string
  total: number
  correct: number
  accuracy: number
}

export interface Settlement {
  attempt_id: number
  status: string
  accuracy: number
  star: number
  duration_ms: number
  correct_count: number
  total_count: number
  points: LevelScore[]
  weak_points: LevelScore[]
  advice: string
}

export interface ReviewQuestion extends PublicQuestion {
  user_answer: string[]
  is_correct: boolean | null
  answered: boolean
  correct_answer: string[]
  explanation: string
}

export interface ReviewLevel extends Omit<PublicLevel, 'questions'> {
  questions: ReviewQuestion[]
}

export interface AttemptDetail {
  attempt: {
    id: number
    outline_id: number
    title: string
    status: string
    started_at?: string
    finished_at?: string | null
  }
  settlement: Settlement
  levels: ReviewLevel[]
}

export interface AttemptHistoryItem {
  attempt_id: number
  outline_id: number
  title: string
  accuracy: number
  star: number
  correct_count: number
  total_count: number
  duration_ms: number
  finished_at: string | null
}

export interface AttemptHistory {
  list: AttemptHistoryItem[]
  total: number
  page: number
  size: number
  has_more: boolean
}

export interface OngoingAttempt {
  attempt_id: number
  outline_id: number
  title: string
  total_count: number
  answered_count: number
  next_question_id: number | null
}

export interface UserStats {
  study_count: number
  answered_count: number
  avg_accuracy: number
  study_days: number
  streak_days: number
  mistake_due_count: number
}

export interface TemplateItem {
  id: string
  name: string
  icon: string
  prefill: string
}
