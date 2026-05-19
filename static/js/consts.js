export const suggestionQueryPool = [
  "刷单返利诈骗有什么常见套路？",
  "冒充电商物流客服诈骗有哪些风险信号？",
  "比较一下冒充客服和冒充公检法的常见话术",
  "推荐适合校园宣讲的典型诈骗案例",
  "推荐适合社区宣传的养老诈骗案例",
  "给老年人整理一段防骗提醒",
  "把刷单返利案例改成 1 分钟口播稿",
  "总结虚假投资理财诈骗的识别信号",
  "比较冒充领导熟人和贷款征信诈骗",
  "推荐适合企业培训的转账诈骗案例",
  "围绕校园贷诈骗设计一个 15 分钟班会任务",
  "把冒充客服案例改写成短视频提醒文案",
  "整理一份面向学生的防骗清单",
  "推荐几个适合以案说法的高风险案例",
  "把养老诈骗案例改成社区海报文案",
  "给刷单返利案例整理中英双语提醒",
  "网络游戏交易诈骗和虚假购物服务有什么区别？",
  "策划一个社区反诈宣传角的内容结构",
];

export function pickSuggestionQueries(count = 6) {
  const pool = [...suggestionQueryPool];
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, Math.max(0, Math.min(count, pool.length)));
}
export const followupQueriesByTask = {
  fact_qa: [
    "这个案例最值得提醒人的风险点是什么？",
    "它和同类骗局最大的区别是什么？",
    "帮我把它改成适合口头提醒的版本",
  ],
  browse_query: [
    "从这些案例里推荐 3 个适合校园宣讲的",
    "把这些案例按风险等级做个比较",
    "帮我从中挑适合社区宣传的案例",
  ],
  comparison: [
    "把这两个骗局整理成对照表",
    "推荐更适合班会讲解的那个",
    "再加入一个同类案例一起比较",
  ],
  recommendation: [
    "基于这些推荐整理一份校园宣讲提纲",
    "给每个推荐案例写一句推荐理由",
    "把推荐结果改成适合播报的提醒稿",
  ],
  exhibition_plan: [
    "把这个方案压缩成 3 分钟宣讲流程",
    "继续补充互动提问和案例讨论",
    "改成适合社区宣传的版本",
  ],
  study_task: [
    "再补 3 个课堂互动问题",
    "改成适合高中生的版本",
    "把这份任务单压缩成 15 分钟班会",
  ],
  content_transform: [
    "再改写一个更年轻化的版本",
    "改成双语传播文案",
    "基于这个案例再推荐几个相关骗局",
  ],
  chitchat: [
    "推荐适合校园宣讲的典型诈骗案例",
    "刷单返利诈骗和虚假投资理财有什么区别？",
    "哪些案例适合做社区反诈宣传？",
  ],
};

export const browserSpeechSupported = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
export const audioSpeechSupported = typeof Audio !== "undefined";
export const speechSupported = browserSpeechSupported || audioSpeechSupported;
export const PROGRESS_STEP_INDEX = {
  classify: 0,
  search: 1,
  generate: 2,
};
export const loadingSteps = [
  { title: "理解问题", label: "理解", detail: "识别骗局类型、宣传目标和上下文指向" },
  { title: "检索案例", label: "检索", detail: "先筛候选案例，必要时再精查细节" },
  { title: "整理结论", label: "整理", detail: "结合案例依据，输出可直接使用的回答" },
];
export const HUMAN_MIN_THINKING_MS = 1120;
export const HUMAN_DISSOLVE_MS = 1180;
export const HUMAN_DISSOLVE_LEAD_MS = 1240;
export const LOADING_MIN_STEP_MS = 500;
