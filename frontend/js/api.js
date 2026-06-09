const JSON_HEADERS = {
  "Content-Type": "application/json",
};

let globalApiKey = "";
let apiBase = resolveInitialApiBase();

function resolveInitialApiBase() {
  const meta = document.querySelector('meta[name="imagegen-api-base"]');
  const metaValue = meta?.getAttribute("content")?.trim();
  if (metaValue) {
    return metaValue.replace(/\/$/, "");
  }

  if (window.location.protocol.startsWith("http")) {
    const path = window.location.pathname || "";
    if (path.startsWith("/ui")) {
      return window.location.origin;
    }
  }

  return "http://localhost:8000";
}

function buildHeaders(headers = {}) {
  return {
    ...JSON_HEADERS,
    ...(globalApiKey ? { "X-API-Key": globalApiKey } : {}),
    ...headers,
  };
}

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: buildHeaders(options.headers),
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || JSON.stringify(payload);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || "请求失败");
  }

  return response.json();
}

export const api = {
  setApiKey(key) {
    globalApiKey = key || "";
  },
  setApiBase(base) {
    apiBase = (base || "").trim().replace(/\/$/, "") || resolveInitialApiBase();
  },
  getApiBase() {
    return apiBase;
  },
  getModels() {
    return request("/api/models", { method: "GET" });
  },
  getStats() {
    return request("/api/stats", { method: "GET" });
  },
  getHealth() {
    return request("/api/health", { method: "GET" });
  },
  generateImage(payload) {
    return request("/api/images/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getTemplates() {
    return request("/api/templates", { method: "GET" });
  },
  createTemplate(payload) {
    return request("/api/templates", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  updateTemplate(id, payload) {
    return request(`/api/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  deleteTemplate(id) {
    return request(`/api/templates/${id}`, { method: "DELETE" });
  },
  getHistory() {
    return request("/api/history", { method: "GET" });
  },
  regenerateHistory(id, payload) {
    return request(`/api/history/${id}/regenerate`, {
      method: "POST",
      body: JSON.stringify(payload || {}),
    });
  },
  deleteHistory(id) {
    return request(`/api/history/${id}`, { method: "DELETE" });
  },
};
