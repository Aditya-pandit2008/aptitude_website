// coding.js

let editor;
let currentChallengeId;
let templateCodeByLanguage = {};
let currentLanguage;

// ── Language stub generator ──────────────────────────────────────────────────
function deriveLanguageStubs(pythonTemplate) {
    const m = pythonTemplate.match(/def\s+(\w+)\s*\(([^)]*)\)/);
    if (!m) return { python: pythonTemplate };

    const fnName = m[1];
    const rawParams = m[2].split(",").map(p => p.trim()).filter(Boolean);
    const params = rawParams
        .map(p => p.split(":")[0].trim())
        .filter(p => p && p !== "self");
    const paramStr = params.join(", ");

    const python = pythonTemplate;

    const javaParams = params.map(p => `int[] ${p}`).join(", ");
    const java = `class Solution {\n    public int[] ${fnName}(${javaParams}) {\n        \n    }\n}`;

    const cppParams = params.map(p => `auto& ${p}`).join(", ");
    const cpp = `class Solution {\npublic:\n    auto ${fnName}(${cppParams}) {\n        \n    }\n};`;

    const jsDoc = params.map(p => ` * @param {*} ${p}`).join("\n");
    const javascript = `/**\n${jsDoc}\n * @return {*}\n */\nvar ${fnName} = function(${paramStr}) {\n    \n};`;

    const cParams = params.map(p => `int* ${p}`).join(", ");
    const c = `/**\n * Note: The returned array must be malloced, assume caller calls free().\n */\nint* ${fnName}(${cParams}, int* returnSize) {\n    \n}`;

    const tsParams = params.map(p => `${p}: any`).join(", ");
    const typescript = `function ${fnName}(${tsParams}): any {\n    \n};`;

    const goParams = params.map(p => `${p} interface{}`).join(", ");
    const go = `func ${fnName}(${goParams}) interface{} {\n    \n}`;

    const ktParams = params.map(p => `${p}: Any`).join(", ");
    const kotlin = `class Solution {\n    fun ${fnName}(${ktParams}): Any {\n        \n    }\n}`;

    const rsParams = params.map(p => `${p}: i32`).join(", ");
    const rust = `impl Solution {\n    pub fn ${fnName}(${rsParams}) -> i32 {\n        \n    }\n}`;

    const ruby = `def ${fnName}(${paramStr})\n    \nend`;

    const csharp = `public class Solution {\n    public object ${fnName}(${params.map(p => `object ${p}`).join(", ")}) {\n        \n    }\n}`;

    const php = `class Solution {\n    function ${fnName}(${params.map(p => `$${p}`).join(", ")}) {\n        \n    }\n}`;

    const swift = `class Solution {\n    func ${fnName}(${params.map(p => `_ ${p}: Any`).join(", ")}) -> Any {\n        \n    }\n}`;

    const scala = `object Solution {\n    def ${fnName}(${params.map(p => `${p}: Any`).join(", ")}): Any = {\n        \n    }\n}`;

    return { python, java, cpp, javascript, c, typescript, go, kotlin, rust, ruby, csharp, php, swift, scala };
}

// ── Monaco language ID map ───────────────────────────────────────────────────
const monacoLangMap = {
    "python":     "python",
    "java":       "java",
    "cpp":        "cpp",
    "javascript": "javascript",
    "typescript": "typescript",
    "go":         "go",
    "kotlin":     "kotlin",
    "rust":       "rust",
    "ruby":       "ruby",
    "csharp":     "csharp",
    "php":        "php",
    "swift":      "swift",
    "scala":      "scala",
    "c":          "c",
};

document.addEventListener("DOMContentLoaded", () => {
    const urlParams = new URLSearchParams(window.location.search);
    currentChallengeId = urlParams.get("id");

    if (!currentChallengeId) {
        document.getElementById("problem-content").innerHTML = "<p>No challenge selected.</p>";
        return;
    }

    loadChallenge(currentChallengeId);

    document.getElementById("run-btn").addEventListener("click", runCode);
    document.getElementById("submit-btn").addEventListener("click", submitCode);
    document.getElementById("language-select").addEventListener("change", changeLanguage);
});

async function loadChallenge(id) {
    try {
        const token = localStorage.getItem("access_token");
        const res = await fetch(`/api/v1/coding/${id}`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await res.json();

        if (data.success) {
            const d = data.data || data;
            renderChallenge(d.challenge, d.question);
            initMonaco(d.challenge.template_code);
        } else {
            document.getElementById("problem-content").innerHTML = `<p style="color:red">${data.error}</p>`;
        }
    } catch (err) {
        document.getElementById("problem-content").innerHTML = `<p style="color:red">Network error.</p>`;
    }
}

function renderChallenge(challenge, question) {
    document.getElementById("problem-title").innerText = challenge.title || "Coding Problem";
    document.getElementById("problem-difficulty").innerText = question.difficulty;
    document.getElementById("problem-difficulty").className = `difficulty-badge ${question.difficulty}`;
    const tags = question.tags || [];
    const topic = tags.find(t => t !== 'groq-ai' && t !== 'coding') || question.category_name;
    document.getElementById("problem-topic").innerText = topic;

    const textHtml = question.text.replace(/\n/g, "<br>");
    document.getElementById("problem-content").innerHTML = `<p>${textHtml}</p>`;

    const examplesContainer = document.getElementById("problem-examples");
    let examplesHtml = "";
    if (challenge.sample_test_cases && challenge.sample_test_cases.length > 0) {
        challenge.sample_test_cases.forEach((tc, i) => {
            examplesHtml += `
                <div class="example-box">
                    <strong>Input:</strong> ${tc.input}<br>
                    <strong>Output:</strong> ${tc.expected_output}
                </div>
            `;
        });
    }
    examplesContainer.innerHTML = examplesHtml;
}

function initMonaco(templateCodeData) {
    // Build templateCodeByLanguage: derive stubs from Python base, then overlay backend templates
    if (templateCodeData && typeof templateCodeData === "object" && !Array.isArray(templateCodeData)) {
        const pythonBase = templateCodeData.python || templateCodeData.Python || "";
        const derived = pythonBase ? deriveLanguageStubs(pythonBase) : {};
        templateCodeByLanguage = { ...derived, ...templateCodeData };
    } else if (typeof templateCodeData === "string" && templateCodeData.trim()) {
        templateCodeByLanguage = deriveLanguageStubs(templateCodeData);
    } else {
        templateCodeByLanguage = {};
    }

    const select = document.getElementById("language-select");
    currentLanguage = (select && select.value) || Object.keys(templateCodeByLanguage)[0] || "python";

    if (select && select.value !== currentLanguage) {
        select.value = currentLanguage;
    }

    if (select) select.disabled = true;

    require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.41.0/min/vs' } });
    require(['vs/editor/editor.main'], function () {
        const startingCode = templateCodeByLanguage[currentLanguage] || "// Write your code here\n";
        editor = monaco.editor.create(document.getElementById('monaco-editor'), {
            value: startingCode,
            language: monacoLangMap[currentLanguage] || currentLanguage,
            theme: 'vs-dark',
            automaticLayout: true,
            fontSize: 14,
            minimap: { enabled: false }
        });

        if (select) select.disabled = false;
    });
}

function changeLanguage() {
    const select = document.getElementById("language-select");
    const newLanguage = select.value;

    if (!editor) {
        console.warn("Editor not ready yet, ignoring language change.");
        return;
    }

    if (newLanguage === currentLanguage) return;

    const newTemplate = templateCodeByLanguage[newLanguage];

    if (newTemplate === undefined) {
        console.warn(`No template_code found for language "${newLanguage}". Keeping current code.`);
        monaco.editor.setModelLanguage(editor.getModel(), monacoLangMap[newLanguage] || newLanguage);
        currentLanguage = newLanguage;
        return;
    }

    const currentCode = editor.getValue();
    const previousTemplate = templateCodeByLanguage[currentLanguage] || "";
    const hasUnsavedEdits = currentCode.trim() !== previousTemplate.trim();

    if (hasUnsavedEdits) {
        const confirmed = window.confirm(
            "Switching languages will replace your current code with the starter template for the new language. Continue?"
        );
        if (!confirmed) {
            select.value = currentLanguage;
            return;
        }
    }

    editor.setValue(newTemplate);
    monaco.editor.setModelLanguage(editor.getModel(), monacoLangMap[newLanguage] || newLanguage);
    currentLanguage = newLanguage;
}

function printToConsole(text, isError = false) {
    const consoleOutput = document.getElementById("console-output");
    consoleOutput.innerText = text;
    if (isError) {
        consoleOutput.classList.add("error");
    } else {
        consoleOutput.classList.remove("error");
    }
}

async function runCode() {
    if (!editor) return;
    const code = editor.getValue();
    const language = document.getElementById("language-select").value;

    const runBtn = document.getElementById("run-btn");
    runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running...';
    runBtn.disabled = true;
    printToConsole("Executing...", false);

    try {
        const token = localStorage.getItem("access_token");
        const res = await fetch("/api/v1/coding/execute", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ code, language })
        });
        const data = await res.json();

        if (data.success) {
            const d = data.data || data;
            printToConsole(d.output, d.exit_code !== 0);
        } else {
            printToConsole(data.error || data.message, true);
        }
    } catch (err) {
        printToConsole("Network error during execution.", true);
    } finally {
        runBtn.innerHTML = '<i class="fa-solid fa-play"></i> Run Code';
        runBtn.disabled = false;
    }
}

async function submitCode() {
    if (!editor) return;
    const user_code = editor.getValue();
    const language = document.getElementById("language-select").value;

    const submitBtn = document.getElementById("submit-btn");
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Evaluating...';
    submitBtn.disabled = true;

    try {
        const token = localStorage.getItem("access_token");
        const res = await fetch(`/api/v1/coding/${currentChallengeId}/submit`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ code: user_code, language })
        });
        const data = await res.json();

        const feedbackPanel = document.getElementById("feedback-panel");
        const feedbackContent = document.getElementById("ai-feedback-content");

        if (data.success) {
            const d = data.data || data;
            feedbackPanel.classList.remove("hidden");
            const { passed_cases, total_cases, score, status, xp_earned, test_results, attempt } = d;
            const statusColor = status === 'passed' ? '#3f7d46' : (status === 'partial' ? '#856404' : '#b45748');
            const statusIcon  = status === 'passed' ? '✅' : (status === 'partial' ? '⚠️' : '❌');

            let testTable = "";
            if (test_results && test_results.length > 0) {
                testTable = `
                    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:12px;">
                        <thead>
                            <tr style="background:#f0f0f0;">
                                <th style="padding:8px;text-align:left;border:1px solid #ddd;">#</th>
                                <th style="padding:8px;text-align:left;border:1px solid #ddd;">Input</th>
                                <th style="padding:8px;text-align:left;border:1px solid #ddd;">Expected</th>
                                <th style="padding:8px;text-align:left;border:1px solid #ddd;">Got</th>
                                <th style="padding:8px;text-align:center;border:1px solid #ddd;">Result</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${test_results.map((r, i) => `
                                <tr style="background:${r.ok ? '#f0fff4' : '#fff5f5'}">
                                    <td style="padding:8px;border:1px solid #ddd;">${i + 1}</td>
                                    <td style="padding:8px;border:1px solid #ddd;font-family:monospace;">${r.input}</td>
                                    <td style="padding:8px;border:1px solid #ddd;font-family:monospace;">${r.expected}</td>
                                    <td style="padding:8px;border:1px solid #ddd;font-family:monospace;">${r.actual}</td>
                                    <td style="padding:8px;border:1px solid #ddd;text-align:center;">${r.ok ? '✅' : '❌'}</td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>`;
            }

            feedbackContent.innerHTML = `
                <div style="padding:14px;background:#f8f7f5;border-radius:8px;border:1px solid #e2e3e5;margin-bottom:14px;">
                    <div style="font-size:18px;font-weight:800;color:${statusColor};">
                        ${statusIcon} ${status.charAt(0).toUpperCase() + status.slice(1)}
                    </div>
                    <div style="margin-top:6px;font-size:14px;color:#555;">
                        Test Cases: <strong>${passed_cases} / ${total_cases}</strong> passed &nbsp;|&nbsp;
                        Score: <strong>${Math.round(score * 100)}%</strong> &nbsp;|&nbsp;
                        XP Earned: <strong style="color:#b8860b">+${xp_earned} ⭐</strong>
                    </div>
                </div>
                ${testTable}
                <div style="margin-top:16px;font-size:14px;line-height:1.7;color:#444;">
                    <strong><i class="fa-solid fa-robot"></i> AI Review:</strong><br>
                    ${(attempt.ai_feedback || "").replace(/\n/g, '<br>')}
                </div>
            `;
        } else {
            alert(data.error || data.message || "Submission failed.");
        }
    } catch (err) {
        alert("Network error during submission.");
    } finally {
        submitBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Submit';
        submitBtn.disabled = false;
    }
}
async function getHint() {
    const hintBtn = document.getElementById("hint-btn");
    const hintPanel = document.getElementById("hint-panel");
    const hintContent = document.getElementById("hint-content");
    const hintCounter = document.getElementById("hint-counter");

    hintBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Getting hint...';
    hintBtn.disabled = true;

    try {
        const token = localStorage.getItem("access_token");
        const res = await fetch(`/api/v1/coding/${currentChallengeId}/hint`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await res.json();

        if (data.success) {
            const d = data.data || data;
            hintPanel.classList.remove("hidden");
            hintContent.innerHTML = d.hint.replace(/\n/g, "<br>");
            hintCounter.innerText = `Hint ${d.hint_number} of 3`;

            if (d.hints_remaining === 0) {
                hintBtn.innerHTML = '<i class="fa-solid fa-lightbulb"></i> No hints remaining';
                hintBtn.disabled = true;
            } else {
                hintBtn.innerHTML = `<i class="fa-solid fa-lightbulb"></i> Next Hint (${d.hints_remaining} left)`;
                hintBtn.disabled = false;
            }
        } else {
            alert(data.error || data.message || "No hints remaining.");
            hintBtn.innerHTML = '<i class="fa-solid fa-lightbulb"></i> Get Hint';
            hintBtn.disabled = true;
        }
    } catch (err) {
        alert("Network error getting hint.");
        hintBtn.innerHTML = '<i class="fa-solid fa-lightbulb"></i> Get Hint';
        hintBtn.disabled = false;
    }
}