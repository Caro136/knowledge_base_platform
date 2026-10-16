<template>
  <div class="kb-page">
    <!-- 指标卡 -->
    <el-row :gutter="12">
      <el-col v-for="card in cards" :key="card.title" :span="4">
        <el-card shadow="never" class="stat-card" :style="{ borderTopColor: card.color }">
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-title">{{ card.title }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="row-gap">
      <el-col :span="15">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>访问趋势</span>
              <el-radio-group v-model="trendDays" size="small" @change="reloadTrend">
                <el-radio-button :label="7">近 7 天</el-radio-button>
                <el-radio-button :label="14">近 14 天</el-radio-button>
                <el-radio-button :label="30">近 30 天</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div ref="trendRef" class="chart"></div>
          <el-empty v-if="!trend.length && !loading" description="暂无访问数据" :image-size="60" />
        </el-card>
      </el-col>

      <el-col :span="9">
        <el-card shadow="never">
          <template #header>热门知识单元 TOP10</template>
          <div ref="docRef" class="chart"></div>
          <el-empty v-if="!topDocs.length && !loading" description="暂无引用数据" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>

    <el-row class="row-gap">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>常见高频问题 TOP10</template>
          <el-table v-loading="loading" :data="topQuestions" border stripe>
            <el-table-column type="index" label="排名" width="80" />
            <el-table-column prop="question" label="问题" min-width="320" show-overflow-tooltip />
            <el-table-column prop="count" label="提问次数" width="120" sortable />
          </el-table>
          <el-empty v-if="!topQuestions.length && !loading" description="暂无提问记录" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>

    <div class="footnote">
      统计窗口：指标卡为近 {{ overview.days || 30 }} 天，排行默认近 30 天；数据源为问答流水。
    </div>
  </div>
</template>

<script setup>
/** 运营看板（T-29）。 */
import * as echarts from 'echarts'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

import { dashOverview, dashTopDocs, dashTopQuestions, dashTrend } from '@/api'

const loading = ref(true)
const overview = ref({})
const topQuestions = ref([])
const topDocs = ref([])
const trend = ref([])
const trendDays = ref(14)

const trendRef = ref(null)
const docRef = ref(null)
let trendChart = null
let docChart = null

function formatNumber(value) {
  if (value === null || value === undefined) return '0'
  return Number(value).toLocaleString('zh-CN')
}
function formatPercent(value) {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`
}
function formatTokens(value) {
  const num = Number(value) || 0
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return String(num)
}

const cards = computed(() => [
  { title: '访问次数', value: formatNumber(overview.value.totalVisits), color: '#409eff' },
  { title: '访问人数', value: formatNumber(overview.value.distinctUsers), color: '#67c23a' },
  { title: '知识单元', value: formatNumber(overview.value.docCount), color: '#e6a23c' },
  { title: 'Token 消耗', value: formatTokens(overview.value.totalTokens), color: '#f56c6c' },
  { title: '平均响应', value: `${overview.value.avgLatencyMs || 0} ms`, color: '#909399' },
  { title: '缓存命中率', value: formatPercent(overview.value.faqHitRate), color: '#9254de' },
])

async function loadOverview() {
  try {
    overview.value = (await dashOverview({ days: 30 })) || {}
  } catch {
    overview.value = {}
  }
}

async function loadTrend() {
  try {
    trend.value = (await dashTrend({ days: trendDays.value })) || []
  } catch {
    trend.value = []
  }
  await nextTick()
  renderTrend()
}

async function loadRankings() {
  try {
    const [questions, docs] = await Promise.all([
      dashTopQuestions({ limit: 10, days: 30 }),
      dashTopDocs({ limit: 10, days: 30 }),
    ])
    topQuestions.value = questions || []
    topDocs.value = docs || []
  } catch {
    topQuestions.value = []
    topDocs.value = []
  }
  await nextTick()
  renderDocs()
}

function renderTrend() {
  if (!trendRef.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)

  trendChart.setOption(
    {
      tooltip: { trigger: 'axis' },
      legend: { data: ['访问次数', '访问人数'], top: 4 },
      grid: { left: 48, right: 24, top: 40, bottom: 32 },
      xAxis: { type: 'category', boundaryGap: false, data: trend.value.map((item) => item.date) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          name: '访问次数',
          type: 'line',
          smooth: true,
          areaStyle: { opacity: 0.12 },
          itemStyle: { color: '#409eff' },
          data: trend.value.map((item) => item.pv),
        },
        {
          name: '访问人数',
          type: 'line',
          smooth: true,
          itemStyle: { color: '#67c23a' },
          data: trend.value.map((item) => item.uv),
        },
      ],
    },
    true,
  )
}

function renderDocs() {
  if (!docRef.value) return
  if (!docChart) docChart = echarts.init(docRef.value)

  const data = topDocs.value.map((item) => ({
    name: item.title.length > 14 ? `${item.title.slice(0, 14)}…` : item.title,
    value: item.count,
  }))

  docChart.setOption(
    {
      tooltip: { trigger: 'item', formatter: '{b}<br/>被引用 {c} 次 ({d}%)' },
      legend: { type: 'scroll', orient: 'vertical', right: 6, top: 12, bottom: 12 },
      series: [
        {
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['38%', '52%'],
          avoidLabelOverlap: true,
          label: { show: false },
          data,
        },
      ],
    },
    true,
  )
}

function reloadTrend() {
  loadTrend()
}

function onResize() {
  trendChart?.resize()
  docChart?.resize()
}

onMounted(async () => {
  try {
    await Promise.all([loadOverview(), loadTrend(), loadRankings()])
  } finally {
    loading.value = false
  }
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  trendChart?.dispose()
  docChart?.dispose()
  trendChart = null
  docChart = null
})
</script>

<style scoped>
.stat-card {
  border-top: 3px solid #409eff;
}

.stat-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.4;
}

.stat-title {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.row-gap {
  margin-top: 12px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chart {
  height: 320px;
}

.footnote {
  margin-top: 12px;
  font-size: 12px;
  color: #a8abb2;
  text-align: right;
}
</style>
