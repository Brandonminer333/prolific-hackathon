function resolveApiBase() {
    const configured = (window.API_BASE || "").replace(/\/$/, "");
    if (configured) {
        return configured;
    }
    if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
        return "http://127.0.0.1:8000";
    }
    return "";
}

const API_BASE = resolveApiBase();

//#region agent log
function debugLog(hypothesisId, message, data) {
    fetch("http://127.0.0.1:7720/ingest/12ac00c5-0739-4afa-80d0-31bd9123d0e6", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "a79914" },
        body: JSON.stringify({
            sessionId: "a79914",
            hypothesisId,
            location: "frontend/app.js",
            message,
            data,
            timestamp: Date.now(),
        }),
    }).catch(() => {});
}
debugLog("H1", "api base resolved", {
    apiBase: API_BASE,
    hostname: location.hostname,
    configured: window.API_BASE || "",
});
//#endregion agent log

function ensureApiBase() {
    if (API_BASE) {
        return API_BASE;
    }
    throw new Error(
        "API URL is not configured. Set API_BASE in Vercel environment variables to your Cloud Run URL, then redeploy the frontend."
    );
}

if (window.ChartBoxPlot) {
    Chart.register(window.ChartBoxPlot.BoxPlotController, window.ChartBoxPlot.BoxAndWiskers);
}

const REQUIRED_COLUMNS = ["manager_id", "worker_type", "text_type", "raw_text"];
const VALID_WORKER_TYPES = new Set(["remote", "in_person"]);

let trustChart = null;
let criticismChart = null;

function formatScore(value) {
    if (value === null || value === undefined) {
        return "—";
    }
    return Number(value).toFixed(2);
}

function formatP(value) {
    if (value === null || value === undefined) {
        return "—";
    }
    return Number(value).toFixed(3);
}

function setStatus(elementId, message, type = "") {
    const element = document.getElementById(elementId);
    element.textContent = message;
    element.className = `status ${type}`.trim();
}

function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;

    for (let i = 0; i < text.length; i += 1) {
        const char = text[i];
        const next = text[i + 1];

        if (char === '"') {
            if (inQuotes && next === '"') {
                field += '"';
                i += 1;
            } else {
                inQuotes = !inQuotes;
            }
            continue;
        }

        if (char === "," && !inQuotes) {
            row.push(field.trim());
            field = "";
            continue;
        }

        if ((char === "\n" || char === "\r") && !inQuotes) {
            if (char === "\r" && next === "\n") {
                i += 1;
            }
            row.push(field.trim());
            field = "";
            if (row.some((cell) => cell.length > 0)) {
                rows.push(row);
            }
            row = [];
            continue;
        }

        field += char;
    }

    if (field.length > 0 || row.length > 0) {
        row.push(field.trim());
        rows.push(row);
    }

    if (rows.length === 0) {
        return [];
    }

    const headers = rows[0].map((header) => header.trim());
    return rows.slice(1).map((cells, index) => {
        const record = {};
        headers.forEach((header, headerIndex) => {
            record[header] = cells[headerIndex] ?? "";
        });
        record.__row = index + 2;
        return record;
    });
}

function validateSubmissions(records) {
    const errors = [];
    const submissions = [];

    records.forEach((record) => {
        const rowLabel = `Row ${record.__row}`;
        const missing = REQUIRED_COLUMNS.filter((column) => !record[column]?.trim());
        if (missing.length > 0) {
            errors.push(`${rowLabel}: missing ${missing.join(", ")}`);
            return;
        }

        const workerType = record.worker_type.trim();
        if (!VALID_WORKER_TYPES.has(workerType)) {
            errors.push(`${rowLabel}: worker_type must be "remote" or "in_person"`);
            return;
        }

        submissions.push({
            manager_id: record.manager_id.trim(),
            worker_type: workerType,
            text_type: record.text_type.trim(),
            raw_text: record.raw_text.trim(),
        });
    });

    return { submissions, errors };
}

async function postSubmissions(submissions) {
    const base = ensureApiBase();
    const url = `${base}/submit`;
    //#region agent log
    debugLog("H1", "postSubmissions start", { url, count: submissions.length });
    //#endregion agent log
    let response;
    try {
        response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ submissions }),
        });
    } catch (error) {
        //#region agent log
        debugLog("H2", "postSubmissions network error", {
            url,
            name: error?.name,
            message: error?.message,
        });
        //#endregion agent log
        throw new Error(`Network error calling ${url}. Check API_BASE and CORS. (${error?.message || error})`);
    }

    if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Submit failed (${response.status})`);
    }

    return response.json();
}

async function fetchResults() {
    const base = ensureApiBase();
    const url = `${base}/results`;
    let response;
    try {
        response = await fetch(url);
    } catch (error) {
        //#region agent log
        debugLog("H2", "fetchResults network error", {
            url,
            name: error?.name,
            message: error?.message,
        });
        //#endregion agent log
        throw new Error(`Network error calling ${url}. Check API_BASE and CORS. (${error?.message || error})`);
    }
    if (!response.ok) {
        throw new Error(`Results request failed (${response.status})`);
    }
    return response.json();
}

function renderSummary(summary) {
    const tbody = document.querySelector("#summary-table tbody");
    tbody.innerHTML = "";

    ["remote", "in_person"].forEach((workerType) => {
        const stats = summary[workerType] || { n: 0 };
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${workerType.replace("_", "-")}</td>
            <td>${stats.n ?? 0}</td>
            <td>${formatScore(stats.mean_trust)}</td>
            <td>${formatScore(stats.mean_criticism)}</td>
            <td>${formatScore(stats.median_trust)}</td>
            <td>${formatScore(stats.median_criticism)}</td>
        `;
        tbody.appendChild(row);
    });
}

function computeBoxStats(values) {
    if (!values.length) {
        return { min: 0, q1: 0, median: 0, q3: 0, max: 0, items: [] };
    }

    const sorted = [...values].sort((a, b) => a - b);
    const quantile = (arr, q) => {
        const pos = (arr.length - 1) * q;
        const base = Math.floor(pos);
        const rest = pos - base;
        if (arr[base + 1] !== undefined) {
            return arr[base] + rest * (arr[base + 1] - arr[base]);
        }
        return arr[base];
    };

    return {
        min: sorted[0],
        q1: quantile(sorted, 0.25),
        median: quantile(sorted, 0.5),
        q3: quantile(sorted, 0.75),
        max: sorted[sorted.length - 1],
        items: sorted,
    };
}

function renderBoxChart(canvasId, chartRef, title, plotData) {
    const canvas = document.getElementById(canvasId);
    const remoteStats = computeBoxStats(plotData.remote || []);
    const inPersonStats = computeBoxStats(plotData.in_person || []);

    if (chartRef) {
        chartRef.destroy();
    }

    return new Chart(canvas, {
        type: "boxplot",
        data: {
            labels: ["Remote", "In-person"],
            datasets: [
                {
                    label: title,
                    data: [remoteStats, inPersonStats],
                    backgroundColor: ["rgba(29, 78, 216, 0.35)", "rgba(4, 120, 87, 0.35)"],
                    borderColor: ["#1d4ed8", "#047857"],
                    borderWidth: 2,
                    outlierBackgroundColor: "#111827",
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    min: 0,
                    max: 1,
                    title: { display: true, text: "Score (0–1)" },
                },
            },
        },
    });
}

function renderStatBlock(title, tests) {
    const mw = tests.mann_whitney || {};
    const lr = tests.logistic || {};

    return `
        <div class="stat-block">
            <h4>${title}</h4>
            <p><strong>Mann-Whitney U:</strong> U=${formatScore(mw.u_statistic)}, p=${formatP(mw.p_value)}, rank-biserial=${formatScore(mw.rank_biserial)}</p>
            <p>${mw.message || "Compares score distributions between remote and in-person groups."}</p>
            <p><strong>Logistic regression:</strong> coef=${formatScore(lr.coefficient)}, odds ratio=${formatScore(lr.odds_ratio)}, p=${formatP(lr.p_value)}</p>
            <p>${lr.message || "Predicts above-median score from worker type."}</p>
        </div>
    `;
}

function renderStatsPanel(tests) {
    const panel = document.getElementById("stats-panel");
    panel.innerHTML = `
        ${renderStatBlock("Trust", tests.trust || {})}
        ${renderStatBlock("Criticism", tests.criticism || {})}
    `;
}

function renderInterpretation(items) {
    const list = document.getElementById("interpretation-list");
    list.innerHTML = "";
    (items || []).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
    });
}

function renderSampleWarning(summary, submissions) {
    const warning = document.getElementById("sample-warning");
    const total = submissions.length;
    const remoteN = summary.remote?.n || 0;
    const inPersonN = summary.in_person?.n || 0;

    if (total < 20 || remoteN < 5 || inPersonN < 5) {
        warning.textContent =
            `Small sample warning: total n=${total}, remote n=${remoteN}, in-person n=${inPersonN}. ` +
            "Treat findings as directional, not definitive.";
        warning.classList.remove("hidden");
    } else {
        warning.classList.add("hidden");
    }
}

async function loadResults() {
    try {
        const data = await fetchResults();
        renderSummary(data.summary || {});
        renderStatsPanel(data.tests || {});
        renderInterpretation(data.interpretation || []);
        renderSampleWarning(data.summary || {}, data.submissions || []);

        trustChart = renderBoxChart("trust-chart", trustChart, "Trust", data.plot_data?.trust || {});
        criticismChart = renderBoxChart(
            "criticism-chart",
            criticismChart,
            "Criticism",
            data.plot_data?.criticism || {}
        );
    } catch (error) {
        setStatus("upload-status", `Could not load results: ${error.message}`, "error");
    }
}

async function handleCsvUpload() {
    const fileInput = document.getElementById("csv-file");
    const errorList = document.getElementById("upload-errors");
    errorList.innerHTML = "";

    if (!fileInput.files?.length) {
        setStatus("upload-status", "Choose a CSV file first.", "error");
        return;
    }

    setStatus("upload-status", "Reading CSV...");
    const text = await fileInput.files[0].text();
    const records = parseCsv(text);
    const { submissions, errors } = validateSubmissions(records);

    errors.forEach((error) => {
        const li = document.createElement("li");
        li.textContent = error;
        errorList.appendChild(li);
    });

    if (errors.length > 0) {
        setStatus("upload-status", "Fix CSV validation errors before uploading.", "error");
        return;
    }

    if (!submissions.length) {
        setStatus("upload-status", "CSV contains no data rows.", "error");
        return;
    }

    try {
        setStatus("upload-status", `Scoring ${submissions.length} submission(s)...`);
        const result = await postSubmissions(submissions);
        const failedCount = result.failed?.length || 0;
        const scoredCount = result.scored?.length || 0;

        if (failedCount > 0) {
            result.failed.forEach((failure) => {
                const li = document.createElement("li");
                li.textContent = `Row index ${failure.row_index}: ${failure.reason}`;
                errorList.appendChild(li);
            });
        }

        setStatus(
            "upload-status",
            `Scored ${scoredCount} submission(s); ${failedCount} failed.`,
            failedCount > 0 ? "error" : "success"
        );
        await loadResults();
    } catch (error) {
        setStatus("upload-status", error.message, "error");
    }
}

async function handleSingleSubmit(event) {
    event.preventDefault();
    const form = event.target;
    const submission = {
        manager_id: form.manager_id.value.trim(),
        worker_type: form.worker_type.value,
        text_type: form.text_type.value.trim(),
        raw_text: form.raw_text.value.trim(),
    };

    try {
        setStatus("single-status", "Scoring submission...");
        const result = await postSubmissions([submission]);
        if (result.failed?.length) {
            setStatus("single-status", result.failed[0].reason, "error");
            return;
        }
        setStatus("single-status", "Submission scored successfully.", "success");
        form.reset();
        form.text_type.value = "performance_review";
        await loadResults();
    } catch (error) {
        setStatus("single-status", error.message, "error");
    }
}

document.getElementById("upload-btn").addEventListener("click", handleCsvUpload);
document.getElementById("single-form").addEventListener("submit", handleSingleSubmit);
document.getElementById("refresh-btn").addEventListener("click", loadResults);

loadResults();
