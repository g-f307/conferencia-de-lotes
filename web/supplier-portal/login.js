const form = document.querySelector("#login-form");
const status = document.querySelector("#auth-status");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const user = document.querySelector("#usuario").value.trim();
  const password = document.querySelector("#senha").value;
  status.removeAttribute("data-auth-error");
  status.hidden = true;

  if (user !== "fornecedor.demo" || password !== "demo-local") {
    status.textContent = "Credenciais inválidas para o ambiente controlado.";
    status.dataset.authError = "true";
    status.hidden = false;
    return;
  }
  window.location.replace("index.html");
});
