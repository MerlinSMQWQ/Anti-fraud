import { state, els } from './state.js';
import { escapeHtml } from './markdown.js';

let rightSearchRequestKey = "";

export function beginAskSessionRelated(requestId) {
  rightSearchRequestKey = `ask:${requestId}`;
}

export async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export function itemTitle(item) {
  return item?.title || "未命名案例";
}

export function itemMetaParts(item, opts = {}) {
  const parts = [];
  const fields = [item?.ccl2023_category, item?.custom_subcategory];
  if (!opts.skipLevel) fields.push(item?.risk_level);
  for (const value of fields) {
    if (value && !parts.includes(value)) parts.push(value);
  }
  return parts;
}

export function itemTagList(item, limit = 4) {
  const tags = [];
  for (const value of [...(item?.tags || []), ...(item?.entry_channels || [])]) {
    if (value && !tags.includes(value)) tags.push(value);
    if (tags.length >= limit) break;
  }
  return tags;
}

export async function loadRightSearchResults(requestKey) {
  const query = els.rightSearchInput?.value?.trim() || "";
  const params = new URLSearchParams({ q: query, limit: "1000" });
  try {
    const data = await fetchJson(`/api/items?${params}`);
    if (requestKey !== rightSearchRequestKey) return;
    renderRelatedItems(data.items, data.total);
  } catch {
    if (requestKey === rightSearchRequestKey) {
      renderRelatedItems([]);
    }
  }
}

export function searchRightPanel() {
  const query = els.rightSearchInput?.value?.trim() || "";
  if (!query) {
    renderRelatedItems([]);
    return;
  }
  const requestKey = query;
  rightSearchRequestKey = requestKey;
  els.relatedCount.textContent = "检索中";
  els.relatedList.innerHTML = `<p class="marginalia-empty is-live">正在检索</p>`;
  loadRightSearchResults(requestKey);
}

export function renderRelatedItems(items, total = items.length) {
  els.relatedCount.textContent = total ? `${total} 条` : "";
  els.relatedList.innerHTML = items.length
    ? items.map(itemButtonHtml).join("")
    : `<p class="marginalia-empty">没有匹配案例</p>`;
  // Click handler for items in the list
  els.relatedList.querySelectorAll(".item-entry[data-id]").forEach((el) => {
    el.addEventListener("click", () => showDetail(el.dataset.id));
  });
}

export function itemButtonHtml(item) {
  const summary = item.summary || "暂无摘要";
  const meta = itemMetaParts(item).join(" · ");
  const tags = itemTagList(item, 4);
  const title = itemTitle(item);
  return `
    <div class="item-entry" data-id="${escapeHtml(item.id)}" data-category="${escapeHtml(item.ccl2023_category || "")}">
      <div class="item-entry-head">
        <div class="item-entry-title">${escapeHtml(title)}</div>
      </div>
      ${meta ? `<div class="item-entry-meta">${escapeHtml(meta)}</div>` : ""}
      <div class="item-entry-summary">${escapeHtml(summary.slice(0, 74))}</div>
      ${tags.length ? `<div class="item-entry-tags">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
    </div>
  `;
}

export async function showDetail(id) {
  try {
    const item = await fetchJson(`/api/items/${encodeURIComponent(id)}`);
    els.detailCategory.textContent = item.ccl2023_category || "";
    els.detailTitle.textContent = itemTitle(item);
    els.detailMeta.innerHTML = detailMetaHtml(item);
    const support = detailSupportText(item);
    els.detailSupport.hidden = !support;
    els.detailSupport.textContent = support;
    els.detailBody.textContent = item.content || "暂无原文。";
    els.searchMode.hidden = true;
    els.detailMode.hidden = false;
  } catch {
    // silently fail if item not found
  }
}

export function hideDetail() {
  els.detailMode.hidden = true;
  els.searchMode.hidden = false;
  els.detailCategory.textContent = "";
  els.detailTitle.textContent = "";
  els.detailMeta.innerHTML = "";
  els.detailSupport.hidden = true;
  els.detailBody.textContent = "";
}

function detailMetaHtml(item) {
  const parts = [];
  for (const value of [item?.ccl2023_category, item?.custom_subcategory, item?.risk_level]) {
    if (value && !parts.includes(value)) parts.push(value);
  }
  return parts.map((p) => `<span>${escapeHtml(p)}</span>`).join("");
}

function detailSupportText(item) {
  if (item?.victim_group) {
    return `受害群体：${item.victim_group}`;
  }
  if (item?.source_name) {
    return `来源：${item.source_name}`;
  }
  return "";
}

export function relatedPanelTitle() {
  return "案例检索";
}

export function updateRelatedPanelTitle() {
  if (els.relatedTitle) {
    els.relatedTitle.textContent = "案例检索";
  }
}
