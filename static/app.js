// === Утилиты ===
const $ = (id) => document.getElementById(id);

async function api(path) {
    const res = await fetch(path);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || `HTTP ${res.status}`);
    }
    return res.json();
}

function timeAgo(isoString) {
    if (!isoString) return "никогда";
    const dateStr = isoString.endsWith("Z") ? isoString : isoString + "Z";
    const past = new Date(dateStr).getTime();
    const now = Date.now();
    const diffSec = Math.floor((now - past) / 1000);

    if (diffSec < 60) return "только что";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} ${plural(diffMin, "минуту", "минуты", "минут")} назад`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour} ${plural(diffHour, "час", "часа", "часов")} назад`;
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay < 30) return `${diffDay} ${plural(diffDay, "день", "дня", "дней")} назад`;
    return new Date(dateStr).toLocaleDateString("ru-RU");
}

function plural(n, one, few, many) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
    return many;
}

function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

function rankIconUrl(rankTier) {
    if (!rankTier) return null;
    const tier = Math.floor(rankTier / 10);
    if (tier < 1 || tier > 8) return null;
    return `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/icons/ranks/rank_icon_${tier}.png`;
}

// === Состояние ===
let currentUser = { id: null, nickname: null };
let currentScope = "all";

// === Инициализация ===
async function init() {
    try {
        const me = await api("/me");
        showAuthBlock(me);
    } catch {
        $("auth-block").innerHTML = '<a href="/login" id="login-btn">Войти через Steam</a>';
    }

    bindToggle();
    await loadUsers();
}

function showAuthBlock(me) {
    $("auth-block").innerHTML = `
        <span style="color:#fff; margin-right:15px;">${escapeHtml(me.nickname || "Игрок")}</span>
        <a href="/logout" id="login-btn">Выйти</a>
    `;
}

function bindToggle() {
    document.querySelectorAll(".toggle-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".toggle-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentScope = btn.dataset.scope;
            if (currentUser.id) loadHeroes(currentUser.id, currentScope);
        });
    });
}

// === Пользователи ===
async function loadUsers() {
    const container = $("users-list");
    container.innerHTML = '<div class="loading">Загрузка...</div>';

    try {
        const users = await api("/users");
        if (!users.length) {
            container.innerHTML = '<div class="loading">Пока никого нет. Авторизуйся первым!</div>';
            return;
        }

        container.innerHTML = "";
        users.forEach(u => {
            const card = document.createElement("div");
            card.className = "user-card";
            card.innerHTML = `
                <img src="${escapeHtml(u.avatar_url || '')}" alt="" onerror="this.style.display='none'">
                <div class="user-meta">
                    <div class="name">${escapeHtml(u.nickname || "Без ника")}</div>
                    <div class="updated-small">обновлено ${timeAgo(u.last_updated)}</div>
                </div>
            `;
            card.addEventListener("click", () => loadFullStats(u.id, u.nickname));
            container.appendChild(card);
        });
    } catch (e) {
        container.innerHTML = `<div class="error">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
}

// === Полная статистика ===
async function loadFullStats(userId, nickname) {
    currentUser = { id: userId, nickname };

    const section = $("stats-section");
    section.classList.remove("hidden");

    $("profile-header").innerHTML = '<div class="loading">Загрузка...</div>';
    $("stats-content").innerHTML = "";
    $("recent-block").innerHTML = "";
    $("patch-block").innerHTML = "";
    $("heroes-list").innerHTML = "";

    await loadProfile(userId, nickname);
    await loadStats(userId);
    await loadRecent(userId);
    await loadPatch(userId);
    await loadHeroes(userId, currentScope);
}

async function loadProfile(userId, nickname) {
    const container = $("profile-header");
    try {
        const data = await api(`/profile/${userId}`);
        const u = data.user;
        const p = data.profile;

        const rankIcon = p ? rankIconUrl(p.rank_tier) : null;
        const rankIconHtml = rankIcon
            ? `<img class="rank-icon" src="${rankIcon}" alt="" onerror="this.style.display='none'">`
            : "";

        container.innerHTML = `
            <img class="profile-avatar" src="${escapeHtml(u.avatar_url || '')}" alt="" onerror="this.style.display='none'">
            <div class="profile-meta">
                <div class="profile-name">${escapeHtml(u.nickname || nickname || "Игрок")}</div>
                <div class="profile-rank">
                    ${rankIconHtml}
                    <span>${p ? escapeHtml(p.rank_str) : "Ранг неизвестен"}</span>
                </div>
                ${p && p.mmr_estimate ? `<div class="profile-mmr">~ ${p.mmr_estimate} MMR</div>` : ""}
            </div>
        `;
    } catch (e) {
        container.innerHTML = `<div class="error">Ошибка профиля: ${escapeHtml(e.message)}</div>`;
    }
}

async function loadStats(userId) {
    const content = $("stats-content");

    try {
        const data = await api(`/stats/${userId}`);
        if (!data.stats) {
            content.innerHTML = `<div class="loading">${escapeHtml(data.message || "Статистика ещё не собрана")}</div>`;
            return;
        }

        const s = data.stats;

        content.innerHTML = `
            <div class="stat-item">
                <div class="stat-value">${s.games_total}</div>
                <div class="stat-label">Всего игр</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${s.winrate_total}%</div>
                <div class="stat-label">Винрейт</div>
                <div class="stat-sub">${s.wins_total}–${s.losses_total}</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${s.avg_kda}</div>
                <div class="stat-label">Средний KDA</div>
                <div class="stat-sub">${s.avg_kills} / ${s