import { api } from "./api.js";

const state = {
  models: [],
  templates: [],
  history: [],
  results: [],
  selectedModel: "",
  apiKey: "",
  selectedTemplate: null,
  apiBase: "",
  refreshTimer: null,
};

const elements = {
  apiKeyInput: document.getElementById("apiKeyInput"),
  apiBaseInput: document.getElementById("apiBaseInput"),
  authLabel: document.getElementById("authLabel"),
  modelSelect: document.getElementById("modelSelect"),
  activeKeyCount: document.getElementById("activeKeyCount"),
  quotaLabel: document.getElementById("quotaLabel"),
  keyLights: document.getElementById("keyLights"),
  footerModel: document.getElementById("footerModel"),
  footerKey: document.getElementById("footerKey"),
  footerCount: document.getElementById("footerCount"),
  promptInput: document.getElementById("promptInput"),
  countSelect: document.getElementById("countSelect"),
  sizeSelect: document.getElementById("sizeSelect"),
  translateToggle: document.getElementById("translateToggle"),
  generateButton: document.getElementById("generateButton"),
  refreshButton: document.getElementById("refreshButton"),
  templatesButton: document.getElementById("templatesButton"),
  historyButton: document.getElementById("historyButton"),
  requestStatus: document.getElementById("requestStatus"),
  resultsGrid: document.getElementById("resultsGrid"),
  downloadAllButton: document.getElementById("downloadAllButton"),
  copyAllButton: document.getElementById("copyAllButton"),
  clearResultsButton: document.getElementById("clearResultsButton"),
  templatesPanel: document.getElementById("templatesPanel"),
  historyPanel: document.getElementById("historyPanel"),
  templatesList: document.getElementById("templatesList"),
  historyList: document.getElementById("historyList"),
  templateForm: document.getElementById("templateForm"),
  templateId: document.getElementById("templateId"),
  templateName: document.getElementById("templateName"),
  templateCategory: document.getElementById("templateCategory"),
  templateDescription: document.getElementById("templateDescription"),
  templatePreviewImagePath: document.getElementById("templatePreviewImagePath"),
  templateBody: document.getElementById("templateBody"),
  templateResetButton: document.getElementById("templateResetButton"),
  templateVariablesPanel: document.getElementById("templateVariablesPanel"),
  templateVariablesHint: document.getElementById("templateVariablesHint"),
  templateVariablesFields: document.getElementById("templateVariablesFields"),
  clearTemplateSelectionButton: document.getElementById("clearTemplateSelectionButton"),
  resultCardTemplate: document.getElementById("resultCardTemplate"),
};

async function initialize() {
  hydrateApiKey();
  hydrateApiBase();
  bindEvents();
  renderModelPlaceholder("请输入 API Key");
  await refreshAll();
  startAutoRefresh();
}

function bindEvents() {
  elements.generateButton.addEventListener("click", onGenerate);
  elements.refreshButton.addEventListener("click", refreshAll);
  elements.templatesButton.addEventListener("click", () => togglePanel(elements.templatesPanel));
  elements.historyButton.addEventListener("click", () => togglePanel(elements.historyPanel));
  elements.templateResetButton.addEventListener("click", resetTemplateForm);
  elements.modelSelect.addEventListener("change", () => {
    state.selectedModel = elements.modelSelect.value;
    renderModelSummary();
  });
  elements.apiKeyInput.addEventListener("change", async () => {
    state.apiKey = elements.apiKeyInput.value.trim();
    persistApiKey();
    await refreshAll();
  });
  elements.apiBaseInput.addEventListener("change", async () => {
    state.apiBase = elements.apiBaseInput.value.trim();
    persistApiBase();
    await refreshAll();
  });
  elements.downloadAllButton.addEventListener("click", downloadAll);
  elements.copyAllButton.addEventListener("click", copyAll);
  elements.clearTemplateSelectionButton.addEventListener("click", clearSelectedTemplate);
  elements.clearResultsButton.addEventListener("click", () => {
    state.results = [];
    renderResults();
  });

  elements.templateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = {
        name: elements.templateName.value.trim(),
        category: elements.templateCategory.value.trim(),
        description: elements.templateDescription.value.trim(),
        template: elements.templateBody.value.trim(),
        preview_image_path: elements.templatePreviewImagePath.value.trim(),
      };
      if (!payload.name || !payload.template) {
        throw new Error("模板名称和内容不能为空");
      }
      if (elements.templateId.value) {
        await api.updateTemplate(elements.templateId.value, payload);
      } else {
        await api.createTemplate(payload);
      }
      resetTemplateForm();
      await loadTemplates();
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = document.getElementById(button.dataset.close);
      panel.classList.add("hidden");
    });
  });
}

async function refreshAll() {
  if (!state.apiKey) {
    state.models = [];
    state.selectedModel = "";
    renderModelPlaceholder("请输入 API Key");
    setAuthState("empty");
    setStatus("请先输入全局 API Key", true);
    return;
  }
  try {
    setStatus("同步状态中...");
    await Promise.all([loadModels(), loadTemplates(), loadHistory(), loadStats()]);
    setAuthState("valid");
    setStatus("状态已更新");
  } catch (error) {
    if (String(error.message || "").toLowerCase().includes("invalid api key")) {
      state.models = [];
      state.selectedModel = "";
      renderModelPlaceholder("API Key 无效");
      setAuthState("invalid");
      setStatus("API Key 无效，请检查后重试", true);
      return;
    }
    state.models = [];
    state.selectedModel = "";
    renderModelPlaceholder("模型加载失败");
    setStatus(error.message, true);
  }
}

async function refreshStatusSilently() {
  if (!state.apiKey) {
    setAuthState("empty");
    return;
  }
  try {
    await Promise.all([loadModels(), loadStats()]);
    setAuthState("valid");
  } catch (error) {
    if (String(error.message || "").toLowerCase().includes("invalid api key")) {
      setAuthState("invalid");
    }
  }
}

async function loadModels() {
  const payload = await api.getModels();
  state.models = payload.models;
  state.selectedModel = state.selectedModel || payload.default_model || payload.models[0]?.id || "";
  renderModels();
}

async function loadTemplates() {
  const payload = await api.getTemplates();
  state.templates = payload.items;
  renderTemplates();
}

async function loadHistory() {
  const payload = await api.getHistory();
  state.history = payload.items;
  renderHistory();
}

async function loadStats() {
  const payload = await api.getStats();
  elements.footerCount.textContent = String(payload.today_generation_count || 0);
  if (!state.selectedModel || !state.models.length) {
    elements.footerModel.textContent = payload.current_model || "--";
    elements.footerKey.textContent = payload.current_key?.id || payload.current_key_id || "--";
  }
}

function renderModels() {
  elements.modelSelect.innerHTML = "";
  if (!state.models.length) {
    renderModelPlaceholder("暂无可用模型");
    return;
  }
  state.models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.display_name;
    if (model.id === state.selectedModel) {
      option.selected = true;
    }
    elements.modelSelect.append(option);
  });
  renderModelSummary();
}

function renderModelPlaceholder(label) {
  elements.modelSelect.innerHTML = "";
  const option = document.createElement("option");
  option.value = "";
  option.textContent = label;
  option.selected = true;
  elements.modelSelect.append(option);
  elements.activeKeyCount.textContent = "0";
  elements.quotaLabel.textContent = "--";
  elements.footerModel.textContent = "--";
  elements.footerKey.textContent = "--";
  elements.keyLights.innerHTML = "";
}

function renderModelSummary() {
  const model = state.models.find((item) => item.id === state.selectedModel);
  if (!model) {
    return;
  }
  const currentKey = model.current_key || null;
  const retryReady = model.retry_ready_key_count || 0;
  elements.activeKeyCount.textContent = retryReady > 0 ? `${model.active_key_count} + ${retryReady}` : String(model.active_key_count);
  elements.quotaLabel.textContent = computeQuotaLabel(currentKey, model.keys);
  elements.footerModel.textContent = model.display_name;
  elements.footerKey.textContent = currentKey?.id || model.next_key_id || "--";
  elements.keyLights.innerHTML = "";

  model.keys.forEach((key) => {
    const wrapper = document.createElement("span");
    wrapper.className = "light-pill";
    wrapper.innerHTML = `
      <span class="light-dot ${key.status}"></span>
      <span>${key.id}${key.retry_ready ? " · 待重试" : ""}</span>
    `;
    elements.keyLights.append(wrapper);
  });
}

function computeQuotaLabel(currentKey, keys) {
  if (currentKey?.quota_remaining_percent !== null && currentKey?.quota_remaining_percent !== undefined) {
    return `${currentKey.quota_remaining_percent}%`;
  }
  const values = keys.map((item) => item.quota_remaining_percent).filter((value) => value !== null);
  if (!values.length) {
    return "--";
  }
  return `${Math.round(values.reduce((sum, value) => sum + value, 0) / values.length)}%`;
}

function renderTemplates() {
  elements.templatesList.innerHTML = "";
  state.templates.forEach((template) => {
    const card = document.createElement("article");
    card.className = "list-card";
    const preview = template.preview_image_path
      ? `
        <div class="template-preview">
          <img src="${escapeHtml(template.preview_image_path)}" alt="${escapeHtml(template.name)} 预览图" loading="lazy" />
        </div>
      `
      : "";
    card.innerHTML = `
      <div>
        <h3>${escapeHtml(template.name)}</h3>
        <p>${escapeHtml(template.description || "无描述")}</p>
      </div>
      ${preview}
      <div class="tag-row">
        <span class="tag">${escapeHtml(template.category || "未分类")}</span>
        <span class="tag">${escapeHtml(template.template)}</span>
      </div>
      <div class="action-row">
        <button class="primary small" data-action="use">一键使用</button>
        <button class="ghost small" data-action="edit">编辑</button>
        <button class="ghost small danger" data-action="delete">删除</button>
      </div>
    `;
    card.querySelector('[data-action="use"]').addEventListener("click", () => {
      selectTemplateForGeneration(template);
      elements.templatesPanel.classList.add("hidden");
    });
    card.querySelector('[data-action="edit"]').addEventListener("click", () => fillTemplateForm(template));
    card.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      try {
        await api.deleteTemplate(template.id);
        await loadTemplates();
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    elements.templatesList.append(card);
  });
}

function renderHistory() {
  elements.historyList.innerHTML = "";
  state.history.forEach((item) => {
    const card = document.createElement("article");
    card.className = "list-card";
    const image = item.thumbnail
      ? `<img src="${item.thumbnail}" alt="" />`
      : "";
    card.innerHTML = `
      <div>
        <h3>${escapeHtml(item.model)} · ${escapeHtml(item.created_at)}</h3>
        <p>${escapeHtml(item.prompt)}</p>
      </div>
      ${image ? `<div class="history-thumb">${image}</div>` : ""}
      <div class="action-row">
        <button class="primary small" data-action="rerun">重新生成</button>
        <button class="ghost small danger" data-action="delete">删除</button>
      </div>
    `;
    card.querySelector('[data-action="rerun"]').addEventListener("click", async () => {
      try {
        clearSelectedTemplate();
        state.selectedModel = item.model;
        elements.modelSelect.value = item.model;
        elements.promptInput.value = item.prompt;
        elements.countSelect.value = String(item.n || 1);
        elements.sizeSelect.value = item.size || "1024x1024";
        elements.generateButton.disabled = true;
        setStatus("根据历史记录重新生成中...");
        const payload = await api.regenerateHistory(item.id, {
          model: item.model,
          auto_translate: elements.translateToggle.checked,
        });
        state.results = payload.data;
        renderResults();
        await Promise.all([loadModels(), loadHistory(), loadStats()]);
        setStatus(`重新生成完成，使用 Key ${payload.key_id}`);
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        elements.generateButton.disabled = false;
      }
    });
    card.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      try {
        await api.deleteHistory(item.id);
        await loadHistory();
        await loadStats();
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    elements.historyList.append(card);
  });
}

function renderResults() {
  elements.resultsGrid.innerHTML = "";
  elements.resultsGrid.classList.toggle("empty", state.results.length === 0);
  if (!state.results.length) {
    elements.resultsGrid.innerHTML = `
      <div class="empty-state">
        <p>生成结果会显示在这里。</p>
        <span>支持最多 4 张图片并排预览与下载。</span>
      </div>
    `;
    return;
  }

  state.results.forEach((result, index) => {
    const node = elements.resultCardTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector("img").src = result.url;
    node.querySelector('[data-action="download"]').addEventListener("click", () => downloadFile(result.url));
    node.querySelector('[data-action="copy"]').addEventListener("click", async () => {
      await navigator.clipboard.writeText(result.url);
      setStatus("链接已复制");
    });
    node.querySelector('[data-action="remove"]').addEventListener("click", () => {
      state.results.splice(index, 1);
      renderResults();
    });
    elements.resultsGrid.append(node);
  });
}

async function onGenerate() {
  const prompt = elements.promptInput.value.trim();
  if (!prompt && !state.selectedTemplate) {
    setStatus("请输入 Prompt", true);
    return;
  }
  try {
    elements.generateButton.disabled = true;
    setStatus("生成中...");
    const payload = await api.generateImage({
      model: state.selectedModel,
      prompt,
      n: Number(elements.countSelect.value),
      size: elements.sizeSelect.value,
      auto_translate: elements.translateToggle.checked,
      template_id: state.selectedTemplate?.id || null,
      variables: collectTemplateVariables(),
    });
    state.results = payload.data;
    renderResults();
    await Promise.all([loadModels(), loadHistory(), loadStats()]);
    setStatus(`生成完成，使用 Key ${payload.key_id}`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    elements.generateButton.disabled = false;
  }
}

function fillTemplateForm(template) {
  elements.templateId.value = template.id;
  elements.templateName.value = template.name;
  elements.templateCategory.value = template.category || "";
  elements.templateDescription.value = template.description || "";
  elements.templatePreviewImagePath.value = template.preview_image_path || "";
  elements.templateBody.value = template.template;
  elements.templatesPanel.classList.remove("hidden");
}

function resetTemplateForm() {
  elements.templateId.value = "";
  elements.templateName.value = "";
  elements.templateCategory.value = "";
  elements.templateDescription.value = "";
  elements.templatePreviewImagePath.value = "";
  elements.templateBody.value = "";
}

function selectTemplateForGeneration(template) {
  state.selectedTemplate = template;
  elements.promptInput.value = "";
  renderTemplateVariables();
}

function clearSelectedTemplate() {
  state.selectedTemplate = null;
  renderTemplateVariables();
}

function renderTemplateVariables() {
  const template = state.selectedTemplate;
  elements.templateVariablesFields.innerHTML = "";
  if (!template) {
    elements.templateVariablesPanel.classList.add("hidden");
    elements.templateVariablesHint.textContent = "";
    return;
  }
  elements.templateVariablesPanel.classList.remove("hidden");
  const variables = Array.isArray(template.variables) ? template.variables : [];
  elements.templateVariablesHint.textContent = variables.length
    ? `当前模板：${template.name}。请填写以下变量后生成。`
    : `当前模板：${template.name}。该模板不需要额外变量。`;
  variables.forEach((variable) => {
    const label = document.createElement("label");
    label.className = "field compact";
    const safeName = escapeHtml(variable);
    label.innerHTML = `
      <span>${safeName}</span>
      <input type="text" data-template-variable="${safeName}" placeholder="输入 ${safeName}" />
    `;
    elements.templateVariablesFields.append(label);
  });
}

function collectTemplateVariables() {
  const payload = {};
  elements.templateVariablesFields.querySelectorAll("[data-template-variable]").forEach((input) => {
    payload[input.dataset.templateVariable] = input.value.trim();
  });
  return payload;
}

function togglePanel(panel) {
  panel.classList.toggle("hidden");
}

function startAutoRefresh() {
  if (state.refreshTimer !== null) {
    window.clearInterval(state.refreshTimer);
  }
  state.refreshTimer = window.setInterval(() => {
    void refreshStatusSilently();
  }, 30000);
}

function hydrateApiKey() {
  state.apiKey = localStorage.getItem("imagegen-pro-api-key") || "";
  elements.apiKeyInput.value = state.apiKey;
  api.setApiKey(state.apiKey);
}

function hydrateApiBase() {
  state.apiBase = localStorage.getItem("imagegen-pro-api-base") || api.getApiBase();
  elements.apiBaseInput.value = state.apiBase;
  api.setApiBase(state.apiBase);
}

function persistApiKey() {
  localStorage.setItem("imagegen-pro-api-key", state.apiKey);
  api.setApiKey(state.apiKey);
}

function persistApiBase() {
  localStorage.setItem("imagegen-pro-api-base", state.apiBase);
  api.setApiBase(state.apiBase);
}

function setStatus(message, isError = false) {
  elements.requestStatus.textContent = message;
  elements.requestStatus.style.color = isError ? "var(--red)" : "";
}

function setAuthState(status) {
  if (status === "valid") {
    elements.authLabel.textContent = "已验证";
    elements.authLabel.style.color = "var(--green)";
    return;
  }
  if (status === "empty") {
    elements.authLabel.textContent = "待输入";
    elements.authLabel.style.color = "";
    return;
  }
  elements.authLabel.textContent = "认证失败";
  elements.authLabel.style.color = "var(--red)";
}

function downloadAll() {
  state.results.forEach((item) => downloadFile(item.url));
}

async function copyAll() {
  if (!state.results.length) {
    return;
  }
  await navigator.clipboard.writeText(state.results.map((item) => item.url).join("\n"));
  setStatus("已复制全部链接");
}

function downloadFile(url) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "";
  anchor.rel = "noopener";
  anchor.click();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

initialize();
