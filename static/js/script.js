  
/* ======================================================
HORÁRIO
====================================================== */

function painelPode(permissao) {
    return Boolean(
        window.PAINEL_ADMIN ||
        (window.PAINEL_PERMISSOES || []).includes(permissao)
    );
}

function atualizarHorario() {
    const elemento = document.getElementById("horario");

    if (elemento) {
        elemento.textContent = new Date().toLocaleString("pt-BR");
    }
}

atualizarHorario();

            setInterval(
                atualizarHorario,
                30000
            );


            /* ======================================================
            RESUMO
            ====================================================== */

            let impressorasRenderizadas = "";
            let filtroStatusAtual = "todos";
            let filtroTonerBaixo = false;
            let tonersNaoConfiaveis = null;
            let atualizacaoResumoSequencia = 0;
            let pesquisaImpressorasAtiva = false;

            const LIMITE_TONER_BAIXO = 7;
            const CORES_TONER = [
                ["ciano", "Ciano", "toner-ciano"],
                ["magenta", "Magenta", "toner-magenta"],
                ["amarelo", "Amarelo", "toner-amarelo"],
                ["preto", "Preto", "toner-preto"]
            ];
          

            function obterNivelToner(valor) {
                if (valor === null || valor === undefined) {
                    return null;
                }
                const texto = String(valor).replace("%", "").trim();
                if (!texto) return null;

                const nivel = Number(texto);
                return Number.isFinite(nivel) && nivel >= 0 && nivel <= 100
                    ? nivel
                    : null;
            }

            function impressoraComTonerBaixo(impressora, naoConfiaveis) {
                if (!naoConfiaveis) return false;
                return impressora.status === "Online" &&
                    CORES_TONER.some(([cor, nome]) => {
                        const nivel = obterNivelToner(impressora[cor]);
                        const naoConfiavel = naoConfiaveis.some(item =>
                            String(item.ip || "").trim() === String(impressora.ip || "").trim() &&
                            String(item.toner || "").trim().toLocaleLowerCase() === nome.toLocaleLowerCase()
                        );
                        const estimado = impressora.niveis_estimados &&
                            impressora.niveis_estimados[nome] &&
                            impressora.niveis_estimados[nome].nivel !== null;
                        return nivel !== null && nivel <= LIMITE_TONER_BAIXO &&
                            (!naoConfiavel || estimado);
                    });
            }

            function atualizarFiltroSetor(grupos) {
                const seletor = document.getElementById("filtro-setor");
                if (!seletor) {
                    return;
                }

                const setorSelecionado = seletor.value;
                seletor.replaceChildren(new Option("Todos os setores", ""));
                grupos.forEach(grupo => {
                    seletor.add(new Option(grupo, grupo));
                });
                seletor.value = grupos.includes(setorSelecionado)
                    ? setorSelecionado
                    : "";
            }

            function filtrarTabelaDashboard() {
                const busca = document.getElementById("filtro-impressoras");
                const setor = document.getElementById("filtro-setor");
                const normalizar = valor =>
                    String(valor || "")
                        .normalize("NFD")
                        .replace(/[\u0300-\u036f]/g, "")
                        .toLocaleLowerCase()
                        .trim();
                const termo = normalizar(busca ? busca.value : "");
                const grupoSelecionado = setor ? setor.value : "";

                document.querySelectorAll(
                    "#corpo-tabela-impressoras tr[data-ip]"
                ).forEach(linha => {
                    const correspondeTexto = [
                        linha.dataset.setor,
                        linha.dataset.grupo,
                        linha.dataset.ip,
                        linha.dataset.modelo,
                        linha.dataset.patrimonio
                    ].some(valor => normalizar(valor).includes(termo));
                    const correspondeSetor =
                        !grupoSelecionado ||
                        linha.dataset.grupo === grupoSelecionado;
                    const correspondeStatus =
                        filtroStatusAtual === "todos" ||
                        linha.dataset.status === filtroStatusAtual;
                    const correspondeToner =
                        !filtroTonerBaixo || linha.dataset.tonerBaixo === "true";

                    linha.style.display =
                        correspondeTexto &&
                        correspondeSetor &&
                        correspondeStatus &&
                        correspondeToner
                            ? ""
                            : "none";
                });
            }

            function definirFiltroStatus(status, botao) {
                filtroStatusAtual = status;
                document.querySelectorAll(
                    ".filtro-status button"
                ).forEach(item => {
                    const selecionado = item === botao;
                    item.classList.toggle("is-selected", selecionado);
                    item.setAttribute("aria-pressed", String(selecionado));
                });
                filtrarTabelaDashboard();
            }

            function resetarFiltrosTabela() {
                const busca = document.getElementById("filtro-impressoras");
                const setor = document.getElementById("filtro-setor");
                const botaoTodos = document.querySelector(
                    '.filtro-status button[data-filtro-status="todos"]'
                );

                if (busca) busca.value = "";
                if (setor) setor.value = "";
                filtroStatusAtual = "todos";
                filtroTonerBaixo = false;
                if (botaoTodos) definirFiltroStatus("todos", botaoTodos);
            }

            function abrirListaGrafico(grupo, status) {
                resetarFiltrosTabela();
                esconderAreas();
                secaoMenuAtiva = null;
                atualizarEstadoBotaoMenu();

                const pesquisa = document.getElementById("pesquisa");
                if (pesquisa) pesquisa.value = "";
                const lista = document.getElementById("area-lista");
                if (!lista) {
                    console.error("ERRO: area-lista não encontrada.");
                    return;
                }

                lista.style.display = "block";
                const titulo = document.getElementById("titulo-grupo");
                if (grupo) {
                    const seletor = document.getElementById("filtro-setor");
                    if (seletor) seletor.value = grupo;
                    if (titulo) titulo.textContent = grupo;
                    atualizarDescricaoSecao(
                        "Impressoras cadastradas neste setor."
                    );
                } else if (status === "todos") {
                    if (titulo) titulo.textContent = "Todas as impressoras";
                    atualizarDescricaoSecao(
                        "Impressoras cadastradas no monitoramento."
                    );
                } else {
                    if (titulo) titulo.textContent = `Impressoras ${status}`;
                    atualizarDescricaoSecao(
                        status === "Offline"
                            ? "Equipamentos que não responderam à última consulta SNMP. Isso não confirma que estão desligados."
                            : "Equipamentos que responderam à última consulta da rede."
                    );
                    const botao = document.querySelector(
                        `.filtro-status button[data-filtro-status="${status}"]`
                    );
                    definirFiltroStatus(status, botao);
                    if (status === "Offline") {
                        const tabela = document.getElementById("tabela-impressoras");
                        if (tabela) tabela.classList.add("tabela-impressoras-offline");
                    }
                }
                filtrarTabelaDashboard();
                window.scrollTo({
                    top: lista.offsetTop - 20,
                    behavior: "smooth"
                });
            }

            function abrirListaTonerBaixoPainel() {
                abrirListaGrafico(null, "Online");
                filtroTonerBaixo = true;
                const titulo = document.getElementById("titulo-grupo");
                if (titulo) titulo.textContent = "Toners baixos";
                atualizarDescricaoTonerBaixo();
                const tabela = document.getElementById("tabela-impressoras");
                if (tabela) tabela.classList.add("tabela-impressoras-toner-baixo");
                filtrarTabelaDashboard();
            }

            function atualizarDescricaoTonerBaixo() {
                atualizarDescricaoSecao(tonersNaoConfiaveis === null
                    ? "Dados de toner baixo indisponíveis. Aguarde a próxima atualização."
                    : `Impressoras online com toner em ${LIMITE_TONER_BAIXO}% ou menos. Leituras não confiáveis são excluídas, exceto estimativas identificadas como tal.`);
            }

            function abrirStatusGrafico(evento) {
                const rosca = evento.currentTarget;
                const total = Number(rosca.dataset.total || 0);
                if (!total) return;

                const limites = rosca.getBoundingClientRect();
                const x = evento.clientX - (limites.left + limites.width / 2);
                const y = evento.clientY - (limites.top + limites.height / 2);
                const raio = Math.hypot(x, y);
                if (raio < 59 || raio > Math.min(limites.width, limites.height) / 2) {
                    return;
                }

                const angulo = (Math.atan2(x, -y) + 2 * Math.PI) % (2 * Math.PI);
                const percentual = Number(rosca.dataset.percentualOnline);
                abrirListaGrafico(
                    null,
                    angulo / (2 * Math.PI) * 100 < percentual ? "Online" : "Offline"
                );
            }

            function atualizarGraficos(impressoras, online, offline) {
                const total = impressoras.length;
                const percentual = total
                    ? Math.round((online / total) * 100)
                    : 0;
                const rosca = document.getElementById("grafico-rosca");
                const percentualElemento =
                    document.getElementById("percentual-online");
                const legendaOnline =
                    document.getElementById("legenda-online");
                const legendaOffline =
                    document.getElementById("legenda-offline");
                const subtitulo =
                    document.getElementById("subtitulo-visao-geral");

                if (rosca) {
                    rosca.dataset.total = String(total);
                    rosca.dataset.percentualOnline = String(percentual);
                    rosca.style.setProperty(
                        "--percentual-online",
                        `${percentual}%`
                    );
                    rosca.classList.toggle("sem-dados", total === 0);
                    rosca.setAttribute(
                        "aria-label",
                        `${online} impressoras online e ${offline} offline`
                    );
                }
                if (percentualElemento) {
                    percentualElemento.textContent = `${percentual}%`;
                }
                if (legendaOnline) legendaOnline.textContent = online;
                if (legendaOffline) legendaOffline.textContent = offline;
                if (subtitulo) {
                    subtitulo.textContent = total
                        ? "Acompanhe o status e a distribuição dos equipamentos por setor."
                        : "Ainda não houve coleta registrada.";
                }

                const contagemSetores = new Map();
                impressoras.forEach(impressora => {
                    const grupo = impressora.grupo || "OUTRAS";
                    contagemSetores.set(
                        grupo,
                        (contagemSetores.get(grupo) || 0) + 1
                    );
                });
                const setores = [...contagemSetores.entries()]
                    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
                    .slice(0, 8);
                const lista = document.getElementById("grafico-setores");
                const subtituloSetores =
                    document.getElementById("subtitulo-setores");
                if (!lista) return;

                lista.replaceChildren();
                if (!setores.length) {
                    const vazio = document.createElement("p");
                    vazio.className = "grafico-vazio";
                    vazio.textContent =
                        "Aguardando coleta dos equipamentos...";
                    lista.appendChild(vazio);
                    if (subtituloSetores) {
                        subtituloSetores.textContent =
                            "Setores com mais impressoras";
                    }
                    return;
                }

                const maiorContagem = setores[0][1];
                setores.forEach(([grupo, quantidade]) => {
                    const linha = document.createElement("button");
                    linha.type = "button";
                    linha.className = "barra-setor-linha";
                    linha.setAttribute(
                        "aria-label",
                        `Ver ${quantidade} impressoras do setor ${grupo}`
                    );
                    linha.addEventListener(
                        "click",
                        () => abrirListaGrafico(grupo, null)
                    );

                    const rotulo = document.createElement("span");
                    rotulo.className = "barra-setor-rotulo";
                    rotulo.textContent = grupo;
                    rotulo.title = grupo;

                    const trilho = document.createElement("div");
                    trilho.className = "barra-setor-trilho";
                    const barra = document.createElement("span");
                    barra.className = "barra-setor-valor";
                    barra.style.width =
                        `${Math.max(3, (quantidade / maiorContagem) * 100)}%`;
                    barra.setAttribute(
                        "aria-label",
                        `${quantidade} impressoras`
                    );
                    trilho.appendChild(barra);

                    const totalSetor = document.createElement("strong");
                    totalSetor.className = "barra-setor-total";
                    totalSetor.textContent = quantidade;

                    linha.append(rotulo, trilho, totalSetor);
                    lista.appendChild(linha);
                });
                if (subtituloSetores) {
                    subtituloSetores.textContent =
                        `Os ${setores.length} setores com mais impressoras`;
                }
            }

            function renderizarImpressoras(impressoras, naoConfiaveis) {

                const dadosSerializados =
                    JSON.stringify([impressoras, naoConfiaveis]);

                if (dadosSerializados === impressorasRenderizadas) {
                    return;
                }

                const corpo =
                    document.getElementById("corpo-tabela-impressoras");

                if (!corpo) {
                    return;
                }

                const grupos = [
                    ...new Set(
                        impressoras.map(
                            impressora => impressora.grupo || "OUTRAS"
                        )
                    )
                ].sort();
                atualizarFiltroSetor(grupos);

                const pastas =
                    document.querySelector(".pastas");

                if (pastas) {
                    pastas.replaceChildren();

                    grupos.forEach(grupo => {
                        const botao = document.createElement("button");
                        botao.type = "button";
                        botao.className = "pastas";
                        botao.textContent = `📁\n${grupo}`;
                        botao.addEventListener(
                            "click",
                            () => abrirPastas(grupo)
                        );
                        pastas.appendChild(botao);
                    });
                }

                corpo.replaceChildren();

                impressoras.forEach(impressora => {
                    const linha = document.createElement("tr");
                    const grupo = impressora.grupo || "OUTRAS";
                    const setor =
                        impressora.nome_planilha ||
                        impressora.modelo ||
                        impressora.nome ||
                        "-";
                    const online = impressora.status === "Online";

                    linha.dataset.grupo = grupo;
                    linha.dataset.status = impressora.status || "Offline";
                    linha.dataset.tonerBaixo = String(
                        impressoraComTonerBaixo(impressora, naoConfiaveis)
                    );
                    linha.dataset.ip = impressora.ip || "";
                    linha.dataset.modelo =
                        impressora.modelo_cadastro || impressora.modelo || "";
                    linha.dataset.patrimonio = impressora.patrimonio || "";
                    linha.dataset.setor = setor;
                    linha.setAttribute("role", "button");
                    linha.tabIndex = 0;
                    linha.setAttribute(
                        "aria-label",
                        `Abrir ficha de ${setor}`
                    );
                    linha.addEventListener(
                        "click",
                        () => abrirFichaImpressora(linha)
                    );
                    linha.addEventListener(
                        "keydown",
                        evento => abrirFichaImpressoraComTeclado(evento, linha)
                    );

                    [
                        impressora.nome_planilha ||
                            impressora.modelo ||
                            impressora.nome ||
                            "-",
                        impressora.patrimonio || "-"
                    ].forEach(valor => {
                        const celula = document.createElement("td");
                        celula.textContent = valor;
                        linha.appendChild(celula);
                    });

                    const celulaIp = document.createElement("td");
                    const ip = String(impressora.ip || "").trim();
                    const octetosIp = ip.split(".");
                    const ipValido =
                        octetosIp.length === 4 &&
                        octetosIp.every(
                            octeto =>
                                /^\d{1,3}$/.test(octeto) &&
                                Number(octeto) <= 255
                        );
                    if (ipValido) {
                        const linkIp = document.createElement("a");
                        linkIp.href = `http://${ip}`;
                        linkIp.target = "_blank";
                        linkIp.rel = "noopener noreferrer";
                        linkIp.textContent = ip;
                        linkIp.title = `Abrir configuração da impressora ${ip} em nova aba`;
                        linkIp.setAttribute(
                            "aria-label",
                            `Abrir configuração da impressora ${ip} em nova aba`
                        );
                        linkIp.addEventListener(
                            "click",
                            evento => evento.stopPropagation()
                        );
                        celulaIp.appendChild(linkIp);
                    } else {
                        celulaIp.textContent = ip || "-";
                    }
                    linha.appendChild(celulaIp);

                    CORES_TONER.forEach(([cor, nome, classe]) => {
                        const celula = document.createElement("td");
                        const toner = impressora[cor];
                        const estimativa = impressora.niveis_estimados &&
                            impressora.niveis_estimados[nome];

                        if (online && toner && toner !== "-") {
                            const barra = document.createElement("div");
                            const valorToner =
                                document.createElement("div");
                            valorToner.className = "toner-valor";
                            const nivel = obterNivelToner(toner);

                            barra.className = `progress-bar ${classe}`;
                            if (nivel !== null) {
                                const percentual = nivel;
                                barra.style.width = `${percentual}%`;
                                barra.dataset.percentual = String(percentual);

                                const rotulo =
                                    document.createElement("span");
                                rotulo.className =
                                    `toner-percentual ${classe}`;
                                rotulo.textContent = `${percentual}%${estimativa ? " estimado" : ""}`;
                                rotulo.setAttribute(
                                    "aria-label",
                                    `${cor}: ${percentual}%${estimativa ? " estimado" : ""}`
                                );
                                valorToner.appendChild(rotulo);
                            } else {
                                barra.textContent = toner;
                            }

                            const progresso =
                                document.createElement("div");
                            progresso.className = "progress toner-bar";
                            progresso.dataset.toner = cor;
                            progresso.appendChild(barra);
                            valorToner.prepend(progresso);
                            celula.appendChild(valorToner);
                        } else {
                            celula.textContent = estimativa ? "Indisponível (sem chip)" : "-";
                        }

                        linha.appendChild(celula);
                    });

                    const status = document.createElement("td");
                    const seloStatus = document.createElement("span");
                    seloStatus.className = online
                        ? "badge bg-success"
                        : "badge bg-danger";
                    seloStatus.textContent = online ? "Online" : "Offline";
                    status.appendChild(seloStatus);
                    linha.appendChild(status);

                    const alerta = document.createElement("td");
                    const niveisToner = online
                        ? CORES_TONER
                            .map(([cor, nome]) => ({
                                nome,
                                nivel: obterNivelToner(impressora[cor])
                            }))
                            .filter(toner => toner.nivel !== null)
                        : [];
                    const tonersCriticos = niveisToner.filter(
                        toner => toner.nivel <= LIMITE_TONER_BAIXO
                    );
                    const tonersEmAtencao = niveisToner.filter(
                        toner =>
                            toner.nivel > LIMITE_TONER_BAIXO &&
                            toner.nivel <= 20
                    );

                    if (tonersCriticos.length) {
                        const selo = document.createElement("span");
                        selo.className = "badge bg-danger";
                        selo.textContent = `Baixo: ${tonersCriticos
                            .map(toner => `${toner.nome} ${toner.nivel}%`)
                            .join(", ")}`;
                        alerta.appendChild(selo);
                    } else if (tonersEmAtencao.length) {
                        const selo = document.createElement("span");
                        selo.className = "badge bg-warning text-dark";
                        selo.textContent = `Atenção: ${tonersEmAtencao
                            .map(toner => `${toner.nome} ${toner.nivel}%`)
                            .join(", ")}`;
                        alerta.appendChild(selo);
                    } else if (online && Object.values(impressora.niveis_estimados || {}).some(
                        estimativa => estimativa.nivel === null
                    )) {
                        const selo = document.createElement("span");
                        selo.className = "badge bg-warning text-dark";
                        selo.textContent = "Estimativa indisponível";
                        alerta.appendChild(selo);
                    } else if (online) {
                        const selo = document.createElement("span");
                        selo.className = "badge bg-success";
                        selo.textContent = "OK";
                        alerta.appendChild(selo);
                    }

                    linha.appendChild(alerta);

                    const acoes = document.createElement("td");
                    acoes.className = "whitespace-nowrap";
                    if (painelPode("printers.edit")) {
                        const botaoEditar = document.createElement("button");
                        botaoEditar.type = "button";
                        botaoEditar.textContent = "Editar";
                        botaoEditar.className =
                            "mr-1 rounded-lg border border-gray-300 px-2 py-1 text-xs hover:bg-gray-100";
                        botaoEditar.setAttribute(
                            "aria-label",
                            `Editar cadastro de ${setor}`
                        );
                        botaoEditar.addEventListener("click", evento => {
                            evento.stopPropagation();
                            abrirEdicaoImpressora(impressora);
                        });
                        acoes.appendChild(botaoEditar);
                    }
                    if (painelPode("printers.delete")) {
                        const botaoExcluir = document.createElement("button");
                        botaoExcluir.type = "button";
                        botaoExcluir.textContent = "Excluir";
                        botaoExcluir.className =
                            "rounded-lg border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50";
                        botaoExcluir.setAttribute(
                            "aria-label",
                            `Excluir ${setor} do painel`
                        );
                        botaoExcluir.addEventListener("click", evento => {
                            evento.stopPropagation();
                            excluirImpressoraPainel(impressora);
                        });
                        acoes.appendChild(botaoExcluir);
                    }
                    linha.appendChild(acoes);
                    corpo.appendChild(linha);
                });

                impressorasRenderizadas = dadosSerializados;
                filtrarTabelaDashboard();
            }

            async function atualizarResumo() {

                const sequencia = ++atualizacaoResumoSequencia;
                try {

                    const resposta = await api.buscarDados();

                    if (!resposta.ok) {

                        throw new Error(
                            "Erro HTTP " + resposta.status
                        );

                    }


                    const impressoras =
                        await resposta.json();

                    let naoConfiaveis = null;
                    try {
                        const respostaNaoConfiaveis = await api.buscarTonersNaoConfiaveis();
                        if (!respostaNaoConfiaveis.ok) {
                            throw new Error("Erro HTTP " + respostaNaoConfiaveis.status);
                        }
                        naoConfiaveis = await respostaNaoConfiaveis.json();
                        if (!Array.isArray(naoConfiaveis)) {
                            throw new Error("Resposta inválida de toners não confiáveis.");
                        }
                    } catch (erro) {
                        console.error("Erro ao verificar toners não confiáveis:", erro);
                        naoConfiaveis = null;
                    }
                    if (sequencia !== atualizacaoResumoSequencia) return;
                    tonersNaoConfiaveis = naoConfiaveis;
                    renderizarImpressoras(impressoras, naoConfiaveis);
                    if (filtroTonerBaixo) atualizarDescricaoTonerBaixo();
                    const pesquisa =
                        document.getElementById("pesquisa");
                    if (pesquisaImpressorasAtiva && pesquisa && pesquisa.value.trim()) {
                        pesquisarImpressoras();
                    }

                    // ==================================================
                    // TOTAL DE IMPRESSORAS
                    // ==================================================

                    const total =
                        impressoras.length;


                    // ==================================================
                    // IMPRESSORAS ONLINE
                    // ==================================================

                    const online =
                        impressoras.filter(
                            impressora =>
                                impressora.status === "Online"
                        ).length;


                    // ==================================================
                    // IMPRESSORAS OFFLINE
                    // ==================================================

                    const offline =
                        impressoras.filter(
                            impressora =>
                                impressora.status !== "Online"
                        ).length;


                    // ==================================================
                    // TONER BAIXO
                    // ==================================================

                    const tonerBaixo = naoConfiaveis === null
                        ? "—"
                        : impressoras.filter(impressora =>
                            impressoraComTonerBaixo(impressora, naoConfiaveis)
                        ).length;

                    atualizarGraficos(impressoras, online, offline);

                    // ==================================================
                    // ATUALIZA OS CARTÕES DO PAINEL
                    // ==================================================

                    const totalElemento =
                        document.getElementById(
                            "total-impressoras"
                        );


                    const onlineElemento =
                        document.getElementById(
                            "online-impressoras"
                        );


                    const offlineElemento =
                        document.getElementById(
                            "offline-impressoras"
                        );


                    const tonerElemento =
                        document.getElementById(
                            "toner-baixo"
                        );


                    if (totalElemento) {

                        totalElemento.textContent =
                            total;

                    }


                    if (onlineElemento) {

                        onlineElemento.textContent =
                            online;

                    }


                    if (offlineElemento) {

                        offlineElemento.textContent =
                            offline;

                    }


                    if (tonerElemento) {

                        tonerElemento.textContent =
                            tonerBaixo;

                    }


                } catch (erro) {

                    console.error(
                        "Erro ao atualizar resumo:",
                        erro
                    );
                    if (sequencia === atualizacaoResumoSequencia) {
                        tonersNaoConfiaveis = null;
                        impressorasRenderizadas = "";
                        document.querySelectorAll("#corpo-tabela-impressoras tr[data-ip]")
                            .forEach(linha => { linha.dataset.tonerBaixo = "false"; });
                        const tonerElemento = document.getElementById("toner-baixo");
                        if (tonerElemento) tonerElemento.textContent = "—";
                        if (filtroTonerBaixo) {
                            atualizarDescricaoTonerBaixo();
                            filtrarTabelaDashboard();
                        }
                    }

                }

            }
            if (painelPode("monitor.view")) {
                atualizarResumo();
                setInterval(atualizarResumo, 30000);
            }

           let secaoMenuAtiva = null;

           const areaPastasInicial =
                document.getElementById("area-pastas");
           const areaListaInicial =
                document.getElementById("area-lista");
           if (areaPastasInicial) areaPastasInicial.style.display = "none";
           if (areaListaInicial) areaListaInicial.style.display = "block";
           const tituloInicial =
                document.getElementById("titulo-grupo");
           if (tituloInicial) {
                tituloInicial.textContent = "Todas as impressoras";
           }
           atualizarDescricaoSecao(
                "Impressoras cadastradas no monitoramento."
           );
           const botaoImpressorasInicial =
                document.querySelector('.item-menu[data-secao="impressoras"]');
           if (botaoImpressorasInicial) {
                botaoImpressorasInicial.classList.add("is-active");
                botaoImpressorasInicial.setAttribute("aria-pressed", "true");
           }

           function atualizarEstadoBotaoMenu() {
                const botoes = document.querySelectorAll(".item-menu");
                const secaoAtual = secaoMenuAtiva;
                const graficoInicial = document.getElementById("grafico-printer-inicio");
                if (graficoInicial) {
                    graficoInicial.hidden = secaoAtual !== null || !painelPode("report.analyze");
                }

                botoes.forEach(botao => {
                    const ativo = botao.dataset.secao === secaoAtual;
                    botao.classList.toggle("is-active", ativo);
                    botao.setAttribute("aria-pressed", String(ativo));
                    botao.title = botao.title || botao.dataset.secao || "Menu";
                });
            }

           function atualizarDescricaoSecao(texto) {
                const descricao =
                    document.getElementById("descricao-grupo");

                if (descricao) {
                    descricao.textContent = texto;
                }
           }

           function alternarSecaoMenu(secao, abrir) {
                if (secaoMenuAtiva === secao) {
                    secaoMenuAtiva = null;
                    atualizarEstadoBotaoMenu();
                    esconderAreas();
                    window.scrollTo({
                        top: 0,
                        behavior: "smooth"
                    });
                    return;
                }

                secaoMenuAtiva = secao;
                atualizarEstadoBotaoMenu();
                abrir();
            }

           function esconderAreas() {
                pesquisaImpressorasAtiva = false;

                const ids = [
                    "area-pastas",
                    "area-lista",
                    "area-estoque",
                    "area-tabela-estoque",
                    "formulario-toner",
                    "formulario-saida-toner",
                    "area-historico",
                    "area-relatorio-impressoes",
                    "area-relatorio-printer"
                ];

                ids.forEach(function(id) {

                    const elemento =
                        document.getElementById(id);

                    if (elemento) {
                        if (elemento instanceof HTMLDialogElement) {
                            if (elemento.open) {
                                elemento.close();
                            }
                        } else {
                            elemento.style.display = "none";
                        }
                    }

                });


                // ==================================================
                // RESTAURA A TABELA PRINCIPAL
                // ==================================================

                const tabelaImpressoras =
                    document.getElementById(
                        "tabela-impressoras"
                    );

                if (tabelaImpressoras) {

                    tabelaImpressoras.style.display =
                        "table";
                    tabelaImpressoras.classList.remove(
                        "tabela-impressoras-offline",
                        "tabela-impressoras-toner-baixo"
                    );

                }


                // ==================================================
                // ESCONDE A TABELA DE NÃO CONFIÁVEIS
                // ==================================================

                const areaNaoConfiaveis =
                    document.getElementById(
                        "area-nao-confiaveis"
                    );

                if (areaNaoConfiaveis) {

                    areaNaoConfiaveis.style.display =
                        "none";

                }


                // ==================================================
                // MOSTRA OS CARTÕES
                // ==================================================

                const cartoes =
                    document.querySelector(".cartoes");

                if (cartoes) {

                    cartoes.style.display =
                        "grid";

                }

            }
            /* ======================================================
                 BARRA DE PESQUISA  
            ====================================================== */
            function pesquisarImpressoras() {

                const campo =
                    document.getElementById("pesquisa");
                if (!campo) return;

                const normalizar = valor =>
                    String(valor || "")
                        .normalize("NFD")
                        .replace(/[\u0300-\u036f]/g, "")
                        .toLocaleLowerCase()
                        .trim();
                const termo = normalizar(campo.value);
                const lista = document.getElementById("area-lista");
                const pastas = document.getElementById("area-pastas");
                const tabela = document.getElementById("tabela-impressoras");
                const cartoes = document.querySelector(".cartoes");
                const titulo = document.getElementById("titulo-grupo");

                resetarFiltrosTabela();
                esconderAreas();
                pesquisaImpressorasAtiva = true;
                secaoMenuAtiva = null;

                if (lista) lista.style.display = "block";
                if (pastas) pastas.style.display = "none";
                if (tabela) {
                    tabela.style.display = "table";
                    tabela.classList.remove(
                        "tabela-impressoras-offline",
                        "tabela-impressoras-toner-baixo"
                    );
                }
                if (cartoes) cartoes.style.display = "none";
                if (titulo) {
                    titulo.textContent = termo
                        ? "Resultados da pesquisa"
                        : "Impressoras";
                }

                const linhas = document.querySelectorAll(
                    "#corpo-tabela-impressoras tr[data-ip]"
                );
                let resultados = 0;

                linhas.forEach(function(linha) {
                    const campos = [
                        linha.dataset.setor,
                        linha.dataset.grupo,
                        linha.dataset.ip,
                        linha.dataset.modelo,
                        linha.dataset.patrimonio,
                        linha.dataset.status
                    ];
                    const corresponde = !termo || campos.some(
                        valor => normalizar(valor).includes(termo)
                    );

                    linha.style.display = corresponde ? "" : "none";
                    if (corresponde) {
                        resultados += 1;
                    }
                });

                if (termo && resultados === 0 && titulo) {
                    titulo.textContent = "Nenhuma impressora encontrada";
                    atualizarDescricaoSecao(
                        "Tente outro termo de pesquisa ou limpe o filtro."
                    );
                } else if (!termo) {
                    atualizarDescricaoSecao("Impressoras cadastradas no monitoramento.");
                }
            }





         

            function abrirRelatorioPrinter() {
                esconderAreas();

                const area = document.getElementById("area-relatorio-printer");
                if (!area) {
                    return;
                }

                area.style.display = "block";
                carregarHistoricoPrinter();
                const cartoes = document.querySelector(".cartoes");
                if (cartoes) {
                    cartoes.style.display = "none";
                }

                window.scrollTo({
                    top: area.offsetTop - 20,
                    behavior: "smooth"
                });
            }

            let historicoPrinter = [];
            let sequenciaHistoricoPrinter = 0;

            async function carregarHistoricoPrinter() {
                const status = document.getElementById("status-historico-printer");
                const sequencia = ++sequenciaHistoricoPrinter;
                try {
                    const resposta = await api.buscarHistoricoPrinter();
                    if (!resposta.ok) {
                        throw new Error(`Não foi possível consultar o histórico (HTTP ${resposta.status}).`);
                    }
                    const dados = await resposta.json();
                    if (sequencia !== sequenciaHistoricoPrinter) return;
                    historicoPrinter = dados.relatorios;
                    const meses = [...new Set(historicoPrinter.map(item => item.competencia))].sort();
                    ["comparar-printer-a", "comparar-printer-b"].forEach((id, indice) => {
                        const seletor = document.getElementById(id);
                        const anterior = seletor.value;
                        seletor.replaceChildren();
                        meses.forEach(mes => {
                            const opcao = document.createElement("option");
                            opcao.value = mes;
                            opcao.textContent = mes.split("-").reverse().join("/");
                            seletor.appendChild(opcao);
                        });
                        if (meses.includes(anterior)) {
                            seletor.value = anterior;
                        } else if (meses.length) {
                            seletor.value = meses[Math.max(0, meses.length - (indice === 0 ? 2 : 1))];
                        }
                    });
                    const lista = document.getElementById("lista-historico-printer");
                    lista.replaceChildren();
                    if (!historicoPrinter.length) {
                        const item = document.createElement("li");
                        item.textContent = "Nenhum relatório salvo.";
                        lista.appendChild(item);
                    }
                    historicoPrinter.forEach(relatorio => {
                        const item = document.createElement("li");
                        const categorias = Object.entries(relatorio.categorias)
                            .map(([nome, valor]) => `${nome}: ${valor.toLocaleString("pt-BR")}`)
                            .join("; ");
                        item.appendChild(document.createTextNode(
                            `${relatorio.setor} — ${relatorio.competencia.split("-").reverse().join("/")} — ` +
                            `${relatorio.paginas.toLocaleString("pt-BR")} páginas (${categorias})` +
                            (relatorio.pagina_metro_linear !== null
                                ? `; página/metro linear: ${relatorio.pagina_metro_linear} (não somado)`
                                : "") + " — "
                        ));
                        const link = document.createElement("a");
                        link.href = `/api/relatorio-printer/historico/${relatorio.id}/pdf`;
                        link.className = "text-blue-700 underline";
                        link.textContent = "Baixar PDF";
                        item.appendChild(link);
                        lista.appendChild(item);
                    });
                    mostrarComparacaoPrinter();
                    mostrarGraficoHistoricoPrinter();
                } catch (erro) {
                    if (sequencia !== sequenciaHistoricoPrinter) return;
                    document.getElementById("grafico-inicio-printer").replaceChildren();
                    document.getElementById("tabela-grafico-inicio-printer").hidden = true;
                    const vazio = document.getElementById("grafico-inicio-vazio");
                    vazio.textContent = "Não foi possível carregar os dados do gráfico.";
                    vazio.hidden = false;
                    status.textContent = erro.message || "Erro ao consultar o histórico.";
                }
            }

            function mostrarGraficoHistoricoPrinter() {
                const grafico = document.getElementById("grafico-inicio-printer");
                const vazio = document.getElementById("grafico-inicio-vazio");
                const tabela = document.getElementById("tabela-grafico-inicio-printer");
                const corpo = document.getElementById("dados-grafico-inicio-printer");
                grafico.replaceChildren();
                corpo.replaceChildren();

                const meses = [...new Set(historicoPrinter.map(item => item.competencia))].sort();
                vazio.textContent = "Salve relatórios para visualizar o gráfico.";
                vazio.hidden = meses.length > 0;
                tabela.hidden = meses.length === 0;
                if (!meses.length) {
                    return;
                }

                const setores = [
                    { nome: "Saúde", cor: "#1d4ed8" },
                    { nome: "Tesouro", cor: "#047857" },
                    { nome: "Educação", cor: "#d97706" }
                ];
                const largura = Math.max(640, 90 + meses.length * 140);
                const inicioX = 80;
                const baseY = 250;
                const altura = 200;
                const espacoMes = (largura - inicioX - 20) / meses.length;
                const maximo = Math.max(1, ...historicoPrinter.map(item => item.paginas));
                const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
                svg.setAttribute("viewBox", `0 0 ${largura} 300`);
                svg.setAttribute("width", largura);
                svg.setAttribute("height", "300");
                svg.style.maxWidth = "none";
                const elemento = (tipo, atributos, texto) => {
                    const no = document.createElementNS("http://www.w3.org/2000/svg", tipo);
                    Object.entries(atributos).forEach(([nome, valor]) => no.setAttribute(nome, valor));
                    if (texto !== undefined) {
                        no.textContent = texto;
                    }
                    svg.appendChild(no);
                    return no;
                };
                for (let passo = 0; passo <= 4; passo++) {
                    const y = baseY - altura * passo / 4;
                    elemento("line", { x1: inicioX, x2: largura - 10, y1: y, y2: y, stroke: "#d1d5db" });
                    elemento("text", {
                        x: inicioX - 8, y: y + 4, "text-anchor": "end",
                        fill: "#374151", "font-size": "12"
                    }, Math.round(maximo * passo / 4).toLocaleString("pt-BR"));
                }
                meses.forEach((mes, indice) => {
                    const inicioMes = inicioX + indice * espacoMes;
                    const linha = document.createElement("tr");
                    const celulaMes = document.createElement("th");
                    celulaMes.scope = "row";
                    celulaMes.textContent = mes.split("-").reverse().join("/");
                    linha.appendChild(celulaMes);
                    elemento("text", {
                        x: inicioMes + espacoMes / 2, y: baseY + 25,
                        "text-anchor": "middle", fill: "#374151", "font-size": "12"
                    }, celulaMes.textContent);
                    setores.forEach((setor, indiceSetor) => {
                        const registro = historicoPrinter.find(item =>
                            item.competencia === mes && item.setor === setor.nome
                        );
                        const celula = document.createElement("td");
                        celula.textContent = registro
                            ? `${registro.paginas.toLocaleString("pt-BR")} páginas`
                            : "Sem relatório";
                        linha.appendChild(celula);
                        if (!registro) {
                            return;
                        }
                        const barraAltura = Math.max(2, registro.paginas / maximo * altura);
                        const x = inicioMes + espacoMes / 2 + (indiceSetor - 1) * 32 - 12;
                        const barra = elemento("rect", {
                            x, y: baseY - barraAltura, width: 24, height: barraAltura,
                            fill: setor.cor
                        });
                        const titulo = document.createElementNS("http://www.w3.org/2000/svg", "title");
                        titulo.textContent = `${setor.nome}, ${celulaMes.textContent}: ${celula.textContent}`;
                        barra.appendChild(titulo);
                        if (registro.paginas === 0) {
                            elemento("text", {
                                x: x + 12, y: baseY - 5, "text-anchor": "middle",
                                fill: "#374151", "font-size": "11"
                            }, "0");
                        }
                    });
                    corpo.appendChild(linha);
                });
                grafico.appendChild(svg);
            }

            function mostrarComparacaoPrinter() {
                const mesA = document.getElementById("comparar-printer-a").value;
                const mesB = document.getElementById("comparar-printer-b").value;
                const corpo = document.getElementById("comparacao-printer");
                corpo.replaceChildren();
                ["Saúde", "Tesouro", "Educação"].forEach(setor => {
                    const a = historicoPrinter.find(item => item.setor === setor && item.competencia === mesA);
                    const b = historicoPrinter.find(item => item.setor === setor && item.competencia === mesB);
                    const diferenca = a && b ? b.paginas - a.paginas : null;
                    const linha = document.createElement("tr");
                    [
                        setor,
                        a ? `${a.paginas.toLocaleString("pt-BR")} páginas` : "Sem relatório",
                        b ? `${b.paginas.toLocaleString("pt-BR")} páginas` : "Sem relatório",
                        diferenca === null ? "—" : `${diferenca > 0 ? "+" : ""}${diferenca.toLocaleString("pt-BR")} páginas`
                    ].forEach(valor => {
                        const celula = document.createElement("td");
                        celula.textContent = valor;
                        linha.appendChild(celula);
                    });
                    corpo.appendChild(linha);
                });
            }

            async function salvarHistoricoPrinter(evento) {
                evento.preventDefault();
                const formulario = evento.currentTarget;
                const botao = formulario.querySelector("button");
                const status = document.getElementById("status-historico-printer");
                const dados = new FormData(formulario);
                botao.disabled = true;
                status.textContent = "Verificando relatório...";
                try {
                    let resposta = await api.salvarHistoricoPrinter(dados);
                    let conteudo = await resposta.json();
                    if (resposta.status === 409 && conteudo.existente_sha256) {
                        const info = conteudo.dados;
                        if (!window.confirm(
                            `Já existe relatório de ${info.setor} para ${info.competencia}. ` +
                            `Substituir pelo novo PDF de ${info.paginas.toLocaleString("pt-BR")} páginas?`
                        )) {
                            status.textContent = "Substituição cancelada; o relatório anterior foi preservado.";
                            return;
                        }
                        dados.set("substituir_sha256", conteudo.existente_sha256);
                        resposta = await api.salvarHistoricoPrinter(dados);
                        conteudo = await resposta.json();
                    }
                    if (!resposta.ok) {
                        throw new Error(conteudo.erro || `Erro ao salvar (HTTP ${resposta.status}).`);
                    }
                    status.textContent = `${conteudo.mensagem} ${conteudo.dados.setor}, ` +
                        `${conteudo.dados.competencia}: ${conteudo.dados.paginas.toLocaleString("pt-BR")} páginas.`;
                    formulario.querySelector('input[type="file"]').value = "";
                    await carregarHistoricoPrinter();
                } catch (erro) {
                    status.textContent = erro.message || "Não foi possível salvar o relatório.";
                } finally {
                    botao.disabled = false;
                }
            }

            document.addEventListener("DOMContentLoaded", function() {
                if (painelPode("report.analyze")) {
                    carregarHistoricoPrinter();
                }
            });

            let substituicoesRelatorio = [];

            function limparSubstituicoesRelatorio() {
                substituicoesRelatorio = [];
            }

            async function analisarRelatorioPrinter(
                mensagemStatus = "",
                substituicoes = substituicoesRelatorio
            ) {
                const entrada = document.getElementById("arquivo-relatorio-printer");
                const botao = document.getElementById("botao-analisar-relatorio");
                const erro = document.getElementById("erro-relatorio-printer");
                const status = document.getElementById("status-aprovacao-relatorio");
                const avisosArquivos = document.getElementById("avisos-arquivos-relatorio");
                const resultado = document.getElementById("resultado-relatorio-printer");
                const resumo = document.getElementById("resumo-relatorio-printer");
                const lista = document.getElementById("lista-divergencias-printer");
                const arquivos = entrada ? Array.from(entrada.files || []) : [];

                if (erro) {
                    erro.hidden = true;
                    erro.textContent = "";
                }
                if (avisosArquivos) {
                    avisosArquivos.hidden = true;
                    avisosArquivos.replaceChildren();
                }
                if (status) {
                    status.hidden = true;
                    status.textContent = "";
                }
                if (resultado) {
                    resultado.hidden = true;
                }
                if (arquivos.length === 0) {
                    if (erro) {
                        erro.textContent = "Selecione pelo menos um PDF do relatório PRINTER.";
                        erro.hidden = false;
                    }
                    return;
                }

                const dados = new FormData();
                arquivos.forEach(arquivo => dados.append("relatorios", arquivo));
                dados.append("substituicoes", JSON.stringify(substituicoes));
                if (botao) {
                    botao.disabled = true;
                    botao.textContent = "Analisando...";
                }

                try {
                    const resposta = await api.analisarRelatorioPrinter(dados);
                    const conteudo = await resposta.json();
                    if (!resposta.ok) {
                        const detalhes = (conteudo.arquivos_com_erro || [])
                            .map(item => `${item.arquivo}: ${item.erro}`)
                            .join(" ");
                        throw new Error(
                            [conteudo.erro, detalhes]
                                .filter(Boolean)
                                .join(" ") ||
                                `Não foi possível analisar os relatórios (HTTP ${resposta.status}).`
                        );
                    }

                    if (!resumo || !lista || !resultado) {
                        throw new Error("A área de resultado do relatório não está disponível na página.");
                    }

                    resumo.textContent =
                        `${conteudo.total_analisado} equipamento(s) analisado(s); ` +
                        `${conteudo.total_divergencias} divergência(s) encontrada(s).` +
                        (conteudo.total_substituicoes
                            ? ` ${conteudo.total_substituicoes} substituição(ões) confirmada(s).`
                            : "");
                    lista.replaceChildren();

                    if (avisosArquivos && conteudo.arquivos_com_erro.length > 0) {
                        const tituloAvisos = document.createElement("strong");
                        tituloAvisos.textContent =
                            "Alguns arquivos não puderam ser analisados:";
                        avisosArquivos.appendChild(tituloAvisos);

                        const listaAvisos = document.createElement("ul");
                        conteudo.arquivos_com_erro.forEach(item => {
                            const aviso = document.createElement("li");
                            aviso.textContent = `${item.arquivo}: ${item.erro}`;
                            listaAvisos.appendChild(aviso);
                        });
                        avisosArquivos.appendChild(listaAvisos);
                        avisosArquivos.hidden = false;
                    }

                    if (conteudo.divergencias.length === 0) {
                        const mensagem = document.createElement("div");
                        mensagem.className = "relatorio-sem-divergencias";
                        mensagem.textContent = "Não foram identificadas divergências.";
                        lista.appendChild(mensagem);
                    } else {
                        conteudo.divergencias.forEach(item => {
                            const cartao = document.createElement("article");
                            cartao.className = "divergencia-printer";

                            const titulo = document.createElement("h4");
                            titulo.textContent = item.detalhe;
                            cartao.appendChild(titulo);

                            [
                                `Identificação PRINTER: ${item.codigo}`,
                                `Número de série: ${item.serie}`,
                                `Modelo: ${item.modelo}`,
                                ...(conteudo.arquivos_analisados.length > 1
                                    ? [`Arquivo: ${item.arquivo}`]
                                    : []),
                                `Local no relatório: ${item.local_relatorio}`,
                                ...(item.local_cadastro
                                    ? [`Local no cadastro: ${item.local_cadastro}`]
                                    : [])
                            ].forEach(texto => {
                                const paragrafo = document.createElement("p");
                                paragrafo.textContent = texto;
                                cartao.appendChild(paragrafo);
                            });

                            const substituicaoConfirmada =
                                substituicoes.some(substituicao =>
                                    String(substituicao.serie)
                                        .replace(/[^A-Z0-9]/gi, "")
                                        .toUpperCase() ===
                                    String(item.serie)
                                        .replace(/[^A-Z0-9]/gi, "")
                                        .toUpperCase()
                                );

                            if (
                                item.tipo_divergencia === "local_divergente" &&
                                substituicaoConfirmada
                            ) {
                                const aviso = document.createElement("p");
                                aviso.textContent =
                                    "Série nova confirmada como substituição. " +
                                    "A diferença de local será mantida como divergência no e-mail; " +
                                    "o cadastro não será alterado.";
                                cartao.appendChild(aviso);
                            } else if (
                                item.tipo_divergencia === "local_divergente" &&
                                painelPode("report.approve")
                            ) {
                                const aprovar = document.createElement("button");
                                aprovar.type = "button";
                                aprovar.className = "botao-aprovar-correcao";
                                aprovar.textContent = "Aprovar correção do local";
                                aprovar.addEventListener("click", () => {
                                    aprovarCorrecaoRelatorio(
                                        item.serie,
                                        item.local_relatorio,
                                        aprovar
                                    );
                                });
                                cartao.appendChild(aprovar);

                                const equivalente = document.createElement("button");
                                equivalente.type = "button";
                                equivalente.className = "botao-aprovar-correcao";
                                equivalente.textContent = "Marcar como mesmo local";
                                equivalente.addEventListener("click", () => {
                                    aprovarEquivalenciaLocal(item, equivalente);
                                });
                                cartao.appendChild(equivalente);
                            } else if (
                                item.tipo_divergencia === "nao_encontrado" &&
                                painelPode("report.approve")
                            ) {
                                const incluir = document.createElement("button");
                                incluir.type = "button";
                                incluir.className = "botao-aprovar-correcao";
                                incluir.textContent = "Cadastrar impressora";
                                incluir.addEventListener("click", () => {
                                    aprovarInclusaoRelatorio(item, incluir);
                                });
                                cartao.appendChild(incluir);

                                const substituicao =
                                    document.createElement("button");
                                substituicao.type = "button";
                                substituicao.className =
                                    "botao-aprovar-correcao";
                                substituicao.textContent =
                                    "Considerar substituição (mesmo IP)";
                                substituicao.addEventListener("click", () => {
                                    aprovarSubstituicaoRelatorio(
                                        item,
                                        substituicao
                                    );
                                });
                                cartao.appendChild(substituicao);
                            }

                            lista.appendChild(cartao);
                        });
                    }

                    document.getElementById("assunto-email-printer").value =
                        conteudo.assunto_email;
                    document.getElementById("corpo-email-printer").value =
                        conteudo.corpo_email;
                    resultado.hidden = false;
                    if (status && mensagemStatus) {
                        status.textContent = mensagemStatus;
                        status.hidden = false;
                    }
                    return true;
                } catch (falha) {
                    if (erro) {
                        erro.textContent = falha.message ||
                            "Ocorreu um erro ao analisar o relatório.";
                        erro.hidden = false;
                    }
                    return false;
                } finally {
                    if (botao) {
                        botao.disabled = false;
                        botao.textContent = "Analisar relatório";
                    }
                }
            }

            async function aprovarSubstituicaoRelatorio(item, botao) {
                const erro = document.getElementById("erro-relatorio-printer");
                const ip = window.prompt(
                    `Informe o IP atual da impressora substituída (${item.serie}):`
                );
                if (ip === null || !ip.trim()) {
                    return;
                }

                const confirmou = window.confirm(
                    `Confirma que a impressora de série ${item.serie} substituiu ` +
                    `a impressora cadastrada no IP ${ip.trim()}?\n\n` +
                    "O cadastro não será alterado; a substituição será informada no e-mail."
                );
                if (!confirmou) {
                    return;
                }

                if (botao) {
                    botao.disabled = true;
                    botao.textContent = "Conferindo substituição...";
                }
                if (erro) {
                    erro.hidden = true;
                    erro.textContent = "";
                }

                const substituicoes = [
                    ...substituicoesRelatorio,
                    {serie: item.serie, ip: ip.trim()}
                ];
                const sucesso = await analisarRelatorioPrinter(
                    "Substituição confirmada pelo mesmo IP. O cadastro foi mantido e o e-mail foi atualizado.",
                    substituicoes
                );
                if (sucesso) {
                    substituicoesRelatorio = substituicoes;
                } else if (botao) {
                    botao.disabled = false;
                    botao.textContent =
                        "Considerar substituição (mesmo IP)";
                }
            }

            async function aprovarCorrecaoRelatorio(serie, local, botao) {
                const erro = document.getElementById("erro-relatorio-printer");
                const confirmou = window.confirm(
                    `Confirma atualizar o local da impressora ${serie} para "${local}"? ` +
                    "O arquivo original será preservado."
                );
                if (!confirmou) {
                    return;
                }

                if (botao) {
                    botao.disabled = true;
                    botao.textContent = "Atualizando...";
                }
                if (erro) {
                    erro.hidden = true;
                    erro.textContent = "";
                }

                try {
                    const resposta = await api.aprovarCorrecaoPrinter({serie, local});
                    const conteudo = await resposta.json();
                    if (!resposta.ok) {
                        throw new Error(
                            conteudo.erro ||
                            `Não foi possível aplicar a correção (HTTP ${resposta.status}).`
                        );
                    }

                    const cartao = botao && botao.closest(".divergencia-printer");
                    if (cartao) {
                        cartao.remove();
                    }

                    await analisarRelatorioPrinter(
                        "Correção aprovada e salva no arquivo atualizado. " +
                        "A divergência e o modelo de e-mail foram recalculados."
                    );
                } catch (falha) {
                    if (erro) {
                        erro.textContent = falha.message ||
                            "Não foi possível aplicar a correção aprovada.";
                        erro.hidden = false;
                    }
                    if (botao) {
                        botao.disabled = false;
                        botao.textContent = "Aprovar correção do local";
                    }
                }
            }

            async function aprovarInclusaoRelatorio(item, botao) {
                const erro = document.getElementById("erro-relatorio-printer");
                const ip = window.prompt(
                    `Informe o endereço IP da impressora ${item.serie}:`
                );
                if (ip === null || !ip.trim()) {
                    return;
                }

                const confirmou = window.confirm(
                    `Autoriza cadastrar a impressora?\n\n` +
                    `Série: ${item.serie}\nModelo: ${item.modelo}\n` +
                    `Local: ${item.local_relatorio}\nIP: ${ip.trim()}`
                );
                if (!confirmou) {
                    return;
                }

                if (botao) {
                    botao.disabled = true;
                    botao.textContent = "Cadastrando...";
                }
                if (erro) {
                    erro.hidden = true;
                    erro.textContent = "";
                }

                try {
                    const enviarInclusao = substituirIp =>
                        api.aprovarInclusaoPrinter({
                            serie: item.serie,
                            modelo: item.modelo,
                            local: item.local_relatorio,
                            ip: ip.trim(),
                            substituir_ip: substituirIp
                        });
                    let resposta = await enviarInclusao(false);
                    let conteudo = await resposta.json();
                    if (
                        resposta.status === 409 &&
                        conteudo.codigo === "ip_ja_cadastrado"
                    ) {
                        const registro = conteudo.registro_existente || {};
                        const substituir = window.confirm(
                            `O IP ${ip.trim()} já está cadastrado:\n` +
                            `${registro.nome || "Nome não informado"}\n` +
                            `Série atual: ${registro.serie || "não informada"}\n\n` +
                            `Deseja substituir esse registro pela impressora do relatório?\n` +
                            `Nova série: ${item.serie}\n` +
                            `Novo local/modelo: ${item.local_relatorio} (${item.modelo})`
                        );
                        if (!substituir) {
                            if (botao) {
                                botao.disabled = false;
                                botao.textContent = "Cadastrar impressora";
                            }
                            return;
                        }

                        resposta = await enviarInclusao(true);
                        conteudo = await resposta.json();
                    }

                    if (!resposta.ok) {
                        throw new Error(
                            conteudo.erro ||
                            `Não foi possível cadastrar a impressora (HTTP ${resposta.status}).`
                        );
                    }

                    await analisarRelatorioPrinter(
                        "Impressora cadastrada após sua aprovação. " +
                        "A divergência e o modelo de e-mail foram recalculados."
                    );
                } catch (falha) {
                    if (erro) {
                        erro.textContent = falha.message ||
                            "Não foi possível cadastrar a impressora aprovada.";
                        erro.hidden = false;
                    }
                    if (botao) {
                        botao.disabled = false;
                        botao.textContent = "Cadastrar impressora";
                    }
                }
            }

            async function aprovarEquivalenciaLocal(item, botao) {
                const erro = document.getElementById("erro-relatorio-printer");
                const confirmou = window.confirm(
                    `Confirma que estes nomes representam o mesmo local?\n\n` +
                    `No relatório: ${item.local_relatorio}\n` +
                    `No cadastro: ${item.local_cadastro}\n\n` +
                    "A equivalência ficará salva para relatórios futuros, " +
                    "sem alterar o nome principal do cadastro."
                );
                if (!confirmou) {
                    return;
                }

                if (botao) {
                    botao.disabled = true;
                    botao.textContent = "Salvando equivalência...";
                }
                if (erro) {
                    erro.hidden = true;
                    erro.textContent = "";
                }

                try {
                    const resposta = await api.aprovarEquivalenciaPrinter({
                        serie: item.serie,
                        local_relatorio: item.local_relatorio,
                        local_cadastro: item.local_cadastro
                    });
                    const conteudo = await resposta.json();
                    if (!resposta.ok) {
                        throw new Error(
                            conteudo.erro ||
                            `Não foi possível salvar a equivalência (HTTP ${resposta.status}).`
                        );
                    }

                    await analisarRelatorioPrinter(
                        "Equivalência aprovada e salva para relatórios futuros. " +
                        "A divergência e o modelo de e-mail foram recalculados."
                    );
                } catch (falha) {
                    if (erro) {
                        erro.textContent = falha.message ||
                            "Não foi possível salvar a equivalência do local.";
                        erro.hidden = false;
                    }
                    if (botao) {
                        botao.disabled = false;
                        botao.textContent = "Marcar como mesmo local";
                    }
                }
            }

            async function copiarEmailPrinter() {
                const assunto = document.getElementById("assunto-email-printer");
                const corpo = document.getElementById("corpo-email-printer");
                const status = document.getElementById("status-copiar-email-printer");
                const texto = `Assunto: ${assunto.value}\n\n${corpo.value}`;

                try {
                    await navigator.clipboard.writeText(texto);
                } catch (_falha) {
                    const temporario = document.createElement("textarea");
                    temporario.value = texto;
                    temporario.setAttribute("readonly", "");
                    temporario.style.position = "fixed";
                    temporario.style.opacity = "0";
                    document.body.appendChild(temporario);
                    temporario.select();
                    const copiado = document.execCommand("copy");
                    temporario.remove();
                    if (!copiado) {
                        if (status) {
                            status.textContent = "Não foi possível copiar. Selecione e copie o texto manualmente.";
                        }
                        return;
                    }
                }

                if (status) {
                    status.textContent = "E-mail copiado.";
                }
            }



            function carregar_offline() {

                resetarFiltrosTabela();
                esconderAreas();

                const lista =
                    document.getElementById("area-lista");

                if (!lista) {

                    console.error(
                        "ERRO: area-lista não encontrada."
                    );

                    return;
                }

                lista.style.display = "block";
                const tabela =
                    document.getElementById("tabela-impressoras");
                if (tabela) {
                    tabela.classList.add("tabela-impressoras-offline");
                }

                const titulo =
                    document.getElementById("titulo-grupo");

                if (titulo) {

                    titulo.textContent = "Impressoras Offline";

                }
                atualizarDescricaoSecao(
                    "Equipamentos que não responderam à última consulta SNMP. Isso não confirma que estão desligados."
                );

                const botaoOffline = document.querySelector(
                    '.filtro-status button[data-filtro-status="Offline"]'
                );
                definirFiltroStatus("Offline", botaoOffline);

                const pesquisa =
                    document.getElementById("pesquisa");

                if (pesquisa) {
                    pesquisa.value = "";
                }

                window.scrollTo({
                    top: lista.offsetTop - 20,
                    behavior: "smooth"
                });
            }
            
            function fecharOffline() {

                esconderAreas();

                window.scrollTo({
                    top: 0,
                    behavior: "smooth"
                });
            }

            /* ==================================================
            TONERS BAIXOS
             ================================================== */
            async function mostrarTonerBaixo() {

                resetarFiltrosTabela();
                esconderAreas();

                const lista = document.getElementById("area-lista");

                if (!lista) {
                    console.error("ERRO: area-lista não encontrada.");
                    return;
                }

                lista.style.display = "block";
                const tabela =
                    document.getElementById("tabela-impressoras");
                if (tabela) {
                    tabela.classList.add("tabela-impressoras-toner-baixo");
                }

                const titulo = document.getElementById("titulo-grupo");

                if (titulo) {
                    titulo.textContent = "Toners baixos";
                }
                filtroTonerBaixo = true;
                atualizarDescricaoTonerBaixo();
                filtrarTabelaDashboard();

                window.scrollTo({
                    top: lista.offsetTop - 20,
                    behavior: "smooth"
                });
            }

            function atualizarResumoEstoque(lista) {
                const total = lista.length;
                const emDia = lista.filter(
                    toner => toner.ativo && toner.estoque > toner.estoque_minimo
                ).length;
                const baixo = lista.filter(
                        toner => toner.ativo && toner.estoque <= toner.estoque_minimo
                    ).length;
                    const inativos = lista.filter(toner => !toner.ativo).length;

                    const atualizarCampo = (id, valor) => {
                        const elemento = document.getElementById(id);
                        if (elemento) {
                            elemento.textContent = valor;
                        }
                    };

                    atualizarCampo("estoque-total", total);
                    atualizarCampo("estoque-ok", emDia);
                    atualizarCampo("estoque-baixo", baixo);
                    atualizarCampo("estoque-inativos", inativos);
                const contagem = document.getElementById("estoque-contagem");
                if (contagem) {
                    contagem.textContent = `${total} toner(s)`;
                }
                const contagemBaixo = document.getElementById(
                    "estoque-contagem-baixo"
                );
                if (contagemBaixo) {
                    contagemBaixo.textContent = `${baixo} com estoque baixo`;
                }
            }

            async function mostrarEstoque(rolar = true) {
                const areaEstoque = document.getElementById("area-estoque");
                const areaTabela = document.getElementById("area-tabela-estoque");
                const tabela = document.getElementById("corpo-tabela-estoque");
                if (!areaEstoque || !areaTabela || !tabela) {
                    return;
                }

                if (!document.getElementById("estoque-compatibilidade-coluna")) {
                    const coluna = document.createElement("th");
                    coluna.id = "estoque-compatibilidade-coluna";
                    coluna.textContent = "Impressoras compatíveis";
                    tabela.closest("table").querySelectorAll("thead th")[2].after(coluna);
                }
                if (!document.getElementById("estoque-compatibilidade-status")) {
                    const status = document.createElement("p");
                    status.id = "estoque-compatibilidade-status";
                    status.className = "mb-3 text-sm text-gray-600";
                    status.setAttribute("role", "status");
                    tabela.closest(".overflow-x-auto").before(status);
                }
                esconderAreas();
                areaEstoque.style.display = "block";
                areaTabela.style.display = "block";
                carregarPedidosEstoque();

                const mostrarInativos = document.getElementById(
                    "mostrar-toners-inativos"
                );
                const incluirInativos =
                    localStorage.getItem("mostrar_toners_inativos") === "1";
                if (mostrarInativos) {
                    mostrarInativos.checked = incluirInativos;
                }

                if (rolar) tabela.innerHTML = `

                    <tr>

                        <td
                            colspan="9"
                            class="text-center">

                            Carregando estoque...

                        </td>

                    </tr>

                `;


                try {

                    const resposta =
                        await api.buscarEstoque(incluirInativos);


                    if (!resposta.ok) {

                        throw new Error(
                            "Erro HTTP " +
                            resposta.status
                        );

                    }


                    const toners =
                        await resposta.json();

                    atualizarResumoEstoque(toners);

                    tabela.innerHTML = "";


                    if (!toners.length) {

                        tabela.innerHTML = `

                            <tr>

                                <td
                                    colspan="9"
                                    class="text-center">

                                    Nenhum toner cadastrado.

                                </td>

                            </tr>

                        `;


                        return;

                    }


                    toners.forEach(
                        function(toner) {

                            let situacao;

                            if (!toner.ativo) {
                                situacao = `
                                    <span class="badge bg-secondary">
                                        Inativo
                                    </span>
                                `;
                            } else if (
                                toner.estoque <=
                                toner.estoque_minimo
                            ) {

                                situacao = `

                                    <span
                                        class="badge bg-danger">

                                        Estoque baixo

                                    </span>

                                `;

                            } else {

                                situacao = `

                                    <span
                                        class="badge bg-success">

                                        OK

                                    </span>

                                `;

                            }

                            tabela.innerHTML += `

                                <tr class="${toner.ativo ? "" : "table-secondary"}" data-busca-estoque="${escaparHtml(`${toner.codigo} ${toner.modelos_compativeis || ""}`)}">

                                    <td>
                                        ${escaparHtml(toner.marca)}
                                    </td>

                                    <td>
                                        ${escaparHtml(toner.codigo)}
                                    </td>

                                    <td>
                                        <span id="modelos-toner-${toner.id}">${escaparHtml(toner.modelos_compativeis || "Não configurado")}</span>
                                        ${
                                            painelPode("toner.manage")
                                                ? `<button class="btn btn-sm btn-outline-primary ms-1" onclick="editarModelosCompativeis(${toner.id})">Editar</button>`
                                                : ""
                                        }
                                    </td>

                                    <td>
                                        <span id="compatibilidade-toner-${toner.id}">Calculando...</span>
                                    </td>

                                    <td>
                                        ${escaparHtml(toner.cor)}
                                    </td>

                                    <td>
                                        ${
                                            painelPode("stock.adjust") && toner.ativo
                                                ? `<button type="button" aria-label="Ajustar estoque de ${escaparHtml(toner.codigo)}" title="Ajustar estoque" onclick="abrirAjusteEstoque(${toner.id}, this)"><strong>${toner.estoque}</strong></button>`
                                                : `<strong>${toner.estoque}</strong>`
                                        }
                                    </td>

                                    <td>
                                        ${toner.estoque_minimo}
                                        ${
                                            painelPode("stock.adjust")
                                                ? `<button type="button" class="btn btn-sm btn-outline-primary ms-1" aria-label="Alterar estoque mínimo" title="Alterar estoque mínimo" onclick="editarEstoqueMinimo(${toner.id}, ${toner.estoque_minimo})"><svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></svg></button>`
                                                : ""
                                        }
                                    </td>

                                    <td>
                                        ${situacao}
                                    </td>
                                    <td>
                                        ${
                                            toner.ativo
                                                ? painelPode("toner.manage")
                                                    ? `<button type="button" class="btn btn-sm btn-danger" aria-label="Remover toner" title="Remover toner" onclick="removerToner(${toner.id})"><svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2m3 0-1 14H6L5 6m5 4v6m4-6v6"/></svg></button>`
                                                    : ""
                                                : painelPode("toner.manage")
                                                    ? `<button class="btn btn-sm btn-success" onclick="reativarToner(${toner.id})">Reativar</button>`
                                                    : ""
                                        }
                                    </td>

                                </tr>

                            `;

                        }
                    );

                    filtrarEstoque(document.getElementById("busca-estoque").value);
                    carregarCompatibilidadeToners();

                } catch (erro) {

                    console.error(
                        "Erro ao carregar estoque:",
                        erro
                    );


                    tabela.innerHTML = `

                        <tr>

                            <td
                                colspan="9"
                                class="text-center text-danger">

                                Erro ao carregar o estoque.

                            </td>

                        </tr>

                    `;

                }


                if (rolar) window.scrollTo({

                    top:
                        document.getElementById(
                            "area-estoque"
                        ).offsetTop - 20,

                    behavior: "smooth"

                });

            }

            function escaparHtml(valor) {
                const entidades = {
                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    '"': "&quot;",
                    "'": "&#39;"
                };
                return String(valor == null ? "" : valor).replace(
                    /[&<>"']/g,
                    caracter => entidades[caracter]
                );
            }

            function filtrarEstoque(valor) {
                const normalizar = texto => String(texto).normalize("NFD")
                    .replace(/[\u0300-\u036f]/g, "")
                    .toLocaleLowerCase().trim();
                const termo = normalizar(valor);
                const tabela = document.getElementById("corpo-tabela-estoque");
                if (!tabela) return;
                const linhas = tabela.querySelectorAll("tr[data-busca-estoque]");
                let visiveis = 0;
                linhas.forEach(linha => {
                    const corresponde = normalizar(linha.dataset.buscaEstoque).includes(termo);
                    linha.hidden = !corresponde;
                    if (corresponde) visiveis++;
                });Rem
                let vazio = document.getElementById("estoque-sem-resultados");
                if (linhas.length && !visiveis) {
                    if (!vazio) {
                        vazio = document.createElement("tr");
                        vazio.id = "estoque-sem-resultados";
                        vazio.innerHTML = '<td colspan="9" class="text-center">Nenhum toner encontrado para esta pesquisa.</td>';
                        tabela.appendChild(vazio);
                    }
                } else if (vazio) {
                    vazio.remove();
                }
            }

            let requisicaoRelatorioImpressoes = 0;

            function alterarMesRelatorioImpressoes() {
                requisicaoRelatorioImpressoes++;
                document.getElementById("resultado-relatorio-impressoes").hidden = true;
                document.getElementById("baixar-relatorio-impressoes").hidden = true;
                document.getElementById("status-relatorio-impressoes").textContent =
                    "Clique em Consultar para atualizar o relatório.";
            }

            function abrirRelatorioImpressoes() {
                esconderAreas();
                const area = document.getElementById("area-relatorio-impressoes");
                area.style.display = "block";
                const mes = document.getElementById("mes-relatorio-impressoes");
                if (!mes.value) {
                    const anterior = new Date();
                    anterior.setDate(1);
                    anterior.setMonth(anterior.getMonth() - 1);
                    mes.value = `${anterior.getFullYear()}-${String(anterior.getMonth() + 1).padStart(2, "0")}`;
                }
                carregarRelatorioImpressoes();
            }

            async function carregarRelatorioImpressoes(evento) {
                if (evento) evento.preventDefault();
                const campoMes = document.getElementById("mes-relatorio-impressoes");
                if (!campoMes.reportValidity()) return;
                const mes = campoMes.value;
                const requisicao = ++requisicaoRelatorioImpressoes;
                const status = document.getElementById("status-relatorio-impressoes");
                const resultado = document.getElementById("resultado-relatorio-impressoes");
                const download = document.getElementById("baixar-relatorio-impressoes");
                resultado.hidden = true;
                download.hidden = true;
                status.textContent = "Carregando relatório...";
                try {
                    const resposta = await api.buscarRelatorioImpressoes(mes);
                    const dados = await resposta.json();
                    if (!resposta.ok) throw new Error(dados.erro || "Não foi possível carregar o relatório.");
                    if (requisicao !== requisicaoRelatorioImpressoes || secaoMenuAtiva !== "relatorio-impressoes") return;
                    const numero = valor => valor === null ? "—" : valor.toLocaleString("pt-BR");
                    const leitura = (valor, data, erro) => {
                        if (valor === null) {
                            return `—<br><small>${escaparHtml(erro || "Leitura não registrada")}</small>`;
                        }
                        return `${numero(valor)}<br><small>${escaparHtml(data.replace("T", " "))}</small>`;
                    };
                    const categoria = (item, chave) => {
                        if (!item.cor_aplicavel) return "—";
                        const dado = item.categorias_cor[chave];
                        return `${numero(dado.inicial)} → ${numero(dado.final)}<br><strong>${dado.impressoes === null ? "—" : `${numero(dado.impressoes)} ${dado.impressoes === 1 ? "página" : "páginas"}`}</strong><br><small>${escaparHtml(dado.situacao)}</small>`;
                    };
                    const horariosCor = item => {
                        if (!item.cor_aplicavel) return "Não disponível para este modelo";
                        const inicial = item.cor_coletado_inicial ? item.cor_coletado_inicial.replace("T", " ") : item.cor_erro_inicial || "Não registrada";
                        const final = item.cor_coletado_final ? item.cor_coletado_final.replace("T", " ") : item.cor_erro_final || "Não registrada";
                        return `Início: ${escaparHtml(inicial)}<br>Fim: ${escaparHtml(final)}`;
                    };
                    const corpo = document.getElementById("corpo-relatorio-impressoes");
                    corpo.innerHTML = dados.itens.length ? dados.itens.map(item => `
                        <tr>
                            <td><strong>${escaparHtml(item.nome)}</strong><br><small>${escaparHtml(item.modelo || "Modelo não informado")}</small></td>
                            <td>${escaparHtml(item.grupo || "Não informado")}<br><small>Patrimônio: ${escaparHtml(item.patrimonio || "Não informado")}</small></td>
                            <td>${leitura(item.contador_inicial, item.coletado_inicial, item.erro_inicial)}</td>
                            <td>${leitura(item.contador_final, item.coletado_final, item.erro_final)}</td>
                            <td>${numero(item.impressoes)}</td>
                            <td>${escaparHtml(item.situacao)}</td>
                            <td>${categoria(item, "preto_branco")}</td>
                            <td>${categoria(item, "nivel_1")}</td>
                            <td>${categoria(item, "nivel_2")}</td>
                            <td>${categoria(item, "nivel_3")}</td>
                            <td>${horariosCor(item)}</td>
                        </tr>`).join("") : '<tr><td colspan="11">Nenhuma impressora cadastrada ou leitura encontrada.</td></tr>';
                    document.getElementById("resumo-relatorio-impressoes").textContent =
                        `Total dos equipamentos calculados: ${dados.total_calculado === null ? "sem dados" : `${numero(dados.total_calculado)} páginas`}. Equipamentos sem total: ${dados.sem_total}.`;
                    download.href = `/api/relatorio-impressoes/excel?mes=${encodeURIComponent(mes)}`;
                    download.hidden = false;
                    resultado.hidden = false;
                    status.textContent = `Comparação das leituras de ${dados.inicio} e ${dados.fim}.`;
                } catch (erro) {
                    if (requisicao !== requisicaoRelatorioImpressoes || secaoMenuAtiva !== "relatorio-impressoes") return;
                    console.error("Erro ao consultar relatório de impressões:", erro);
                    status.textContent = erro.message || "Não foi possível carregar o relatório.";
                }
            }

            let requisicaoCompatibilidadeToners = 0;

            async function carregarCompatibilidadeToners() {
                const requisicao = ++requisicaoCompatibilidadeToners;
                const status = document.getElementById("estoque-compatibilidade-status");
                const descricao = "Contagem estimada pelo modelo ou família cadastrada, incluindo impressoras offline. Um equipamento pode ser compatível com mais de um toner; a contagem não confirma o toner instalado.";
                try {
                    const resposta = await api.buscarCompatibilidadeToners();
                    if (!resposta.ok) throw new Error("HTTP " + resposta.status);
                    const dados = await resposta.json();
                    if (requisicao !== requisicaoCompatibilidadeToners) return;
                    Object.entries(dados.contagens).forEach(([id, quantidade]) => {
                        const campo = document.getElementById(`compatibilidade-toner-${id}`);
                        if (!campo) return;
                        const lista = dados.impressoras_por_toner && dados.impressoras_por_toner[id];
                        if (quantidade !== null && Array.isArray(lista) && lista.length === quantidade) {
                            const codigo = campo.closest("tr").cells[1].textContent.trim();
                            const botao = document.createElement("button");
                            botao.type = "button";
                            botao.textContent = quantidade;
                            botao.setAttribute("aria-label", `Ver ${quantidade} impressoras compatíveis com ${codigo}`);
                            botao.title = "Ver impressoras compatíveis";
                            botao.addEventListener("click", () => mostrarImpressorasCompativeis(codigo, lista));
                            campo.replaceChildren(botao);
                        } else {
                            campo.textContent = quantidade === null ? "Modelo não identificado" : quantidade;
                        }
                    });
                    status.textContent = descricao + (dados.impressoras_por_toner
                        ? " Clique na quantidade para ver as impressoras."
                        : " A lista de impressoras exige permissão de monitoramento.")
                        + (dados.modelos_nao_identificados
                        ? ` ${dados.modelos_nao_identificados} impressora(s) sem modelo identificado não entram na contagem.`
                        : "");
                } catch (erro) {
                    if (requisicao !== requisicaoCompatibilidadeToners) return;
                    console.error("Erro ao calcular impressoras compatíveis:", erro);
                    document.querySelectorAll('[id^="compatibilidade-toner-"]').forEach(campo => {
                        campo.textContent = "Indisponível";
                    });
                    status.textContent = "Não foi possível calcular as impressoras compatíveis. Atualize o estoque para tentar novamente.";
                }
            }

            function mostrarImpressorasCompativeis(codigo, impressoras) {
                const dialogo = document.getElementById("impressoras-compativeis");
                const titulo = document.getElementById("impressoras-compativeis-titulo");
                const lista = document.getElementById("impressoras-compativeis-lista");
                titulo.textContent = `Impressoras compatíveis — ${codigo}`;
                lista.innerHTML = impressoras.length
                    ? `<p class="mb-3 text-sm font-semibold">${impressoras.length} impressora(s) compatível(is)</p>
                       <ul class="grid gap-3">${impressoras.map(impressora => `
                           <li class="rounded-lg border border-gray-200 p-3 text-sm">
                               <strong>${escaparHtml(impressora.nome || "Nome não informado")}</strong>
                               <div>Modelo: ${escaparHtml(impressora.modelo || "Não informado")}</div>
                               <div>Setor: ${escaparHtml(impressora.grupo || "Não informado")}</div>
                               <div>Patrimônio: ${escaparHtml(impressora.patrimonio || "Não informado")}</div>
                               <div>IP: ${escaparHtml(impressora.ip || "Não informado")}</div>
                           </li>`).join("")}</ul>`
                    : "<p>Nenhuma impressora compatível identificada no cadastro.</p>";
                dialogo.showModal();
            }

            let requisicaoPedidosEstoque = 0;

            async function carregarPedidosEstoque() {
                const area = document.getElementById("pedidos-estoque");
                let status = document.getElementById("pedidos-estoque-status");
                if (!status) {
                    status = document.createElement("p");
                    status.id = "pedidos-estoque-status";
                    status.className = "mt-4 text-sm";
                    status.setAttribute("role", "status");
                    area.before(status);
                    area.textContent = "";
                }
                const requisicao = ++requisicaoPedidosEstoque;
                try {
                    const resposta = await api.buscarPedidosEstoque();
                    if (!resposta.ok) throw new Error("HTTP " + resposta.status);
                    const dados = await resposta.json();
                    if (requisicao !== requisicaoPedidosEstoque) return;
                    const podeAlterar = painelPode("stock.adjust");
                    const ultimaSugestao = dados.sugestoes[0];
                    const sugestaoAtual = ultimaSugestao && ultimaSugestao.status === "ABERTA"
                        ? ultimaSugestao
                        : null;
                    const sugestoesAnteriores = dados.sugestoes.filter(sugestao =>
                        !ultimaSugestao || sugestao.semana !== ultimaSugestao.semana
                    );
                    const dataSugestaoFormatada = sugestaoAtual
                        ? sugestaoAtual.semana.split("-").reverse().join("/")
                        : "";
                    const amanha = new Date();
                    amanha.setDate(amanha.getDate() + 1);
                    const dataMinimaAdiamento = [
                        amanha.getFullYear(),
                        String(amanha.getMonth() + 1).padStart(2, "0"),
                        String(amanha.getDate()).padStart(2, "0"),
                    ].join("-");
                    const itensSugeridos = sugestaoAtual
                        ? sugestaoAtual.itens.filter(item => item.ativo && item.quantidade_sugerida > 0)
                        : [];
                    const itensOpcionais = sugestaoAtual
                        ? sugestaoAtual.itens.filter(item => item.ativo && item.quantidade_sugerida === 0)
                        : [];
                    const itensInativos = sugestaoAtual
                        ? sugestaoAtual.itens.filter(item => !item.ativo && item.quantidade_sugerida > 0)
                        : [];
                    const mensagemSemItens = sugestaoAtual && !sugestaoAtual.itens.length
                        ? "Nenhum toner estava abaixo do estoque mínimo quando esta sugestão foi gerada."
                        : itensInativos.length
                            ? `${itensInativos.length} toner(s) inativo(s) precisam ser reativados antes de entrar em um pedido.`
                            : "O estoque atual e os pedidos pendentes já cobrem o mínimo dos itens sugeridos.";
                    const renderizarItemSugestao = (item, quantidade) => {
                        const nome = escaparHtml(`${item.marca} ${item.codigo} (${item.cor})`);
                        const entrada = podeAlterar
                            ? `<label class="flex items-center gap-2 text-sm font-semibold text-gray-700"><span class="whitespace-nowrap">Qtd. a pedir</span><input type="number" min="0" max="1000000" step="1" value="${quantidade}" data-toner-id="${item.toner_id}" aria-label="Quantidade para ${nome}" class="w-20 rounded border border-gray-300 p-2"></label>`
                            : `<span class="text-sm font-semibold text-gray-700">${quantidade} ${quantidade === 1 ? "unidade" : "unidades"}</span>`;
                        return `<li class="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 py-3">
                            <div>
                                <p class="font-semibold text-gray-900">${nome}</p>
                                <p class="mt-1 text-xs text-gray-600">Estoque atual: ${item.estoque_atual} · Mínimo: ${item.minimo_atual} · Em pedidos pendentes: ${item.quantidade_pendente}</p>
                            </div>
                            ${entrada}
                        </li>`;
                    };
                    const itensDaSugestao = itensSugeridos
                        .map(item => renderizarItemSugestao(item, item.quantidade_sugerida))
                        .join("");
                    const itensOpcionaisHtml = itensOpcionais
                        .map(item => renderizarItemSugestao(item, 0))
                        .join("");
                    const sugestao = sugestaoAtual
                        ? `<form class="rounded-lg border border-gray-200 bg-white p-4" data-semana="${escaparHtml(sugestaoAtual.semana)}" onsubmit="confirmarSugestaoEstoque(event)">
                            <h5 class="font-semibold text-gray-900">Sugestão de ${escaparHtml(dataSugestaoFormatada)}</h5>
                            <p class="mt-1 text-sm text-gray-600">A quantidade sugerida completa o estoque mínimo, descontando o saldo atual e o que ainda está pendente em outros pedidos. Você pode ajustar antes de registrar.</p>
                            ${itensSugeridos.length
                                ? `<ul class="mt-3">${itensDaSugestao}</ul>`
                                : `<p class="mt-3 rounded-lg ${itensInativos.length ? "bg-amber-50 text-amber-800" : "bg-green-50 text-green-800"} p-3 text-sm">${mensagemSemItens}</p>`}
                            ${itensOpcionais.length
                                ? `<details class="mt-3 rounded-lg border border-gray-200 p-3">
                                    <summary class="cursor-pointer text-sm font-semibold text-gray-700">Adicionar outros toners (${itensOpcionais.length})</summary>
                                    <p class="mt-2 text-sm text-gray-600">Estes itens já estão no mínimo ou cobertos por pedidos pendentes. Se precisar de uma quantidade adicional, informe-a aqui.</p>
                                    <ul class="mt-2">${itensOpcionaisHtml}</ul>
                                </details>`
                                : ""}
                            ${podeAlterar && (itensSugeridos.length || itensOpcionais.length) ? '<button type="submit" class="mt-4 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800">Enviar e-mail ao responsável</button>' : ""}
                            ${podeAlterar ? `<div class="mt-4 flex flex-wrap items-end gap-3 border-t border-gray-200 pt-4">
                                <label class="text-sm font-semibold text-gray-700">Data para nova verificação
                                    <input type="date" min="${dataMinimaAdiamento}" data-data-verificacao class="mt-1 block rounded border border-gray-300 p-2">
                                </label>
                                <button type="button" onclick="adiarSugestaoEstoque(event)" class="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50">Adiar pedido</button>
                            </div>` : ""}
                        </form>`
                        : `<p class="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">${!ultimaSugestao
                            ? "Ainda não há uma sugestão semanal disponível."
                            : ultimaSugestao.status === "ENVIANDO"
                                ? "O e-mail da solicitação está sendo enviado."
                                : ultimaSugestao.status === "AGUARDANDO_ACEITE"
                                    ? "A solicitação foi enviada e aguarda resposta do responsável."
                                    : ultimaSugestao.status === "ACEITA"
                                        ? "A solicitação foi aceita. O pedido está na seção de recebimento."
                                        : ultimaSugestao.status === "ADIADA"
                                            ? `Sugestão adiada. Uma nova será calculada em ${escaparHtml(ultimaSugestao.verificar_em.split("-").reverse().join("/"))}, usando o estoque atualizado; até lá, nenhum e-mail será enviado.`
                                            : ultimaSugestao.status === "ARQUIVADA"
                                                ? "Esta sugestão foi arquivada após uma nova verificação."
                                                : "A solicitação foi recusada. Uma nova sugestão será gerada na próxima segunda-feira."}</p>`;
                    const sugestoesAnterioresHtml = sugestoesAnteriores.length
                        ? `<details class="mt-3 rounded-lg border border-gray-200 p-3">
                            <summary class="cursor-pointer text-sm font-semibold text-gray-700">Sugestões anteriores (${sugestoesAnteriores.length})</summary>
                            <p class="mt-2 text-sm text-gray-600">Estas sugestões antigas ficam arquivadas para consulta. Registre a reposição usando a sugestão mais recente.</p>
                            <ul class="mt-2 list-inside list-disc text-sm text-gray-600">${sugestoesAnteriores.map(item => `<li>${escaparHtml(item.semana.split("-").reverse().join("/"))} — ${item.status === "ARQUIVADA" ? "arquivada" : escaparHtml(item.status.toLowerCase())}${item.verificar_em ? `; nova verificação em ${escaparHtml(item.verificar_em.split("-").reverse().join("/"))}` : ""}</li>`).join("")}</ul>
                        </details>`
                        : "";
                    const renderizarPedido = pedido => {
                        const pendente = pedido.itens.some(item =>
                            item.recebida + (item.cancelada || 0) < item.quantidade
                        );
                        const recebidoParcialmente = pendente && pedido.itens.some(item => item.recebida > 0);
                        const possuiCancelamento = pedido.itens.some(item => item.cancelada > 0);
                        const statusPedido = !pendente
                            ? possuiCancelamento ? "Encerrado com cancelamento" : "Recebido"
                            : recebidoParcialmente
                                ? "Parcialmente recebido"
                                : "Aguardando recebimento";
                        const itens = pedido.itens.map(item => {
                            const cancelada = item.cancelada || 0;
                            const restante = item.quantidade - item.recebida - cancelada;
                            const nome = escaparHtml(`${item.marca} — ${item.codigo} — ${item.cor}`);
                            const entrada = podeAlterar && restante && item.ativo
                                ? `<label>Recebido agora <input type="number" min="0" max="${restante}" step="1" value="0" data-toner-id="${item.toner_id}" class="w-24 rounded border border-gray-300 p-1"></label>`
                                : (!item.ativo && restante ? "<span>Reative o toner para receber</span>" : "");
                            const resumoCancelamento = cancelada
                                ? `, cancelado ${cancelada}`
                                : "";
                            return `<li class="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 py-2"><span>${nome} — pedido ${item.quantidade}, recebido ${item.recebida}${resumoCancelamento}, pendente ${restante}</span>${entrada}</li>`;
                        }).join("");
                        return `<form class="mb-4 rounded-lg border border-gray-200 bg-white p-3" data-pedido-id="${pedido.id}" onsubmit="receberPedidoEstoque(event)">
                            <h4 class="font-semibold">Pedido #${pedido.id} — ${statusPedido}</h4>
                            <p class="text-xs text-gray-500">Criado em ${escaparHtml(pedido.criado_em)} por ${escaparHtml(pedido.responsavel)}</p>
                            <ul class="mt-2 text-sm">${itens}</ul>
                            ${podeAlterar && pendente ? `<div class="mt-3 flex flex-wrap gap-2">
                                <button type="submit" class="rounded-lg bg-green-700 px-3 py-2 text-sm font-semibold text-white">Adicionar recebimento ao estoque</button>
                                <button type="button" onclick="cancelarPendenciasPedidoEstoque(event, ${pedido.id})" class="rounded-lg border border-red-300 px-3 py-2 text-sm font-semibold text-red-700">Cancelar saldo pendente</button>
                            </div>` : ""}
                        </form>`;
                    };
                    const renderizarSolicitacao = solicitacao => {
                        const itens = solicitacao.itens.map(item => {
                            const nome = escaparHtml(`${item.marca} — ${item.codigo} — ${item.cor}`);
                            return `<li class="border-t border-gray-200 py-2">${nome} — ${item.quantidade} ${item.quantidade === 1 ? "unidade" : "unidades"}</li>`;
                        }).join("");
                        const decisoes = podeAlterar && solicitacao.status === "AGUARDANDO_ACEITE"
                            ? `<div class="mt-3 flex flex-wrap gap-2">
                                <button type="button" onclick="decidirSolicitacaoEstoque(event, ${solicitacao.id}, 'aceitar')" class="rounded-lg bg-green-700 px-3 py-2 text-sm font-semibold text-white">Registrar aceite</button>
                                <button type="button" onclick="decidirSolicitacaoEstoque(event, ${solicitacao.id}, 'recusar')" class="rounded-lg border border-red-300 px-3 py-2 text-sm font-semibold text-red-700">Recusar e excluir</button>
                            </div>`
                            : "";
                        return `<article class="mb-3 rounded-lg border border-gray-200 bg-white p-3">
                            <h5 class="font-semibold text-gray-900">Solicitação #${solicitacao.id} — ${solicitacao.status === "ENVIANDO" ? "Enviando e-mail" : "Aguardando resposta"}</h5>
                            <p class="mt-1 text-xs text-gray-500">Semana de ${escaparHtml(solicitacao.semana.split("-").reverse().join("/"))} · enviada por ${escaparHtml(solicitacao.responsavel)} para ${escaparHtml(solicitacao.destinatario)}</p>
                            <ul class="mt-2 text-sm text-gray-700">${itens}</ul>
                            ${decisoes}
                        </article>`;
                    };
                    const solicitacoes = dados.solicitacoes || [];
                    const pedidosEmAndamento = dados.pedidos.filter(pedido =>
                        pedido.itens.some(item =>
                            item.recebida + (item.cancelada || 0) < item.quantidade
                        )
                    );
                    const pedidosEncerrados = dados.pedidos.filter(pedido =>
                        pedido.itens.every(item =>
                            item.recebida + (item.cancelada || 0) >= item.quantidade
                        )
                    );
                    const rascunhos = new Map();
                    area.querySelectorAll("form").forEach(formulario => {
                        const chave = formulario.dataset.semana
                            ? `semana:${formulario.dataset.semana}`
                            : `pedido:${formulario.dataset.pedidoId}`;
                        const valores = new Map();
                        formulario.querySelectorAll("input[data-toner-id]").forEach(input => {
                            if (input.value !== input.defaultValue) {
                                valores.set(input.dataset.tonerId, input.value);
                            }
                        });
                        rascunhos.set(chave, valores);
                    });
                    area.innerHTML = `<section aria-labelledby="sugestao-toner-titulo">
                            <h4 id="sugestao-toner-titulo" class="mb-2 font-semibold text-gray-900">Sugestão de reposição</h4>
                            ${sugestao}
                            ${sugestoesAnterioresHtml}
                        </section>
                        <section class="mt-6" aria-labelledby="pedidos-pendentes-titulo">
                            <h4 id="pedidos-pendentes-titulo" class="mb-2 font-semibold text-gray-900">Solicitações enviadas — aguardando resposta (${solicitacoes.length})</h4>
                            ${solicitacoes.length
                                ? solicitacoes.map(renderizarSolicitacao).join("")
                                : '<p class="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">Nenhuma solicitação aguardando resposta.</p>'}
                        </section>
                        <section class="mt-6" aria-labelledby="pedidos-recebimento-titulo">
                            <h4 id="pedidos-recebimento-titulo" class="mb-2 font-semibold text-gray-900">Pedidos aceitos — aguardando recebimento (${pedidosEmAndamento.length})</h4>
                            ${pedidosEmAndamento.length
                                ? pedidosEmAndamento.map(renderizarPedido).join("")
                                : '<p class="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">Nenhum pedido aceito aguardando recebimento.</p>'}
                        </section>
                        ${pedidosEncerrados.length
                            ? `<details class="mt-4 rounded-lg border border-gray-200 p-3">
                                <summary class="cursor-pointer text-sm font-semibold text-gray-700">Pedidos encerrados — recebidos ou cancelados (${pedidosEncerrados.length})</summary>
                                <div class="mt-3">${pedidosEncerrados.map(renderizarPedido).join("")}</div>
                            </details>`
                            : ""}`;
                    area.querySelectorAll("form").forEach(formulario => {
                        const chave = formulario.dataset.semana
                            ? `semana:${formulario.dataset.semana}`
                            : `pedido:${formulario.dataset.pedidoId}`;
                        const valores = rascunhos.get(chave);
                        if (!valores) return;
                        formulario.querySelectorAll("input[data-toner-id]").forEach(input => {
                            if (valores.has(input.dataset.tonerId)) {
                                input.value = valores.get(input.dataset.tonerId);
                            }
                        });
                    });
                    status.textContent = "";
                } catch (erro) {
                    if (requisicao !== requisicaoPedidosEstoque) return;
                    console.error("Erro ao carregar pedidos:", erro);
                    status.textContent = "Não foi possível atualizar sugestões e pedidos. Se houver valores não confirmados, eles permanecem na tela.";
                }
            }

            async function enviarFormularioPedido(evento, url, mensagem, mensagemSucesso = "Operação registrada com sucesso.") {
                evento.preventDefault();
                const formulario = evento.currentTarget;
                if (!formulario.reportValidity()) return;
                const itens = Array.from(formulario.querySelectorAll("input[data-toner-id]"))
                    .filter(input => Number(input.value) > 0)
                    .map(input => ({toner_id: Number(input.dataset.tonerId), quantidade: Number(input.value)}));
                if (!itens.length) {
                    alert("Informe ao menos uma quantidade maior que zero.");
                    return;
                }
                if (!confirm(mensagem)) return;
                const botao = formulario.querySelector('button[type="submit"]');
                botao.disabled = true;
                try {
                    const resposta = await api.enviarPedidoEstoque(url, {semana: formulario.dataset.semana, itens});
                    const resultado = await resposta.json();
                    if (!resposta.ok) throw new Error(resultado.erro || "Operação não concluída.");
                    document.querySelectorAll("#pedidos-estoque form").forEach(atual => {
                        if ((formulario.dataset.semana && atual.dataset.semana === formulario.dataset.semana) ||
                            (formulario.dataset.pedidoId && atual.dataset.pedidoId === formulario.dataset.pedidoId)) {
                            atual.reset();
                        }
                    });
                    alert(mensagemSucesso);
                    await mostrarEstoque();
                } catch (erro) {
                    console.error("Erro ao registrar pedido:", erro);
                    alert(erro.message || "Erro de comunicação com o servidor.");
                } finally {
                    botao.disabled = false;
                }
            }

            function confirmarSugestaoEstoque(evento) {
                return enviarFormularioPedido(
                    evento,
                    "/api/pedidos-estoque",
                    "Enviar a solicitação de aceite por e-mail ao responsável? O pedido só ficará disponível para recebimento depois que você registrar o aceite.",
                    "E-mail enviado; solicitação aguardando resposta do responsável."
                );
            }

            async function adiarSugestaoEstoque(evento) {
                const botao = evento.currentTarget;
                const formulario = botao.closest("form");
                const dataVerificacao = formulario.querySelector("[data-data-verificacao]").value;
                if (!dataVerificacao) {
                    alert("Selecione uma data futura para a nova verificação.");
                    return;
                }
                if (!confirm(`A sugestão atual será arquivada e uma nova será calculada em ${dataVerificacao}. Nenhum e-mail será enviado automaticamente.`)) return;
                botao.disabled = true;
                try {
                    const resposta = await api.enviarPedidoEstoque(
                        `/api/pedidos-estoque/sugestoes/${formulario.dataset.semana}/adiar`,
                        {data_verificacao: dataVerificacao}
                    );
                    const resultado = await resposta.json();
                    if (!resposta.ok) throw new Error(resultado.erro || "Adiamento não concluído.");
                    alert("Sugestão adiada. Ela será recalculada na data escolhida.");
                    await mostrarEstoque();
                } catch (erro) {
                    console.error("Erro ao adiar sugestão de estoque:", erro);
                    alert(erro.message || "Erro de comunicação com o servidor.");
                } finally {
                    botao.disabled = false;
                }
            }

            async function decidirSolicitacaoEstoque(evento, pedidoId, decisao) {
                const botao = evento.currentTarget;
                const mensagem = decisao === "aceitar"
                    ? "Confirmar que o responsável aceitou? O pedido ficará disponível para registrar o recebimento."
                    : "Recusar e excluir esta solicitação? Ela será removida e não poderá ser recuperada.";
                if (!confirm(mensagem)) return;
                botao.disabled = true;
                try {
                    const resposta = await api.enviarPedidoEstoque(
                        `/api/pedidos-estoque/${pedidoId}/decisao`,
                        {decisao}
                    );
                    const resultado = await resposta.json();
                    if (!resposta.ok) throw new Error(resultado.erro || "Decisão não concluída.");
                    alert(decisao === "aceitar"
                        ? "Aceite registrado. O pedido está disponível para recebimento."
                        : "Solicitação recusada e excluída.");
                    await mostrarEstoque();
                } catch (erro) {
                    console.error("Erro ao registrar a decisão da solicitação:", erro);
                    alert(erro.message || "Erro de comunicação com o servidor.");
                } finally {
                    botao.disabled = false;
                }
            }

            function receberPedidoEstoque(evento) {
                return enviarFormularioPedido(evento, `/api/pedidos-estoque/${evento.currentTarget.dataset.pedidoId}/receber`, "Adicionar as quantidades informadas ao estoque?");
            }

            async function cancelarPendenciasPedidoEstoque(evento, pedidoId) {
                const botao = evento.currentTarget;
                if (!confirm("Cancelar todo o saldo ainda não recebido deste pedido? O estoque não será alterado.")) return;
                botao.disabled = true;
                try {
                    const resposta = await api.enviarPedidoEstoque(
                        `/api/pedidos-estoque/${pedidoId}/cancelar-pendentes`,
                        {}
                    );
                    const resultado = await resposta.json();
                    if (!resposta.ok) throw new Error(resultado.erro || "Cancelamento não concluído.");
                    alert("Saldo pendente cancelado sem alterar o estoque.");
                    await mostrarEstoque();
                } catch (erro) {
                    console.error("Erro ao cancelar saldo pendente do pedido:", erro);
                    alert(erro.message || "Erro de comunicação com o servidor.");
                } finally {
                    botao.disabled = false;
                }
            }

            function definirTonersInativos(exibir, botao) {
                localStorage.setItem(
                    "mostrar_toners_inativos",
                    exibir ? "1" : "0"
                );
                const grupo = botao && botao.closest('[role="group"]');
                if (grupo) {
                    grupo.querySelectorAll("button").forEach(function(item) {
                        item.setAttribute(
                            "aria-pressed",
                            item === botao ? "true" : "false"
                        );
                    });
                }
                mostrarEstoque();
            }

            function filtrarInativos(exibir, botao) {
                definirTonersInativos(exibir, botao);
            }

            async function editarModelosCompativeis(tonerId) {
                const elemento = document.getElementById(
                    "modelos-toner-" + tonerId
                );
                const atuais =
                    elemento.textContent === "Não configurado"
                        ? ""
                        : elemento.textContent;
                const modelos = prompt(
                    "Informe os modelos compatíveis separados por vírgula:",
                    atuais
                );
                if (modelos === null) {
                    return;
                }

                try {
                    const resposta = await api.atualizarModelosCompativeis(tonerId, modelos);
                    const resultado = await resposta.json();
                    if (!resposta.ok) {
                        alert(resultado.erro || "Não foi possível atualizar os modelos.");
                        return;
                    }
                    mostrarEstoque();
                } catch (erro) {
                    console.error("Erro ao atualizar modelos compatíveis:", erro);
                    alert("Erro de comunicação com o servidor.");
                }
            }

            async function editarEstoqueMinimo(tonerId, estoqueMinimoAtual) {
                const valor = prompt(
                    "Informe a nova quantidade mínima:",
                    estoqueMinimoAtual
                );
                if (valor === null) {
                    return;
                }

                const quantidade = valor.trim();
                if (!/^\d+$/.test(quantidade)) {
                    alert("Informe um número inteiro igual ou maior que zero.");
                    return;
                }

                try {
                    const resposta = await api.atualizarEstoqueMinimo(tonerId, Number(quantidade));
                    const resultado = await resposta.json();
                    if (!resposta.ok) {
                        alert(resultado.erro || "Não foi possível atualizar o estoque mínimo.");
                        return;
                    }
                    mostrarEstoque();
                } catch (erro) {
                    console.error("Erro ao atualizar estoque mínimo:", erro);
                    alert("Erro de comunicação com o servidor.");
                }
            }
 
            async function reativarToner(tonerId) {
                try {
                    const resposta = await api.reativarToner(tonerId);
                    const resultado = await resposta.json();
                    if (!resposta.ok) {
                        alert(resultado.erro || "Não foi possível reativar o toner.");
                        return;
                    }
                    mostrarEstoque();
                } catch (erro) {
                    console.error("Erro ao reativar toner:", erro);
                    alert("Erro de comunicação com o servidor.");
                }
            }


            async function mostrarTonersNaoConfiaveis() {

                esconderAreas();

                const lista =
                    document.getElementById("area-lista");

                if (!lista) {
                    return;
                }

                lista.style.display = "block";

                const titulo =
                    document.getElementById("titulo-grupo");

                if (titulo) {
                    titulo.textContent = "Toners não confiáveis";
                }
                atualizarDescricaoSecao(
                    "Leituras não confiáveis incluem toners sem chip. Os níveis por páginas são estimativas, não medições do toner."
                );


                // ==================================================
                // ESCONDE A TABELA PRINCIPAL
                // ==================================================

                const tabelaImpressoras =
                    document.getElementById(
                        "tabela-impressoras"
                    );

                if (tabelaImpressoras) {
                    tabelaImpressoras.style.display = "none";
                }


                // ==================================================
                // MOSTRA A TABELA DE NÃO CONFIÁVEIS
                // ==================================================

                const areaNaoConfiaveis =
                    document.getElementById(
                        "area-nao-confiaveis"
                    );

                if (!areaNaoConfiaveis) {
                    console.error(
                        "ERRO: area-nao-confiaveis não encontrada."
                    );
                    return;
                }

                areaNaoConfiaveis.style.display = "block";


                const tabela =
                    document.getElementById(
                        "corpo-nao-confiaveis"
                    );

                if (!tabela) {
                    console.error(
                        "ERRO: corpo-nao-confiaveis não encontrado."
                    );
                    return;
                }


                try {

                    const resposta =
                        await api.buscarTonersNaoConfiaveis();


                    if (!resposta.ok) {

                        throw new Error(
                            "Erro HTTP " +
                            resposta.status
                        );

                    }


                    const toners =
                        await resposta.json();


                    // Limpa SOMENTE a tabela
                    // de toners não confiáveis

                    tabela.innerHTML = "";


                    if (!toners.length) {

                        tabela.innerHTML = `
                            <tr>
                                <td colspan="5"
                                    class="text-center">

                                    Nenhum toner não confiável encontrado.

                                </td>
                            </tr>
                        `;

                        return;
                    }


                    toners.forEach(function(toner) {
                        const linha = document.createElement("tr");
                        const dados = toner.estimativa;
                        let consumo = "-";
                        if (dados) {
                            const paginas = dados.paginas === null ? "indisponível" : `${dados.paginas} páginas`;
                            const media = dados.media_paginas === null ? "aguardando ciclo completo" : `${dados.media_paginas} páginas`;
                            consumo = `${paginas} / ${media}`;
                        }
                        [toner.impressora || "-", toner.ip || "-", toner.toner || "-", consumo, toner.status || "Não confiável"]
                            .forEach(valor => {
                                const celula = document.createElement("td");
                                celula.textContent = valor;
                                linha.appendChild(celula);
                            });
                        tabela.appendChild(linha);
                    });


                } catch (erro) {

                    console.error(
                        "Erro ao carregar toners não confiáveis:",
                        erro
                    );

                }


                window.scrollTo({
                    top: lista.offsetTop - 20,
                    behavior: "smooth"
                });

            }
            /* ======================================================
            FECHAR CADASTRO
            ====================================================== */

            function abrirCadastroToner() {
                const formulario = document.getElementById("formulario-toner");
                if (formulario && !formulario.open) {
                    formulario.showModal();
                }
            }

            function fecharCadastroToner() {
                const formulario = document.getElementById("formulario-toner");
                if (formulario && formulario.open) {
                    formulario.close();
                }
            }


          

            /* ======================================================
            CADASTRAR TONER
            ====================================================== */

            async function cadastrarToner() {

                const marca =
                    document.getElementById(
                        "toner-marca"
                    ).value.trim();


                const codigo =
                    document.getElementById(
                        "toner-codigo"
                    ).value.trim();


                const cor =
                    document.getElementById(
                        "toner-cor"
                    ).value;

                const modelosCompativeis =
                    document.getElementById(
                        "toner-modelos"
                    ).value.trim();


                const estoque =
                    document.getElementById(
                        "toner-estoque"
                    ).valueAsNumber;


                const estoqueMinimo =
                    document.getElementById(
                        "toner-minimo"
                    ).valueAsNumber;


                if (
                    !marca ||
                    !codigo ||
                    !cor
                ) {

                    alert(
                        "Preencha marca, código e cor."
                    );

                    return;

                }


                if (
                    !Number.isInteger(estoque) ||
                    !Number.isInteger(estoqueMinimo) ||
                    estoque < 0 ||
                    estoqueMinimo < 0
                ) {

                    alert(
                        "Informe quantidades inteiras e não negativas."
                    );

                    return;

                }


                try {

                    const resposta =
                        await api.cadastrarToner({
                            marca: marca,
                            codigo: codigo,
                            cor: cor,
                            modelos_compativeis: modelosCompativeis,
                            estoque: estoque,
                            estoque_minimo: estoqueMinimo
                        });


                    const resultado =
                        await resposta.json();


                    if (!resposta.ok) {

                        alert(
                            resultado.erro ||
                            "Não foi possível cadastrar."
                        );

                        return;

                    }


                    alert(
                        "Toner cadastrado com sucesso!"
                    );


                    document.getElementById(
                        "toner-marca"
                    ).value = "";


                    document.getElementById(
                        "toner-codigo"
                    ).value = "";


                    document.getElementById(
                        "toner-cor"
                    ).value = "";

                    document.getElementById(
                        "toner-modelos"
                    ).value = "";


                    document.getElementById(
                        "toner-estoque"
                    ).value = "0";


                    document.getElementById(
                        "toner-minimo"
                    ).value = "1";


                    fecharCadastroToner();


                    mostrarEstoque();


                } catch (erro) {

                    console.error(erro);


                    alert(
                        "Erro de comunicação com o servidor."
                    );

                }

            }
            
            async function mostrarhistorico() {

                esconderAreas();

                 try {

                    const resposta = await api.buscarHistorico();

                    const texto = await resposta.text();

                    if (!resposta.ok) {
                        throw new Error(
                            "Erro HTTP " +
                            resposta.status +
                            ": " +
                            texto
                        );
                    }

                    const dados = JSON.parse(texto);

                    if (secaoMenuAtiva !== "historico") {
                        return;
                    }

                    let areahistorico =
                        document.getElementById("area-historico");

                    if (!areahistorico) {

                        areahistorico =
                            document.createElement("div");

                        areahistorico.id =
                            "area-historico";

                        areahistorico.className =
                            "mb-4";

                        document
                            .querySelector(".container-fluid")
                            .appendChild(areahistorico);
                    }

                    function criarTabela(lista, tipo) {

                        if (!lista || lista.length === 0) {

                            return `
                                <div class="alert alert-info">
                                    Nenhum registro encontrado.
                                </div>
                            `;
                        }

                        if (
                            tipo === "ENTRADAS" ||
                            tipo === "SAIDAS" ||
                            tipo === "AUTOMATICAS"
                        ) {
                            const colunaLocal =
                                tipo === "AUTOMATICAS"
                                    ? "<th>Local</th>"
                                    : "";
                            const colunasImpressora =
                                tipo === "ENTRADAS"
                                    ? ""
                                    : `<th>IP</th>${colunaLocal}<th>Patrimônio</th>`;
                            const colunaResponsavel =
                                tipo === "AUTOMATICAS"
                                    ? ""
                                    : "<th>Responsável</th>";

                            return `
                                <div class="table-responsive">

                                    <table class="table table-striped table-hover">

                                        <thead class="table-dark">

                                            <tr>
                                                <th>Data</th>
                                                <th>Tipo</th>
                                                <th>Toner</th>
                                                <th>Quantidade</th>
                                                ${colunasImpressora}
                                                ${colunaResponsavel}
                                                <th>Observação</th>
                                            </tr>

                                        </thead>

                                        <tbody>

                                            ${lista.map(item => `

                                                <tr>

                                                    <td>
                                                        ${item.data || "-"}
                                                    </td>

                                                    <td>
                                                        ${item.tipo || "-"}
                                                    </td>

                                                    <td>
                                                        ${item.toner || "-"}
                                                    </td>

                                                    <td>
                                                        ${item.quantidade || "-"}
                                                    </td>

                                                    ${
                                                        tipo === "ENTRADAS"
                                                            ? ""
                                                            : `
                                                                <td>${item.ip_impressora || "-"}</td>
                                                                ${
                                                                    tipo === "AUTOMATICAS"
                                                                        ? `<td>${item.local_impressora || "-"}</td>`
                                                                        : ""
                                                                }
                                                                <td>${item.patrimonio || "-"}</td>
                                                            `
                                                    }

                                                    ${
                                                        tipo === "AUTOMATICAS"
                                                            ? ""
                                                            : `<td>${item.responsavel || "-"}</td>`
                                                    }

                                                    <td>
                                                        ${item.observacao || "-"}
                                                    </td>

                                                </tr>

                                            `).join("")}

                                        </tbody>

                                    </table>

                                </div>
                            `;
                        }

                        return `
                            <div class="table-responsive">

                                <table class="table table-striped table-hover">

                                    <thead class="table-dark">

                                        <tr>
                                            <th>Data</th>
                                            <th>Modelo / Local</th>
                                            <th>IP</th>
                                            <th>Patrimônio</th>
                                            <th>Tempo Offline</th>
                                        </tr>

                                    </thead>

                                    <tbody>

                                        ${lista.map(item => `

                                            <tr>

                                                <td>
                                                    ${item.data || "-"}
                                                </td>

                                                <td>
                                                    ${item.modelo || "-"}
                                                </td>

                                                <td>
                                                    ${item.ip_impressora || "-"}
                                                </td>

                                                <td>
                                                    ${item.patrimonio || "-"}
                                                </td>

                                                <td>
                                                    <strong>
                                                        ${item.duracao || "-"}
                                                    </strong>
                                                </td>

                                            </tr>

                                        `).join("")}

                                    </tbody>

                                </table>

                            </div>
                        `;
                    }

                    const criarSecaoHistorico = (titulo, lista, tipo) => `
                        <section class="historico-secao">
                            <div class="historico-secao-cabecalho">
                                <h4>${titulo}</h4>
                                <span class="historico-contagem">
                                    ${Array.isArray(lista) ? lista.length : 0}
                                </span>
                            </div>
                            ${criarTabela(lista, tipo)}
                        </section>
                    `;

                    areahistorico.innerHTML = `
                        <div class="cabecalho-lista">
                            <h3>Histórico de movimentações</h3>
                            <p class="descricao-secao">
                                As contagens consideram os registros exibidos: até ${dados.paginacao.limite} entradas e saídas manuais da página, todas as trocas automáticas e eventos offline de hoje. Cada troca automática é uma saída, contada uma única vez.
                            </p>
                        </div>

                        <div class="historico-abas" role="tablist" aria-label="Categorias do histórico">
                            <button
                                id="barra-entradas"
                                class="historico-aba"
                                type="button"
                                role="tab"
                                aria-selected="false"
                                aria-controls="historico-painel-entradas"
                                onclick="mostrarAbahistorico('entradas')">
                                <span>Entradas</span>
                                <span class="historico-aba-contagem">${dados.entradas.length}</span>
                            </button>
                            <button
                                id="barra-saidas"
                                class="historico-aba"
                                type="button"
                                role="tab"
                                aria-selected="false"
                                aria-controls="historico-painel-saidas"
                                onclick="mostrarAbahistorico('saidas')">
                                <span>Saídas</span>
                                <span class="historico-aba-contagem">${dados.saidas.length + dados.saidas_automaticas.length}</span>
                            </button>
                            <button
                                id="barra-geral"
                                class="historico-aba ativa"
                                type="button"
                                role="tab"
                                aria-selected="true"
                                aria-controls="historico-painel-geral"
                                onclick="mostrarAbahistorico('geral')">
                                <span>Geral</span>
                                <span class="historico-aba-contagem">${
                                    dados.entradas.length +
                                    dados.saidas.length +
                                    dados.saidas_automaticas.length +
                                    dados.offline.length
                                }</span>
                            </button>
                        </div>

                        <div
                            id="historico-painel-entradas"
                            class="historico-painel"
                            role="tabpanel"
                            aria-labelledby="barra-entradas"
                            hidden>
                            ${criarSecaoHistorico(
                                "Entradas de toner",
                                dados.entradas,
                                "ENTRADAS"
                            )}
                        </div>

                        <div
                            id="historico-painel-saidas"
                            class="historico-painel"
                            role="tabpanel"
                            aria-labelledby="barra-saidas"
                            hidden>
                            ${criarSecaoHistorico(
                                "Saídas manuais de toner",
                                dados.saidas,
                                "SAIDAS"
                            )}
                            ${criarSecaoHistorico(
                                "Trocas automáticas (saídas)",
                                dados.saidas_automaticas,
                                "AUTOMATICAS"
                            )}
                        </div>

                        <div
                            id="historico-painel-geral"
                            class="historico-painel"
                            role="tabpanel"
                            aria-labelledby="barra-geral">
                            ${criarSecaoHistorico(
                                "Entradas de toner",
                                dados.entradas,
                                "ENTRADAS"
                            )}
                            ${criarSecaoHistorico(
                                "Saídas manuais de toner",
                                dados.saidas,
                                "SAIDAS"
                            )}
                            ${criarSecaoHistorico(
                                "Trocas automáticas (saídas)",
                                dados.saidas_automaticas,
                                "AUTOMATICAS"
                            )}
                            ${criarSecaoHistorico(
                                "Impressoras offline",
                                dados.offline,
                                "OFFLINE"
                            )}
                        </div>
                    `;


                    window.mostrarAbahistorico =
                        function(tipo) {
                            const tab = document.getElementById(
                                `barra-${tipo}`
                            );
                            const painel = document.getElementById(
                                `historico-painel-${tipo}`
                            );

                            if (!tab || !painel) {
                                return;
                            }

                            document
                                .querySelectorAll(".historico-aba")
                                .forEach(botao => {
                                    const selecionada = botao === tab;
                                    botao.classList.toggle(
                                        "ativa",
                                        selecionada
                                    );
                                    botao.setAttribute(
                                        "aria-selected",
                                        String(selecionada)
                                    );
                                });

                            document
                                .querySelectorAll(".historico-painel")
                                .forEach(secao => {
                                    secao.hidden = secao !== painel;
                                });
                        };


                    areahistorico.style.display =
                        "block";


                    window.scrollTo({

                        top:
                            areahistorico.offsetTop - 20,

                        behavior:
                            "smooth"

                    });


                } catch (erro) {

                    console.error(
                        "Erro ao carregar histórico:",
                        erro
                    );

                    if (secaoMenuAtiva === "historico") {
                        alert(
                            "Não foi possível carregar o Histórico."
                        );
                    }
                }
            }

            /* ======================================================
            REMOVER TONER
            ====================================================== */

            async function removerToner(tonerId) {

                const confirmar = confirm(
                    "Tem certeza que deseja remover este toner do estoque?"
                );

                if (!confirmar) {

                    return;

                }


                try {

                    const resposta = await api.removerToner(tonerId);


                    const resultado =
                        await resposta.json();


                    if (!resposta.ok) {

                        alert(
                            resultado.erro ||
                            "Não foi possível remover o toner."
                        );

                        return;

                    }


                    alert(
                        "Toner removido com sucesso!"
                    );


                    mostrarEstoque();


                } catch (erro) {

                    console.error(
                        "Erro ao remover toner:",
                        erro
                    );


                    alert(
                        "Erro de comunicação com o servidor."
                    );

                }

            }
            /* ======================================================
            ABRIR SAÍDA DE TONER
            ====================================================== */

            async function abrirSaidaToner() {

                const formularioCadastro = document.getElementById(
                    "formulario-toner"
                );
                if (formularioCadastro && formularioCadastro.open) {
                    formularioCadastro.close();
                }

                const formularioSaida = document.getElementById(
                    "formulario-saida-toner"
                );
                if (!formularioSaida) {
                    return;
                }
                if (!formularioSaida.open) {
                    formularioSaida.showModal();
                }


                const select =
                    document.getElementById(
                        "saida-toner"
                    );


                select.innerHTML = `
                    <option value="">
                        Carregando toners...
                    </option>
                `;


                try {

                    const resposta =
                        await api.buscarEstoque();


                    const toners =
                        await resposta.json();


                    select.innerHTML = `
                        <option value="">
                            Selecione o toner
                        </option>
                    `;


                    toners.forEach(function(toner) {

                        select.innerHTML += `

                            <option
                                value="${toner.id}"
                                data-estoque="${toner.estoque}">

                                ${toner.marca}
                                -
                                ${toner.codigo}
                                -
                                ${toner.cor}

                                (Estoque:
                                ${toner.estoque})

                            </option>

                        `;

                    });


                } catch (erro) {

                    console.error(erro);


                    select.innerHTML = `
                        <option value="">
                            Erro ao carregar toners
                        </option>
                    `;

                }

            }


            /* ======================================================
            FECHAR SAÍDA DE TONER
            ====================================================== */

            function fecharSaidaToner() {

                const formulario = document.getElementById(
                    "formulario-saida-toner"
                );
                if (formulario && formulario.open) {
                    formulario.close();
                }

            }

            /* ======================================================
            REGISTRAR SAÍDA DE TONER
            ====================================================== */

            async function salvarSaidaToner() {

                const tonerId =
                    document.getElementById(
                        "saida-toner"
                    ).value;


                const quantidade =
                    parseInt(
                        document.getElementById(
                            "saida-quantidade"
                        ).value
                    );


                const ip =
                    document.getElementById(
                        "saida-ip"
                    ).value.trim();


                const patrimonio =
                    document.getElementById(
                        "saida-patrimonio"
                    ).value.trim();


                const responsavel =
                    document.getElementById(
                        "saida-responsavel"
                    ).value.trim();


                const observacao =
                    document.getElementById(
                        "saida-observacao"
                    ).value.trim();
                const campoTrocaSemChip = document.getElementById("saida-troca-sem-chip");
                const trocaSemChip = campoTrocaSemChip ? campoTrocaSemChip.checked : false;


                if (!tonerId) {

                    alert(
                        "Selecione o toner."
                    );

                    return;

                }


                if (
                    isNaN(quantidade) ||
                    quantidade <= 0
                ) 
                {

                    alert(
                        "Informe uma quantidade válida."
                    );

                    return;

                }


                if (!ip) {

                    alert(
                        "Informe o IP da impressora."
                    );

                    return;

                }


                if (!responsavel) {

                    alert(
                        "Informe o responsável."
                    );

                    return;

                }


                const confirmar = confirm(
                    "Confirmar saída de " +
                    quantidade +
                    " unidade(s) deste toner?" +
                    (trocaSemChip ? "\nA troca será registrada com o contador atual da impressora." : "")
                );


                if (!confirmar) {

                    return;

                }


                const botaoSalvar = document.getElementById("botao-salvar-saida");
                botaoSalvar.disabled = true;
                try {

                    const resposta =
                        await api.registrarSaidaToner({
                            toner_id: tonerId,
                            quantidade: quantidade,
                            ip_impressora: ip,
                            patrimonio: patrimonio,
                            responsavel: responsavel,
                            observacao: observacao,
                            troca_sem_chip: trocaSemChip
                        });


                    const resultado =
                        await resposta.json();


                    if (!resposta.ok) {

                        alert(
                            resultado.erro ||
                            "Não foi possível registrar a saída."
                        );

                        return;

                    }


                    alert(
                        resultado.mensagem + "\n\n" +
                        "Novo estoque: " +
                        resultado.novo_estoque +
                        (resultado.aviso ? "\n\n" + resultado.aviso : "")
                    );


                    document.getElementById(
                        "saida-toner"
                    ).value = "";


                    document.getElementById(
                        "saida-quantidade"
                    ).value = "1";


                    document.getElementById(
                        "saida-ip"
                    ).value = "";


                    document.getElementById(
                        "saida-patrimonio"
                    ).value = "";


                    document.getElementById(
                        "saida-responsavel"
                    ).value = "";


                    document.getElementById(
                        "saida-observacao"
                    ).value = "";
                    if (campoTrocaSemChip) campoTrocaSemChip.checked = false;


                    fecharSaidaToner();


                    mostrarEstoque();


                } catch (erro) {

                    console.error(
                        "Erro ao registrar saída:",
                        erro
                    );


                    alert(
                        "Erro de comunicação com o servidor."
                    );
                } finally {
                    botaoSalvar.disabled = false;
                }
            }


            /* ======================================================
            BUSCAR IMPRESSORA PELO IP
            ====================================================== */

            async function buscarImpressoraSaida() {

                const ip =
                    document.getElementById(
                        "saida-busca-ip"
                    ).value.trim();


                const resultado =
                    document.getElementById(
                        "resultado-impressora-saida"
                    );


                const dados =
                    document.getElementById(
                        "dados-impressora-saida"
                    );


                if (!ip) {

                    alert(
                        "Digite o IP da impressora."
                    );

                    return;

                }


                resultado.style.display = "block";


                dados.className =
                    "alert alert-info mb-0";


                dados.textContent =
                    "Procurando impressora...";


                try {

                    const resposta =
                        await api.buscarDados();


                    if (!resposta.ok) {

                        throw new Error(
                            "Não foi possível consultar as impressoras."
                        );

                    }


                    const impressoras =
                        await resposta.json();


                    const impressora =
                        impressoras.find(
                            item =>
                                String(item.ip).trim() === ip
                        );


                    if (!impressora) {

                        dados.className =
                            "alert alert-danger mb-0";


                        dados.textContent =
                            "Nenhuma impressora encontrada com o IP " +
                            ip;


                        return;

                    }


                    dados.className =
                        "alert alert-success mb-0";


                    dados.innerHTML = `

                        <strong>
                            Impressora encontrada
                        </strong>

                        <br>

                        Modelo/Local:
                        ${impressora.modelo || "-"}

                        <br>

                        Patrimônio:
                        ${impressora.patrimonio || "-"}

                        <br>

                        IP:
                        ${impressora.ip}

                    `;


                    document.getElementById(
                        "saida-ip"
                    ).value =
                        impressora.ip;


                    document.getElementById(
                        "saida-patrimonio"
                    ).value =
                        impressora.patrimonio || "";

                } catch (erro) {

                    console.error(erro);


                    dados.className =
                        "alert alert-danger mb-0";


                    dados.textContent =
                        "Erro ao consultar as impressoras.";

                }

            }
            /* ======================================================
            MOSTRAR ESTOQUE DISPONÍVEL
            ====================================================== */

            function atualizarEstoqueSaida() {

                const select =
                    document.getElementById(
                        "saida-toner"
                    );

                const opcao =
                    select.options[
                        select.selectedIndex
                    ];


                const quantidade =
                    document.getElementById(
                        "saida-quantidade"
                    );


                const aviso =
                    document.getElementById(
                        "saida-estoque-disponivel"
                    );


                if (
                    !opcao ||
                    !opcao.value
                ) 
                {

                    aviso.textContent =
                        "Estoque disponível: -";

                    quantidade.max = "";

                    return;

                }


                const estoque = Number(opcao.dataset.estoque);
                if (!Number.isInteger(estoque)) {

                    aviso.textContent =
                        "Estoque disponível: não informado";

                    quantidade.max = "";

                    return;

                }


                aviso.textContent =
                    "Estoque disponível: " +
                    estoque +
                    " (a baixa pode deixar o estoque negativo)";
                quantidade.removeAttribute("max");

            }

            function abrirAjusteEstoque(tonerId, botao) {
                const linha = botao && botao.closest("tr");
                if (!linha) {
                    console.error("Não foi possível identificar o toner para ajuste.");
                    alert("Não foi possível identificar o toner.");
                    return;
                }
                const dialogo = document.getElementById("ajuste-estoque");
                const formulario = dialogo.querySelector("form");
                formulario.reset();
                formulario.dataset.tonerId = tonerId;
                document.getElementById("ajuste-estoque-titulo").textContent =
                    [linha.cells[0], linha.cells[1], linha.cells[4]]
                        .map(celula => celula.textContent.trim()).join(" — ");
                document.getElementById("ajuste-estoque-saldo").textContent =
                    "Saldo atual: " + linha.cells[5].querySelector("strong").textContent.trim();
                document.getElementById("ajuste-estoque-erro").textContent = "";
                dialogo.showModal();
            }

            async function salvarAjusteEstoque(evento) {
                evento.preventDefault();
                const formulario = evento.currentTarget;
                if (!formulario.reportValidity()) return;
                const dialogo = document.getElementById("ajuste-estoque");
                const acao = document.getElementById("ajuste-estoque-acao").value;
                const quantidade = Number(document.getElementById("ajuste-estoque-quantidade").value);
                const titulo = document.getElementById("ajuste-estoque-titulo").textContent;
                const mensagem = acao === "entrada"
                    ? `Adicionar ${quantidade} unidade(s) ao estoque de ${titulo}?`
                    : `Retirar ${quantidade} unidade(s) do estoque de ${titulo}?`;
                if (!confirm(mensagem)) return;
                const controles = formulario.querySelectorAll("button, input, select");
                const mensagemErro = document.getElementById("ajuste-estoque-erro");
                controles.forEach(controle => { controle.disabled = true; });
                mensagemErro.textContent = "";
                try {
                    const resposta = await api.ajustarEstoque(formulario.dataset.tonerId, {acao, quantidade});
                    const resultado = await resposta.json();
                    if (!resposta.ok) throw new Error(resultado.erro || "Erro ao alterar estoque.");
                    dialogo.close();
                    await mostrarEstoque(false);
                    alert(`Ajuste registrado com sucesso. Novo saldo: ${resultado.novo_estoque}.`);
                } catch (erro) {
                    console.error("Erro ao alterar estoque:", erro);
                    const mensagem = erro.message || "Não foi possível registrar o ajuste.";
                    if (dialogo.open) mensagemErro.textContent = mensagem;
                    else alert(mensagem);
                } finally {
                    controles.forEach(controle => { controle.disabled = false; });
                }
            }

      


/* ======================================================
BARRA LATERAL RECOLHÍVEL
====================================================== */

function alternarMenu() {
    const corpo = document.body;
    const btnToggle = document.getElementById("btn-toggle-menu");

    if (window.matchMedia("(max-width: 768px)").matches) {
        const menuAberto = corpo.classList.toggle("menu-aberto-mobile");
        const acao = menuAberto ? "Fechar" : "Abrir";

        if (btnToggle) {
            btnToggle.setAttribute("aria-expanded", String(menuAberto));
            btnToggle.setAttribute("aria-label", `${acao} menu`);
            btnToggle.setAttribute("title", `${acao} menu`);
            const texto = btnToggle.querySelector(".texto-toggle");
            if (texto) {
                texto.textContent = `${acao} Menu`;
            }
        }

        return;
    }

    corpo.classList.remove("menu-aberto-mobile");
    const estaRecolhido = corpo.classList.toggle("menu-recolhido");

    try {
        localStorage.setItem("menu_recolhido", estaRecolhido ? "1" : "0");
    } catch (erro) {
        console.error("Não foi possível salvar o estado do menu:", erro);
    }

    if (btnToggle) {
        btnToggle.setAttribute("aria-expanded", String(!estaRecolhido));
        btnToggle.setAttribute(
            "title",
            estaRecolhido ? "Expandir menu lateral" : "Recolher menu lateral"
        );
        btnToggle.setAttribute(
            "aria-label",
            estaRecolhido ? "Expandir menu lateral" : "Recolher menu lateral"
        );
        const texto = btnToggle.querySelector(".texto-toggle");
        if (texto) {
            texto.textContent =
                estaRecolhido ? "Expandir Menu" : "Recolher Menu";
        }
    }
}

function focarPesquisa() {
    if (document.body.classList.contains("menu-recolhido")) {
        alternarMenu();
    }
    const inputPesquisa = document.getElementById("pesquisa");
    if (inputPesquisa) {
        setTimeout(() => inputPesquisa.focus(), 150);
    }
}

window.alternarMenu = alternarMenu;
window.focarPesquisa = focarPesquisa;


w
