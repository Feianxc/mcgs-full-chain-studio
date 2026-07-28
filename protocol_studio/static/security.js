const authEnabled = document.querySelector('meta[name="auth-enabled"]')?.content === "true";
const csrfMeta = document.querySelector('meta[name="csrf-token"]');
const passwordChangeMeta = document.querySelector('meta[name="password-change-required"]');

function currentCsrfToken() {
  return csrfMeta?.content || "";
}

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const nativeFetch = window.fetch.bind(window);

window.fetch = async (input, init = {}) => {
  const inputUrl = input instanceof Request ? input.url : String(input);
  const url = new URL(inputUrl, window.location.href);
  const method = String(
    init.method || (input instanceof Request ? input.method : "GET"),
  ).toUpperCase();
  const options = { ...init };

  if (
    authEnabled &&
    url.origin === window.location.origin &&
    unsafeMethods.has(method) &&
    currentCsrfToken()
  ) {
    const headers = new Headers(
      init.headers || (input instanceof Request ? input.headers : undefined),
    );
    if (!headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", currentCsrfToken());
    }
    options.headers = headers;
  }

  const response = await nativeFetch(input, options);
  if (authEnabled && response.status === 401) {
    window.location.assign("/login?reason=session_expired");
  } else if (authEnabled && response.status === 403) {
    try {
      const payload = await response.clone().json();
      if (payload?.code === "password_change_required") {
        openPasswordDialog();
      }
    } catch (_error) {
      // Business callers keep ownership of non-JSON 403 responses.
    }
  }
  return response;
};

function openPasswordDialog() {
  const dialog = document.getElementById("passwordDialog");
  if (!dialog) {
    return;
  }
  document.getElementById("accountMenu")?.setAttribute("hidden", "");
  document.getElementById("accountMenuToggle")?.setAttribute("aria-expanded", "false");
  if (!dialog.open) {
    dialog.showModal();
  }
  window.setTimeout(() => document.getElementById("currentPassword")?.focus(), 30);
}

window.protocolSecurity = {
  csrfToken: currentCsrfToken,
  requirePasswordChange: openPasswordDialog,
};

if (window.lucide?.createIcons) {
  window.lucide.createIcons({
    attrs: { "aria-hidden": "true", "stroke-width": 1.8 },
  });
}

if (authEnabled) {
  const accountToggle = document.getElementById("accountMenuToggle");
  const accountMenu = document.getElementById("accountMenu");
  const changePasswordButton = document.getElementById("changePasswordBtn");
  const logoutButton = document.getElementById("logoutBtn");
  const passwordDialog = document.getElementById("passwordDialog");
  const passwordForm = document.getElementById("passwordForm");
  const passwordFeedback = document.getElementById("passwordFeedback");
  const passwordSubmit = document.getElementById("passwordSubmitBtn");
  const passwordClose = document.getElementById("passwordDialogClose");
  const passwordCancel = document.getElementById("passwordCancelBtn");
  const isForcedChange = passwordDialog?.dataset.forceChange === "true";

  function setPasswordFeedback(message, tone = "error") {
    if (!passwordFeedback) {
      return;
    }
    passwordFeedback.textContent = message || "";
    passwordFeedback.classList.toggle("is-success", tone === "success");
  }

  function closeAccountMenu() {
    accountMenu?.setAttribute("hidden", "");
    accountToggle?.setAttribute("aria-expanded", "false");
  }

  function closePasswordDialog() {
    if (!isForcedChange && passwordDialog?.open) {
      passwordDialog.close();
      passwordForm?.reset();
      setPasswordFeedback("");
    }
  }

  accountToggle?.addEventListener("click", (event) => {
    event.stopPropagation();
    const willOpen = accountMenu?.hasAttribute("hidden");
    if (willOpen) {
      accountMenu?.removeAttribute("hidden");
    } else {
      accountMenu?.setAttribute("hidden", "");
    }
    accountToggle.setAttribute("aria-expanded", String(Boolean(willOpen)));
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".account-control")) {
      closeAccountMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && accountMenu && !accountMenu.hasAttribute("hidden")) {
      closeAccountMenu();
      accountToggle?.focus();
    }
  });

  changePasswordButton?.addEventListener("click", openPasswordDialog);
  passwordClose?.addEventListener("click", closePasswordDialog);
  passwordCancel?.addEventListener("click", closePasswordDialog);

  passwordDialog?.addEventListener("cancel", (event) => {
    if (isForcedChange) {
      event.preventDefault();
    }
  });

  logoutButton?.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        cache: "no-store",
        headers: { "X-CSRF-Token": currentCsrfToken() },
      });
    } finally {
      window.location.replace("/login");
    }
  });

  passwordForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const currentPassword = document.getElementById("currentPassword")?.value || "";
    const newPassword = document.getElementById("newPassword")?.value || "";
    const confirmPassword = document.getElementById("confirmPassword")?.value || "";
    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordFeedback("请完整填写三项密码");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordFeedback("两次输入的新密码不一致");
      document.getElementById("confirmPassword")?.focus();
      return;
    }

    passwordSubmit.disabled = true;
    passwordSubmit.textContent = "正在更新";
    setPasswordFeedback("");
    try {
      const response = await fetch("/api/auth/change-password", {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": currentCsrfToken(),
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) {
        throw new Error(payload.detail || "密码更新失败，请检查后重试");
      }
      setPasswordFeedback("密码已更新，即将返回登录页", "success");
      if (passwordChangeMeta) {
        passwordChangeMeta.content = "false";
      }
      window.setTimeout(() => window.location.replace("/login?password=changed"), 550);
    } catch (error) {
      setPasswordFeedback(error.message || "密码更新失败，请稍后重试");
      document.getElementById("currentPassword")?.select();
    } finally {
      passwordSubmit.disabled = false;
      passwordSubmit.textContent = "更新密码";
    }
  });

  if (isForcedChange) {
    window.setTimeout(openPasswordDialog, 80);
  }
}
