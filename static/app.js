// === Утилиты ===
const $ = (id) => document.getElementById(id);

async function api(path) {
    const res = await fetch(path);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
}

// Преобразует ISO-дату в "N минут/часов/дней назад"
function timeAgo(isoString) {
    if (!isoString) return "никогда";

    // Бэкенд отдаёт naive datetime (UTC без пометки). Добавляем 'Z', чтобы JS понял.
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

// Склонение русских слов: 1 минуту, 2 минуты, 5 минут
function plural(n, one, few, many) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
    return many;
}

// === Инициализация ===
async function init() {
    try {
        const me = await api("/me");
        showAuthBlock(me);
    } catch {
        $("auth-block").innerHTML = '<a href="/login" id="login-btn">Войти через Steam</a>';
    }

    await loadUsers();
}

function showAuthBlock(me) {
    $("auth-block").innerHTML = `
        <span style="color:#fff; margin-right:15px;">${me.nickname || "Игрок"}</span>
        <a href="/logout" id="login-btn">Выйти</a>
    `;
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
                <img src="${u.avatar_url || ''}" alt="" onerror="this.style.display='none'">
                <div class="user-meta">
                    <div class="name">${u.nickname || "Без ника"}</div>
                    <div class="updated-small">обновлено ${timeAgo(u.last_updated)}</div>
                </div>
            `;
            card.addEventListener("click", () => loadStats(u.id, u.nickname));
            container.appendChild(card);
        });
    } catch (e) {
        container.innerHTML = `<div class="error">Ошибка: ${e.message}</div>`;
    }
}

// === Статистика ===
async function loadStats(userId, nickname) {
    const section = $("stats-section");
    const content = $("stats-content");
    const heroesList = $("heroes-list");

    section.classList.remove("hidden");
    content.innerHTML = '<div class="loading">Загрузка...</div>';
    heroesList.innerHTML = "";

    // Общая статистика
    try {
        const data = await api(`/stats/${userId}`);

        const title = `Статистика: ${nickname || "Игрок"}`;
        let updatedLabel = "";

        if (data.stats && data.stats.updated_at) {
            updatedLabel = ` · обновлено ${timeAgo(data.stats.updated_at)}`;
        }
        $("stats-title").textContent = title + updatedLabel;

        if (!data.stats) {
            content.innerHTML = `<div class="loading">${data.message || "Статистика ещё не собрана"}</div>`;
        } else {
            const s = data.stats;
            content.innerHTML = `
                <div class="stats-block">
                    <div class="stat-item">
                        <div class="stat-value">${s.games_total}</div>
                        <div class="stat-label">Всего игр</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${s.winrate_total}%</div>
                        <div class="stat-label">Винрейт (всего)</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${s.games_recent}</div>
                        <div class="stat-label">Игр (последние)</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${s.winrate_recent}%</div>
                        <div class="stat-label">Винрейт (последние)</div>
                    </div>
                </div>
            `;
        }
    } catch (e) {
        $("stats-title").textContent = `Статистика: ${nickname || "Игрок"}`;
        content.innerHTML = `<div class="error">Ошибка: ${e.message}</div>`;
    }

    // Топ героев
    try {
        const data = await api(`/stats/${userId}/heroes?limit=12`);
        if (!data.heroes.length) {
            heroesList.innerHTML = '<div class="loading">Нет данных по героям</div>';
            return;
        }

        heroesList.innerHTML = "";
        data.heroes.forEach(h => {
            const card = document.createElement("div");
            card.className = "hero-card";
            const wrClass = h.winrate >= 50 ? "" : "low";
            card.innerHTML = `
                <img src="${h.hero_image || ''}" alt="${h.hero_name}" onerror="this.style.display='none'">
                <div class="hero-info">
                    <div class="hero-name">${h.hero_name}</div>
                    <div class="hero-stats">
                        <span>${h.games} игр</span>
                        <span class="winrate ${wrClass}">${h.winrate}%</span>
                    </div>
                </div>
            `;
            heroesList.appendChild(card);
        });
    } catch (e) {
        heroesList.innerHTML = `<div class="error">Ошибка: ${e.message}</div>`;
    }
}

// === Старт ===
init();