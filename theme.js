(() => {
  const root = document.documentElement;
  const key = "mynews-theme";
  let theme = "night";
  try {
    const saved = localStorage.getItem(key);
    if (saved === "day" || saved === "night") theme = saved;
  } catch (error) {
    console.warn("Preferința de temă nu poate fi citită:", error);
  }

  function applyTheme() {
    root.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === "night" ? "#0c1015" : "#f4f6f8";
    const button = document.querySelector("#theme-toggle");
    if (!button) return;
    button.setAttribute("aria-checked", String(theme === "night"));
    button.title = theme === "night" ? "Tema Noapte este activă. Comută la Zi." : "Tema Zi este activă. Comută la Noapte.";
  }

  applyTheme();
  document.addEventListener("DOMContentLoaded", () => {
    applyTheme();
    const button = document.querySelector("#theme-toggle");
    button.disabled = false;
    button.addEventListener("click", () => {
      theme = theme === "night" ? "day" : "night";
      applyTheme();
      try {
        localStorage.setItem(key, theme);
      } catch (error) {
        console.warn("Preferința de temă nu poate fi salvată:", error);
      }
    });
  });
})();
