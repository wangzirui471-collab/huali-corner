'use strict';
// AI 客服宠物：客服页右下角的悬浮入口。
// 点击打开对话，走 /api/ai/chat（本地知识库 + DeepSeek；不确定会转人工）。
// 只在客服页、config.ai 为真时渲染；线上 Cloudflare 不显示。

export function aiPet(){
  return `<div class="ai-pet" id="ai-pet">
    <button type="button" class="ai-pet-bubble" data-action="ai-pet-toggle">有问题？点我问 AI 小助手</button>
    <button type="button" class="ai-pet-body" data-action="ai-pet-toggle" aria-label="打开 AI 小助手">
      <span class="ai-pet-sprite" aria-hidden="true"></span>
    </button>
    <section class="ai-pet-panel" id="ai-pet-panel" hidden aria-label="AI 小助手">
      <header class="ai-pet-head">
        <span class="ai-pet-avatar"><img src="/assets/ai-pet/pet.png" alt=""></span>
        <div><b>转角 AI 小助手</b><small>基于平台规则 · 不确定会引导提交工单</small></div>
        <button type="button" class="ai-pet-close" data-action="ai-pet-toggle" aria-label="关闭">×</button>
      </header>
      <div class="ai-pet-log" id="ai-pet-log">
        <div class="ai-pet-msg bot">你好，我是转角 AI 小助手。发布、退款、面交、客服时间都可以问我；不确定的会建议你提交工单。</div>
      </div>
      <div class="ai-pet-chips" aria-label="常见问题">
        <button type="button" data-action="ai-pet-chip" data-q="怎么发布闲置？">怎么发布</button>
        <button type="button" data-action="ai-pet-chip" data-q="怎么退款？">怎么退款</button>
        <button type="button" data-action="ai-pet-chip" data-q="客服什么时候在线？">客服时间</button>
        <button type="button" data-action="ai-pet-chip" data-q="怎么注销账号？">注销账号</button>
      </div>
      <form id="ai-pet-form" class="ai-pet-form">
        <label class="ai-pet-sr" for="ai-pet-q">输入问题</label>
        <textarea id="ai-pet-q" name="q" maxlength="300" rows="1" placeholder="输入你的问题，例如：怎么发布？" required></textarea>
        <button type="submit" class="ai-pet-send">发送</button>
      </form>
      <p class="ai-pet-note">AI 回答仅供参考。问题会发送给第三方 AI 服务用于生成回答，请勿输入密码、手机号、恢复码等敏感信息。</p>
    </section>
  </div>`;
}
