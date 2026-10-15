(() => {
  const token = getCookie("access_token");
  const loginNav = document.getElementById("nav-login");
  const registerNav = document.getElementById("nav-register");
  const logoutNav = document.getElementById("nav-logout");
  const logoutButton = document.getElementById("logoutButton");

  if (loginNav) loginNav.hidden = Boolean(token);
  if (registerNav) registerNav.hidden = Boolean(token);
  if (logoutNav) logoutNav.hidden = !token;
  logoutButton?.addEventListener("click", () => {
    document.cookie = "access_token=; Max-Age=0; path=/";
    window.location.href = "/";
  });

  const trackGrid = document.getElementById("trackGrid");
  const catalogStatus = document.getElementById("catalogStatus");
  const playlistGrid = document.getElementById("playlistGrid");
  const playlistStatus = document.getElementById("playlistStatus");
  const playlistForm = document.getElementById("playlistForm");

  if (!trackGrid || !catalogStatus || !playlistGrid || !playlistStatus || !playlistForm) return;

  let tracks = [];
  loadTracks();
  if (token) {
    loadPlaylists();
  } else {
    playlistStatus.textContent = "Log in to save and manage your playlists.";
  }

  playlistForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!token) {
      playlistStatus.textContent = "Log in to create a playlist.";
      return;
    }

    const selectedIds = Array.from(trackGrid.querySelectorAll(".track-select:checked"))
      .map((input) => Number(input.value));
    if (selectedIds.length === 0) {
      setStatus(playlistStatus, "Choose at least one track from the catalog first.", true);
      return;
    }

    const name = new FormData(playlistForm).get("name");
    try {
      await apiRequest("/music/playlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, track_ids: selectedIds }),
      });
      playlistForm.reset();
      trackGrid.querySelectorAll(".track-select:checked").forEach((input) => {
        input.checked = false;
      });
      setStatus(playlistStatus, "Playlist created.");
      await loadPlaylists();
    } catch (error) {
      setStatus(playlistStatus, error.message, true);
    }
  });

  playlistGrid.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-target-explicit]");
    if (!button) return;

    button.disabled = true;
    try {
      const playlistId = button.dataset.playlistId;
      const targetExplicit = button.dataset.targetExplicit === "true";
      await apiRequest(`/music/playlists/${playlistId}/variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `${button.dataset.playlistName} (${targetExplicit ? "Explicit" : "Clean"})`,
          target_explicit: targetExplicit,
        }),
      });
      setStatus(playlistStatus, "Playlist version created.");
      await loadPlaylists();
    } catch (error) {
      setStatus(playlistStatus, error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  async function loadTracks() {
    try {
      tracks = await apiRequest("/music/tracks");
      renderTracks();
      setStatus(catalogStatus, `${tracks.length} tracks in the catalog.`);
    } catch (error) {
      setStatus(catalogStatus, `Could not load tracks: ${error.message}`, true);
    }
  }

  async function loadPlaylists() {
    try {
      const playlists = await apiRequest("/music/playlists");
      renderPlaylists(playlists);
      if (playlists.length === 0) {
        setStatus(playlistStatus, "Select tracks above and create your first playlist.");
      }
    } catch (error) {
      setStatus(playlistStatus, `Could not load your playlists: ${error.message}`, true);
    }
  }

  function renderTracks() {
    trackGrid.replaceChildren();
    tracks.forEach((track, index) => {
      const card = document.createElement("label");
      card.className = "track-card";

      const art = document.createElement("span");
      art.className = "track-art";
      art.setAttribute("aria-hidden", "true");
      art.textContent = String(index + 1).padStart(2, "0");

      const info = document.createElement("span");
      info.className = "track-info";
      const title = document.createElement("span");
      title.className = "track-info-title";
      title.textContent = track.title;
      const heading = document.createElement("h3");
      heading.append(title);
      const artist = document.createElement("p");
      artist.textContent = track.artist;
      info.append(heading, artist);
      if (track.explicit) {
        const badge = document.createElement("span");
        badge.className = "explicit-badge";
        badge.textContent = "EXPLICIT";
        info.append(badge);
      } else {
        const badge = document.createElement("span");
        badge.className = "explicit-badge";
        badge.textContent = "CLEAN";
        info.append(badge);
      }

      const checkbox = document.createElement("input");
      checkbox.className = "track-select";
      checkbox.type = "checkbox";
      checkbox.value = track.id;
      checkbox.setAttribute("aria-label", `Add ${track.title} to your playlist`);

      card.append(art, info, checkbox);
      trackGrid.append(card);
    });
  }

  function renderPlaylists(playlists) {
    playlistGrid.replaceChildren();
    playlists.forEach((playlist) => {
      const card = document.createElement("article");
      card.className = "playlist-card";

      const title = document.createElement("h3");
      title.textContent = playlist.name;
      const details = document.createElement("p");
      const trackCount = playlist.tracks.length;
      details.textContent = `${trackCount} ${trackCount === 1 ? "track" : "tracks"}`;
      card.append(title, details);

      if (playlist.tracks.length > 0) {
        const list = document.createElement("ul");
        list.className = "playlist-tracks";
        playlist.tracks.forEach((track) => {
          const item = document.createElement("li");
          item.textContent = `${track.title} · ${track.artist}${track.explicit ? " · Explicit" : " · Clean"}`;
          list.append(item);
        });
        card.append(list);
      }

      const actions = document.createElement("div");
      actions.className = "playlist-actions";
      actions.append(
        makeVariantButton(playlist, false),
        makeVariantButton(playlist, true),
      );
      card.append(actions);
      playlistGrid.append(card);
    });
  }

  function makeVariantButton(playlist, targetExplicit) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-primary";
    button.dataset.playlistId = playlist.id;
    button.dataset.playlistName = playlist.name;
    button.dataset.targetExplicit = String(targetExplicit);
    button.textContent = targetExplicit ? "Make explicit version" : "Make clean version";
    return button;
  }

  async function apiRequest(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(url, { ...options, headers });
    const body = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      const detail = body?.detail ?? body?.message ?? response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  function setStatus(element, message, isError = false) {
    element.textContent = message;
    element.classList.toggle("is-error", isError);
  }

  function getCookie(name) {
    const prefix = `${name}=`;
    const cookie = document.cookie.split(";").map((item) => item.trim())
      .find((item) => item.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
  }
})();
