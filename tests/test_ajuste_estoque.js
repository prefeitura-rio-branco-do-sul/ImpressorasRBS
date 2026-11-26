const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const codigo = fs.readFileSync(path.join(__dirname, "..", "static", "js", "script.js"), "utf8");

async function renderizarEstoque(ativo, podeAjustar) {
    const campos = {
        "area-estoque": { style: {} },
        "area-tabela-estoque": { style: {} },
        "corpo-tabela-estoque": { innerHTML: "" },
        "estoque-compatibilidade-coluna": {},
        "estoque-compatibilidade-status": {},
        "mostrar-toners-inativos": {},
        "busca-estoque": { value: "" }
    };
    const contexto = {
        document: { getElementById: id => campos[id] },
        localStorage: { getItem: () => "0" },
        api: {
            buscarEstoque: async () => ({
                ok: true,
                json: async () => [{
                    id: 1, marca: "Marca", codigo: 'TK"1', cor: "Preto",
                    estoque: 3, estoque_minimo: 1, ativo, modelos_compativeis: ""
                }]
            })
        },
        painelPode: permissao => permissao === "stock.adjust" && podeAjustar,
        esconderAreas() {}, carregarPedidosEstoque() {}, atualizarResumoEstoque() {},
        filtrarEstoque() {}, carregarCompatibilidadeToners() {}, console
    };
    const inicio = codigo.indexOf("async function mostrarEstoque(");
    const fim = codigo.indexOf("function filtrarEstoque(", inicio);
    assert.ok(inicio >= 0 && fim > inicio);
    vm.runInNewContext(codigo.slice(inicio, fim), contexto);
    await contexto.mostrarEstoque(false);
    return campos["corpo-tabela-estoque"].innerHTML;
}

test("quantidade ativa é clicável apenas com permissão de ajuste", async () => {
    const html = await renderizarEstoque(true, true);
    assert.match(html, /aria-label="Ajustar estoque de TK&quot;1"/);
    assert.match(html, /onclick="abrirAjusteEstoque\(1, this\)"><strong>3<\/strong><\/button>/);
    assert.doesNotMatch(html, />Ajustar<\/button>/);
    for (const [ativo, permissao] of [[false, true], [true, false]]) {
        const semAjuste = await renderizarEstoque(ativo, permissao);
        assert.doesNotMatch(semAjuste, /onclick="abrirAjusteEstoque/);
        assert.match(semAjuste, /<strong>3<\/strong>/);
    }
});

test("clicar na quantidade abre ajuste com o saldo e o toner corretos", () => {
    const campos = {
        "ajuste-estoque-titulo": { textContent: "" },
        "ajuste-estoque-saldo": { textContent: "" },
        "ajuste-estoque-erro": { textContent: "" }
    };
    const formulario = { dataset: {}, reset() { this.resetado = true; } };
    campos["ajuste-estoque"] = {
        querySelector: () => formulario,
        showModal() { this.aberto = true; }
    };
    const celulas = [
        { textContent: "Marca" }, { textContent: "TK-1" }, {}, {},
        { textContent: "Preto" },
        { querySelector: () => ({ textContent: "3" }) }
    ];
    const contexto = { document: { getElementById: id => campos[id] }, console };
    const inicio = codigo.indexOf("function abrirAjusteEstoque(");
    const fim = codigo.indexOf("async function salvarAjusteEstoque(", inicio);
    assert.ok(inicio >= 0 && fim > inicio);
    vm.runInNewContext(codigo.slice(inicio, fim), contexto);
    contexto.abrirAjusteEstoque(1, { closest: () => ({ cells: celulas }) });
    assert.equal(formulario.dataset.tonerId, 1);
    assert.equal(campos["ajuste-estoque-saldo"].textContent, "Saldo atual: 3");
    assert.equal(campos["ajuste-estoque-titulo"].textContent, "Marca — TK-1 — Preto");
    assert.equal(campos["ajuste-estoque"].aberto, true);
});
