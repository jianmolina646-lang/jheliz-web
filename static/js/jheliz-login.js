(() => {
  const form = document.querySelector("[data-login-form]");
  if (!form) return;

  const password = form.querySelector('input[name="password"]');
  const passwordToggle = form.querySelector("[data-password-toggle]");
  if (password && passwordToggle) {
    passwordToggle.addEventListener("click", () => {
      const visible = password.type === "text";
      password.type = visible ? "password" : "text";
      passwordToggle.setAttribute("aria-pressed", visible ? "false" : "true");
      passwordToggle.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
      const icon = passwordToggle.querySelector(".material-symbols-outlined");
      if (icon) icon.textContent = visible ? "visibility" : "visibility_off";
      password.focus({ preventScroll: true });
      const length = password.value.length;
      password.setSelectionRange(length, length);
    });
  }

  const messages = document.querySelector("body > .pb-wrap");
  const identity = document.querySelector(".jli-identity");
  if (messages && identity) {
    messages.setAttribute("role", "alert");
    messages.setAttribute("aria-live", "assertive");
    identity.insertAdjacentElement("afterend", messages);
    form.querySelectorAll("input").forEach((input) => input.setAttribute("aria-invalid", "true"));
  }

  form.addEventListener("submit", () => {
    const button = form.querySelector(".jli-submit");
    const label = form.querySelector("[data-login-label]");
    if (!button || !label || button.disabled) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    form.setAttribute("aria-busy", "true");
    label.textContent = "Ingresando…";
  });
})();
