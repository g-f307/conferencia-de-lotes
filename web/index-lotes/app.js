const produtos = [
  "Monitor",
  "Teclado",
  "Mouse",
  "Notebook",
  "Impressora",
  "Scanner",
  "Webcam",
  "Headset",
  "Cadeira",
  "Mesa",
  "Suporte",
  "Cabo HDMI",
  "Fonte",
  "Adaptador",
  "Não informado",
];

const formulario = document.querySelector("#lote-form");
const numeroLote = document.querySelector("#numero-lote");
const produto = document.querySelector("#produto");
const mensagem = document.querySelector("#mensagem");
const erroNumeroLote = document.querySelector("#erro-numero-lote");
const erroProduto = document.querySelector("#erro-produto");
const mensagemResultado = document.querySelector("#mensagem-resultado");

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

  const resultado = formulario.elements.resultadoValidacao.value;
  const rotulos = {
    APROVADO: "Aprovado",
    DIVERGENCIA: "Divergência",
    REVISAO: "Revisão humana",
    ERRO: "Erro técnico",
  };
  const classes = {
    APROVADO: "message--success",
    DIVERGENCIA: "message--warning",
    REVISAO: "message--warning",
    ERRO: "message--error",
  };
  mensagem.textContent =
    `${rotulos[resultado]} — lote ${numeroLote.value.trim()}: ` +
    `${mensagemResultado.value.trim() || "resultado registrado"}`;
  mensagem.dataset.resultado = resultado;
  mensagem.classList.add(classes[resultado]);
  mensagem.hidden = false;
});
