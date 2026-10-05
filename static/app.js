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

function wrClass(winrate) {
    return winrate >= 50 ? "" : "low";
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

// === Пользователи (левая колонка) ===
async function loadUsers() {
    const container = $("users-list");
    container.innerHTML = '<div class="loading">Загрузка...</div>';

    try {
        const users = await api("/users");
        if (!users.length) {
            container.innerHTML = '<div class="loading">Пока никого нет</div>';
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
                    <div class="updated-small">${timeAgo(u.last_updated)}</div>
                </div>
            `;
            card.addEventListener("click", () => loadFullStats(u.id, u.nickname));
            container.appendChild(card);
        });

        // Показываем блок с колонками
        $("player-layout").classList.remove("hidden");
    } catch (e) {
        container.innerHTML = `<div class="error">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
}

// === Полная статистика ===
async function loadFullStats(userId, nickname) {
    currentUser = { id: userId, nickname };

    $("player-layout").classList.remove("hidden");

    $("profile-header").innerHTML = '<div class="loading">Загрузка...</div>';
    $("stats-content").innerHTML = "";
    $("recent-block").innerHTML = "";
    $("peers-block").innerHTML = "";
    $("patch-block").innerHTML = "";
    $("heroes-list").innerHTML = "";

    await loadProfile(userId, nickname);
    await loadStats(userId);
    await loadRecent(userId);
    await loadPeers(userId);
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
                <div class="profile-rank">${p ? escapeHtml(p.rank_str) : "Ранг неизвестен"}</div>
            </div>
            ${rankIconHtml}
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
                <div class="stat-value stat-wl">
                    <span class="wins">${s.wins_total}</span><span class="wl-dash">-</span><span class="losses">${s.losses_total}</span>
                </div>
                <div class="stat-label">Всего игр</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${s.winrate_total}%</div>
                <div class="stat-label">Винрейт</div>
                <div class="stat-sub">${s.games_total} игр</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${s.avg_kda}</div>
                <div class="stat-label">Средний KDA</div>
                <div class="stat-sub">${s.avg_kills} / ${s.avg_deaths} / ${s.avg_assists}</div>
            </div>
        `;
    } catch (e) {
        content.innerHTML = `<div class="error">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
}

async function loadRecent(userId) {
    const container = $("recent-block");
    try {
        const data = await api(`/stats/${userId}/recent`);
        if (!data.recent) {
            container.innerHTML = `<div class="loading">${escapeHtml(data.message || "Нет матчей")}</div>`;
            return;
        }
        const r = data.recent;

        let heroesHtml = "";
        r.heroes.forEach(h => {
            heroesHtml += `
                <div class="mini-hero">
                    <img src="${escapeHtml(h.hero_image || '')}" alt="" onerror="this.style.display='none'">
                    <div class="mini-hero-info">
                        <div class="mini-hero-name">${escapeHtml(h.hero_name)}</div>
                        <div class="mini-hero-stats">${h.games} игр · <span class="${wrClass(h.winrate)}">${h.winrate}%</span></div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = `
            <div class="recent-summary">
                <span class="big">${r.games}</span> игр · винрейт
                <span class="big ${wrClass(r.winrate)}">${r.winrate}%</span>
                (${r.wins}–${r.games - r.wins})
            </div>
            <div class="mini-heroes-grid">${heroesHtml || '<div class="loading">Нет героев</div>'}</div>
        `;
    } catch (e) {
        container.innerHTML = `<div class="error">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
}

async function loadPatch(userId) {
    const title = $("patch-title");
    const container = $("patch-block");

    try {
        const data = await api(`/stats/${userId}/patch`);
        if (!data.patch) {
            title.textContent = "Статистика за патч";
            container.innerHTML = `<div class="loading">${escapeHtml(data.message || "Патч неизвестен")}</div>`;
            return;
        }

        title.textContent = `Статистика за патч ${data.patch.name}`;

        const s = data.summary;

        let topByGames = "";
        (data.heroes_by_games || []).forEach(h => {
            topByGames += `
                <div class="mini-hero">
                    <img src="${escapeHtml(h.hero_image || '')}" alt="" onerror="this.style.display='none'">
                    <div class="mini-hero-info">
                        <div class="mini-hero-name">${escapeHtml(h.hero_name)}</div>
                        <div class="mini-hero-stats">${h.games} игр · <span class="${wrClass(h.winrate)}">${h.winrate}%</span></div>
                    </div>
                </div>
            `;
        });

        let topByWinrate = "";
        (data.heroes_by_winrate || []).forEach(h => {
            topByWinrate += `
                <div class="mini-hero">
                    <img src="${escapeHtml(h.hero_image || '')}" alt="" onerror="this.style.display='none'">
                    <div class="mini-hero-info">
                        <div class="mini-hero-name">${escapeHtml(h.hero_name)}</div>
                        <div class="mini-hero-stats">${h.games} игр · <span class="${wrClass(h.winrate)}">${h.winrate}%</span></div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = `
            <div class="patch-summary">
                <div class="stat-item">
                    <div class="stat-value">${s.games}</div>
                    <div class="stat-label">Игр за патч</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${s.winrate}%</div>
                    <div class="stat-label">Винрейт</div>
                    <div class="stat-sub">${s.wins}–${s.games - s.wins}</div>
                </div>
            </div>

            <div class="patch-tops">
                <div class="patch-section">
                    <h4>Топ-5 по играм</h4>
                    <div class="mini-heroes-grid">${topByGames || '<div class="loading">Нет данных</div>'}</div>
                </div>
                <div class="patch-section">
                    <h4>Топ-5 по винрейту</h4>
                    <div class="mini-heroes-grid">${topByWinrate || '<div class="loading">Нет данных</div>'}</div>
                </div>
            </div>
        `;
    } catch (e) {
        title.textContent = "Статистика за патч";
        container.innerHTML = `<div class="error">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
}

// === Герои (правая колонка, компактный список) ===
async function loadHeroes(userId, scope) {
    const container = $("heroes-list");
    container.innerHTML = '<div class="loading">Загрузка...</div>';

    try {
        const data = await api(`/stats/${userId}/heroes?scope=${scope}&limit=10`);
        if (!data.heroes.length) {
            container.innerHTML = '<div class="loading">Нет данных</div>';
            return;
        }

        container.innerHTML = "";
        data.heroes.forEach(h => {
            const card = document.createElement("div");
            card.className = "hero-card";
            card.innerHTML = `
                <img src="${escapeHtml(h.hero_image || '')}" alt="${escapeHtml(h.hero_name)}" onerror="this.style.display='none'">
                <div class="hero-info">
                    <div class="hero-name">${escapeHtml(h.hero_name)}</div>
                    <div class="hero-stats">
                        <span>${h.games} игр · </span>
                        <span class="winrate ${wrClass(h.winrate)}">${h.winrate}%</span>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        container.innerHTML = `<div class="error">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
}

// === Пиры (правая колонка, компактно) ===
async function loadPeers(userId) {
    const container = $("peers-block");
    container.innerHTML = '<div class="loading">Загрузка...</div>';

    try {
        const data = await api(`/stats/${userId}/peers?limit=5`);
        if (!data.peers.length) {
            container.innerHTML = '<div class="loading">Нет данных</div>';
            return;
        }

        let rows = "";
        data.peers.forEach(p => {
            rows += `
                <div class="peer-row">
                    <img src="${escapeHtml(p.avatar || '')}" alt="" onerror="this.style.display='none'">
                    <div class="peer-info">
                        <div class="peer-name">${escapeHtml(p.nickname || "Без ника")}</div>
                        <div class="peer-stats">
                            <span class="peer-games-count">${p.with_games} игр</span> · <span class="wr ${wrClass(p.winrate)}">${p.winrate}%</span>
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = `<div class="peers-list">${rows}</div>`;
    } catch (e) {
        container.innerHTML = `<div class="error">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
}

// === Старт ===
init();