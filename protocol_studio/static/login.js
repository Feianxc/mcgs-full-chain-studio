const form = document.getElementById("loginForm");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const csrfInput = document.getElementById("loginCsrf");
const submitButton = document.getElementById("loginSubmit");
const passwordToggle = document.getElementById("passwordToggle");
const feedback = document.getElementById("loginFeedback");

function setFeedback(message, tone = "error") {
  feedback.textContent = message || "";
  feedback.classList.toggle("is-success", tone === "success");
}

passwordToggle.addEventListener("click", () => {
  const shouldShow = passwordInput.type === "password";
  passwordInput.type = shouldShow ? "text" : "password";
  passwordToggle.textContent = shouldShow ? "隐藏" : "显示";
  passwordToggle.setAttribute("aria-pressed", String(shouldShow));
  passwordInput.focus({ preventScroll: true });
});

[usernameInput, passwordInput].forEach((input) => {
  input.addEventListener("input", () => setFeedback(""));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    setFeedback("请输入账号和密码");
    (!username ? usernameInput : passwordInput).focus();
    return;
  }

  submitButton.disabled = true;
  submitButton.querySelector("span:first-child").textContent = "正在验证";
  setFeedback("");
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password,
        csrf_token: csrfInput.value,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || "登录失败，请检查账号和密码");
    }
    setFeedback("验证通过，正在进入工作台…", "success");
    window.setTimeout(() => window.location.replace("/"), 220);
  } catch (error) {
    setFeedback(error.message || "登录失败，请稍后重试");
    passwordInput.select();
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span:first-child").textContent = "进入制表台";
  }
});
