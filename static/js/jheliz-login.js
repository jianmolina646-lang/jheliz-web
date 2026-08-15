(() => {
  const form = document.querySelector("[data-login-form]");
  if (!form) return;

  const password = form.querySelector("#jcLoginPassword");
  const toggle = form.querySelector("[data-password-toggle]");
  if (password && toggle) {
    toggle.addEventListener("click", () => {
      const showing = password.type === "text";
      password.type = showing ? "password" : "text";
      toggle.setAttribute("aria-pressed", String(!showing));
      toggle.setAttribute("aria-label", showing ? "Mostrar contraseña" : "Ocultar contraseña");
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
