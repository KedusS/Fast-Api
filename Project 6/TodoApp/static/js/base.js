(() => {
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");

  loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = document.getElementById("authError");
    setError(error, "");
    const payload = new URLSearchParams(new FormData(loginForm));

    try {
      const response = await fetch("/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: payload,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(getErrorMessage(result));

      document.cookie = `access_token=${encodeURIComponent(result.access_token)}; Max-Age=1200; Path=/; SameSite=Lax`;
      window.location.href = "/";
    } catch (requestError) {
      setError(error, requestError.message || "Unable to log in. Please try again.");
    }
  });

  registerForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = document.getElementById("authError");
    setError(error, "");
    const form = new FormData(registerForm);

    if (form.get("password") !== form.get("password2")) {
      setError(error, "Passwords do not match.");
      return;
    }

    const payload = {
      email: form.get("email"),
      username: form.get("username"),
      first_name: form.get("firstname"),
      last_name: form.get("lastname"),
      password: form.get("password"),
      role: "user",
      phone_number: "",
    };

    try {
      const response = await fetch("/auth/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = response.status === 204 ? null : await response.json();
      if (!response.ok) throw new Error(getErrorMessage(result));

      window.location.href = "/auth/login-page";
    } catch (requestError) {
      setError(error, requestError.message || "Unable to create an account. Please try again.");
    }
  });

  function getErrorMessage(payload) {
    const detail = payload?.detail ?? payload?.message;
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
    return "The request could not be completed.";
  }

  function setError(element, message) {
    if (!element) return;
    element.textContent = message;
    element.hidden = !message;
  }
})();
