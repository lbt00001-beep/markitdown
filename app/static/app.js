const state = {
  mode: "files",
  latestJobId: null,
  latestBatchUrl: null,
  latestMarkdown: "",
  batchJobs: [],
  batchInfo: null,
};

const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => [...document.querySelectorAll(selector)];

const elements = {
  fileForm: qs("#fileForm"),
  urlForm: qs("#urlForm"),
  textForm: qs("#textForm"),
  uriForm: qs("#uriForm"),
  fileInput: qs("#fileInput"),
  selectedFiles: qs("#selectedFiles"),
  dropZone: qs(".drop-zone"),
  markdownOutput: qs("#markdownOutput"),
  resultMeta: qs("#resultMeta"),
  downloadMarkdown: qs("#downloadMarkdown"),
  downloadPdf: qs("#downloadPdf"),
  downloadBatch: qs("#downloadBatch"),
  batchSelector: qs("#batchSelector"),
  batchResultSelect: qs("#batchResultSelect"),
  copyMarkdown: qs("#copyMarkdown"),
  historyList: qs("#historyList"),
  formatsGrid: qs("#formatsGrid"),
  toast: qs("#toast"),
};

function toast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.setTimeout(() => elements.toast.classList.remove("show"), 2600);
}

function collectOptions(formData) {
  formData.set("enable_builtins", qs("#enableBuiltins").checked ? "true" : "false");
  formData.set("enable_plugins", qs("#enablePlugins").checked ? "true" : "false");
  formData.set("strict_html", qs("#strictHtml").checked ? "true" : "false");
  formData.set("keep_data_uris", qs("#keepDataUris").checked ? "true" : "false");
  formData.set("use_llm", qs("#useLlm").checked ? "true" : "false");
  formData.set("openai_api_key", qs("#openaiApiKey").value.trim());
  formData.set("openai_base_url", qs("#openaiBaseUrl").value.trim());
  formData.set("llm_model", qs("#llmModel").value.trim());
  formData.set("llm_prompt", qs("#llmPrompt").value.trim());
  formData.set("extension_hint", qs("#extensionHint").value.trim());
  formData.set("mime_type_hint", qs("#mimeTypeHint").value.trim());
  formData.set("charset_hint", qs("#charsetHint").value.trim());
  formData.set("exiftool_path", qs("#exiftoolPath").value.trim());
  formData.set("style_map", qs("#styleMap").value.trim());
  formData.set("azure_api_key", qs("#azureApiKey").value.trim());
  formData.set("docintel_endpoint", qs("#docintelEndpoint").value.trim());
  formData.set("docintel_api_version", qs("#docintelApiVersion").value.trim());
  formData.set("docintel_file_types", qs("#docintelFileTypes").value.trim());
  formData.set("cu_endpoint", qs("#cuEndpoint").value.trim());
  formData.set("cu_analyzer_id", qs("#cuAnalyzerId").value.trim());
  formData.set("cu_file_types", qs("#cuFileTypes").value.trim());
  return formData;
}

function setBusy(form, busy) {
  qsa("button").forEach((button) => {
    if (button.closest("form") === form || button.classList.contains("segment")) {
      button.disabled = busy;
    }
  });
}

function updatePreview(markdown, job, batch = null) {
  state.latestMarkdown = markdown || "";
  state.latestJobId = job?.id || null;
  state.latestBatchUrl = batch?.downloadUrl || null;
  elements.markdownOutput.textContent = markdown || "No se ha generado contenido Markdown.";
  if (job) {
    const status = job.status === "completed" ? "completado" : "fallido";
    const batchText =
      batch && batch.total > 1
        ? ` - mostrando el ultimo de ${batch.total}; ${batch.completed} completado(s)`
        : "";
    elements.resultMeta.textContent = `${job.source_name} - ${status} - ${job.markdown_chars} caracteres - ${job.duration_ms} ms${batchText}`;
  }
  if (state.latestJobId && job?.status === "completed") {
    elements.downloadMarkdown.href = `/api/jobs/${state.latestJobId}/download`;
    elements.downloadMarkdown.classList.remove("disabled");
    elements.downloadPdf.href = `/api/jobs/${state.latestJobId}/pdf`;
    elements.downloadPdf.classList.remove("disabled");
  } else {
    elements.downloadMarkdown.removeAttribute("href");
    elements.downloadMarkdown.classList.add("disabled");
    elements.downloadPdf.removeAttribute("href");
    elements.downloadPdf.classList.add("disabled");
  }

  if (state.latestBatchUrl) {
    elements.downloadBatch.href = state.latestBatchUrl;
    elements.downloadBatch.classList.remove("disabled");
  } else {
    elements.downloadBatch.removeAttribute("href");
    elements.downloadBatch.classList.add("disabled");
  }
}

function renderBatchSelector(jobs = [], selectedId = null) {
  state.batchJobs = jobs;
  elements.batchResultSelect.replaceChildren();
  elements.batchSelector.classList.toggle("hidden", jobs.length < 2);

  jobs.forEach((job, index) => {
    const option = document.createElement("option");
    option.value = job.id;
    option.disabled = job.status !== "completed";
    option.textContent = `${index + 1}. ${job.source_name} - ${job.status === "completed" ? "completado" : "fallido"}`;
    option.selected = job.id === selectedId;
    elements.batchResultSelect.appendChild(option);
  });
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "La solicitud no se pudo completar.");
  }
  return payload;
}

async function requestText(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "No se pudo abrir ese resultado.");
  }
  return response.text();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadHealth() {
  try {
    const health = await requestJson("/api/health");
    qs("#healthMarkitdown").textContent = health.markitdown_available ? "Listo" : "Pendiente";
    qs("#healthOpenai").textContent = health.openai_key_available ? "Clave activa" : "Opcional";
    qs("#healthAzure").textContent =
      health.azure_docintel_endpoint_available || health.azure_cu_endpoint_available ? "Endpoint activo" : "Opcional";
  } catch {
    qs("#healthMarkitdown").textContent = "Error";
  }
}

async function loadFormats() {
  const payload = await requestJson("/api/formats");
  elements.formatsGrid.innerHTML = payload.groups
    .map(
      (group) => `
        <article class="format-card">
          <strong>${group.name}</strong>
          <p>${group.description}</p>
          <div class="tag-row">
            ${group.extensions.map((extension) => `<span class="tag">${escapeHtml(extension)}</span>`).join("")}
          </div>
        </article>
      `,
    )
    .join("");
}

async function loadPlugins() {
  const payload = await requestJson("/api/plugins");
  const pluginText = payload.plugins.length
    ? payload.plugins.map((plugin) => `${plugin.name} (${plugin.value})`).join(", ")
    : "No hay plugins de terceros instalados.";
  const helpIntro = qs(".help-intro");
  if (helpIntro && !qs("#pluginSummary")) {
    const paragraph = document.createElement("p");
    paragraph.id = "pluginSummary";
    paragraph.textContent = `Plugins detectados: ${pluginText}`;
    helpIntro.appendChild(paragraph);
  }
}

async function loadHistory() {
  const payload = await requestJson("/api/jobs");
  if (!payload.jobs.length) {
    elements.historyList.innerHTML = '<article class="history-item"><p class="history-title">Aun no hay trabajos.</p></article>';
    return;
  }
  elements.historyList.innerHTML = payload.jobs
    .map((job) => {
      const badgeClass = job.status === "failed" ? "status-badge failed" : "status-badge";
      const action =
        job.status === "completed"
          ? `<a class="icon-button" href="/api/jobs/${job.id}/download" title="Descargar" aria-label="Descargar">D</a>`
          : "";
      return `
        <article class="history-item">
          <div>
            <p class="history-title">${escapeHtml(job.source_name)}</p>
            <p class="history-meta">${escapeHtml(job.source_type)} - ${job.markdown_chars} caracteres - ${job.duration_ms} ms ${
              job.batch_id ? "- lote " + escapeHtml(job.batch_id) : ""
            } ${job.error ? "- " + escapeHtml(job.error) : ""
            }</p>
          </div>
          <div class="preview-actions">
            <span class="${badgeClass}">${job.status === "completed" ? "Completado" : "Fallido"}</span>
            ${action}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderSelectedFiles() {
  const files = [...elements.fileInput.files];
  if (!files.length) {
    elements.selectedFiles.innerHTML = "";
    return;
  }
  elements.selectedFiles.innerHTML = files
    .map((file) => `<div class="file-pill"><span>${escapeHtml(file.name)}</span><span>${Math.ceil(file.size / 1024)} KB</span></div>`)
    .join("");
}

qsa(".nav-tab").forEach((button) => {
  button.addEventListener("click", () => {
    qsa(".nav-tab").forEach((item) => item.classList.remove("active"));
    qsa(".view").forEach((view) => view.classList.remove("active"));
    button.classList.add("active");
    qs(`#view-${button.dataset.view}`).classList.add("active");
    if (button.dataset.view === "history") loadHistory();
    if (button.dataset.view === "formats") loadFormats();
    if (button.dataset.view === "help") loadPlugins();
  });
});

qsa(".segment").forEach((button) => {
  button.addEventListener("click", () => {
    state.mode = button.dataset.mode;
    qsa(".segment").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    elements.fileForm.classList.toggle("hidden", state.mode !== "files");
    elements.urlForm.classList.toggle("hidden", state.mode !== "url");
    elements.textForm.classList.toggle("hidden", state.mode !== "text");
    elements.uriForm.classList.toggle("hidden", state.mode !== "uri");
  });
});

elements.fileInput.addEventListener("change", renderSelectedFiles);

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("dragging");
  });
});

elements.dropZone.addEventListener("drop", (event) => {
  elements.fileInput.files = event.dataTransfer.files;
  renderSelectedFiles();
});

elements.fileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.fileInput.files.length) {
    toast("Selecciona al menos un archivo.");
    return;
  }

  const formData = collectOptions(new FormData(elements.fileForm));
  setBusy(elements.fileForm, true);
  try {
    const payload = await requestJson("/api/convert/files", { method: "POST", body: formData });
    const latestJob = [...payload.jobs].reverse().find((job) => job.status === "completed") || payload.jobs.at(-1);
    state.batchInfo = {
      total: payload.jobs.length,
      completed: payload.completed_count,
      downloadUrl: payload.batch_download_url,
    };
    renderBatchSelector(payload.jobs, latestJob?.id);
    updatePreview(payload.markdown, latestJob, state.batchInfo);
    await loadHistory();
    toast(`Conversion completada: ${payload.completed_count} de ${payload.jobs.length} trabajo(s).`);
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(elements.fileForm, false);
  }
});

elements.urlForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = collectOptions(new FormData(elements.urlForm));
  setBusy(elements.urlForm, true);
  try {
    const payload = await requestJson("/api/convert/url", { method: "POST", body: formData });
    state.batchInfo = null;
    renderBatchSelector();
    updatePreview(payload.markdown, payload.job);
    await loadHistory();
    toast("URL convertida.");
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(elements.urlForm, false);
  }
});

elements.textForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!qs("#textInput").value.trim()) {
    toast("Pega algun contenido para convertir.");
    return;
  }
  const formData = collectOptions(new FormData(elements.textForm));
  setBusy(elements.textForm, true);
  try {
    const payload = await requestJson("/api/convert/text", { method: "POST", body: formData });
    state.batchInfo = null;
    renderBatchSelector();
    updatePreview(payload.markdown, payload.job);
    await loadHistory();
    toast("Texto convertido.");
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(elements.textForm, false);
  }
});

elements.uriForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!qs("#uriInput").value.trim()) {
    toast("Introduce una URI.");
    return;
  }
  const formData = collectOptions(new FormData(elements.uriForm));
  formData.set("allow_file_uri", qs("#allowFileUri").checked ? "true" : "false");
  setBusy(elements.uriForm, true);
  try {
    const payload = await requestJson("/api/convert/uri", { method: "POST", body: formData });
    state.batchInfo = null;
    renderBatchSelector();
    updatePreview(payload.markdown, payload.job);
    await loadHistory();
    toast("URI convertida.");
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(elements.uriForm, false);
  }
});

elements.batchResultSelect.addEventListener("change", async () => {
  const job = state.batchJobs.find((item) => item.id === elements.batchResultSelect.value);
  if (!job || job.status !== "completed") return;

  try {
    const markdown = await requestText(`/api/jobs/${job.id}/raw`);
    updatePreview(markdown, job, state.batchInfo);
  } catch (error) {
    toast(error.message);
  }
});

elements.copyMarkdown.addEventListener("click", async () => {
  if (!state.latestMarkdown) {
    toast("No hay Markdown para copiar.");
    return;
  }
  await navigator.clipboard.writeText(state.latestMarkdown);
  toast("Markdown copiado.");
});

qs("#refreshJobs").addEventListener("click", async () => {
  await loadHistory();
  toast("Historial actualizado.");
});

loadHealth();
loadFormats();
loadHistory();
