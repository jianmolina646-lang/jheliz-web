document.addEventListener("DOMContentLoaded", () => {
  const button = document.querySelector("[data-sync-button]");
  if (!button) return;

  button.addEventListener("click", () => {
    if (button.classList.contains("is-syncing")) return;
    button.classList.add("is-syncing");
    button.disabled = true;
    const label = button.querySelector("span");
    if (label) label.textContent = "Sincronizando…";
    window.setTimeout(() => window.location.reload(), 650);
  });
});
