// Camada única de acesso ao servidor. Todas as funções devolvem a Response do
// fetch, para que cada tela continue tratando status e mensagens como antes.
const api = (() => {
    const CABECALHO_JSON = {"Content-Type": "application/json"};

    // Envia JSON quando `dados` é um objeto comum; FormData segue sem cabeçalho extra.
    function fazerRequisicao(url, metodo = "GET", dados = undefined, opcoes = {}) {
        const configuracao = {method: metodo, ...opcoes};
        if (dados instanceof FormData) {
            configuracao.body = dados;
        } else if (dados !== undefined) {
            configuracao.headers = CABECALHO_JSON;
            configuracao.body = JSON.stringify(dados);
        }
        return fetch(url, configuracao);
    }

    const segmento = valor => encodeURIComponent(valor);

    return {
        fazerRequisicao,

        // Impressoras
        buscarDados: () => fazerRequisicao("/dados"),
        buscarTonersNaoConfiaveis: () => fazerRequisicao("/toners-nao-confiaveis"),
        cadastrarImpressora: formulario =>
            fazerRequisicao("/api/impressoras", "POST", formulario),
        editarImpressora: dados => fazerRequisicao("/api/impressoras/editar", "PUT", dados),
        excluirImpressora: dados => fazerRequisicao("/api/impressoras/excluir", "DELETE", dados),
        buscarTonersImpressora: (ip, sinal) =>
            fazerRequisicao(`/api/impressoras/${segmento(ip)}/toners`, "GET", undefined, {signal: sinal}),
        buscarContadorImpressora: (ip, sinal) =>
            fazerRequisicao(`/api/impressoras/${segmento(ip)}/contador`, "GET", undefined, {signal: sinal}),

        // Relatório PRINTER
        buscarHistoricoPrinter: () => fazerRequisicao("/api/relatorio-printer/historico"),
        salvarHistoricoPrinter: formulario =>
            fazerRequisicao("/api/relatorio-printer/historico", "POST", formulario),
        analisarRelatorioPrinter: formulario =>
            fazerRequisicao("/api/relatorio-printer/analisar", "POST", formulario),
        aprovarCorrecaoPrinter: dados =>
            fazerRequisicao("/api/relatorio-printer/aprovar-correcao", "POST", dados),
        aprovarInclusaoPrinter: dados =>
            fazerRequisicao("/api/relatorio-printer/aprovar-inclusao", "POST", dados),
        aprovarEquivalenciaPrinter: dados =>
            fazerRequisicao("/api/relatorio-printer/aprovar-equivalencia", "POST", dados),

        // Relatório de impressões
        buscarRelatorioImpressoes: mes =>
            fazerRequisicao(`/api/relatorio-impressoes?mes=${segmento(mes)}`),

        // Estoque e toners
        buscarEstoque: (incluirInativos = false) =>
            fazerRequisicao("/estoque" + (incluirInativos ? "?incluir_inativos=1" : "")),
        buscarCompatibilidadeToners: () => fazerRequisicao("/api/toners/compatibilidade"),
        cadastrarToner: dados => fazerRequisicao("/cadastrar-toner", "POST", dados),
        removerToner: id => fazerRequisicao("/remover-toner/" + id, "DELETE"),
        reativarToner: id => fazerRequisicao("/reativar-toner/" + id, "POST"),
        atualizarModelosCompativeis: (id, modelos) =>
            fazerRequisicao("/toner/" + id + "/modelos-compativeis", "PUT", {modelos_compativeis: modelos}),
        atualizarEstoqueMinimo: (id, quantidade) =>
            fazerRequisicao("/toner/" + id + "/estoque-minimo", "PUT", {estoque_minimo: quantidade}),
        ajustarEstoque: (id, dados) => fazerRequisicao(`/ajustar-estoque/${id}`, "POST", dados),
        registrarSaidaToner: dados => fazerRequisicao("/registrar-saida-toner", "POST", dados),
        buscarHistorico: () => fazerRequisicao("/historico"),

        // Pedidos de estoque
        buscarPedidosEstoque: () => fazerRequisicao("/api/pedidos-estoque"),
        enviarPedidoEstoque: (url, dados) => fazerRequisicao(url, "POST", dados),

        // Usuários
        buscarPresencaUsuarios: url => fazerRequisicao(url),
    };
})();
