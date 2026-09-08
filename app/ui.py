"""Single-file HTML/CSS/JS frontend dashboard for Document Intelligence pipeline."""

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Document Intelligence Dashboard</title>
  <style>
    :root {
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --border: #e2e8f0;
      --success: #16a34a;
      --warning: #d97706;
      --danger: #dc2626;
      --invoice-badge: #e0e7ff;
      --invoice-text: #3730a3;
      --resume-badge: #dcfce7;
      --resume-text: #166534;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }

    .container {
      max-width: 1080px;
      margin: 0 auto;
    }

    header {
      margin-bottom: 24px;
    }

    header h1 {
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 4px;
    }

    header p {
      color: var(--text-muted);
      font-size: 0.95rem;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }

    .card h2 {
      font-size: 1.15rem;
      font-weight: 600;
      margin-bottom: 14px;
    }

    .upload-form {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }

    input[type="file"] {
      padding: 8px;
      border: 1px dashed var(--border);
      border-radius: 6px;
      background: #fdfdfd;
      font-size: 0.9rem;
      flex: 1;
      min-width: 240px;
    }

    button, select {
      font-family: inherit;
      font-size: 0.9rem;
      padding: 9px 16px;
      border-radius: 6px;
      border: 1px solid var(--border);
      cursor: pointer;
      transition: all 0.15s ease;
    }

    button.btn-primary {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
      font-weight: 500;
    }

    button.btn-primary:hover:not(:disabled) {
      background: var(--primary-hover);
    }

    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .status-msg {
      margin-top: 12px;
      font-size: 0.9rem;
      display: none;
      padding: 8px 12px;
      border-radius: 6px;
    }

    .status-msg.info { display: block; background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
    .status-msg.success { display: block; background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
    .status-msg.error { display: block; background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      gap: 12px;
      flex-wrap: wrap;
    }

    .toolbar-left {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .badge {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .badge-invoice { background: var(--invoice-badge); color: var(--invoice-text); }
    .badge-resume { background: var(--resume-badge); color: var(--resume-text); }
    .badge-unknown { background: #f1f5f9; color: #475569; }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      text-align: left;
    }

    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
    }

    th {
      background-color: #f8fafc;
      font-weight: 600;
      color: var(--text-muted);
      border-top: 1px solid var(--border);
    }

    tr:hover td {
      background-color: #fbfcfe;
    }

    .empty-state {
      text-align: center;
      padding: 40px 16px;
      color: var(--text-muted);
      font-size: 0.95rem;
    }

    .json-details {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.8rem;
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 8px;
      margin-top: 6px;
      max-height: 200px;
      overflow-y: auto;
      white-space: pre-wrap;
    }

    .link-toggle {
      color: var(--primary);
      text-decoration: none;
      font-size: 0.8rem;
      cursor: pointer;
      display: inline-block;
      margin-top: 4px;
    }
    .link-toggle:hover { text-decoration: underline; }

    .link-danger {
      color: var(--danger);
      text-decoration: none;
      font-size: 0.8rem;
      cursor: pointer;
      display: inline-block;
      margin-top: 4px;
    }
    .link-danger:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Document Intelligence Pipeline</h1>
      <p>Upload invoices and resumes to extract structured business fields and retrieve document records.</p>
    </header>

    <!-- Upload Section -->
    <div class="card">
      <h2>Upload Document</h2>
      <form id="uploadForm" class="upload-form">
        <input type="file" id="fileInput" name="file" accept=".pdf,.docx,.png,.jpg,.jpeg" required />
        <button type="submit" id="submitBtn" class="btn-primary">Upload & Process</button>
      </form>
      <div id="statusMsg" class="status-msg"></div>
    </div>

    <!-- Documents Explorer -->
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <label for="docTypeFilter" style="font-weight: 500; font-size: 0.9rem;">Filter by Type:</label>
          <select id="docTypeFilter">
            <option value="">All Documents</option>
            <option value="invoice">Invoices Only</option>
            <option value="resume">Resumes Only</option>
          </select>
        </div>
        <div>
          <button id="refreshBtn" type="button">Refresh List</button>
        </div>
      </div>

      <div style="overflow-x: auto;">
        <table id="docsTable">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Type</th>
              <th>Company / Candidate Name</th>
              <th>Invoice # / Role</th>
              <th>Date</th>
              <th>Amount</th>
              <th>Currency</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody id="docsBody">
            <tr>
              <td colspan="8" class="empty-state">Loading documents...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const uploadForm = document.getElementById("uploadForm");
    const fileInput = document.getElementById("fileInput");
    const submitBtn = document.getElementById("submitBtn");
    const statusMsg = document.getElementById("statusMsg");
    const docTypeFilter = document.getElementById("docTypeFilter");
    const refreshBtn = document.getElementById("refreshBtn");
    const docsBody = document.getElementById("docsBody");

    function showStatus(text, type) {
      statusMsg.className = `status-msg ${type}`;
      statusMsg.textContent = text;
    }

    function clearStatus() {
      statusMsg.className = "status-msg";
      statusMsg.textContent = "";
      statusMsg.style.display = "none";
    }

    async function loadDocuments() {
      try {
        const typeVal = docTypeFilter.value;
        const url = typeVal
          ? `/documents/search?summary=true&doc_type=${encodeURIComponent(typeVal)}`
          : "/documents/search?summary=true";

        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch documents`);
        const data = await res.json();
        renderTable(data.results || []);
      } catch (err) {
        docsBody.innerHTML = `<tr><td colspan="8" class="empty-state" style="color: var(--danger);">Error loading documents: ${escapeHtml(err.message)}</td></tr>`;
      }
    }

    function renderTable(docs) {
      if (!docs || docs.length === 0) {
        docsBody.innerHTML = `<tr><td colspan="8" class="empty-state">No documents found. Upload a PDF, DOCX, or image above to get started.</td></tr>`;
        return;
      }

      docsBody.innerHTML = docs.map((doc, index) => {
        const type = doc.doc_type || "unknown";
        const fields = doc.structured_data || {};
        
        let primaryName = "-";
        let secondaryInfo = "-";
        let dateVal = "-";
        let amountVal = "-";
        let currencyVal = "-";

        if (type === "invoice") {
          primaryName = fields.company_name || "-";
          secondaryInfo = fields.invoice_number || "-";
          dateVal = fields.date || "-";
          amountVal = fields.amount !== undefined && fields.amount !== null ? Number(fields.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "-";
          currencyVal = fields.currency || "-";

        } else if (type === "resume") {
          primaryName = fields.name || "-";
          const firstExp = (fields.experience && fields.experience[0]) ? fields.experience[0].title : null;
          const skillsList = (fields.skills && fields.skills.length) ? fields.skills.slice(0, 3).join(", ") : null;
          secondaryInfo = firstExp || skillsList || "-";
          dateVal = "-";
          amountVal = "-";
          currencyVal = "-";
        }

        const badgeClass = type === "invoice" ? "badge-invoice" : (type === "resume" ? "badge-resume" : "badge-unknown");
        const detailsId = `details-${index}`;

        return `
          <tr>
            <td><strong>${escapeHtml(doc.filename)}</strong></td>
            <td><span class="badge ${badgeClass}">${escapeHtml(type)}</span></td>
            <td>${escapeHtml(primaryName)}</td>
            <td>${escapeHtml(secondaryInfo)}</td>
            <td>${escapeHtml(dateVal)}</td>
            <td>${escapeHtml(amountVal)}</td>
            <td>${escapeHtml(currencyVal)}</td>
            <td>
              <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <span class="link-toggle" onclick="toggleDetails('${detailsId}')">View JSON</span>
                <span style="color: var(--border);">|</span>
                <span class="link-danger" onclick="deleteDocument('${escapeHtml(doc.id)}')">Delete</span>
              </div>
              <div id="${detailsId}" class="json-details" style="display: none;">${escapeHtml(JSON.stringify(fields, null, 2))}</div>
            </td>
          </tr>
        `;
      }).join("");
    }

    async function deleteDocument(docId) {
      const confirmed = window.confirm("Are you sure you want to delete this document?");
      if (!confirmed) return;

      try {
        const res = await fetch(`/documents/${encodeURIComponent(docId)}`, {
          method: "DELETE",
        });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `HTTP ${res.status}: Failed to delete document`);
        }
        showStatus(`Document ${docId} successfully deleted.`, "success");
        await loadDocuments();
      } catch (err) {
        showStatus(`Error deleting document: ${err.message}`, "error");
      }
    }

    function toggleDetails(id) {
      const el = document.getElementById(id);
      if (!el) return;
      el.style.display = el.style.display === "none" ? "block" : "none";
    }

    function escapeHtml(str) {
      if (str === null || str === undefined) return "";
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    // Form submission
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const file = fileInput.files[0];
      if (!file) return;

      submitBtn.disabled = true;
      submitBtn.textContent = "Processing...";
      showStatus("Uploading and analyzing document through intelligence pipeline...", "info");

      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch("/documents", {
          method: "POST",
          body: formData,
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Upload and ingestion failed");
        }

        const docType = data.doc_type || "document";
        showStatus(`Successfully ingested ${escapeHtml(file.name)} as [${docType.toUpperCase()}]!`, "success");
        uploadForm.reset();
        await loadDocuments();
      } catch (err) {
        showStatus(`Error: ${err.message}`, "error");
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Upload & Process";
      }
    });

    docTypeFilter.addEventListener("change", loadDocuments);
    refreshBtn.addEventListener("click", loadDocuments);

    // Initial load
    loadDocuments();
  </script>
</body>
</html>
"""
