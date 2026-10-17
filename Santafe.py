"""Conclui e explica a superfície pública do Santafé no Sublime Text."""

from __future__ import annotations

import html
import json
import re

import sublime
import sublime_plugin


ESCOPO = "source.santafe"
RECURSO_DO_CATÁLOGO = "Packages/Santafe/api-publica.json"
INÍCIO_DE_IDENTIFICADOR = r"[^\W\d]"
IDENTIFICADOR = rf"{INÍCIO_DE_IDENTIFICADOR}\w*"
# O segundo grupo pode estar vazio: ao escrever `correio.` o editor já deve
# oferecer os membros da biblioteca.  Não acrescente `*` a IDENTIFICADOR,
# pois ele já contém uma repetição para os caracteres restantes.
ACESSO_FINAL = re.compile(rf"({IDENTIFICADOR}[.:])({INÍCIO_DE_IDENTIFICADOR}\w*)?$")
FUNÇÃO_LOCAL = re.compile(rf"^\s*(?:local\s+)?função\s+({IDENTIFICADOR})", re.MULTILINE)

PALAVRAS_RESERVADAS = (
    "local", "função", "retorne", "se", "então", "senão", "enquanto",
    "para", "em", "repita", "até", "início", "fim", "pare", "vápara",
    "nulo", "verdadeiro", "falso", "e", "ou", "não",
)

FUNÇÕES_DO_NÚCLEO = (
    ("mostre", "Exibe valores na saída padrão.", "mostre(${1})"),
    ("tipo", "Devolve o tipo lógico de um valor.", "tipo(${1:valor})"),
    ("tamanho", "Conta grafemas de um colar; em tabelas, segue #.", "tamanho(${1:valor})"),
    ("octetos", "Mede os octetos de um colar.", "octetos(${1:dados})"),
    ("importe", "Carrega uma biblioteca Santafé.", "importe \"${1:biblioteca}\""),
    ("carregue", "Compila um colar sem o executar.", "carregue(${1:fonte})"),
    ("carregueArquivo", "Compila um arquivo sem o executar.", "carregueArquivo(${1:caminho})"),
    ("executeArquivo", "Executa um arquivo Santafé.", "executeArquivo(${1:caminho})"),
    ("garanta", "Interrompe quando a condição não é verdadeira.", "garanta(${1:condição}, ${2:mensagem})"),
    ("proteja", "Executa uma função protegida.", "proteja(função()\n    ${0}\nfim)"),
    ("protejaMais", "Executa uma função com tratador de falhas.", "protejaMais(${1:função}, ${2:tratador})"),
    ("paraNúmero", "Converte um valor em número quando possível.", "paraNúmero(${1:valor})"),
    ("paraColar", "Converte um valor em colar.", "paraColar(${1:valor})"),
    ("pares", "Itera as chaves de uma tabela.", "pares(${1:tabela})"),
    ("ipares", "Itera a sequência numérica inicial de uma tabela.", "ipares(${1:tabela})"),
    ("próximo", "Avança manualmente sobre as chaves de uma tabela.", "próximo(${1:tabela})"),
    ("erro", "Interrompe a execução com uma falha.", "erro(${1:mensagem})"),
    ("coleteLixo", "Controla o coletor de lixo.", "coleteLixo(${1:opção})"),
)

BIBLIOTECAS = (
    "arquivo", "bit32", "caminheiro", "colar", "correio", "es", "imagem",
    "json", "mariadb", "mat", "nomes", "pulso", "rede", "rpdf", "segredo",
    "tomada", "turing", "vigia",
)


def leia_catálogo():
    try:
        bruto = sublime.load_resource(RECURSO_DO_CATÁLOGO)
        catálogo = json.loads(bruto)
        itens = catálogo.get("itens", [])
        return tuple(item for item in itens if isinstance(item, dict) and isinstance(item.get("rótulo"), str))
    except (OSError, ValueError, TypeError):
        return ()


CATÁLOGO_PÚBLICO = leia_catálogo()
INFORMAÇÕES = {
    nome: {"rótulo": nome, "categoria": "função global", "documentação": documentação}
    for nome, documentação, _ in FUNÇÕES_DO_NÚCLEO
}
for item in CATÁLOGO_PÚBLICO:
    INFORMAÇÕES.setdefault(item["rótulo"], {
        "rótulo": item["rótulo"],
        "categoria": item.get("categoria", "API pública"),
        "documentação": f"API pública em {item.get('origem', 'biblioteca Santafé')}."
    })


def acesso_antes_do(view: sublime.View, ponto: int) -> str:
    começo = max(0, ponto - 256)
    trecho = view.substr(sublime.Region(começo, ponto))
    encontrado = ACESSO_FINAL.search(trecho)
    return encontrado.group(1) if encontrado else ""


def nomes_locais(view: sublime.View) -> tuple[str, ...]:
    return tuple(sorted({encontrado.group(1) for encontrado in FUNÇÃO_LOCAL.finditer(view.substr(sublime.Region(0, view.size())))}, key=str.casefold))


def item_de_conclusão(rótulo, anotação, espécie, conteúdo=None, detalhes=""):
    argumentos = {
        "annotation": anotação,
        "kind": espécie,
        "details": detalhes or anotação,
    }
    if conteúdo and "${" in conteúdo:
        return sublime.CompletionItem.snippet_completion(rótulo, conteúdo, **argumentos)
    argumentos["completion"] = conteúdo or rótulo
    return sublime.CompletionItem(rótulo, **argumentos)


class SantafeConclusões(sublime_plugin.EventListener):
    """Conclusões locais e da API pública, sem depender do cliente LSP."""

    def on_query_completions(self, view, prefix, locations):
        if not locations or not view.match_selector(locations[0], ESCOPO):
            return None

        acesso = acesso_antes_do(view, locations[0])
        itens = []
        if not acesso:
            itens.extend(item_de_conclusão(palavra, "palavra reservada", sublime.KIND_KEYWORD) for palavra in PALAVRAS_RESERVADAS)
            itens.extend(item_de_conclusão(biblioteca, "biblioteca Santafé", sublime.KIND_NAMESPACE) for biblioteca in BIBLIOTECAS)
            itens.extend(item_de_conclusão(nome, "função deste arquivo", sublime.KIND_FUNCTION) for nome in nomes_locais(view))

        inserções = {nome: inserção for nome, _, inserção in FUNÇÕES_DO_NÚCLEO}
        for nome, informação in INFORMAÇÕES.items():
            if acesso and not nome.startswith(acesso):
                continue
            rótulo = nome[len(acesso):] if acesso else nome
            anotação = f"{nome} — {informação['categoria']}" if acesso else informação["categoria"]
            itens.append(item_de_conclusão(
                rótulo,
                anotação,
                sublime.KIND_FUNCTION,
                None if acesso else inserções.get(nome),
                informação["documentação"],
            ))
        return (itens, sublime.INHIBIT_WORD_COMPLETIONS)

    def on_hover(self, view, point, hover_zone):
        if hover_zone != sublime.HOVER_TEXT or not view.match_selector(point, ESCOPO):
            return
        palavra = view.substr(view.word(point))
        if not palavra:
            return
        acesso = acesso_antes_do(view, view.word(point).begin())
        informação = INFORMAÇÕES.get(acesso + palavra) or INFORMAÇÕES.get(palavra)
        if not informação:
            return
        rótulo = html.escape(informação["rótulo"])
        categoria = html.escape(informação["categoria"])
        documentação = html.escape(informação["documentação"])
        view.show_popup(
            f"<body><h3>{rótulo}</h3><p><b>{categoria}</b></p><p>{documentação}</p></body>",
            location=point,
            max_width=520,
        )
