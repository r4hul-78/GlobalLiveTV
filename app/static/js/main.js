/**
 * Global Live TV Platform - Client Application
 * Vanilla ES6 JavaScript
 * Step 5: Responsive Channel Discovery UI
 * Step 6: Direct Browser HLS Video Player
 */

document.addEventListener("DOMContentLoaded", () => {
    initNavigationLinks();
    initHealthMonitoring();
    const reportController = initIssueReporting();
    const playerController = initHlsPlayer(reportController);
    initChannelDiscovery(playerController, reportController);
});

/**
 * Resolve API base URL based on the current viewing context.
 * When viewed directly via file://, route API calls to local Flask backend.
 */
function getApiBaseUrl() {
    if (window.location.protocol === "file:") {
        return "http://127.0.0.1:5000";
    }
    return "";
}

/**
 * Step 7: Centralized REST API Client & Request Utilities
 */
var apiClient = window.apiClient = window.apiClient || {
    async get(endpoint, params = {}, options = {}) {
        const base = getApiBaseUrl();
        const url = new URL(base ? base + endpoint : endpoint, window.location.origin);
        Object.entries(params).forEach(([k, v]) => {
            if (v !== undefined && v !== null && String(v).trim() !== "") {
                url.searchParams.set(k, String(v).trim());
            }
        });

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), options.timeout || 8000);

        try {
            const res = await fetch(url.toString(), {
                method: "GET",
                headers: { "Accept": "application/json", ...(options.headers || {}) },
                signal: options.signal || controller.signal
            });
            clearTimeout(timeoutId);
            if (!res.ok) {
                const errJson = await res.json().catch(() => ({}));
                const err = new Error(errJson.message || `HTTP ${res.status}`);
                err.status = res.status;
                err.data = errJson;
                throw err;
            }
            return await res.json();
        } catch (err) {
            clearTimeout(timeoutId);
            if (err.name === "AbortError") {
                const timeoutErr = new Error("Request timed out. Please check your network connection.");
                timeoutErr.status = 408;
                throw timeoutErr;
            }
            throw err;
        }
    },

    async post(endpoint, body = {}, options = {}) {
        const base = getApiBaseUrl();
        const url = base ? base + endpoint : endpoint;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), options.timeout || 8000);

        try {
            const res = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    ...(options.headers || {})
                },
                body: JSON.stringify(body),
                signal: options.signal || controller.signal
            });
            clearTimeout(timeoutId);
            if (!res.ok) {
                const errJson = await res.json().catch(() => ({}));
                const err = new Error(errJson.message || `HTTP ${res.status}`);
                err.status = res.status;
                err.data = errJson;
                throw err;
            }
            return await res.json();
        } catch (err) {
            clearTimeout(timeoutId);
            if (err.name === "AbortError") {
                const timeoutErr = new Error("Request timed out. Please check your network connection.");
                timeoutErr.status = 408;
                throw timeoutErr;
            }
            throw err;
        }
    }
};

/**
 * Accessible Live Status Announcer for Screen Readers
 */
function announceToScreenReader(message) {
    const announcer = document.getElementById("a11yAnnouncer");
    if (announcer && message) {
        announcer.textContent = "";
        setTimeout(() => {
            announcer.textContent = message;
        }, 50);
    }
}

/**
 * Ensure navigation links function properly in both Flask web routing and direct file browsing.
 */
function initNavigationLinks() {
    const isFile = window.location.protocol === "file:";

    const routes = [
        { id: "navHome", fileTarget: "index.html", webTarget: "/" },
        { id: "navAbout", fileTarget: "about.html", webTarget: "/about" },
        { id: "brandLink", fileTarget: "index.html", webTarget: "/" },
        { id: "btnBackToHome", fileTarget: "index.html", webTarget: "/" },
        { id: "btn404Home", fileTarget: "index.html", webTarget: "/" },
        { id: "btn500Home", fileTarget: "index.html", webTarget: "/" }
    ];

    routes.forEach(({ id, fileTarget, webTarget }) => {
        const el = document.getElementById(id);
        if (!el) return;

        const currentHref = el.getAttribute("href") || "";

        if (isFile || currentHref.includes("{{") || currentHref.includes("%7B")) {
            el.setAttribute("href", fileTarget);
        }

        el.addEventListener("click", (e) => {
            if (window.location.protocol === "file:") {
                e.preventDefault();
                window.location.href = fileTarget;
            }
        });
    });
}

/**
 * Helper: Convert 2-letter ISO country code to Unicode Flag Emoji.
 */
function getCountryFlag(code) {
    if (!code || typeof code !== "string" || code.length !== 2) return "🌐";
    const upper = code.toUpperCase();
    if (!/^[A-Z]{2}$/.test(upper)) return "🌐";
    return String.fromCodePoint(...[...upper].map(c => 127397 + c.charCodeAt(0)));
}

/**
 * Helper: Human-friendly health status label and styling class.
 */
function formatHealthStatus(status) {
    const normalized = (status || "unknown").toLowerCase();
    switch (normalized) {
        case "healthy":
            return { label: "Healthy", class: "healthy" };
        case "degraded":
            return { label: "Degraded", class: "degraded" };
        case "unavailable":
            return { label: "Offline", class: "unavailable" };
        case "unsupported":
            return { label: "Unsupported", class: "unsupported" };
        default:
            return { label: "Unchecked", class: "unknown" };
    }
}

/**
 * Helper: Format ISO date string to human-readable local time.
 */
function formatDateTime(isoString) {
    if (!isoString) return "Never";
    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + " " +
               date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
        return isoString;
    }
}

/**
 * Render channel logo with visual fallback handling
 */
function renderChannelLogo(container, channel) {
    if (!container) return;
    container.innerHTML = "";
    const logoUrl = channel ? channel.logo_url : null;
    const channelName = channel ? channel.name : "TV";

    const hasValidUrl = logoUrl && (logoUrl.startsWith("http://") || logoUrl.startsWith("https://"));

    if (hasValidUrl) {
        const img = document.createElement("img");
        img.className = "channel-logo-img";
        img.src = logoUrl;
        img.alt = `${channelName} logo`;
        img.loading = "lazy";

        img.onerror = () => {
            renderInitialsFallback(container, channelName);
        };

        container.appendChild(img);
    } else {
        renderInitialsFallback(container, channelName);
    }
}

/**
 * Render initial-letter avatar fallback for missing or failed channel logos
 */
function renderInitialsFallback(container, name) {
    if (!container) return;
    container.innerHTML = "";
    const fallback = document.createElement("div");
    fallback.className = "channel-logo-fallback";
    const initials = (name || "TV")
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map(w => w[0].toUpperCase())
        .join("");
    fallback.textContent = initials || "TV";
    container.appendChild(fallback);
}


/**
 * Step 6: Dedicated HLS Video Player Engine
 * Implements HTML5 Video playback using pinned HLS.js (v1.5.17) and Safari native fallback.
 */
function initHlsPlayer(reportController) {
    const playerModal = document.getElementById("playerModal");
    const btnClosePlayer = document.getElementById("btnClosePlayer");
    const btnCloseFromError = document.getElementById("btnCloseFromError");
    const btnReportPlayer = document.getElementById("btnReportPlayer");
    const videoElement = document.getElementById("hlsVideoPlayer");
    const playerLoadingOverlay = document.getElementById("playerLoadingOverlay");
    const playerLoadingText = document.getElementById("playerLoadingText");
    const playerAutoplayOverlay = document.getElementById("playerAutoplayOverlay");
    const btnUnmuteAutoplay = document.getElementById("btnUnmuteAutoplay");
    const playerErrorOverlay = document.getElementById("playerErrorOverlay");
    const playerErrorTitle = document.getElementById("playerErrorTitle");
    const playerErrorDescription = document.getElementById("playerErrorDescription");
    const playerErrorReason = document.getElementById("playerErrorReason");
    const btnRetryPlayer = document.getElementById("btnRetryPlayer");
    const btnOpenStreamExternal = document.getElementById("btnOpenStreamExternal");
    const btnTestStream = document.getElementById("btnTestStream");

    const playerLogoContainer = document.getElementById("playerLogoContainer");
    const playerChannelName = document.getElementById("playerChannelName");
    const playerMetaTags = document.getElementById("playerMetaTags");
    const playerHealthTag = document.getElementById("playerHealthTag");
    const playerStreamUrlDisplay = document.getElementById("playerStreamUrlDisplay");
    const btnCopyPlayerUrl = document.getElementById("btnCopyPlayerUrl");

    if (!playerModal || !videoElement) {
        return { playChannel: () => {}, destroyPlayer: () => {}, closePlayer: () => {} };
    }

    // State tracking
    let hlsInstance = null;
    let activeChannel = null;
    let networkRetryCount = 0;
    const MAX_NETWORK_RETRIES = 2;
    const VERIFIED_TEST_STREAM = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8";

    /**
     * Stop and destroy any active playback resources to prevent memory leaks and background audio.
     */
    function destroyPlayer() {
        if (hlsInstance) {
            try {
                hlsInstance.stopLoad();
                hlsInstance.detachMedia();
                hlsInstance.destroy();
            } catch (err) {
                console.warn("Error destroying Hls instance:", err);
            }
            hlsInstance = null;
        }

        if (videoElement) {
            videoElement.pause();
            videoElement.removeAttribute("src");
            videoElement.load();
        }

        networkRetryCount = 0;
    }

    /**
     * Close the player modal and release resources without modifying directory filters.
     */
    function closePlayer() {
        destroyPlayer();
        playerModal.classList.remove("open");
        announceToScreenReader("Video player closed");
        window.dispatchEvent(new CustomEvent("player:closed"));
    }

    /**
     * Show player error overlay with actionable diagnostic explanations.
     */
    function showPlayerError(title, description, technicalReason) {
        if (playerLoadingOverlay) playerLoadingOverlay.style.display = "none";
        if (playerAutoplayOverlay) playerAutoplayOverlay.style.display = "none";
        if (playerErrorOverlay) playerErrorOverlay.style.display = "flex";

        if (playerErrorTitle) playerErrorTitle.textContent = title;
        if (playerErrorDescription) playerErrorDescription.textContent = description;
        if (playerErrorReason) {
            playerErrorReason.textContent = technicalReason ? `Diagnostic: ${technicalReason}` : "Reason: Unknown playback failure";
        }

        if (btnOpenStreamExternal && activeChannel) {
            btnOpenStreamExternal.href = activeChannel.stream_url;
        }
    }

    /**
     * Hide all overlays once media starts rendering.
     */
    function hideAllOverlays() {
        if (playerLoadingOverlay) playerLoadingOverlay.style.display = "none";
        if (playerAutoplayOverlay) playerAutoplayOverlay.style.display = "none";
        if (playerErrorOverlay) playerErrorOverlay.style.display = "none";
    }

    /**
     * Handle browser autoplay rejection gracefully by muting and offering unmute trigger.
     */
    function attemptPlaySafely() {
        const playPromise = videoElement.play();
        if (playPromise !== undefined) {
            playPromise
                .then(() => {
                    hideAllOverlays();
                })
                .catch((err) => {
                    if (err.name === "NotAllowedError") {
                        // Autoplay policy restricted playback with audio: mute and continue
                        videoElement.muted = true;
                        videoElement.play()
                            .then(() => {
                                if (playerLoadingOverlay) playerLoadingOverlay.style.display = "none";
                                if (playerAutoplayOverlay) playerAutoplayOverlay.style.display = "flex";
                            })
                            .catch(() => {
                                showPlayerError(
                                    "Autoplay Restricted",
                                    "Your browser blocked automated playback. Click below to start the stream manually.",
                                    err.message
                                );
                            });
                    } else {
                        showPlayerError(
                            "Playback Blocked",
                            "Browser media subsystem failed to start playback: " + err.message,
                            err.name
                        );
                    }
                });
        }
    }

    /**
     * Launch video stream playback for a given channel object.
     */
    function playChannel(channel) {
        if (!channel || !channel.stream_url) return;

        activeChannel = channel;
        networkRetryCount = 0;

        // Populate Player Header
        if (playerChannelName) playerChannelName.textContent = channel.name;
        if (playerLogoContainer) {
            playerLogoContainer.innerHTML = "";
            renderChannelLogo(playerLogoContainer, channel);
        }

        // Meta tags
        if (playerMetaTags) {
            playerMetaTags.innerHTML = "";
            if (channel.country && channel.country.code) {
                const cPill = document.createElement("span");
                cPill.className = "country-pill";
                cPill.textContent = `${getCountryFlag(channel.country.code)} ${channel.country.name || channel.country.code}`;
                playerMetaTags.appendChild(cPill);
            }
            if (Array.isArray(channel.genres)) {
                channel.genres.forEach(g => {
                    const gPill = document.createElement("span");
                    gPill.className = "genre-pill";
                    gPill.textContent = g.name;
                    playerMetaTags.appendChild(gPill);
                });
            }
            const fmtPill = document.createElement("span");
            fmtPill.className = "lang-pill";
            fmtPill.textContent = "HLS Stream";
            playerMetaTags.appendChild(fmtPill);
        }

        // Health Tag
        if (playerHealthTag) {
            const st = formatHealthStatus(channel.health_status);
            playerHealthTag.className = `status-badge ${st.class}`;
            playerHealthTag.innerHTML = `<span class="dot"></span><span>${st.label}</span>`;
        }

        // Stream URL Display & Copy
        if (playerStreamUrlDisplay) {
            playerStreamUrlDisplay.textContent = channel.stream_url;
        }

        if (btnCopyPlayerUrl) {
            btnCopyPlayerUrl.textContent = "Copy";
            btnCopyPlayerUrl.onclick = async () => {
                try {
                    await navigator.clipboard.writeText(channel.stream_url);
                    btnCopyPlayerUrl.textContent = "Copied!";
                    setTimeout(() => { btnCopyPlayerUrl.textContent = "Copy"; }, 2000);
                } catch {
                    btnCopyPlayerUrl.textContent = "Failed";
                }
            };
        }

        // Open modal
        playerModal.classList.add("open");
        announceToScreenReader(`Connecting to live stream for ${channel.name}`);
        window.dispatchEvent(new CustomEvent("player:started", { detail: { channel } }));

        // Show loading overlay
        if (playerLoadingOverlay) {
            playerLoadingOverlay.style.display = "flex";
            if (playerLoadingText) playerLoadingText.textContent = `Connecting to ${channel.name}...`;
        }
        if (playerAutoplayOverlay) playerAutoplayOverlay.style.display = "none";
        if (playerErrorOverlay) playerErrorOverlay.style.display = "none";

        // Clean up previous media
        destroyPlayer();

        const streamUrl = channel.stream_url;

        // Check HLS.js support
        const hasHlsJs = typeof Hls !== "undefined" && Hls.isSupported();
        const hasNativeHls = videoElement.canPlayType("application/vnd.apple.mpegurl");

        if (hasHlsJs) {
            try {
                hlsInstance = new Hls({
                    enableWorker: true,
                    lowLatencyMode: true,
                    backBufferLength: 60,
                    manifestLoadingTimeOut: 10000,
                    manifestLoadingMaxRetry: 2,
                    levelLoadingTimeOut: 10000,
                    fragLoadingTimeOut: 12000
                });

                hlsInstance.loadSource(streamUrl);
                hlsInstance.attachMedia(videoElement);

                hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
                    attemptPlaySafely();
                });

                hlsInstance.on(Hls.Events.ERROR, (event, data) => {
                    if (data.fatal) {
                        switch (data.type) {
                            case Hls.ErrorTypes.NETWORK_ERROR:
                                if (networkRetryCount < MAX_NETWORK_RETRIES) {
                                    networkRetryCount++;
                                    if (playerLoadingText) {
                                        playerLoadingText.textContent = `Broadcaster connection retry (${networkRetryCount}/${MAX_NETWORK_RETRIES})...`;
                                    }
                                    hlsInstance.startLoad();
                                } else {
                                    destroyPlayer();
                                    showPlayerError(
                                        "Broadcaster Stream Offline or Blocked",
                                        "Could not retrieve video playlist from the broadcaster. This is typically caused by a temporary broadcaster outage, origin CORS policy restrictions on third-party domains, or mixed-content browser blocking.",
                                        `${data.details} (${data.response?.code || "No HTTP response"})`
                                    );
                                }
                                break;
                            case Hls.ErrorTypes.MEDIA_ERROR:
                                hlsInstance.recoverMediaError();
                                break;
                            default:
                                destroyPlayer();
                                showPlayerError(
                                    "Playback Encountered Unrecoverable Error",
                                    "The video format or codec sent by the broadcaster cannot be decoded by your browser.",
                                    data.details
                                );
                                break;
                        }
                    }
                });
            } catch (err) {
                showPlayerError(
                    "Player Initialization Error",
                    "Failed to initialize HLS.js streaming engine: " + err.message,
                    err.name
                );
            }
        } else if (hasNativeHls) {
            // Native Safari / iOS HLS fallback
            videoElement.src = streamUrl;
            videoElement.addEventListener("loadedmetadata", () => {
                attemptPlaySafely();
            }, { once: true });

            videoElement.addEventListener("error", () => {
                const mediaError = videoElement.error;
                showPlayerError(
                    "Native Playback Failed",
                    "The native HLS player was unable to open this stream. Check broadcaster server availability.",
                    mediaError ? `MediaError code ${mediaError.code}` : "Native error"
                );
            }, { once: true });
        } else {
            showPlayerError(
                "Browser Incompatible With HLS",
                "Your web browser does not support MediaSource Extensions (MSE) or native HLS video playback. Please use a modern browser such as Google Chrome, Mozilla Firefox, Microsoft Edge, or Apple Safari.",
                "HLS_NOT_SUPPORTED"
            );
        }
    }

    // Modal Control Event Listeners
    if (btnClosePlayer) btnClosePlayer.addEventListener("click", closePlayer);
    if (btnCloseFromError) btnCloseFromError.addEventListener("click", closePlayer);

    if (playerModal) {
        playerModal.addEventListener("click", (e) => {
            if (e.target === playerModal) closePlayer();
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && playerModal.classList.contains("open")) {
            closePlayer();
        }
    });

    if (btnRetryPlayer) {
        btnRetryPlayer.addEventListener("click", () => {
            if (activeChannel) {
                playChannel(activeChannel);
            }
        });
    }

    if (btnUnmuteAutoplay) {
        btnUnmuteAutoplay.addEventListener("click", () => {
            if (videoElement) {
                videoElement.muted = false;
                videoElement.play().catch(() => {});
            }
            if (playerAutoplayOverlay) playerAutoplayOverlay.style.display = "none";
        });
    }

    if (btnReportPlayer) {
        btnReportPlayer.addEventListener("click", () => {
            if (activeChannel && reportController) {
                reportController.openReportModal(activeChannel);
            }
        });
    }

    if (btnTestStream) {
        btnTestStream.addEventListener("click", () => {
            playChannel({
                id: 0,
                name: "Mux Big Buck Bunny (HLS Test)",
                stream_url: VERIFIED_TEST_STREAM,
                health_status: "healthy",
                country: { code: "US", name: "United States" },
                genres: [{ name: "Demonstration", slug: "demo" }],
                logo_url: "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Big_buck_bunny_poster_big.jpg/320px-Big_buck_bunny_poster_big.jpg"
            });
        });
    }

    // Expose globally for testing and card interactions
    window.openVideoPlayer = playChannel;
    window.destroyVideoPlayer = destroyPlayer;

    return {
        playChannel,
        destroyPlayer,
        closePlayer
    };
}

/**
 * Step 5 & 7: Responsive Channel Discovery UI Controller & Application Integration
 */
function initChannelDiscovery(playerController, reportController) {
    const searchInput = document.getElementById("channelSearchInput");
    const clearSearchBtn = document.getElementById("btnClearSearch");
    const filterCountry = document.getElementById("filterCountry");
    const filterGenre = document.getElementById("filterGenre");
    const filterLanguage = document.getElementById("filterLanguage");
    const filterStatus = document.getElementById("filterStatus");
    const clearFiltersBtn = document.getElementById("btnClearFilters");
    const resultsSummary = document.getElementById("resultsSummary");
    const activeChips = document.getElementById("activeFilterChips");
    const skeletonGrid = document.getElementById("skeletonGrid");
    const channelGrid = document.getElementById("channelGrid");
    const emptyState = document.getElementById("emptyState");
    const emptyStateMessage = document.getElementById("emptyStateMessage");
    const emptyResetBtn = document.getElementById("btnEmptyReset");
    const errorState = document.getElementById("errorState");
    const errorMessage = document.getElementById("errorMessage");
    const retryBtn = document.getElementById("btnRetryFetch");
    const paginationNav = document.getElementById("paginationNav");
    const btnPrevPage = document.getElementById("btnPrevPage");
    const btnNextPage = document.getElementById("btnNextPage");
    const pageIndicators = document.getElementById("pageIndicators");

    // Modal elements
    const channelModal = document.getElementById("channelDetailsModal");
    const btnModalClose = document.getElementById("btnModalClose");
    const modalLogoContainer = document.getElementById("modalLogoContainer");
    const modalChannelTitle = document.getElementById("modalChannelTitle");
    const modalMetaRow = document.getElementById("modalMetaRow");
    const modalStreamUrl = document.getElementById("modalStreamUrl");
    const btnCopyStreamUrl = document.getElementById("btnCopyStreamUrl");
    const modalChecksList = document.getElementById("modalChecksList");
    const btnReportFromDetails = document.getElementById("btnReportFromDetails");

    if (!channelGrid) return; // Exit if discovery UI elements are not present

    // Internal reactive state
    const state = {
        q: "",
        country: "",
        genre: "",
        language: "",
        status: "",
        page: 1,
        per_page: 20,
        total_items: 0,
        total_pages: 0,
        currentRequestId: 0,
        filtersLoaded: false
    };

    let debounceTimer = null;
    let activePlayingChannelId = null;
    let activeModalChannel = null;

    /**
     * Synchronize URL query parameters with current active discovery and player state.
     */
    function syncUrlState(push = false) {
        if (window.location.protocol === "file:") return;
        const params = new URLSearchParams();
        if (state.q.trim()) params.set("q", state.q.trim());
        if (state.country) params.set("country", state.country);
        if (state.genre) params.set("genre", state.genre);
        if (state.language) params.set("language", state.language);
        if (state.status) params.set("status", state.status);
        if (state.page > 1) params.set("page", state.page.toString());
        if (activePlayingChannelId) params.set("channel", activePlayingChannelId.toString());

        const query = params.toString();
        const newUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
        const currentQuery = window.location.search.replace(/^\?/, "");

        if (currentQuery !== query) {
            if (push) {
                window.history.pushState({ ...state, channel: activePlayingChannelId }, "", newUrl);
            } else {
                window.history.replaceState({ ...state, channel: activePlayingChannelId }, "", newUrl);
            }
        }
    }

    // Synchronize player lifecycle events with URL state
    window.addEventListener("player:started", (e) => {
        if (e.detail && e.detail.channel) {
            activePlayingChannelId = e.detail.channel.id;
            syncUrlState(true);
        }
    });

    window.addEventListener("player:closed", () => {
        activePlayingChannelId = null;
        syncUrlState(false);
    });

    // Handle browser back/forward buttons (popstate)
    window.addEventListener("popstate", () => {
        if (window.location.protocol === "file:") return;
        const params = new URLSearchParams(window.location.search);
        state.q = params.get("q") || "";
        state.country = params.get("country") || "";
        state.genre = params.get("genre") || "";
        state.language = params.get("language") || "";
        state.status = params.get("status") || "";
        state.page = parseInt(params.get("page") || "1", 10) || 1;

        if (searchInput) {
            searchInput.value = state.q;
            if (clearSearchBtn) clearSearchBtn.style.display = state.q ? "flex" : "none";
        }
        if (filterCountry) filterCountry.value = state.country;
        if (filterGenre) filterGenre.value = state.genre;
        if (filterLanguage) filterLanguage.value = state.language;
        if (filterStatus) filterStatus.value = state.status;

        const urlChannelId = params.get("channel");
        if (urlChannelId) {
            const chId = parseInt(urlChannelId, 10);
            if (chId && chId !== activePlayingChannelId) {
                apiClient.get(`/api/channels/${chId}`)
                    .then(res => {
                        if (res && res.data && playerController && playerController.playChannel) {
                            playerController.playChannel(res.data);
                        }
                    })
                    .catch(() => {});
            }
        } else {
            if (activePlayingChannelId && playerController && playerController.closePlayer) {
                playerController.closePlayer();
            }
        }

        fetchChannels();
    });

    // Parse URL params on initial page load
    if (window.location.protocol !== "file:") {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get("q")) state.q = urlParams.get("q").trim();
        if (urlParams.get("country")) state.country = urlParams.get("country").trim();
        if (urlParams.get("genre")) state.genre = urlParams.get("genre").trim();
        if (urlParams.get("language")) state.language = urlParams.get("language").trim();
        if (urlParams.get("status")) state.status = urlParams.get("status").trim();
        if (urlParams.get("page")) {
            const p = parseInt(urlParams.get("page"), 10);
            if (!isNaN(p) && p >= 1) state.page = p;
        }

        if (searchInput && state.q) searchInput.value = state.q;
        if (clearSearchBtn && state.q) clearSearchBtn.style.display = "flex";
        if (filterStatus && state.status) filterStatus.value = state.status;

        // Auto-play deep-linked channel parameter if provided (e.g. ?channel=5)
        const initialChannelParam = urlParams.get("channel");
        if (initialChannelParam) {
            const chId = parseInt(initialChannelParam, 10);
            if (!isNaN(chId) && chId > 0) {
                apiClient.get(`/api/channels/${chId}`)
                    .then(res => {
                        if (res && res.data && playerController && playerController.playChannel) {
                            playerController.playChannel(res.data);
                        }
                    })
                    .catch(err => {
                        console.warn("Could not auto-load deep-linked channel:", err);
                    });
            }
        }
    }

    /**
     * Load dynamic taxonomy filters from /api/filters
     */
    async function loadFilterMetadata() {
        if (state.filtersLoaded) return;

        try {
            const data = await apiClient.get("/api/filters");

            // Populate Countries
            if (filterCountry && Array.isArray(data.countries)) {
                filterCountry.innerHTML = '<option value="">All Countries</option>';
                data.countries.forEach(c => {
                    const opt = document.createElement("option");
                    opt.value = c.code;
                    opt.textContent = `${getCountryFlag(c.code)} ${c.name} (${c.code})`;
                    filterCountry.appendChild(opt);
                });
                if (state.country) filterCountry.value = state.country;
            }

            // Populate Genres
            if (filterGenre && Array.isArray(data.genres)) {
                filterGenre.innerHTML = '<option value="">All Categories</option>';
                data.genres.forEach(g => {
                    const opt = document.createElement("option");
                    opt.value = g.slug;
                    opt.textContent = g.name;
                    filterGenre.appendChild(opt);
                });
                if (state.genre) filterGenre.value = state.genre;
            }

            // Populate Languages
            if (filterLanguage && Array.isArray(data.languages)) {
                filterLanguage.innerHTML = '<option value="">All Languages</option>';
                data.languages.forEach(l => {
                    const opt = document.createElement("option");
                    opt.value = l.code;
                    opt.textContent = `${l.name} (${l.code})`;
                    filterLanguage.appendChild(opt);
                });
                if (state.language) filterLanguage.value = state.language;
            }

            state.filtersLoaded = true;
        } catch (err) {
            console.warn("Could not load dynamic filter options:", err);
        }
    }

    /**
     * Fetch channel catalog matching active state and render cards
     */
    async function fetchChannels() {
        state.currentRequestId++;
        const requestId = state.currentRequestId;

        // UI Loading State
        if (skeletonGrid) skeletonGrid.style.display = "grid";
        if (channelGrid) channelGrid.style.display = "none";
        if (emptyState) emptyState.style.display = "none";
        if (errorState) errorState.style.display = "none";
        if (paginationNav) paginationNav.style.display = "none";
        if (resultsSummary) resultsSummary.textContent = "Querying live catalog...";

        // Build query string params
        const params = {};
        if (state.q.trim()) params.q = state.q.trim();
        if (state.country.trim()) params.country = state.country.trim();
        if (state.genre.trim()) params.genre = state.genre.trim();
        if (state.language.trim()) params.language = state.language.trim();
        if (state.status.trim()) params.status = state.status.trim();
        params.page = state.page.toString();
        params.per_page = state.per_page.toString();

        try {
            const payload = await apiClient.get("/api/channels", params);

            // Ignore stale responses if a newer request was dispatched
            if (requestId !== state.currentRequestId) return;

            // Update pagination state
            const pag = payload.pagination || {};
            state.total_items = pag.total_items || 0;
            state.total_pages = pag.total_pages || 0;
            state.page = pag.page || 1;

            if (skeletonGrid) skeletonGrid.style.display = "none";

            renderActiveChips();
            updateClearFiltersButton();

            const channels = payload.data || [];

            if (channels.length === 0) {
                // Empty State
                if (channelGrid) channelGrid.style.display = "none";
                if (paginationNav) paginationNav.style.display = "none";
                if (emptyState) emptyState.style.display = "block";
                if (resultsSummary) resultsSummary.textContent = "0 channels found";

                if (emptyStateMessage) {
                    if (state.q) {
                        emptyStateMessage.textContent = `No channels found matching "${state.q}". Try adjusting your keywords or clearing filters.`;
                    } else {
                        emptyStateMessage.textContent = "No channels match the selected filter combination. Try resetting your filters.";
                    }
                }
                announceToScreenReader("0 channels found matching active filters");
            } else {
                // Success State with results
                if (emptyState) emptyState.style.display = "none";
                renderChannelCards(channels);
                if (channelGrid) channelGrid.style.display = "grid";

                // Update summary text
                const startIdx = (state.page - 1) * state.per_page + 1;
                const endIdx = Math.min(startIdx + channels.length - 1, state.total_items);
                if (resultsSummary) {
                    resultsSummary.innerHTML = `Showing <strong>${startIdx}–${endIdx}</strong> of <strong>${state.total_items}</strong> channels`;
                }

                // Render pagination
                renderPagination(pag);

                announceToScreenReader(`Showing ${startIdx} to ${endIdx} of ${state.total_items} channels`);
            }

            syncUrlState(false);
        } catch (error) {
            if (requestId !== state.currentRequestId) return;

            if (skeletonGrid) skeletonGrid.style.display = "none";
            if (channelGrid) channelGrid.style.display = "none";
            if (paginationNav) paginationNav.style.display = "none";
            if (emptyState) emptyState.style.display = "none";
            if (errorState) errorState.style.display = "block";
            if (resultsSummary) resultsSummary.textContent = "Unable to load channels";

            if (errorMessage) {
                errorMessage.textContent = `Error connecting to REST API: ${error.message}`;
            }
            announceToScreenReader("Error connecting to channel catalog API");
        }
    }

    /**
     * Safely render channel cards using DOM construction (strictly XSS-safe)
     */
    function renderChannelCards(channels) {
        if (!channelGrid) return;
        channelGrid.innerHTML = "";

        channels.forEach(channel => {
            const card = document.createElement("article");
            card.className = "channel-card";
            card.setAttribute("tabindex", "0");
            card.setAttribute("role", "button");
            card.setAttribute("aria-label", `Watch ${channel.name} live stream`);

            // Top Row: Logo & Health Status
            const topRow = document.createElement("div");
            topRow.className = "channel-card-top";

            const logoContainer = document.createElement("div");
            logoContainer.className = "channel-logo-container";
            renderChannelLogo(logoContainer, channel);

            const statusInfo = formatHealthStatus(channel.health_status);
            const statusBadge = document.createElement("div");
            statusBadge.className = `status-badge ${statusInfo.class}`;
            const dot = document.createElement("span");
            dot.className = "dot";
            const statusText = document.createElement("span");
            statusText.textContent = statusInfo.label;
            statusBadge.appendChild(dot);
            statusBadge.appendChild(statusText);

            topRow.appendChild(logoContainer);
            topRow.appendChild(statusBadge);
            card.appendChild(topRow);

            // Channel Title
            const title = document.createElement("h3");
            title.className = "channel-title";
            title.textContent = channel.name;
            title.title = channel.name;
            card.appendChild(title);

            // Meta Row: Country Flag, Genres, Language
            const metaRow = document.createElement("div");
            metaRow.className = "channel-meta-row";

            // Country Pill
            if (channel.country && channel.country.code) {
                const countryPill = document.createElement("span");
                countryPill.className = "country-pill";
                countryPill.textContent = `${getCountryFlag(channel.country.code)} ${channel.country.name || channel.country.code}`;
                metaRow.appendChild(countryPill);
            }

            // Genre Pills (up to 2)
            if (Array.isArray(channel.genres)) {
                channel.genres.slice(0, 2).forEach(g => {
                    const genrePill = document.createElement("span");
                    genrePill.className = "genre-pill";
                    genrePill.textContent = g.name;
                    metaRow.appendChild(genrePill);
                });
            }

            // Language Pill (if present)
            if (Array.isArray(channel.languages) && channel.languages.length > 0) {
                const langPill = document.createElement("span");
                langPill.className = "lang-pill";
                langPill.textContent = channel.languages[0].code;
                metaRow.appendChild(langPill);
            }

            card.appendChild(metaRow);

            // Actions Row
            const actionsRow = document.createElement("div");
            actionsRow.className = "card-actions-row";

            const btnPlay = document.createElement("button");
            btnPlay.type = "button";
            btnPlay.className = "btn-card-action primary";
            btnPlay.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                <span>Watch Live</span>
            `;

            const btnDetails = document.createElement("button");
            btnDetails.type = "button";
            btnDetails.className = "btn-card-action secondary";
            btnDetails.title = "View Stream Diagnostics & URL";
            btnDetails.setAttribute("aria-label", "Stream Diagnostics");
            btnDetails.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="16" x2="12" y2="12"></line>
                    <line x1="12" y1="8" x2="12.01" y2="8"></line>
                </svg>
            `;

            // Action Handlers
            const watchLiveHandler = (e) => {
                e.stopPropagation();
                if (playerController && playerController.playChannel) {
                    playerController.playChannel(channel);
                } else if (window.openVideoPlayer) {
                    window.openVideoPlayer(channel);
                }
            };

            const detailsHandler = (e) => {
                e.stopPropagation();
                openChannelModal(channel.id);
            };

            btnPlay.addEventListener("click", watchLiveHandler);
            btnDetails.addEventListener("click", detailsHandler);
            card.addEventListener("click", watchLiveHandler);
            card.addEventListener("keydown", (e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    watchLiveHandler(e);
                }
            });

            actionsRow.appendChild(btnPlay);
            actionsRow.appendChild(btnDetails);
            card.appendChild(actionsRow);

            channelGrid.appendChild(card);
        });
    }

    /**
     * Render channel logo with visual fallback handling
     */
    function renderChannelLogo(container, channel) {
        container.innerHTML = "";
        const logoUrl = channel.logo_url;

        const hasValidUrl = logoUrl && (logoUrl.startsWith("http://") || logoUrl.startsWith("https://"));

        if (hasValidUrl) {
            const img = document.createElement("img");
            img.className = "channel-logo-img";
            img.src = logoUrl;
            img.alt = `${channel.name} logo`;
            img.loading = "lazy";

            img.onerror = () => {
                renderInitialsFallback(container, channel.name);
            };

            container.appendChild(img);
        } else {
            renderInitialsFallback(container, channel.name);
        }
    }

    /**
     * Create stylized initial avatar fallback
     */
    function renderInitialsFallback(container, channelName) {
        container.innerHTML = "";
        const fallback = document.createElement("div");
        fallback.className = "channel-logo-fallback";
        const initial = (channelName || "TV").trim().charAt(0).toUpperCase();
        fallback.textContent = initial;
        container.appendChild(fallback);
    }

    /**
     * Render active filter tags/chips
     */
    function renderActiveChips() {
        if (!activeChips) return;
        activeChips.innerHTML = "";

        const createChip = (label, onRemove) => {
            const chip = document.createElement("div");
            chip.className = "filter-chip";
            
            const span = document.createElement("span");
            span.textContent = label;
            chip.appendChild(span);

            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.className = "chip-remove-btn";
            removeBtn.innerHTML = "&times;";
            removeBtn.setAttribute("aria-label", `Remove ${label} filter`);
            removeBtn.addEventListener("click", onRemove);
            chip.appendChild(removeBtn);

            activeChips.appendChild(chip);
        };

        if (state.q) {
            createChip(`"${state.q}"`, () => {
                state.q = "";
                if (searchInput) searchInput.value = "";
                if (clearSearchBtn) clearSearchBtn.style.display = "none";
                state.page = 1;
                syncUrlState(true);
                fetchChannels();
            });
        }

        if (state.country) {
            const countryName = filterCountry?.selectedOptions[0]?.textContent || state.country;
            createChip(countryName, () => {
                state.country = "";
                if (filterCountry) filterCountry.value = "";
                state.page = 1;
                syncUrlState(true);
                fetchChannels();
            });
        }

        if (state.genre) {
            const genreName = filterGenre?.selectedOptions[0]?.textContent || state.genre;
            createChip(genreName, () => {
                state.genre = "";
                if (filterGenre) filterGenre.value = "";
                state.page = 1;
                syncUrlState(true);
                fetchChannels();
            });
        }

        if (state.language) {
            const langName = filterLanguage?.selectedOptions[0]?.textContent || state.language;
            createChip(langName, () => {
                state.language = "";
                if (filterLanguage) filterLanguage.value = "";
                state.page = 1;
                syncUrlState(true);
                fetchChannels();
            });
        }

        if (state.status) {
            const statusInfo = formatHealthStatus(state.status);
            createChip(statusInfo.label, () => {
                state.status = "";
                if (filterStatus) filterStatus.value = "";
                state.page = 1;
                syncUrlState(true);
                fetchChannels();
            });
        }
    }

    /**
     * Update clear-filters button disabled/active state
     */
    function updateClearFiltersButton() {
        if (!clearFiltersBtn) return;
        const hasActiveFilter = Boolean(state.q || state.country || state.genre || state.language || state.status);
        clearFiltersBtn.disabled = !hasActiveFilter;
    }

    /**
     * Render pagination controls
     */
    function renderPagination(pagination) {
        if (!paginationNav) return;

        const totalPages = pagination.total_pages || 1;
        const currentPage = pagination.page || 1;

        if (totalPages <= 1) {
            paginationNav.style.display = "none";
            return;
        }

        paginationNav.style.display = "flex";

        if (btnPrevPage) {
            btnPrevPage.disabled = !pagination.has_prev;
            btnPrevPage.onclick = () => {
                if (state.page > 1) {
                    state.page--;
                    syncUrlState(true);
                    fetchChannels();
                    scrollToDirectory();
                }
            };
        }

        if (btnNextPage) {
            btnNextPage.disabled = !pagination.has_next;
            btnNextPage.onclick = () => {
                if (state.page < totalPages) {
                    state.page++;
                    syncUrlState(true);
                    fetchChannels();
                    scrollToDirectory();
                }
            };
        }

        if (pageIndicators) {
            pageIndicators.innerHTML = "";

            let startPage = Math.max(1, currentPage - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            if (endPage - startPage < 4) {
                startPage = Math.max(1, endPage - 4);
            }

            if (startPage > 1) {
                appendPageBtn(1, currentPage);
                if (startPage > 2) {
                    const ell = document.createElement("span");
                    ell.className = "page-ellipsis";
                    ell.textContent = "...";
                    pageIndicators.appendChild(ell);
                }
            }

            for (let p = startPage; p <= endPage; p++) {
                appendPageBtn(p, currentPage);
            }

            if (endPage < totalPages) {
                if (endPage < totalPages - 1) {
                    const ell = document.createElement("span");
                    ell.className = "page-ellipsis";
                    ell.textContent = "...";
                    pageIndicators.appendChild(ell);
                }
                appendPageBtn(totalPages, currentPage);
            }
        }
    }

    function appendPageBtn(pageNumber, currentPage) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `page-btn ${pageNumber === currentPage ? "active" : ""}`;
        btn.textContent = pageNumber.toString();
        btn.setAttribute("aria-label", `Go to page ${pageNumber}`);
        btn.onclick = () => {
            if (state.page !== pageNumber) {
                state.page = pageNumber;
                syncUrlState(true);
                fetchChannels();
                scrollToDirectory();
            }
        };
        pageIndicators.appendChild(btn);
    }

    function scrollToDirectory() {
        const target = document.querySelector(".discovery-toolbar") || channelGrid;
        if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    /**
     * Modal Dialog: Inspect Single Channel Details
     */
    async function openChannelModal(channelId) {
        if (!channelModal) return;

        if (modalChannelTitle) modalChannelTitle.textContent = "Loading...";
        if (modalLogoContainer) modalLogoContainer.innerHTML = "";
        if (modalMetaRow) modalMetaRow.innerHTML = "";
        if (modalStreamUrl) modalStreamUrl.textContent = "Fetching stream metadata...";
        if (modalChecksList) modalChecksList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.82rem;">Retrieving health audits...</div>';

        channelModal.classList.add("open");
        announceToScreenReader("Channel details dialog opened");

        try {
            const data = await apiClient.get(`/api/channels/${channelId}`);
            const ch = data.data;
            activeModalChannel = ch;

            if (modalChannelTitle) modalChannelTitle.textContent = ch.name;
            if (modalLogoContainer) renderChannelLogo(modalLogoContainer, ch);

            // Modal Meta Pills
            if (modalMetaRow) {
                modalMetaRow.innerHTML = "";
                const st = formatHealthStatus(ch.health_status);
                const stBadge = document.createElement("span");
                stBadge.className = `status-badge ${st.class}`;
                stBadge.innerHTML = `<span class="dot"></span><span>${st.label}</span>`;
                modalMetaRow.appendChild(stBadge);

                if (ch.country && ch.country.code) {
                    const cPill = document.createElement("span");
                    cPill.className = "country-pill";
                    cPill.textContent = `${getCountryFlag(ch.country.code)} ${ch.country.name}`;
                    modalMetaRow.appendChild(cPill);
                }

                if (Array.isArray(ch.genres)) {
                    ch.genres.forEach(g => {
                        const gPill = document.createElement("span");
                        gPill.className = "genre-pill";
                        gPill.textContent = g.name;
                        modalMetaRow.appendChild(gPill);
                    });
                }

                // Add "Watch Stream Now" button directly in Details modal
                const watchBtn = document.createElement("button");
                watchBtn.type = "button";
                watchBtn.className = "btn-card-action primary";
                watchBtn.style.padding = "0.3rem 0.85rem";
                watchBtn.style.marginLeft = "0.5rem";
                watchBtn.innerHTML = `<span>▶ Watch Now</span>`;
                watchBtn.onclick = () => {
                    closeModal();
                    if (playerController && playerController.playChannel) {
                        playerController.playChannel(ch);
                    } else if (window.openVideoPlayer) {
                        window.openVideoPlayer(ch);
                    }
                };
                modalMetaRow.appendChild(watchBtn);
            }

            // Stream URL
            if (modalStreamUrl) {
                modalStreamUrl.textContent = ch.stream_url;
            }

            // Copy Action
            if (btnCopyStreamUrl) {
                btnCopyStreamUrl.textContent = "Copy";
                btnCopyStreamUrl.onclick = async () => {
                    try {
                        await navigator.clipboard.writeText(ch.stream_url);
                        btnCopyStreamUrl.textContent = "Copied!";
                        setTimeout(() => { btnCopyStreamUrl.textContent = "Copy"; }, 2000);
                    } catch {
                        btnCopyStreamUrl.textContent = "Failed";
                    }
                };
            }

            // Health Checks List
            if (modalChecksList) {
                modalChecksList.innerHTML = "";
                const checks = ch.recent_checks || [];
                if (checks.length === 0) {
                    modalChecksList.innerHTML = `
                        <div class="check-item">
                            <span style="color: var(--text-muted);">No automated checks recorded yet.</span>
                            <span class="status-badge unknown"><span class="dot"></span><span>Unchecked</span></span>
                        </div>
                    `;
                } else {
                    checks.forEach(check => {
                        const item = document.createElement("div");
                        item.className = "check-item";

                        const timeSpan = document.createElement("span");
                        timeSpan.className = "check-item-time";
                        timeSpan.textContent = `${formatDateTime(check.checked_at)} ${check.response_time_ms ? `(${Math.round(check.response_time_ms)}ms)` : ""}`;

                        const statusWrap = document.createElement("div");
                        statusWrap.className = "check-item-status";

                        if (check.diagnostic_reason) {
                            const reasonSpan = document.createElement("span");
                            reasonSpan.style.cssText = "color: var(--text-secondary); font-size: 0.75rem; margin-right: 0.5rem;";
                            reasonSpan.textContent = check.diagnostic_reason;
                            statusWrap.appendChild(reasonSpan);
                        }

                        const chkStatus = formatHealthStatus(check.outcome);
                        const chkBadge = document.createElement("span");
                        chkBadge.className = `status-badge ${chkStatus.class}`;
                        chkBadge.innerHTML = `<span class="dot"></span><span>${chkStatus.label}</span>`;
                        statusWrap.appendChild(chkBadge);

                        item.appendChild(timeSpan);
                        item.appendChild(statusWrap);
                        modalChecksList.appendChild(item);
                    });
                }
            }
        } catch (err) {
            if (modalChannelTitle) modalChannelTitle.textContent = "Failed to load channel";
            if (modalStreamUrl) modalStreamUrl.textContent = `Error: ${err.message}`;
        }
    }

    function closeModal() {
        if (channelModal) {
            channelModal.classList.remove("open");
            announceToScreenReader("Channel details dialog closed");
        }
    }

    if (btnModalClose) btnModalClose.addEventListener("click", closeModal);
    if (channelModal) {
        channelModal.addEventListener("click", (e) => {
            if (e.target === channelModal) closeModal();
        });
    }

    if (btnReportFromDetails) {
        btnReportFromDetails.addEventListener("click", () => {
            if (activeModalChannel && reportController) {
                closeModal();
                reportController.openReportModal(activeModalChannel);
            }
        });
    }

    /**
     * Reset all active search & filter states
     */
    function resetAllFilters() {
        state.q = "";
        state.country = "";
        state.genre = "";
        state.language = "";
        state.status = "";
        state.page = 1;

        if (searchInput) searchInput.value = "";
        if (clearSearchBtn) clearSearchBtn.style.display = "none";
        if (filterCountry) filterCountry.value = "";
        if (filterGenre) filterGenre.value = "";
        if (filterLanguage) filterLanguage.value = "";
        if (filterStatus) filterStatus.value = "";

        syncUrlState(true);
        fetchChannels();
    }

    // Attach Event Listeners
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            const query = e.target.value;
            if (clearSearchBtn) {
                clearSearchBtn.style.display = query.length > 0 ? "flex" : "none";
            }

            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                state.q = query;
                state.page = 1;
                syncUrlState(true);
                fetchChannels();
            }, 300);
        });
    }

    if (clearSearchBtn) {
        clearSearchBtn.addEventListener("click", () => {
            if (searchInput) searchInput.value = "";
            clearSearchBtn.style.display = "none";
            state.q = "";
            state.page = 1;
            syncUrlState(true);
            fetchChannels();
        });
    }

    if (filterCountry) {
        filterCountry.addEventListener("change", (e) => {
            state.country = e.target.value;
            state.page = 1;
            syncUrlState(true);
            fetchChannels();
        });
    }

    if (filterGenre) {
        filterGenre.addEventListener("change", (e) => {
            state.genre = e.target.value;
            state.page = 1;
            syncUrlState(true);
            fetchChannels();
        });
    }

    if (filterLanguage) {
        filterLanguage.addEventListener("change", (e) => {
            state.language = e.target.value;
            state.page = 1;
            syncUrlState(true);
            fetchChannels();
        });
    }

    if (filterStatus) {
        filterStatus.addEventListener("change", (e) => {
            state.status = e.target.value;
            state.page = 1;
            syncUrlState(true);
            fetchChannels();
        });
    }

    if (clearFiltersBtn) clearFiltersBtn.addEventListener("click", resetAllFilters);
    if (emptyResetBtn) emptyResetBtn.addEventListener("click", resetAllFilters);
    if (retryBtn) retryBtn.addEventListener("click", fetchChannels);

    // Initial Load Sequence
    loadFilterMetadata();
    fetchChannels();
}

/**
 * Step 7: Anonymous Stream Issue Reporting Controller
 */
function initIssueReporting() {
    const reportModal = document.getElementById("reportModal");
    const btnReportClose = document.getElementById("btnReportClose");
    const btnCancelReport = document.getElementById("btnCancelReport");
    const btnSubmitReport = document.getElementById("btnSubmitReport");
    const reportIssueForm = document.getElementById("reportIssueForm");
    const reportChannelId = document.getElementById("reportChannelId");
    const reportTargetChannelName = document.getElementById("reportTargetChannelName");
    const reportIssueType = document.getElementById("reportIssueType");
    const reportDescription = document.getElementById("reportDescription");
    const reportFeedbackMessage = document.getElementById("reportFeedbackMessage");

    let currentChannel = null;

    function openReportModal(channel) {
        if (!channel || !reportModal) return;
        currentChannel = channel;

        if (reportChannelId) reportChannelId.value = channel.id;
        if (reportTargetChannelName) reportTargetChannelName.textContent = channel.name;
        if (reportIssueType) reportIssueType.value = "";
        if (reportDescription) reportDescription.value = "";

        if (reportFeedbackMessage) {
            reportFeedbackMessage.className = "report-feedback";
            reportFeedbackMessage.style.display = "none";
            reportFeedbackMessage.textContent = "";
        }

        if (btnSubmitReport) {
            btnSubmitReport.disabled = false;
            btnSubmitReport.textContent = "Submit Anonymous Report";
        }

        reportModal.classList.add("open");
        if (reportIssueType) reportIssueType.focus();
        announceToScreenReader(`Issue report dialog opened for ${channel.name}`);
    }

    function closeReportModal() {
        if (reportModal) {
            reportModal.classList.remove("open");
            announceToScreenReader("Issue report dialog closed");
        }
    }

    async function handleReportSubmit(e) {
        if (e) e.preventDefault();
        if (!currentChannel || !reportChannelId || !reportIssueType) return;

        const channelId = reportChannelId.value;
        const issueType = reportIssueType.value;
        const description = reportDescription ? reportDescription.value.trim() : "";

        if (!issueType) {
            if (reportFeedbackMessage) {
                reportFeedbackMessage.className = "report-feedback error";
                reportFeedbackMessage.textContent = "Please select an issue category from the list.";
                reportFeedbackMessage.style.display = "block";
            }
            return;
        }

        if (btnSubmitReport) {
            btnSubmitReport.disabled = true;
            btnSubmitReport.textContent = "Submitting...";
        }

        try {
            const result = await apiClient.post(`/api/channels/${channelId}/report`, {
                issue_type: issueType,
                description: description
            });

            if (reportFeedbackMessage) {
                reportFeedbackMessage.className = "report-feedback success";
                reportFeedbackMessage.textContent = result.message || "Thank you! Your issue report has been recorded anonymously.";
                reportFeedbackMessage.style.display = "block";
            }

            announceToScreenReader("Issue report submitted successfully");

            setTimeout(() => {
                closeReportModal();
            }, 1800);
        } catch (err) {
            if (reportFeedbackMessage) {
                reportFeedbackMessage.className = "report-feedback error";
                reportFeedbackMessage.textContent = err.message || "Failed to submit report. Please try again.";
                reportFeedbackMessage.style.display = "block";
            }
            if (btnSubmitReport) {
                btnSubmitReport.disabled = false;
                btnSubmitReport.textContent = "Submit Anonymous Report";
            }
        }
    }

    if (btnReportClose) btnReportClose.addEventListener("click", closeReportModal);
    if (btnCancelReport) btnCancelReport.addEventListener("click", closeReportModal);
    if (reportModal) {
        reportModal.addEventListener("click", (e) => {
            if (e.target === reportModal) closeReportModal();
        });
    }
    if (reportIssueForm) {
        reportIssueForm.addEventListener("submit", handleReportSubmit);
    }
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && reportModal && reportModal.classList.contains("open")) {
            closeReportModal();
        }
    });

    return {
        openReportModal,
        closeReportModal
    };
}

/**
 * Initialize health monitoring and diagnostic display.
 */
function initHealthMonitoring() {
    const diagnosticOutput = document.getElementById("diagnosticOutput");
    const refreshBtn = document.getElementById("btnRefreshHealth");
    const healthBadge = document.getElementById("systemHealthBadge");

    async function checkHealth() {
        if (diagnosticOutput) {
            diagnosticOutput.textContent = "Querying /api/health endpoint...";
        }

        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.textContent = "Checking...";
        }

        try {
            const data = await apiClient.get("/api/health", {}, { timeout: 4000 });

            if (diagnosticOutput) {
                diagnosticOutput.textContent = JSON.stringify(data, null, 2);
            }

            if (healthBadge) {
                const dot = healthBadge.querySelector(".status-dot");
                const label = healthBadge.querySelector(".status-label");
                if (dot && label) {
                    const isHealthy = data.status === "healthy";
                    dot.className = "status-dot " + (isHealthy ? "healthy" : "degraded");
                    label.textContent = isHealthy ? "Operational" : "Degraded";
                }
            }
        } catch (error) {
            const isFile = window.location.protocol === "file:";
            const fallbackMessage = isFile
                ? `{\n  "status": "preview_mode",\n  "environment": "Local File Preview",\n  "backend_url": "${getApiBaseUrl()}/api/health",\n  "note": "To connect live backend, ensure Flask is running via: python run.py",\n  "error": "${error.message}"\n}`
                : `{\n  "status": "unavailable",\n  "error": "Failed to connect to health endpoint: ${error.message}"\n}`;

            if (diagnosticOutput) {
                diagnosticOutput.textContent = fallbackMessage;
            }

            if (healthBadge) {
                const dot = healthBadge.querySelector(".status-dot");
                const label = healthBadge.querySelector(".status-label");
                if (dot && label) {
                    dot.className = "status-dot " + (isFile ? "degraded" : "unavailable");
                    label.textContent = isFile ? "Local Preview" : "Offline";
                }
            }
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.textContent = "Check Health";
            }
        }
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", (e) => {
            e.preventDefault();
            checkHealth();
        });
    }

    checkHealth();
}
