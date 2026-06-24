// coding-list.js

let allChallenges = [];

document.addEventListener("DOMContentLoaded", () => {
    fetchChallenges();

    const generateBtn = document.getElementById("generate-challenge-btn");
    generateBtn.addEventListener("click", generateChallenge);

    // Event listeners for filters
    const topicSelect = document.getElementById("challenge-category");
    const diffSelect = document.getElementById("challenge-difficulty");
    const searchInput = document.getElementById("challenge-search");

    topicSelect.addEventListener("change", filterAndRenderChallenges);
    diffSelect.addEventListener("change", filterAndRenderChallenges);
    if (searchInput) {
        searchInput.addEventListener("input", filterAndRenderChallenges);
    }
});

async function fetchChallenges() {
    const listContainer = document.getElementById("challenge-list-container");
    listContainer.innerHTML = '<p><i class="fa-solid fa-spinner fa-spin"></i> Loading challenges...</p>';

    try {
        const token = localStorage.getItem("access_token");
        const res = await fetch("/api/v1/coding/", {
            headers: { "Authorization": `Bearer ${token}` }
        });

        const data = await res.json();
        if (data.success) {
            allChallenges = data.data ? data.data.challenges : data.challenges;
            filterAndRenderChallenges();
        } else {
            listContainer.innerHTML = `<p style="color:red">Failed to load challenges: ${data.error}</p>`;
        }
    } catch (err) {
        listContainer.innerHTML = `<p style="color:red">Network error.</p>`;
    }
}

function filterAndRenderChallenges() {
    const listContainer = document.getElementById("challenge-list-container");
    const category = document.getElementById("challenge-category").value;
    const difficulty = document.getElementById("challenge-difficulty").value;
    const searchInput = document.getElementById("challenge-search");
    const search = searchInput ? searchInput.value.toLowerCase() : "";

    // If no category (topic) is selected, show prompt message
    if (!category) {
        listContainer.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #666; background: #f9f9f9; border-radius: 8px; border: 1px dashed #ccc;">
                <i class="fa-solid fa-code" style="font-size: 32px; margin-bottom: 12px; color: #aaa;"></i>
                <p style="font-size: 16px; font-weight: 500;">Please select a topic from the dropdown to view coding challenges.</p>
            </div>
        `;
        return;
    }

    const filtered = allChallenges.filter(q => {
        const c = q.code_challenge;
        if (!c) return false;

        // Get topic from question tags, fallback to category_name
        const tags = q.question?.tags || [];
        const topic = tags.find(t => t !== 'groq-ai' && t !== 'coding') || q.category_name;

        // Filter checks
        const matchesCategory = topic.toLowerCase() === category.toLowerCase();
        const matchesDifficulty = q.difficulty.toLowerCase() === difficulty.toLowerCase();
        
        const titleMatch = (c.title || "").toLowerCase().includes(search);
        const textMatch = (q.text || "").toLowerCase().includes(search);
        const matchesSearch = titleMatch || textMatch;

        return matchesCategory && matchesDifficulty && matchesSearch;
    });

    renderChallenges(filtered);
}

function renderChallenges(challenges) {
    const listContainer = document.getElementById("challenge-list-container");
    listContainer.innerHTML = "";

    if (!challenges || challenges.length === 0) {
        listContainer.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #666;">
                <p>No coding challenges found for this topic and difficulty. Click 'Generate New Challenge' to create one!</p>
            </div>
        `;
        return;
    }

    challenges.forEach(q => {
        const c = q.code_challenge;
        if (!c) return;
        
        const card = document.createElement("div");
        card.className = "task-card";
        card.onclick = () => {
            window.location.href = `/challenge-editor?id=${c.id}`;
        };

        const difficultyColor = q.difficulty === 'hard' ? '#842029' : (q.difficulty === 'medium' ? '#856404' : '#2e6b3a');
        const tags = q.question?.tags || [];
        const topic = tags.find(t => t !== 'groq-ai' && t !== 'coding') || q.category_name;

        card.innerHTML = `
            <h3><i class="fa-solid fa-file-code"></i> ${c.title || 'Coding Problem'}</h3>
            <div style="margin-bottom: 12px;">
                <span class="level-badge" style="color: ${difficultyColor}; background: ${difficultyColor}22">${q.difficulty}</span>
                <span style="font-size: 12px; color: #888;">${topic}</span>
            </div>
            <p style="font-size: 13px; color: #555; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;">
                ${q.text}
            </p>
        `;
        listContainer.appendChild(card);
    });
}

async function generateChallenge() {
    const categorySelect = document.getElementById("challenge-category");
    const category = categorySelect.value;
    if (!category) {
        alert("Please select a topic from the dropdown before generating a challenge!");
        return;
    }

    const btn = document.getElementById("generate-challenge-btn");
    const difficulty = document.getElementById("challenge-difficulty").value;
    
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating...';
    btn.disabled = true;

    try {
        const token = localStorage.getItem("access_token");
        const res = await fetch("/api/v1/coding/generate", {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}` 
            },
            body: JSON.stringify({ category, difficulty })
        });

        const data = await res.json();
        if (data.success) {
            // Re-fetch all challenges from the backend
            await fetchChallenges();
        } else {
            alert(`Error: ${data.error || data.message || 'Generation failed'}`);
        }
    } catch (err) {
        alert("Network error.");
    } finally {
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate New Challenge';
        btn.disabled = false;
    }
}
