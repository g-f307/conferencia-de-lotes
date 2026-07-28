const loginForm = document.querySelector("#login-form");
const usuario = document.querySelector("#usuario");
const senha = document.querySelector("#senha");
const erroUsuario = document.querySelector("#erro-usuario");
const erroSenha = document.querySelector("#erro-senha");
const mensagemLogin = document.querySelector("#mensagem-login");

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();

  erroUsuario.textContent = "";
  erroSenha.textContent = "";
  mensagemLogin.hidden = true;
  mensagemLogin.className = "message";

  let formularioValido = true;

  if (!usuario.value.trim()) {
    erroUsuario.textContent = "Informe o usuário.";
    formularioValido = false;
  }

  if (!senha.value) {
    erroSenha.textContent = "Informe a senha.";
    formularioValido = false;
  }

  if (!formularioValido) {
    mensagemLogin.textContent = "Revise os campos obrigatórios.";
    mensagemLogin.classList.add("message--error");
    mensagemLogin.hidden = false;
    return;
  }

  window.location.replace("index.html");
});
