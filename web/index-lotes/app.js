const produtos = [
  "Monitor",
  "Teclado",
  "Mouse",
  "Notebook",
  "Impressora",
  "Scanner",
];

const formulario = document.querySelector("#lote-form");
const numeroLote = document.querySelector("#numero-lote");
const produto = document.querySelector("#produto");
const mensagem = document.querySelector("#mensagem");
const erroNumeroLote = document.querySelector("#erro-numero-lote");
const erroProduto = document.querySelector("#erro-produto");

for (const nome of produtos) {
  const option = document.createElement("option");
  option.value = nome;
  option.textContent = nome;
  produto.append(option);
}

formulario.addEventListener("submit", (event) => {
  event.preventDefault();

  erroNumeroLote.textContent = "";
  erroProduto.textContent = "";
  mensagem.hidden = true;
  mensagem.className = "message";

  let formularioValido = true;

  if (!numeroLote.value.trim()) {
    erroNumeroLote.textContent = "Informe o número do lote.";
    formularioValido = false;
  }

  if (!produto.value) {
    erroProduto.textContent = "Selecione um produto.";
    formularioValido = false;
  }

  if (!formularioValido) {
    mensagem.textContent = "Revise os campos obrigatórios.";
    mensagem.classList.add("message--error");
    mensagem.hidden = false;
    return;
  }

  const status = formulario.elements.status.value;
  mensagem.textContent =
    `Lote ${numeroLote.value.trim()} processado com sucesso: ` +
    `${produto.value} — ${status}.`;
  mensagem.classList.add("message--success");
  mensagem.hidden = false;
});
