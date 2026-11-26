const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Elemento {
    constructor(tipo) {
        this.tipo = tipo;
        this.children = [];
        this.attributes = {};
        this.style = {};
        this.hidden = false;
        this.textContent = "";
    }

    setAttribute(nome, valor) {
        this.attributes[nome] = String(valor);
    }

    appendChild(filho) {
        this.children.push(filho);
    }

    replaceChildren() {
        this.children = [];
    }
}

function criarGrafico(relatorios) {
    const ids = [
        "grafico-inicio-printer", "grafico-inicio-vazio",
        "tabela-grafico-inicio-printer", "dados-grafico-inicio-printer"
    ];
    const elementos = Object.fromEntries(ids.map(id => [id, new Elemento(id)]));
    const document = {
        getElementById: id => elementos[id],
        createElement: tipo => new Elemento(tipo),
        createElementNS: (_, tipo) => new Elemento(tipo)
    };
    const codigo = fs.readFileSync(path.join(__dirname, "..", "static", "js", "script.js"), "utf8");
    const inicio = codigo.indexOf("function mostrarGraficoHistoricoPrinter()");
    const fim = codigo.indexOf("function mostrarComparacaoPrinter()", inicio);
    assert.ok(inicio >= 0 && fim > inicio);
    const contexto = { document, historicoPrinter: relatorios };
    vm.runInNewContext(codigo.slice(inicio, fim), contexto);
    return { elementos, contexto };
}

test("sem relatórios, mostra mensagem em vez de gráfico", () => {
    const { elementos, contexto } = criarGrafico([]);
    contexto.mostrarGraficoHistoricoPrinter();
    assert.equal(elementos["grafico-inicio-printer"].children.length, 0);
    assert.equal(elementos["grafico-inicio-vazio"].hidden, false);
    assert.equal(elementos["tabela-grafico-inicio-printer"].hidden, true);
});

test("mostra meses ordenados, zero e ausências sem inventar barras", () => {
    const { elementos, contexto } = criarGrafico([
        { competencia: "2026-10", setor: "Saúde", paginas: 0 },
        { competencia: "2026-09", setor: "Tesouro", paginas: 38840 },
        { competencia: "2026-09", setor: "Saúde", paginas: 50897 }
    ]);
    contexto.mostrarGraficoHistoricoPrinter();
    const linhas = elementos["dados-grafico-inicio-printer"].children;
    assert.deepEqual(linhas.map(linha => linha.children.map(celula => celula.textContent)), [
        ["09/2026", "50.897 páginas", "38.840 páginas", "Sem relatório"],
        ["10/2026", "0 páginas", "Sem relatório", "Sem relatório"]
    ]);
    const svg = elementos["grafico-inicio-printer"].children[0];
    assert.equal(svg.children.filter(item => item.tipo === "rect").length, 3);
    assert.equal(svg.children.filter(item => item.tipo === "text" && item.textContent === "0").length, 2);
    assert.equal(elementos["grafico-inicio-vazio"].hidden, true);

    contexto.historicoPrinter = [];
    contexto.mostrarGraficoHistoricoPrinter();
    assert.equal(elementos["grafico-inicio-printer"].children.length, 0);
    assert.equal(elementos["dados-grafico-inicio-printer"].children.length, 0);
});
