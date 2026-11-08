// A preferência fica apenas neste navegador; falhas no armazenamento não bloqueiam a página.
(function () {
    let theme = "claro";
    try {
        const saved = localStorage.getItem("tickets-tema");
        theme = saved === "escuro" || saved === "claro" ? saved :
            (window.matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro");
    } catch (error) {}
    document.documentElement.dataset.tema = theme;
    document.addEventListener("DOMContentLoaded", function () {
        const button = document.getElementById("themeToggle");
        function update() {
            const dark = document.documentElement.dataset.tema === "escuro";
            button.textContent = dark ? "Modo claro" : "Modo escuro";
            button.setAttribute("aria-pressed", String(dark));
        }
        button.addEventListener("click", function () {
            const value = document.documentElement.dataset.tema === "escuro" ? "claro" : "escuro";
            document.documentElement.dataset.tema = value;
            try { localStorage.setItem("tickets-tema", value); } catch (error) {}
            update();
        });
        update();
    });
})();
