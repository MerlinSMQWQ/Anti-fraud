import { els } from './state.js';
import { stripMarkdown } from './markdown.js';

let humanIdleTimer = 0;
export let currentHumanState = "idle";

export function initHuman() {
  els.digitalHumanPanel.dataset.state = "idle";
}

export function setDigitalHumanState(stateName, status, speech = "") {
  window.clearTimeout(humanIdleTimer);
  currentHumanState = stateName;
  els.digitalHumanPanel.dataset.state = stateName;
  els.digitalHumanStatus.textContent = status;
  els.digitalHumanSpeech.textContent = digitalHumanCaption(stateName, status, speech);
}

export function responseHumanState(query) {
  const farewellTerms = ["谢谢", "感谢", "辛苦了", "再见", "拜拜", "下次见"];
  return farewellTerms.some((term) => query.includes(term)) ? "farewell" : "speaking";
}

export function waitForThinkingDissolve(startedAt) {
  // With static image, no dissolve animation needed
  return Promise.resolve();
}

export function scheduleHumanReturnToIdle(delayMs) {
  window.clearTimeout(humanIdleTimer);
  humanIdleTimer = window.setTimeout(() => {
    if (currentHumanState === "speaking" || currentHumanState === "farewell") {
      setDigitalHumanState("idle", "待机", "我在这里，可以继续问我。");
    }
  }, delayMs);
}

export function visualAnswerDuration(text) {
  const length = stripMarkdown(text).length;
  return Math.min(22000, Math.max(7500, 3600 + length * 90));
}

export function digitalHumanCaption(stateName, status, fallback = "") {
  const captions = {
    idle: "我在这里，可以继续问我。",
    thinking: "我先从资料库里找和问题最相关的内容。",
    speaking: "正在为你讲述。",
    farewell: "期待下次再见。",
  };
  if (status === "出现错误") {
    return "刚才没有答好，请再试一次。";
  }
  return captions[stateName] || fallback || "我在这里。";
}
