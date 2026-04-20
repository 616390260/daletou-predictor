<template>
  <div class="container about">
    <div class="page-head">
      <h1>关于本项目</h1>
      <p>一个用来戳破"彩票能被算法预测"这个幻觉的小实验。</p>
    </div>

    <section class="card section">
      <h2>1. 项目定位</h2>
      <p>
        大乐透作为真随机系统，任何模型的长期中奖率都应该
        <b>收敛到随机基线</b>。本项目用多种模型并行跑，每期生成 4 注投注，
        真实开奖后做命中与投入产出核算，长期观察各模型之间、各模型与随机基线之间是否存在"显著差异"。
      </p>
      <p class="muted">
        换句话说：这是一个用于<b>证伪</b>各种彩票预测"神论"的平台，而非为了发财。
      </p>
    </section>

    <section class="card section">
      <h2>2. 七个模型简介</h2>
      <div class="models">
        <div class="model-item">
          <span class="model-badge" data-model="random">随机基线</span>
          <p>均匀随机抽号。所有其他模型的参照系，理论命中率 ≈ 6.7%。</p>
        </div>
        <div class="model-item">
          <span class="model-badge" data-model="frequency">频率统计</span>
          <p>按号码在近 300 期的出现频率加权抽样，测试"冷热号理论"。</p>
        </div>
        <div class="model-item">
          <span class="model-badge" data-model="bayesian">贝叶斯</span>
          <p>对每个号码建立独立的 Beta-Bernoulli 后验分布。带时间衰减，规范的频率派推断。</p>
        </div>
        <div class="model-item">
          <span class="model-badge" data-model="markov">马尔可夫链</span>
          <p>基于"上一期号码 → 下一期号码"的转移概率，测试"号码记忆"。</p>
        </div>
        <div class="model-item">
          <span class="model-badge" data-model="lstm">LSTM 神经网络</span>
          <p>把每期编码为多热向量，LSTM 学习序列模式。支持<b>增量微调</b>：新一期开奖后会热启动 checkpoint 继续训练，而非从零开始。</p>
        </div>
        <div class="model-item">
          <span class="model-badge" data-model="genetic">遗传算法</span>
          <p>以"这一注号码在历史上的回本率"为适应度，迭代进化种群。</p>
        </div>
        <div class="model-item">
          <span class="model-badge" data-model="ensemble">集成投票</span>
          <p>读取其他 5 个模型的当期预测，按各自<b>历史命中率</b>加权投票得出共识号码。表现越好的模型话语权越大。</p>
        </div>
      </div>
    </section>

    <section class="card section">
      <h2>3. 持续学习机制</h2>
      <p>
        每当 GitHub Actions 跑一次，以下流程会自动发生：
      </p>
      <ol class="steps">
        <li><b>增量抓取</b>：只抓数据库里没有的最新期数，通常 1~2 条</li>
        <li><b>评估上次预测</b>：对照实际开奖计算命中奖级和金额</li>
        <li>
          <b>更新模型</b>：
          <ul class="sub-list">
            <li>频率 / 马尔可夫 / 遗传：无状态，每次用全量历史重算</li>
            <li>LSTM：加载 checkpoint 热启动 → 在新数据 + 近 400 期回放样本上微调 8 轮</li>
            <li>集成：重新计算各模型历史命中率，作为下一期投票权重</li>
          </ul>
        </li>
        <li><b>生成下期预测</b>：每模型 4 注，共 24 注</li>
        <li><b>导出 JSON + 前端重新部署</b></li>
      </ol>
    </section>

    <section class="card section">
      <h2>4. 数据与更新时点</h2>
      <ul>
        <li>数据源：500 彩票网（主），中国体育彩票官方 API（备）</li>
        <li>数据范围：<b>从 2007 年首次开奖至今</b>，共计 2800+ 期（大乐透全量历史）</li>
        <li>存储：SQLite 数据库（随仓库托管）</li>
        <li>定时：GitHub Actions</li>
        <li class="sub">· 每周一/三/六 北京时间 18:00 生成下期预测</li>
        <li class="sub">· 每周一/三/六 北京时间 22:30 抓取开奖 + 评估 + 重新部署</li>
      </ul>
    </section>

    <section class="card section warn">
      <h2>5. 免责声明</h2>
      <p>
        彩票本身是负期望博弈，理论上没有任何方法能长期跑赢随机。本平台的全部
        预测仅用于算法研究与数据可视化展示，
        <b>不构成任何形式的购彩建议或投资建议</b>。
      </p>
      <p>
        未成年人不得购买彩票。请理性购彩、量力而行。
      </p>
    </section>
  </div>
</template>

<style scoped>
.page-head h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.page-head p {
  color: var(--text-3);
  font-size: 14px;
  margin-top: 4px;
  margin-bottom: 24px;
}

.section {
  margin-bottom: 16px;
}

.section h2 {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 12px;
}

.section p {
  font-size: 14px;
  color: var(--text-2);
  line-height: 1.7;
  margin-bottom: 8px;
}

.section p.muted {
  color: var(--text-3);
  font-size: 13px;
}

.section ul,
.section ol {
  list-style: none;
  padding: 0;
}

.section ol.steps {
  counter-reset: step;
  margin-top: 8px;
}

.section ol.steps > li {
  counter-increment: step;
  padding-left: 36px;
  position: relative;
  padding-top: 4px;
  padding-bottom: 8px;
}

.section ol.steps > li::before {
  content: counter(step);
  position: absolute;
  left: 0;
  top: 4px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(245, 158, 11, 0.15);
  color: #fcd34d;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  font-family: var(--font-mono);
}

.section ul.sub-list {
  margin-top: 6px;
  padding-left: 16px;
}

.section ul.sub-list li {
  font-size: 13px;
  color: var(--text-3);
  position: relative;
  padding-left: 12px;
}

.section ul.sub-list li::before {
  content: "·";
  position: absolute;
  left: 0;
  top: 0;
}

.section li {
  font-size: 14px;
  color: var(--text-2);
  line-height: 1.7;
  padding: 4px 0;
}

.section li.sub {
  padding-left: 16px;
  color: var(--text-3);
  font-size: 13px;
}

.section code {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
  color: #fca5a5;
}

.section.warn {
  border-color: rgba(245, 158, 11, 0.3);
  background: linear-gradient(180deg, rgba(245, 158, 11, 0.06), rgba(245, 158, 11, 0.02));
}

.models {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.model-item {
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
}

.model-item p {
  font-size: 13px;
  color: var(--text-3);
  margin-top: 8px;
  line-height: 1.6;
}

.model-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
}

.model-badge[data-model="random"] { background: rgba(113, 113, 122, 0.2); color: #d4d4d8; }
.model-badge[data-model="frequency"] { background: rgba(59, 130, 246, 0.2); color: #93c5fd; }
.model-badge[data-model="bayesian"] { background: rgba(6, 182, 212, 0.2); color: #67e8f9; }
.model-badge[data-model="markov"] { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; }
.model-badge[data-model="lstm"] { background: rgba(236, 72, 153, 0.2); color: #f9a8d4; }
.model-badge[data-model="genetic"] { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }
.model-badge[data-model="ensemble"] { background: rgba(245, 158, 11, 0.2); color: #fcd34d; }
</style>
