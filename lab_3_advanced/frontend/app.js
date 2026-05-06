"use strict";

const API = {
  base: "/api",

  async request(method, path, body, options = {}) {
    const timeoutMs = options.timeoutMs ?? 15_000;
    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs);

    let res;
    try {
      res = await fetch(`${this.base}${path}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
        signal: timeoutController.signal,
      });
    } catch (err) {
      if (err && err.name === "AbortError") {
        throw new Error(`Request timeout after ${Math.round(timeoutMs / 1000)}s`);
      }
      throw err;
    } finally {
      clearTimeout(timeoutId);
    }

    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = data?.detail || `HTTP ${res.status}`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  },

  listInstances: () => API.request("GET", "/instances"),
  createInstance: (name) => API.request("POST", "/instances", { name }, { timeoutMs: 120_000 }),
  startInstance: (id) => API.request("POST", `/instances/${id}/start`),
  stopInstance: (id) => API.request("POST", `/instances/${id}/stop`),
  deleteInstance: (id) => API.request("DELETE", `/instances/${id}`),
  getDetails: (id) => API.request("GET", `/instances/${id}/details`),
  createBucket: (id, name) => API.request("POST", `/instances/${id}/buckets`, { name }),
  listObjects: (id, bucket) => API.request("GET", `/instances/${id}/buckets/${encodeURIComponent(bucket)}/objects?limit=200`),
  createUploadUrl: (id, bucket, objectName) =>
    API.request("POST", `/instances/${id}/buckets/${encodeURIComponent(bucket)}/presigned-upload`, {
      object_name: objectName,
      expires_seconds: 3600,
    }),
};

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function relativeTime(dateStr) {
  const diff = (Date.now() - new Date(dateStr + "Z").getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(1)} ${units[idx]}`;
}

const svgCopy = () => `
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
  </svg>`;

const svgCheck = () => `
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>`;

const svgEye = () => `
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
  </svg>`;

function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast toast--${type}`;
  el.innerHTML = `<div class="toast-dot"></div><span>${escHtml(message)}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add("removing");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, 3500);
}

async function copyText(text, btn) {
  await navigator.clipboard.writeText(text);
  btn.classList.add("copied");
  btn.innerHTML = svgCheck();
  setTimeout(() => {
    btn.classList.remove("copied");
    btn.innerHTML = svgCopy();
  }, 1800);
}

function renderField(label, value, { secret = false, link = false } = {}) {
  const id = `f_${Math.random().toString(36).slice(2)}`;
  const textClass = secret ? "field-text field-text--secret" : "field-text";
  const display = link
    ? `<a class="field-text" href="${escHtml(value)}" target="_blank" rel="noopener">${escHtml(value)}</a>`
    : `<span class="${textClass}" id="${id}">${escHtml(value)}</span>`;
  const revealBtn = secret
    ? `<button class="btn-copy btn-eye" title="Reveal" data-target="${id}">${svgEye()}</button>`
    : "";
  return `
    <div class="card-field">
      <div class="field-label">${label}</div>
      <div class="field-value">
        ${display}
        ${revealBtn}
        <button class="btn-copy" title="Copy" data-copy="${escHtml(value)}">${svgCopy()}</button>
      </div>
    </div>`;
}

function renderCard(inst) {
  const running = inst.status === "running";
  const stopped = inst.status === "stopped";
  const toggleBtn = running
    ? `<button class="btn btn-ghost btn-sm" data-action="stop" data-id="${inst.id}" data-name="${escHtml(inst.name)}">Stop</button>`
    : stopped
    ? `<button class="btn btn-success btn-sm" data-action="start" data-id="${inst.id}" data-name="${escHtml(inst.name)}">Start</button>`
    : "";
  const bucketText = Number.isInteger(inst.bucket_count) ? `${inst.bucket_count} bucket(s)` : "bucket scan unavailable";

  return `
    <div class="instance-card" data-card-id="${inst.id}">
      <div class="card-header">
        <div class="card-title-row">
          <div class="status-dot status-dot--${inst.status}"></div>
          <span class="card-name">${escHtml(inst.name)}</span>
        </div>
        <span class="status-badge status-badge--${inst.status}">${inst.status}</span>
      </div>
      <div class="card-body">
        ${renderField("S3 API Endpoint", inst.api_endpoint, { link: true })}
        ${renderField("Console", inst.console_endpoint, { link: true })}
        ${renderField("Access Key", inst.access_key)}
        ${renderField("Secret Key", inst.secret_key, { secret: true })}
        <div class="field-label">Monitoring: ${escHtml(bucketText)}</div>
      </div>
      <div class="card-footer">
        <div class="card-footer-left">
          ${toggleBtn}
          <button class="btn btn-ghost btn-sm" data-action="details" data-id="${inst.id}" data-name="${escHtml(inst.name)}" ${running ? "" : "disabled"}>
            Details
          </button>
          <button class="btn btn-danger btn-sm" data-action="delete" data-id="${inst.id}" data-name="${escHtml(inst.name)}">
            Delete
          </button>
        </div>
        <span class="card-meta">${relativeTime(inst.created_at)}</span>
      </div>
    </div>`;
}

const App = {
  instances: [],
  details: { instanceId: null, selectedBucket: null, selectedName: null },

  async init() {
    this.bindNavEvents();
    this.bindModalEvents();
    this.bindDelegated();
    await this.refresh();
    setInterval(() => this.refresh(), 15_000);
  },

  async refresh() {
    try {
      this.instances = await API.listInstances();
      this.renderAll();
    } catch (e) {
      toast(`Failed to load instances: ${e.message}`, "error");
    }
  },

  renderAll() {
    const grid = document.getElementById("instance-grid");
    const empty = document.getElementById("empty-state");

    document.getElementById("stat-total").textContent = this.instances.length;
    document.getElementById("stat-running").textContent = this.instances.filter((i) => i.status === "running").length;
    document.getElementById("stat-stopped").textContent = this.instances.filter((i) => i.status === "stopped").length;
    document.getElementById("stat-buckets").textContent = this.instances.reduce(
      (sum, i) => sum + (Number.isInteger(i.bucket_count) ? i.bucket_count : 0),
      0,
    );

    if (this.instances.length === 0) {
      grid.innerHTML = "";
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    grid.innerHTML = this.instances.map(renderCard).join("");
  },

  openCreateModal() {
    const modal = document.getElementById("modal-create");
    modal.hidden = false;
    modal.style.display = "";
    const input = document.getElementById("input-name");
    input.value = "";
    setTimeout(() => input.focus(), 40);
  },

  closeCreateModal() {
    const modal = document.getElementById("modal-create");
    modal.hidden = true;
    modal.style.display = "none";
  },

  openDetailsModal() {
    const modal = document.getElementById("modal-details");
    modal.hidden = false;
    modal.style.display = "";
  },

  closeDetailsModal() {
    const modal = document.getElementById("modal-details");
    modal.hidden = true;
    modal.style.display = "none";
    this.details.instanceId = null;
    this.details.selectedBucket = null;
    this.details.selectedName = null;
  },

  async submitCreate() {
    const input = document.getElementById("input-name");
    const name = input.value.trim();
    if (!name) return;

    const btn = document.getElementById("btn-modal-submit");
    const label = document.getElementById("btn-submit-label");
    const spinner = document.getElementById("btn-submit-spinner");
    btn.disabled = true;
    label.hidden = true;
    spinner.hidden = false;

    try {
      const inst = await API.createInstance(name);
      this.closeCreateModal();
      toast(`Instance "${inst.name}" created.`, "success");
      await this.refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      btn.disabled = false;
      label.hidden = false;
      spinner.hidden = true;
    }
  },

  async openDetails(id, name) {
    this.details.instanceId = id;
    this.details.selectedBucket = null;
    this.details.selectedName = name;
    document.getElementById("details-title").textContent = `Instance Details — ${name}`;
    document.getElementById("details-summary").innerHTML = `<p class="form-hint">Loading details...</p>`;
    document.getElementById("details-buckets").innerHTML = "";
    document.getElementById("details-objects").innerHTML = "";
    document.getElementById("details-upload-output").textContent = "Select a bucket and generate a presigned upload URL.";
    this.openDetailsModal();

    try {
      const data = await API.getDetails(id);
      this.renderDetails(data);
    } catch (e) {
      document.getElementById("details-summary").innerHTML = `<p class="form-hint">Failed to load: ${escHtml(e.message)}</p>`;
      toast(e.message, "error");
    }
  },

  renderDetails(data) {
    const inst = data.instance;
    document.getElementById("details-summary").innerHTML = `
      ${renderField("Console", inst.console_endpoint, { link: true })}
      ${renderField("S3 API Endpoint", inst.api_endpoint, { link: true })}
      ${renderField("Access Key", inst.access_key)}
      ${renderField("Secret Key", inst.secret_key, { secret: true })}
      <p class="form-hint">${escHtml(data.quick_upload_hint)}</p>
    `;

    if (!data.buckets.length) {
      document.getElementById("details-buckets").innerHTML = `<p class="form-hint">No buckets yet. Create one above.</p>`;
      return;
    }

    document.getElementById("details-buckets").innerHTML = data.buckets.map((b) => `
      <div class="details-item">
        <div>
          <strong>${escHtml(b.name)}</strong>
          <p class="form-hint">${b.objects_count} object(s)</p>
        </div>
        <div class="card-footer-left">
          <button class="btn btn-ghost btn-sm" data-detail-action="objects" data-bucket="${escHtml(b.name)}">Objects</button>
          <button class="btn btn-ghost btn-sm" data-detail-action="select-bucket" data-bucket="${escHtml(b.name)}">Use For Upload</button>
        </div>
      </div>
    `).join("");
  },

  async createBucketFromDetails() {
    if (!this.details.instanceId) return;
    const input = document.getElementById("input-bucket-name");
    const name = input.value.trim();
    if (!name) return;
    try {
      await API.createBucket(this.details.instanceId, name);
      input.value = "";
      toast(`Bucket "${name}" created.`, "success");
      await this.openDetails(this.details.instanceId, this.details.selectedName);
      await this.refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async loadObjects(bucket) {
    if (!this.details.instanceId) return;
    document.getElementById("details-objects").innerHTML = `<p class="form-hint">Loading objects from ${escHtml(bucket)}...</p>`;
    try {
      const objects = await API.listObjects(this.details.instanceId, bucket);
      if (!objects.length) {
        document.getElementById("details-objects").innerHTML = `<p class="form-hint">Bucket is empty.</p>`;
        return;
      }
      document.getElementById("details-objects").innerHTML = objects.map((o) => `
        <div class="details-item">
          <div>
            <strong>${escHtml(o.name)}</strong>
            <p class="form-hint">${formatBytes(o.size)} · ${o.last_modified || "unknown time"}</p>
          </div>
        </div>
      `).join("");
    } catch (e) {
      document.getElementById("details-objects").innerHTML = `<p class="form-hint">Failed to load objects: ${escHtml(e.message)}</p>`;
    }
  },

  async generateUploadUrl() {
    if (!this.details.instanceId) return toast("Open instance details first.", "info");
    if (!this.details.selectedBucket) return toast("Select bucket with 'Use For Upload'.", "info");

    const input = document.getElementById("input-object-name");
    const objectName = input.value.trim() || `uploads/${Date.now()}.bin`;
    try {
      const data = await API.createUploadUrl(this.details.instanceId, this.details.selectedBucket, objectName);
      document.getElementById("details-upload-output").textContent = `${data.upload_url}\n\n${data.curl_example}`;
      toast(`Upload URL generated for ${this.details.selectedBucket}.`, "success");
    } catch (e) {
      document.getElementById("details-upload-output").textContent = `Failed: ${e.message}`;
      toast(e.message, "error");
    }
  },

  async handleAction(action, id, name) {
    const card = document.querySelector(`[data-card-id="${id}"]`);
    switch (action) {
      case "start":
        await API.startInstance(id).then(() => toast(`Instance "${name}" started.`, "success")).catch((e) => toast(e.message, "error"));
        await this.refresh();
        break;
      case "stop":
        await API.stopInstance(id).then(() => toast(`Instance "${name}" stopped.`, "info")).catch((e) => toast(e.message, "error"));
        await this.refresh();
        break;
      case "details":
        await this.openDetails(id, name);
        break;
      case "delete":
        if (!confirm(`Delete instance "${name}"?\n\nThis destroys container and data.`)) return;
        try {
          await API.deleteInstance(id);
          if (card) {
            card.style.opacity = "0";
            await new Promise((r) => setTimeout(r, 180));
          }
          toast(`Instance "${name}" deleted.`, "info");
          await this.refresh();
        } catch (e) {
          toast(e.message, "error");
        }
        break;
    }
  },

  bindNavEvents() {
    const openModal = () => this.openCreateModal();
    document.getElementById("btn-new-instance").addEventListener("click", openModal);
    document.getElementById("btn-new-instance-empty").addEventListener("click", openModal);
    document.getElementById("btn-refresh").addEventListener("click", () => this.refresh());
  },

  bindModalEvents() {
    document.getElementById("btn-modal-close").addEventListener("click", () => this.closeCreateModal());
    document.getElementById("btn-modal-cancel").addEventListener("click", () => this.closeCreateModal());
    document.getElementById("btn-modal-submit").addEventListener("click", () => this.submitCreate());
    document.getElementById("input-name").addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.submitCreate();
    });
    document.getElementById("modal-create").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) this.closeCreateModal();
    });

    document.getElementById("btn-details-close").addEventListener("click", () => this.closeDetailsModal());
    document.getElementById("modal-details").addEventListener("click", (e) => {
      if (e.target === e.currentTarget) this.closeDetailsModal();
    });
    document.getElementById("btn-create-bucket").addEventListener("click", () => this.createBucketFromDetails());
    document.getElementById("btn-generate-upload-url").addEventListener("click", () => this.generateUploadUrl());
  },

  bindDelegated() {
    document.getElementById("instance-grid").addEventListener("click", async (e) => {
      const copyBtn = e.target.closest("[data-copy]");
      if (copyBtn) return copyText(copyBtn.dataset.copy, copyBtn);

      const eyeBtn = e.target.closest(".btn-eye");
      if (eyeBtn) {
        const target = document.getElementById(eyeBtn.dataset.target);
        if (target) target.classList.toggle("revealed");
        return;
      }

      const actionBtn = e.target.closest("[data-action]");
      if (actionBtn) {
        const { action, id, name } = actionBtn.dataset;
        await this.handleAction(action, Number(id), name);
      }
    });

    document.getElementById("modal-details").addEventListener("click", async (e) => {
      const copyBtn = e.target.closest("[data-copy]");
      if (copyBtn) return copyText(copyBtn.dataset.copy, copyBtn);

      const eyeBtn = e.target.closest(".btn-eye");
      if (eyeBtn) {
        const target = document.getElementById(eyeBtn.dataset.target);
        if (target) target.classList.toggle("revealed");
        return;
      }

      const detailBtn = e.target.closest("[data-detail-action]");
      if (!detailBtn) return;
      const bucket = detailBtn.dataset.bucket;
      const action = detailBtn.dataset.detailAction;
      if (action === "objects") await this.loadObjects(bucket);
      if (action === "select-bucket") {
        this.details.selectedBucket = bucket;
        toast(`Selected bucket "${bucket}" for upload API.`, "info");
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        this.closeCreateModal();
        this.closeDetailsModal();
      }
    });
  },
};

document.addEventListener("DOMContentLoaded", () => App.init());
