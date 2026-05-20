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

function currentSearchCriteria() {
  const query = els.rightSearchInput?.value?.trim() || "";
  const category = els.filterCategory?.value?.trim() || "";
  const riskLevel = els.filterRiskLevel?.value?.trim() || "";
  const entryChannel = els.filterEntryChannel?.value?.trim() || "";
  state.searchFilters = { category, riskLevel, entryChannel };
  return { query, category, riskLevel, entryChannel };
}

function buildSearchParams() {
  const { query, category, riskLevel, entryChannel } = currentSearchCriteria();
  const params = new URLSearchParams({ limit: "1000" });
  if (query) params.set("q", query);
  if (category) params.set("category", category);
  if (riskLevel) params.set("risk_level", riskLevel);
  if (entryChannel) params.set("entry_channel", entryChannel);
  return params;
}

export async function loadRightSearchResults(requestKey, paramsString = requestKey) {
  try {
    const data = await fetchJson(`/api/items?${paramsString}`);
    if (requestKey !== rightSearchRequestKey) return;
    renderRelatedItems(data.items, data.total);
  } catch {
    if (requestKey === rightSearchRequestKey) {
      renderRelatedItems([]);
    }
  }
}

export function searchRightPanel() {
  const params = buildSearchParams();
  const requestKey = params.toString();
  rightSearchRequestKey = requestKey;
  els.relatedCount.textContent = "查询中";
  els.relatedList.innerHTML = `<p class="marginalia-empty is-live">正在查询</p>`;
  loadRightSearchResults(requestKey, requestKey);
}

export async function loadInitialRandomItems() {
  const requestKey = "initial-random";
  rightSearchRequestKey = requestKey;
  els.relatedCount.textContent = "加载中";
  els.relatedList.innerHTML = `<p class="marginalia-empty is-live">正在加载案例</p>`;
  try {
    const data = await fetchJson("/api/items?limit=1000");
    if (requestKey !== rightSearchRequestKey) return;
    renderRelatedItems(shuffleItems(data.items), data.total);
  } catch {
    if (requestKey === rightSearchRequestKey) {
      renderRelatedItems([]);
    }
  }
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

export function populateSearchFilters(meta) {
  const preserve = currentSearchCriteria();
  populateSelect(
    els.filterCategory,
    "全部分类",
    (meta?.categories || []).map((category) => category.name),
    preserve.category,
  );
  populateSelect(
    els.filterRiskLevel,
    "全部等级",
    meta?.risk_levels || [],
    preserve.riskLevel,
  );
  populateSelect(
    els.filterEntryChannel,
    "全部渠道",
    meta?.entry_channels || [],
    preserve.entryChannel,
  );
}

function populateSelect(select, defaultLabel, values, selectedValue = "") {
  if (!select) return;
  const options = [`<option value="">${escapeHtml(defaultLabel)}</option>`];
  for (const value of values) {
    const selected = value === selectedValue ? " selected" : "";
    options.push(`<option value="${escapeHtml(value)}"${selected}>${escapeHtml(value)}</option>`);
  }
  select.innerHTML = options.join("");
}

function shuffleItems(items) {
  const shuffled = [...items];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}
