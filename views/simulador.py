"""Aba "Simulador & Redação", dividida em duas frentes independentes.

1. **Gerar redação nova** — a IA escreve um texto original calibrado pela
   nota-alvo de cada competência.
2. **Ajustar a minha redação** — o aluno envia a própria redação (texto, arquivo
   ou fotos da folha) e a IA a reescreve preservando as ideias originais.

Cada frente tem widgets e chaves de sessão próprias (prefixos ``gerar`` e
``evoluir``), para que mexer em uma não interfira na outra.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.ai_evaluator import (
    OPCOES_ESTILO_ARGUMENTACAO,
    OPCOES_REPERTORIO,
    OPCOES_TOM_INTERVENCAO,
    OPCOES_VOCABULARIO,
    evoluir_redacao_usuario,
    gerar_redacao_customizada,
    obter_api_key,
)
from services.documento_service import (
    gerar_doc_redacao,
    gerar_docx_redacao,
    subtitulo_padrao,
)
from services.parser_service import detectar_mime, extrair_texto_arquivo

PASSO_NOTA = 10  # sliders em degraus de 10 pontos
ALTURA_TEXTO = 420

COMPETENCIAS = (
    ("c1", "C1 — Norma Culta"),
    ("c2", "C2 — Tema/Estrutura"),
    ("c3", "C3 — Argumentação"),
    ("c4", "C4 — Coesão"),
    ("c5", "C5 — Intervenção"),
)

ROTULOS_CHECKLIST_C5 = {
    "agente": "Agente",
    "acao": "Ação",
    "meio_modo": "Meio/Modo",
    "detalhamento": "Detalhamento",
    "efeito": "Efeito",
}

FORMATOS_ENTRADA = [
    "Digitar / Colar Texto",
    "📷 Fotos da Folha (câmera ou arquivo)",
    "Arquivo (.docx, .txt, .pdf)",
]


# --------------------------------------------------------------------------- #
# Helpers de interface
# --------------------------------------------------------------------------- #
def _ultima_avaliacao() -> dict:
    """Correção mais recente da sessão (pode estar vazia)."""
    return st.session_state.get("ultima_avaliacao") or {}


def _notas_alvo(prefixo: str) -> tuple[dict, int]:
    """Cinco sliders (0 a 200, de 10 em 10) e a soma das metas."""
    st.subheader("Nota-alvo por competência")
    st.caption("Notas de 10 em 10 pontos, como na correção oficial do ENEM.")

    colunas = st.columns(5)
    metas = {}
    for coluna, (chave, rotulo) in zip(colunas, COMPETENCIAS):
        with coluna:
            metas[chave] = st.slider(
                rotulo,
                min_value=0,
                max_value=200,
                value=200,
                step=PASSO_NOTA,
                key=f"{prefixo}_meta_{chave}",
            )

    total = sum(metas.values())
    st.metric("Nota Total Alvo", f"{total} / 1000 pts")
    return metas, total


def _controles_estilo(prefixo: str) -> dict:
    """Vocabulário, argumentação, repertório, tom da C5 e orientações livres."""
    st.subheader("Personalização do texto")
    col_esq, col_dir = st.columns(2)

    with col_esq:
        vocabulario = st.segmented_control(
            "Nível de vocabulário",
            OPCOES_VOCABULARIO,
            default="Padrão ENEM",
            key=f"{prefixo}_vocabulario",
            help="Erudito eleva a densidade lexical; Acessível privilegia clareza e frases curtas.",
        ) or "Padrão ENEM"

        estilo_argumentacao = st.segmented_control(
            "Estilo da argumentação",
            OPCOES_ESTILO_ARGUMENTACAO,
            default="Tradicional/Clássico",
            key=f"{prefixo}_estilo",
            help="Criativo busca ângulos originais; Tradicional segue o modelo de 4 parágrafos; "
                 "Crítico assume postura de denúncia fundamentada.",
        ) or "Tradicional/Clássico"

    with col_dir:
        repertorio = st.selectbox(
            "Eixo de repertório sociocultural",
            OPCOES_REPERTORIO,
            index=0,
            key=f"{prefixo}_repertorio",
            help="Todos os repertórios do texto virão deste eixo.",
        )

        tom_intervencao = st.selectbox(
            "Tom da proposta de intervenção (C5)",
            OPCOES_TOM_INTERVENCAO,
            index=0,
            key=f"{prefixo}_tom",
            help="Define o agente principal da proposta de intervenção.",
        )

    diretrizes_extras = st.text_area(
        "Orientações extras (opcional)",
        placeholder="Ex.: cite um dado do IBGE, evite clichês, foque no público jovem, "
                    "use a obra 'Vidas Secas'...",
        height=90,
        key=f"{prefixo}_diretrizes",
    )

    return {
        "vocabulario": vocabulario,
        "estilo_argumentacao": estilo_argumentacao,
        "repertorio": repertorio,
        "tom_intervencao": tom_intervencao,
        "diretrizes_extras": diretrizes_extras,
    }


def _campo_api_key(prefixo: str) -> str:
    """Chave manual do Gemini — só aparece quando o .env não tem a chave."""
    if obter_api_key():
        st.caption("🔑 Chave do Gemini carregada automaticamente do arquivo `.env`.")
        return ""

    return st.text_input(
        "Gemini API Key",
        type="password",
        key=f"{prefixo}_api_key",
        help="Chave de API do Google Gemini",
    )


def _botoes_word(
    texto: str,
    tema: str,
    nome_arquivo: str,
    nota_alvo: int | None,
    observacoes: list[str],
    prefixo: str,
    titulo: str = "Redação ENEM",
) -> None:
    """Dois botões de download: .docx formatado e .doc (Word 97-2003)."""
    st.markdown("**Baixar em Word — escolha o formato:**")
    col_docx, col_doc = st.columns(2)

    subtitulo = subtitulo_padrao(nota_alvo)
    comum = {
        "tema": tema,
        "titulo": titulo,
        "subtitulo": subtitulo,
        "observacoes": observacoes,
    }

    with col_docx:
        st.download_button(
            "⬇️ Baixar .docx (Word)",
            data=gerar_docx_redacao(texto=texto, **comum),
            file_name=f"{nome_arquivo}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key=f"{prefixo}_docx",
            help="Documento Word já formatado: Times New Roman 12, espaçamento 1,5, "
                 "texto justificado e margens ABNT (3/2/3/2 cm).",
        )

    with col_doc:
        st.download_button(
            "⬇️ Baixar .doc (Word 97-2003)",
            data=gerar_doc_redacao(texto=texto, **comum),
            file_name=f"{nome_arquivo}.doc",
            mime="application/msword",
            key=f"{prefixo}_doc",
            help="Mesmo conteúdo na extensão antiga .doc, para quem precisa desse formato.",
        )

    nome_txt = f"{nome_arquivo}.txt"
    st.download_button(
        "⬇️ Baixar apenas o texto (.txt)",
        data=(texto or "").encode("utf-8"),
        file_name=nome_txt,
        mime="text/plain",
        key=f"{prefixo}_txt",
    )


def _mostrar_checklist_c5(checklist: dict) -> None:
    if not checklist:
        return
    with st.expander("✅ Checklist da proposta de intervenção (C5)", expanded=False, icon="✅"):
        for chave, rotulo in ROTULOS_CHECKLIST_C5.items():
            valor = checklist.get(chave)
            st.markdown(f"**{rotulo}:** {valor if valor else '—'}")


# --------------------------------------------------------------------------- #
# Entrada da redação do aluno (usada na sub-aba de ajuste)
# --------------------------------------------------------------------------- #
def _coletar_redacao_do_aluno(
    formato: str,
    prefixo: str,
    imagens_anteriores: list[tuple[bytes, str]] | None = None,
    sufixo: int | str = 0,
) -> tuple[str, list[tuple[bytes, str]]]:
    """Devolve (texto, imagens) conforme o formato escolhido.

    ``imagens_anteriores`` são as fotos enviadas na aba "Nova Avaliação"; quando
    existem, vêm pré-carregadas e entram na revisão sem precisar reenviar nada.
    ``sufixo`` versiona as chaves dos widgets, para que tudo recarregue depois de
    uma nova avaliação.
    """
    base = f"{prefixo}{sufixo}"
    texto = ""
    imagens: list[tuple[bytes, str]] = []

    if formato == "Digitar / Colar Texto":
        sugestao = (_ultima_avaliacao().get("texto") or "").strip()
        if sugestao.startswith("["):  # marcador de "fotos enviadas", não é texto
            sugestao = ""
        texto = st.text_area(
            "Cole a sua redação aqui:",
            value=sugestao,
            height=320,
            key=f"{base}_texto",
        )

    elif formato.startswith("📷"):
        anteriores = list(imagens_anteriores or [])

        if anteriores:
            usar_anteriores = st.toggle(
                f"Usar as {len(anteriores)} foto(s) da última avaliação",
                value=True,
                key=f"{base}_usar_fotos_anteriores",
                help="As fotos enviadas na aba 'Nova Avaliação' já vêm carregadas aqui — "
                     "desligue se quiser trocar por outras imagens.",
            )
            if usar_anteriores:
                with st.expander(f"🖼️ Ver as {len(anteriores)} foto(s) da última avaliação", expanded=False):
                    colunas_anteriores = st.columns(min(len(anteriores), 3))
                    for i, (dados_foto, _mime) in enumerate(anteriores):
                        with colunas_anteriores[i % 3]:
                            st.image(
                                dados_foto,
                                caption=f"{i + 1}ª página — última avaliação",
                                width="stretch",
                            )
                imagens.extend(anteriores)
                st.caption(
                    "Essas fotos entram na revisão na ordem das páginas (a 1ª página primeiro). "
                    "Fotos novas enviadas abaixo entram junto."
                )

        st.caption(
            "Envie as fotos da folha abaixo. Se a redação tiver mais de uma folha, envie várias "
            "fotos — elas são lidas juntas, na ordem das páginas."
        )

        fotos_enviadas = st.file_uploader(
            "Envie as fotos da folha",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key=f"{base}_fotos",
        )

        with st.expander("📷 Tirar foto agora com a câmera", expanded=False):
            foto_camera = st.camera_input("Tirar foto da folha", key=f"{base}_camera")

        fotos = []
        if foto_camera is not None:
            fotos.append(("foto_camera.jpg", foto_camera.getvalue()))
        for arquivo in (fotos_enviadas or []):
            fotos.append((arquivo.name, arquivo.getvalue()))

        if fotos:
            st.success(f"{len(fotos)} foto(s) nova(s) pronta(s) para revisão.")
            with st.expander(f"🖼️ Ver as {len(fotos)} foto(s) nova(s)", expanded=False):
                colunas_preview = st.columns(min(len(fotos), 3))
                for i, (nome_foto, dados_foto) in enumerate(fotos):
                    with colunas_preview[i % 3]:
                        st.image(dados_foto, caption=f"{i + 1}ª página — {nome_foto}", width="stretch")

        imagens.extend((dados_foto, detectar_mime(nome_foto, dados_foto)) for nome_foto, dados_foto in fotos)

        sugestao = (_ultima_avaliacao().get("texto") or "").strip()
        if sugestao.startswith("["):  # marcador de "fotos enviadas", não é texto
            sugestao = ""

        texto = st.text_area(
            "Transcrição / observações (opcional):",
            value=sugestao,
            placeholder="Se quiser, cole aqui a transcrição da redação ou observações para o professor.",
            height=120,
            key=f"{base}_transcricao",
        )

    else:
        arquivo_enviado = st.file_uploader(
            "Selecione o arquivo",
            type=["txt", "docx", "pdf"],
            key=f"{base}_arquivo",
        )
        if arquivo_enviado:
            texto = extrair_texto_arquivo(arquivo_enviado)
            st.text_area("Texto extraído:", value=texto, height=150, key=f"{base}_extraido")

    return texto, imagens


# --------------------------------------------------------------------------- #
# Sub-aba 1: gerar redação nova
# --------------------------------------------------------------------------- #
def _aba_gerar_nova() -> None:
    st.caption(
        "A IA escreve uma redação original sobre o tema escolhido, calibrada para corresponder "
        "exatamente à pontuação simulada."
    )

    metas, total_meta = _notas_alvo("gerar")
    parametros = _controles_estilo("gerar")

    ultima = _ultima_avaliacao()
    tema = st.text_input(
        "Tema da redação modelo",
        value=ultima.get("tema", ""),
        placeholder="Ex: Os desafios da valorização do trabalho de cuidado no Brasil",
        key="gerar_tema",
    )

    usar_parecer = st.toggle(
        "Usar o parecer da última correção como base",
        value=False,
        key="gerar_usar_parecer",
        disabled=not bool(ultima),
        help="Se houver uma correção na sessão, a IA usa os pontos fracos apontados para evoluir o texto.",
    )

    api_key = _campo_api_key("gerar")

    if st.button("✨ Gerar Redação Modelo Personalizada", type="primary", key="btn_gerar_modelo"):
        if not tema.strip():
            st.warning("Informe o tema da redação modelo.")
        else:
            parecer_base = ""
            if usar_parecer and ultima:
                parecer_base = ultima.get("res", {}).get("parecer", "")

            with st.spinner("Redigindo a redação modelo com os parâmetros escolhidos..."):
                try:
                    gerado = gerar_redacao_customizada(
                        tema=tema,
                        competencias=metas,
                        vocabulario=parametros["vocabulario"],
                        estilo_argumentacao=parametros["estilo_argumentacao"],
                        repertorio=parametros["repertorio"],
                        tom_intervencao=parametros["tom_intervencao"],
                        diretrizes_extras=parametros["diretrizes_extras"],
                        parecer_base=parecer_base,
                        api_key_manual=api_key,
                    )
                    st.session_state["redacao_customizada"] = gerado
                    # versão nova = chave nova no campo de texto, sem reaproveitar o texto antigo
                    st.session_state["redacao_customizada_versao"] = (
                        st.session_state.get("redacao_customizada_versao", 0) + 1
                    )
                    st.success("Redação modelo gerada!")
                except Exception as e:
                    st.error(f"Erro ao gerar a redação modelo: {e}")

    _mostrar_redacao_gerada(total_meta)


def _mostrar_redacao_gerada(nota_simulada: int) -> None:
    gerado = st.session_state.get("redacao_customizada")

    if not gerado:
        if _ultima_avaliacao():
            st.divider()
            st.info(
                "Já existe uma correção nesta sessão. Ajuste os parâmetros acima e clique em "
                "**Gerar Redação Modelo Personalizada** para criar um texto sob medida."
            )
            st.markdown("### Exemplo de Redação Modelo da última correção")
            st.write(
                _ultima_avaliacao().get("res", {}).get(
                    "redacao_modelo", "Instrução modelo indisponível."
                )
            )
        else:
            st.divider()
            st.info("Defina o tema e os parâmetros, depois clique em gerar para ver a redação modelo.")
        return

    st.divider()
    parametros = gerado.get("parametros", {})
    nota_alvo = gerado.get("nota_alvo", nota_simulada)
    tema_gerado = parametros.get("tema", "")

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    col_r1.metric("Nota-alvo", f"{nota_alvo} pts")
    col_r2.metric("Vocabulário", parametros.get("vocabulario", "—"))
    col_r3.metric("Argumentação", parametros.get("estilo_argumentacao", "—"))
    col_r4.metric("Repertório", parametros.get("repertorio", "—"))

    st.markdown(f"**Tema:** {tema_gerado}")
    st.markdown(f"**Intervenção (C5):** {parametros.get('tom_intervencao', '—')}")

    st.markdown("### 📄 Redação Modelo")
    texto_editado = st.text_area(
        "Texto gerado (editável)",
        value=gerado.get("redacao", ""),
        height=ALTURA_TEXTO,
        key=f"texto_redacao_modelo_{st.session_state.get('redacao_customizada_versao', 0)}",
    )

    _botoes_word(
        texto=texto_editado,
        tema=tema_gerado,
        nome_arquivo="redacao_modelo_enem",
        nota_alvo=nota_alvo,
        observacoes=[
            f"Nota-alvo: {nota_alvo}/1000 pts",
            f"Vocabulário: {parametros.get('vocabulario', '—')}",
            f"Argumentação: {parametros.get('estilo_argumentacao', '—')}",
            f"Repertório: {parametros.get('repertorio', '—')}",
            f"Intervenção (C5): {parametros.get('tom_intervencao', '—')}",
        ],
        prefixo="gerar",
    )

    if gerado.get("repertorios_usados"):
        with st.expander("📚 Repertórios utilizados", expanded=False, icon="📚"):
            for item in gerado["repertorios_usados"]:
                st.markdown(f"- {item}")

    _mostrar_checklist_c5(gerado.get("checklist_c5") or {})

    if gerado.get("justificativa_nota"):
        with st.expander("🎯 Por que o texto corresponde à nota-alvo", expanded=False, icon="🎯"):
            st.write(gerado["justificativa_nota"])

    aviso = (gerado.get("aviso_calibragem") or "").strip()
    if aviso and aviso.lower() != "nenhum":
        with st.expander("⚠️ Desvios inseridos propositalmente para calibrar a nota", expanded=False):
            st.write(aviso)


# --------------------------------------------------------------------------- #
# Sub-aba padrão: ajustar a minha redação
# --------------------------------------------------------------------------- #
def _aba_ajustar_minha() -> None:
    st.caption(
        "Envie a **sua** redação. A IA reescreve mantendo as suas ideias, argumentos e repertórios, "
        "corrigindo os desvios e completando o que faltava até a nota-alvo."
    )

    ultima = _ultima_avaliacao()
    versao = st.session_state.get("versao_avaliacao", 0)

    st.subheader("1️⃣ Sua redação")
    tema = st.text_input(
        "Tema da redação",
        value=ultima.get("tema", ""),
        placeholder="Ex: Os desafios da valorização do trabalho de cuidado no Brasil",
        key=f"evoluir_tema_{versao}",
    )

    formato = st.radio(
        "Como você quer enviar a sua redação?",
        FORMATOS_ENTRADA,
        index=1 if (ultima.get("imagens") or []) else 0,
        key=f"evoluir_formato_{versao}",
    )

    texto_aluno, imagens = _coletar_redacao_do_aluno(
        formato, "evoluir", ultima.get("imagens"), versao
    )

    st.divider()
    metas, total_meta = _notas_alvo("evoluir")
    parametros = _controles_estilo("evoluir")

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        preservar_estilo = st.toggle(
            "Preservar as minhas ideias e o meu jeito de escrever",
            value=True,
            key="evoluir_preservar",
            help="Quando ligado, a IA só ajusta o que precisa; o texto continua sendo reconhecidamente seu.",
        )
    with col_t2:
        usar_parecer = st.toggle(
            "Usar o parecer da última correção",
            value=False,
            key="evoluir_usar_parecer",
            disabled=not bool(ultima),
            help="Aproveita o diagnóstico da aba 'Nova Avaliação' como ponto de partida da revisão.",
        )

    api_key = _campo_api_key("evoluir")

    if st.button("🖊️ Evoluir minha redação", type="primary", key="btn_evoluir"):
        if not tema.strip():
            st.warning("Informe o tema da redação.")
        elif not texto_aluno.strip() and not imagens:
            st.warning("Envie o texto, o arquivo ou pelo menos uma foto da redação.")
        else:
            parecer_base = ultima.get("res", {}).get("parecer", "") if usar_parecer and ultima else ""

            with st.spinner("Lendo a sua redação e reescrevendo com base na nota-alvo..."):
                try:
                    resultado = evoluir_redacao_usuario(
                        tema=tema,
                        texto=texto_aluno,
                        imagens=imagens,
                        competencias=metas,
                        vocabulario=parametros["vocabulario"],
                        estilo_argumentacao=parametros["estilo_argumentacao"],
                        repertorio=parametros["repertorio"],
                        tom_intervencao=parametros["tom_intervencao"],
                        diretrizes_extras=parametros["diretrizes_extras"],
                        preservar_estilo=preservar_estilo,
                        parecer_base=parecer_base,
                        api_key_manual=api_key,
                    )
                    st.session_state["redacao_evoluida"] = resultado
                    st.session_state["redacao_evoluida_versao"] = (
                        st.session_state.get("redacao_evoluida_versao", 0) + 1
                    )
                    st.success("Revisão concluída — confira o que mudou abaixo.")
                except Exception as e:
                    st.error(f"Erro ao revisar a redação: {e}")

    _mostrar_redacao_evoluida(total_meta)


def _mostrar_redacao_evoluida(nota_alvo_simulada: int) -> None:
    resultado = st.session_state.get("redacao_evoluida")

    if not resultado:
        st.divider()
        st.info(
            "Envie a sua redação, ajuste a nota-alvo de cada competência e clique em "
            "**Evoluir minha redação** para ver o texto revisado e a lista de mudanças."
        )
        return

    st.divider()
    parametros = resultado.get("parametros", {})
    tema_revisado = parametros.get("tema", "")
    nota_alvo = resultado.get("nota_alvo", nota_alvo_simulada)

    antes = resultado.get("notas_estimadas_originais") or {}
    depois = resultado.get("notas_estimadas_revisadas") or {}
    delta = (depois.get("total", 0) or 0) - (antes.get("total", 0) or 0)

    col_n1, col_n2, col_n3 = st.columns(3)
    col_n1.metric("Nota estimada da sua versão", f"{antes.get('total', 0)} pts")
    col_n2.metric("Nota estimada após a revisão", f"{depois.get('total', 0)} pts", delta=f"{delta:+d} pts")
    col_n3.metric("Nota-alvo definida", f"{nota_alvo} pts")

    tabela = pd.DataFrame(
        {
            "Competência": [rotulo for _, rotulo in COMPETENCIAS],
            "Antes": [antes.get(chave, 0) for chave, _ in COMPETENCIAS],
            "Depois": [depois.get(chave, 0) for chave, _ in COMPETENCIAS],
        }
    )
    st.dataframe(tabela, hide_index=True, width="stretch")

    if resultado.get("diagnostico"):
        st.markdown("### 🩺 O que estava fraco e o que foi feito")
        st.info(resultado["diagnostico"])

    st.markdown("### 📝 Redação revisada (editável)")
    texto_editado = st.text_area(
        "Texto revisado",
        value=resultado.get("redacao_revisada", ""),
        height=ALTURA_TEXTO,
        key=f"texto_redacao_evoluida_{st.session_state.get('redacao_evoluida_versao', 0)}",
    )

    _botoes_word(
        texto=texto_editado,
        tema=tema_revisado,
        nome_arquivo="minha_redacao_revisada",
        nota_alvo=nota_alvo,
        observacoes=[
            f"Nota estimada da versão original: {antes.get('total', 0)}/1000 pts",
            f"Nota estimada após a revisão: {depois.get('total', 0)}/1000 pts",
            f"Nota-alvo definida: {nota_alvo}/1000 pts",
            f"Vocabulário: {parametros.get('vocabulario', '—')}",
            f"Repertório: {parametros.get('repertorio', '—')}",
            f"Preservar meu estilo: {'sim' if parametros.get('preservar_estilo') else 'não'}",
        ],
        prefixo="evoluir",
    )

    mudancas = resultado.get("mudancas") or []
    if mudancas:
        with st.expander(f"🔍 O que mudou ({len(mudancas)} ajuste(s))", expanded=True):
            st.dataframe(
                pd.DataFrame(mudancas)[["onde", "antes", "depois", "motivo"]].rename(
                    columns={
                        "onde": "Onde",
                        "antes": "Como estava",
                        "depois": "Como ficou",
                        "motivo": "Motivo",
                    }
                ),
                hide_index=True,
                width="stretch",
            )

    if resultado.get("repertorios_adicionados"):
        with st.expander("📚 Repertórios acrescentados", expanded=False, icon="📚"):
            for item in resultado["repertorios_adicionados"]:
                st.markdown(f"- {item}")

    _mostrar_checklist_c5(resultado.get("checklist_c5") or {})

    original = (resultado.get("texto_original_transcrito") or "").strip()
    if original:
        with st.expander("📄 Comparar com a versão original", expanded=False):
            st.write(original)

    aviso = (resultado.get("aviso_calibragem") or "").strip()
    if aviso and aviso.lower() != "nenhum":
        with st.expander("⚠️ Desvios mantidos de propósito para respeitar a nota-alvo", expanded=False):
            st.write(aviso)


# --------------------------------------------------------------------------- #
# Entrada da aba
# --------------------------------------------------------------------------- #
def render_aba_simulador() -> None:
    """Desenha a aba 3 com as duas sub-abas independentes."""
    st.header("Simulador & Redação")
    st.caption(
        "A frente principal é **ajustar a sua redação**, aproveitando o tema e as fotos da última "
        "avaliação. Gerar um texto novo, do zero, é a opção secundária."
    )

    sub_ajustar, sub_gerar = st.tabs(["🖊️ Ajustar a minha redação", "🆕 Gerar redação nova (opcional)"])

    with sub_ajustar:
        _aba_ajustar_minha()

    with sub_gerar:
        _aba_gerar_nova()
