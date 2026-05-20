export const state = {
  query: "",
  selectedId: "",
  currentTaskType: "",
  lastAskContext: null,
  sessionId: "",
  searchFilters: {
    category: "",
    riskLevel: "",
    entryChannel: "",
  },
};

export const els = {};

export function bindElements(map) {
  Object.assign(els, map);
}
