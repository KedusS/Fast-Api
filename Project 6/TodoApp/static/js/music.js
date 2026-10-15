(() => {
  const token = getCookie("access_token");
  const loginNav = document.getElementById("nav-login");
  const registerNav = document.getElementById("nav-register");
  const logoutNav = document.getElementById("nav-logout");

  if (loginNav) loginNav.hidden = Boolean(token);
  if (registerNav) registerNav.hidden = Boolean(token);
  if (logoutNav) logoutNav.hidden = !token;
  logoutNav?.addEventListener("click", () => {
    document.cookie = "access_token=; Max-Age=0; path=/";
    window.location.href = "/";
  });

  const trackGrid = document.getElementById("trackGrid");
  const catalogStatus = document.getElementById("catalogStatus");
  const playlistGrid = document.getElementById("playlistGrid");
  const playlistStatus = document.getElementById("playlistStatus");
  const playlistForm = document.getElementById("playlistForm");
  const playlistSubmit = document.getElementById("playlistSubmit");
  const cancelPlaylistEdit = document.getElementById("cancelPlaylistEdit");
  const passwordForm = document.getElementById("passwordForm");
  const passwordStatus = document.getElementById("passwordStatus");

  if (!trackGrid || !catalogStatus || !playlistGrid || !playlistStatus || !playlistForm) return;

  let tracks = [];
  let editingPlaylistId = null;
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
      // Reuse the form for creating playlists and saving edits.
      const isEditing = editingPlaylistId !== null;
      await apiRequest(
        isEditing ? `/music/playlists/${editingPlaylistId}` : "/music/playlists",
        {
          method: isEditing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, track_ids: selectedIds }),
        },
      );
      resetPlaylistForm();
      setStatus(playlistStatus, isEditing ? "Playlist updated." : "Playlist created.");
      await loadPlaylists();
    } catch (error) {
      setStatus(playlistStatus, error.message, true);
    }
  });

  cancelPlaylistEdit?.addEventListener("click", () => {
    resetPlaylistForm();
    setStatus(playlistStatus, "Playlist edit cancelled.");
  });

  passwordForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(passwordForm);
    const newPassword = form.get("new_password");
    if (newPassword !== form.get("confirm_password")) {
      setStatus(passwordStatus, "The new passwords do not match.", true);
      return;
    }

    try {
      await apiRequest("/user/password", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          password: form.get("password"),
          new_password: newPassword,
        }),
      });
      passwordForm.reset();
      setStatus(passwordStatus, "Password updated.");
    } catch (error) {
      setStatus(passwordStatus, error.message, true);
    }
  });

  playlistGrid.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-target-explicit], [data-delete-playlist], [data-edit-playlist]");
    if (!button) return;

    if (button.hasAttribute("data-edit-playlist")) {
      startPlaylistEdit(button.dataset.playlistId);
      return;
    }

    button.disabled = true;
    try {
      const playlistId = button.dataset.playlistId;
      if (button.hasAttribute("data-delete-playlist")) {
        // Ask before making the destructive delete request.
        if (!window.confirm("Delete this playlist? This cannot be undone.")) return;
        await apiRequest(`/music/playlists/${playlistId}`, { method: "DELETE" });
        setStatus(playlistStatus, "Playlist deleted.");
        await loadPlaylists();
        return;
      }

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
      const row = document.createElement("tr");
      const number = document.createElement("td");
      number.textContent = String(index + 1);
      const title = document.createElement("td");
      title.textContent = track.title;
      const artist = document.createElement("td");
      artist.textContent = track.artist;
      const version = document.createElement("td");
      version.textContent = track.explicit ? "Explicit" : "Clean";
      const checkbox = document.createElement("input");
      checkbox.className = "track-select";
      checkbox.type = "checkbox";
      checkbox.value = track.id;
      checkbox.setAttribute("aria-label", `Add ${track.title} to your playlist`);
      const selection = document.createElement("td");
      selection.append(checkbox);
      row.append(number, title, artist, version, selection);
      trackGrid.append(row);
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
        makeEditButton(playlist),
        makeVariantButton(playlist, false),
        makeVariantButton(playlist, true),
        makeDeleteButton(playlist),
      );
      card.append(actions);
      playlistGrid.append(card);
    });
  }

  function makeEditButton(playlist) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-secondary";
    button.dataset.playlistId = playlist.id;
    button.dataset.editPlaylist = "";
    button.textContent = "Edit playlist";
    return button;
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

  function makeDeleteButton(playlist) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-primary";
    button.dataset.playlistId = playlist.id;
    button.dataset.deletePlaylist = "";
    button.textContent = "Delete playlist";
    return button;
  }

  async function startPlaylistEdit(playlistId) {
    try {
      const playlist = await apiRequest(`/music/playlists/${playlistId}`);
      editingPlaylistId = playlist.id;
      playlistForm.elements.name.value = playlist.name;
      // Reflect the saved songs in the catalog checkboxes for editing.
      const selectedTrackIds = new Set(playlist.tracks.map((track) => track.id));
      trackGrid.querySelectorAll(".track-select").forEach((input) => {
        input.checked = selectedTrackIds.has(Number(input.value));
      });
      playlistSubmit.textContent = "Save changes";
      cancelPlaylistEdit.hidden = false;
      setStatus(playlistStatus, "Update the name or selected tracks, then save changes.");
      document.getElementById("playlists").scrollIntoView({ behavior: "smooth" });
    } catch (error) {
      setStatus(playlistStatus, error.message, true);
    }
  }

  function resetPlaylistForm() {
    editingPlaylistId = null;
    playlistForm.reset();
    trackGrid.querySelectorAll(".track-select:checked").forEach((input) => {
      input.checked = false;
    });
    playlistSubmit.textContent = "Create playlist";
    cancelPlaylistEdit.hidden = true;
  }

  async function apiRequest(url, options = {}) {
    const headers = new Headers(options.headers || {});
    // Share authentication and API error handling across playlist actions.
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
