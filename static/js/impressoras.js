/* ==================================================
            MÓDULO DE IMPRESSORAS
================================================== */

/* --------------------------------------------------
   1. NAVEGAÇÃO E PASTAS DE SETORES
-------------------------------------------------- */

function abrirImpressoras() {
    esconderAreas();

    const pastas = document.getElementById("area-pastas");
    if (!pastas) {
        console.error("ERRO: area-pastas não encontrada.");
        return;
    }

    pastas.style.display = "block";
    const descricaoPastas = document.getElementById("descricao-pastas");
    if (descricaoPastas) {
        descricaoPastas.textContent =
            "Selecione um setor para consultar as impressoras cadastradas.";
    }

    window.scrollTo({
        top: pastas.offsetTop - 20,
        behavior: "smooth"
    });
}

function abrirPastas(grupo) {
    resetarFiltrosTabela();
    esconderAreas();

    const lista = document.getElementById("area-lista");
    if (!lista) {
        console.error("ERRO: area-lista não encontrada.");
        return;
    }

    lista.style.display = "block";

    const titulo = document.getElementById("titulo-grupo");
    if (titulo) {
        titulo.textContent = grupo;
    }
    atualizarDescricaoSecao("Impressoras cadastradas neste setor.");

    const linhas = document.querySelectorAll("#area-lista tr[data-grupo]");
    linhas.forEach(function(linha) {
        const grupoLinha = linha.getAttribute("data-grupo");
        linha.style.display = (grupoLinha === grupo) ? "" : "none";
    });

    const pesquisa = document.getElementById("pesquisa");
    if (pesquisa) {
        pesquisa.value = "";
    }

    window.scrollTo({
        top: lista.offsetTop - 20,
        behavior: "smooth"
    });
}

function voltarInicio() {
    esconderAreas();
    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}


/* --------------------------------------------------
   2. CADASTRO, EDIÇÃO E EXCLUSÃO DE IMPRESSORAS
-------------------------------------------------- */

let impressoraEmEdicao = null;
let modoCadastroImpressora = false;

function abrirEdicaoImpressora(impressora) {
    modoCadastroImpressora = false;
    impressoraEmEdicao = {
        ip: impressora.ip || "",
        serie_original: impressora.serie_planilha || "",
        patrimonio_original: impressora.patrimonio_planilha || "",
        formato_cadastro: impressora.formato_cadastro || "original"
    };
    const nome = impressora.nome_planilha || impressora.nome || "";
    const novoFormato = impressora.formato_cadastro === "consolidado";

    document.getElementById("cadastro-impressora-ip-campo").classList.add("hidden");
    document.getElementById("cadastro-impressora-ip").required = false;
    document.getElementById("cadastro-impressora-ip").value = "";

    document.getElementById("cadastro-impressora-nome-rotulo").textContent = "Nome / local";
    document.getElementById("cadastro-impressora-nome").value = nome;

    document.getElementById("cadastro-impressora-setor-campo").classList.toggle("hidden", novoFormato);
    const campoSetor = document.getElementById("cadastro-impressora-setor");
    campoSetor.value = impressora.grupo || "OUTRAS";
    campoSetor.required = !novoFormato;

    document.getElementById("cadastro-impressora-serie-campo").classList.toggle("hidden", !novoFormato);
    document.getElementById("cadastro-impressora-serie").value = impressora.serie_planilha || "";

    document.getElementById("cadastro-impressora-modelo").value =
        impressora.modelo_cadastro || impressora.modelo || "";
    document.getElementById("cadastro-impressora-modelo").required = false;

    document.getElementById("cadastro-impressora-patrimonio-campo").classList.remove("hidden");
    document.getElementById("cadastro-impressora-patrimonio").value =
        impressora.patrimonio_planilha || "";

    document.getElementById("editar-impressora-titulo").textContent = "Editar impressora";
    document.getElementById("cadastro-impressora-salvar").textContent = "Salvar alterações";
    document.getElementById("cadastro-impressora-ajuda").textContent =
        "O endereço IP e as leituras de monitoramento não são alterados por este formulário.";
    document.getElementById("cadastro-impressora-erro").textContent = "";

    const status = document.getElementById("cadastro-impressora-status");
    status.textContent = "";
    status.hidden = true;

    document.getElementById("editar-impressora").showModal();
}

function abrirCadastroImpressora() {
    modoCadastroImpressora = true;
    impressoraEmEdicao = null;

    const formulario = document.querySelector("#editar-impressora form");
    formulario.reset();

    document.getElementById("cadastro-impressora-ip-campo").classList.remove("hidden");
    document.getElementById("cadastro-impressora-ip").required = true;

    document.getElementById("cadastro-impressora-setor-campo").classList.remove("hidden");
    document.getElementById("cadastro-impressora-setor").required = true;

    document.getElementById("cadastro-impressora-serie-campo").classList.remove("hidden");
    document.getElementById("cadastro-impressora-patrimonio-campo").classList.remove("hidden");

    document.getElementById("cadastro-impressora-modelo").required = true;
    document.getElementById("cadastro-impressora-nome-rotulo").textContent = "Local";

    document.getElementById("editar-impressora-titulo").textContent = "Cadastrar impressora";
    document.getElementById("cadastro-impressora-salvar").textContent = "Cadastrar impressora";
    document.getElementById("cadastro-impressora-ajuda").textContent =
        "Informe IP, setor, local e modelo. No cadastro antigo, preencha patrimônio ou número de série, não ambos.";
    document.getElementById("cadastro-impressora-erro").textContent = "";

    const status = document.getElementById("cadastro-impressora-status");
    status.textContent = "";
    status.hidden = true;

    document.getElementById("editar-impressora").showModal();
}

function fecharEdicaoImpressora() {
    document.getElementById("editar-impressora").close();
    impressoraEmEdicao = null;
    modoCadastroImpressora = false;
}

async function salvarEdicaoImpressora(evento) {
    evento.preventDefault();
    if (!modoCadastroImpressora && !impressoraEmEdicao) {
        return;
    }

    const formulario = evento.currentTarget;
    const botao = evento.currentTarget.querySelector('button[type="submit"]');
    const mensagem = document.getElementById("cadastro-impressora-erro");
    botao.disabled = true;
    mensagem.textContent = "";

    try {
        const cadastrando = modoCadastroImpressora;
        const resposta = cadastrando
            ? await api.cadastrarImpressora(new FormData(formulario))
            : await api.editarImpressora({
                ...impressoraEmEdicao,
                nome: document.getElementById("cadastro-impressora-nome").value,
                setor: document.getElementById("cadastro-impressora-setor").value,
                serie: document.getElementById("cadastro-impressora-serie").value,
                modelo: document.getElementById("cadastro-impressora-modelo").value,
                patrimonio: document.getElementById("cadastro-impressora-patrimonio").value
            });
        const resultado = await resposta.json();
        if (!resposta.ok) {
            throw new Error(
                resultado.erro || `Não foi possível salvar (HTTP ${resposta.status}).`
            );
        }
        fecharEdicaoImpressora();
        await atualizarResumo();
        if (cadastrando) {
            const status = document.getElementById("cadastro-impressora-status");
            status.textContent =
                "Impressora cadastrada. O monitoramento será atualizado em instantes.";
            status.hidden = false;
        }
    } catch (erro) {
        mensagem.textContent =
            erro.message || "Não foi possível salvar as alterações.";
    } finally {
        botao.disabled = false;
    }
}

async function excluirImpressoraPainel(impressora) {
    const local = impressora.nome_planilha || impressora.modelo || impressora.ip;
    if (!window.confirm(
        `Excluir "${local}" do painel? O registro será mantido no cadastro como excluído.`
    )) {
        return;
    }

    try {
        const resposta = await api.excluirImpressora({
            ip: impressora.ip || "",
            serie: impressora.serie_planilha || ""
        });
        const resultado = await resposta.json();
        if (!resposta.ok) {
            throw new Error(
                resultado.erro || `Não foi possível excluir (HTTP ${resposta.status}).`
            );
        }
        await atualizarResumo();
    } catch (erro) {
        window.alert(
            erro.message || "Não foi possível excluir a impressora."
        );
    }
}


/* --------------------------------------------------
   3. FICHA DA IMPRESSORA (MODAL DE DETALHES TÉCNICOS)
-------------------------------------------------- */

let consultaContadorAtual = null;
let idConsultaContador = 0;

function formatarModeloImpressora(modelo) {
    const descricao = String(modelo || "").trim();
    const correspondencia = descricao.match(/\(([^()]*)\)\s*$/);
    const nomeModelo = correspondencia
        ? correspondencia[1].trim()
        : descricao;

    return nomeModelo.replace(/^(?:Kyocera|Brother|Canon|Ricoh)\s+/i, "") ||
        "Não informado";
}

async function abrirFichaImpressora(linha) {
    const ficha = document.getElementById("ficha-impressora");
    const ip = (linha.dataset.ip || "").trim();

    if (!ficha || !ip) {
        console.error("Não foi possível abrir a ficha da impressora.");
        return;
    }

    if (consultaContadorAtual) {
        consultaContadorAtual.abort();
    }

    const idConsulta = ++idConsultaContador;
    consultaContadorAtual = new AbortController();

    document.getElementById("ficha-impressora-titulo").textContent =
        linha.dataset.setor || linha.dataset.modelo || "Impressora";
    document.getElementById("ficha-impressora-setor").textContent =
        linha.dataset.setor || "-";
    document.getElementById("ficha-impressora-ip").textContent = ip;
    document.getElementById("ficha-impressora-patrimonio").textContent =
        linha.dataset.patrimonio || "Não informado";
    document.getElementById("ficha-impressora-modelo").textContent =
        formatarModeloImpressora(linha.dataset.modelo);
    document.getElementById("ficha-impressora-status").textContent =
        linha.dataset.status || "Não informado";
    document.getElementById("ficha-impressora-toner").textContent =
        "Consultando cadastro...";
    document.getElementById("ficha-impressora-contador").textContent =
        "Consultando impressora...";
    document.getElementById("ficha-impressora-mensagem").textContent = "";

    if (!ficha.open) {
        ficha.showModal();
    }

    const sinal = consultaContadorAtual.signal;
    const consultaAtiva = () => idConsulta === idConsultaContador && ficha.open;
    const consultar = async buscar => {
        const resposta = await buscar(sinal);
        const dados = await resposta.json();
        if (!resposta.ok) {
            throw new Error(dados.erro || `Erro HTTP ${resposta.status}`);
        }
        return dados;
    };

    const consultarToners = async () => {
        try {
            const dados = await consultar(sinalAtual => api.buscarTonersImpressora(ip, sinalAtual));
            if (!consultaAtiva()) return;
            const areaToner = document.getElementById("ficha-impressora-toner");
            areaToner.replaceChildren();

            if (!dados.modelo_identificado) {
                areaToner.textContent = "Modelo não identificado no cadastro.";
            } else if (!dados.toners.length) {
                areaToner.textContent = "Nenhum toner compatível cadastrado para este modelo.";
            } else {
                dados.toners.forEach(function(toner) {
                    const item = document.createElement("span");
                    item.className = "ficha-impressora-toner-item";
                    item.textContent = `${toner.marca} ${toner.codigo} (${toner.cor})`;
                    areaToner.appendChild(item);
                });
            }
        } catch (erro) {
            if (erro.name === "AbortError" || !consultaAtiva()) return;
            console.error("Erro ao consultar toners compatíveis:", erro);
            document.getElementById("ficha-impressora-toner").textContent =
                erro.message || "Não foi possível carregar os toners compatíveis.";
        }
    };

    const consultarContador = async () => {
        try {
            const dados = await consultar(sinalAtual => api.buscarContadorImpressora(ip, sinalAtual));
            if (!consultaAtiva()) return;
            if (!Number.isSafeInteger(dados.contador) || dados.contador < 0) {
                document.getElementById("ficha-impressora-contador").textContent =
                    "Contador indisponível";
                document.getElementById("ficha-impressora-mensagem").textContent =
                    dados.erro || "A impressora não informou o contador de páginas.";
                return;
            }
            document.getElementById("ficha-impressora-contador").textContent =
                `${dados.contador.toLocaleString("pt-BR")} páginas`;
            document.getElementById("ficha-impressora-mensagem").textContent =
                "Contador lido diretamente da impressora via SNMP.";
        } catch (erro) {
            if (erro.name === "AbortError" || !consultaAtiva()) return;
            console.error("Erro ao consultar contador da impressora:", erro);
            document.getElementById("ficha-impressora-contador").textContent =
                "Contador indisponível";
            document.getElementById("ficha-impressora-mensagem").textContent =
                erro.message || "Não foi possível consultar o contador.";
        }
    };

    await Promise.all([consultarToners(), consultarContador()]);
}

function abrirFichaImpressoraComTeclado(evento, linha) {
    if (evento.target !== linha) {
        return;
    }
    if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        abrirFichaImpressora(linha);
    }
}

function fecharFichaImpressora() {
    const ficha = document.getElementById("ficha-impressora");
    if (ficha && ficha.open) {
        ficha.close();
    }
}

document.addEventListener("DOMContentLoaded", function() {
    const ficha = document.getElementById("ficha-impressora");
    if (ficha) {
        ficha.addEventListener("close", function() {
            idConsultaContador++;
            if (consultaContadorAtual) {
                consultaContadorAtual.abort();
                consultaContadorAtual = null;
            }
        });
    }
});


/* --------------------------------------------------
   4. EXPOSIÇÃO GLOBAL NO WINDOW
-------------------------------------------------- */

window.abrirImpressoras = abrirImpressoras;
window.abrirPastas = abrirPastas;
window.voltarInicio = voltarInicio;
window.abrirEdicaoImpressora = abrirEdicaoImpressora;
window.abrirCadastroImpressora = abrirCadastroImpressora;
window.fecharEdicaoImpressora = fecharEdicaoImpressora;
window.salvarEdicaoImpressora = salvarEdicaoImpressora;
window.excluirImpressoraPainel = excluirImpressoraPainel;
window.formatarModeloImpressora = formatarModeloImpressora;
window.abrirFichaImpressora = abrirFichaImpressora;
window.abrirFichaImpressoraComTeclado = abrirFichaImpressoraComTeclado;
window.fecharFichaImpressora = fecharFichaImpressora;