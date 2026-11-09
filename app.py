import hashlib
import os

import pandas as pd
import streamlit as st

from database.models import RedacaoRecord, init_db
from services.ai_evaluator import avaliar_redacao, extrair_tema_da_foto, obter_api_key
from services.parser_service import detectar_mime, extrair_texto_arquivo
from views.simulador import render_aba_simulador

st.set_page_config(
    page_title="Corretor ENEM Pro",
    page_icon="📝",
    layout="wide"
)

# Garantir existência da pasta de dados
os.makedirs("data", exist_ok=True)
SessionLocal = init_db()

st.title("📝 Plataforma Inteligente de Correção ENEM")
st.markdown("Avalie redações no modelo oficial do ENEM, receba diagnósticos completos e acompanhe a evolução das notas.")

# Abas Principais
aba1, aba2, aba3, aba4 = st.tabs([
    "📥 Nova Avaliação", 
    "✏️ Diagnóstico & Correções", 
    "🎯 Simulador & Redação Modelo", 
    "🗄️ Histórico e Evolução"
])

if "ultima_avaliacao" not in st.session_state:
    st.session_state["ultima_avaliacao"] = None


def _rotulo_pagina(indice: int) -> str:
    """Deixa a ordem das fotos explícita: '1ª página', '2ª página'..."""
    return f"{indice + 1}ª página"


def _tema_da_primeira_foto(imagens) -> str:
    """Lê o tema na 1ª página da folha, uma única vez por conjunto de imagens."""
    if not imagens:
        return ""

    assinatura = hashlib.sha256(imagens[0][0]).hexdigest()[:16]
    if st.session_state.get("tema_foto_assinatura") == assinatura:
        return ""  # já tentamos para esta foto — não gasta outra chamada

    st.session_state["tema_foto_assinatura"] = assinatura

    try:
        with st.spinner("Lendo o tema na 1ª página da foto..."):
            dados = extrair_tema_da_foto(imagens)
    except Exception as erro:
        st.warning(f"Não consegui ler o tema automaticamente: {erro}")
        return ""

    return (dados.get("tema") or dados.get("titulo") or "").strip()


with aba1:
    st.header("Envie a Redação")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        tipo_entrada = st.radio(
            "Formato da redação:",
            ["Digitar / Colar Texto", "📷 Fotos da Folha (câmera ou arquivo)", "Arquivo (.docx, .txt, .pdf)"]
        )

        texto_digitado = ""
        arquivo_enviado = None
        imagens = []  # lista de tuplas (bytes, mime_type)

        if tipo_entrada == "Digitar / Colar Texto":
            texto_digitado = st.text_area("Cole a redação aqui:", height=300)

        elif tipo_entrada.startswith("📷"):
            st.caption(
                "Envie as fotos da folha abaixo. Se a redação tiver mais de uma folha, envie várias "
                "fotos — elas são avaliadas juntas, na ordem das páginas."
            )

            fotos_enviadas = st.file_uploader(
                "Envie as fotos da folha",
                type=["png", "jpg", "jpeg", "webp"],
                accept_multiple_files=True,
                key="fotos_redacao",
            )

            with st.expander("📷 Tirar foto agora com a câmera", expanded=False):
                foto_camera = st.camera_input("Tirar foto da folha", key="camera_redacao")

            fotos = []
            if foto_camera is not None:
                fotos.append(("foto_camera.jpg", foto_camera.getvalue()))
            for f in (fotos_enviadas or []):
                fotos.append((f.name, f.getvalue()))

            if fotos:
                st.success(f"{len(fotos)} foto(s) pronta(s) para avaliação.")
                with st.expander(f"🖼️ Ver as {len(fotos)} foto(s) enviada(s)", expanded=False):
                    colunas_preview = st.columns(min(len(fotos), 3))
                    for i, (nome_foto, dados_foto) in enumerate(fotos):
                        with colunas_preview[i % 3]:
                            st.image(
                                dados_foto,
                                caption=f"{_rotulo_pagina(i)} — {nome_foto}",
                                width="stretch",
                            )

            imagens = [(dados_foto, detectar_mime(nome_foto, dados_foto)) for nome_foto, dados_foto in fotos]

            texto_digitado = st.text_area(
                "Transcrição / observações (opcional):",
                placeholder="Se quiser, cole aqui a transcrição da redação ou observações para o corretor.",
                height=120,
            )

        else:
            arquivo_enviado = st.file_uploader("Selecione o arquivo", type=["txt", "docx", "pdf"])
            if arquivo_enviado:
                texto_digitado = extrair_texto_arquivo(arquivo_enviado)
                st.text_area("Texto extraído:", value=texto_digitado, height=150)

        # ---- Tema: lido automaticamente na 1ª página, quando houver fotos ---- #
        tema_automatico = _tema_da_primeira_foto(imagens)

        if "tema_input" not in st.session_state:
            st.session_state["tema_input"] = ""

        if tema_automatico and not (st.session_state.get("tema_input") or "").strip():
            st.session_state["tema_input"] = tema_automatico
            st.session_state["tema_origem"] = "1ª foto"

        tema_input = st.text_input(
            "Tema da Redação",
            key="tema_input",
            placeholder="Ex: Os desafios da valorização do trabalho de cuidado no Brasil",
            help="Quando a redação vem em fotos, o tema é lido automaticamente na 1ª página.",
        )

        if imagens and st.session_state.get("tema_origem") == "1ª foto":
            st.caption("🔎 Tema preenchido automaticamente pela 1ª página da foto — edite se precisar.")

        api_key_env = obter_api_key()
        api_key_manual = ""
        if api_key_env:
            st.caption("🔑 Chave do Gemini carregada automaticamente do arquivo `.env`.")
        else:
            st.warning(
                "Nenhuma chave do Gemini encontrada. Coloque `GEMINI_API_KEY=...` no arquivo "
                "`.env` na raiz do projeto ou informe abaixo."
            )
            api_key_manual = st.text_input("Gemini API Key", type="password", help="Chave de API do Google Gemini")

        btn_corrigir = st.button("🚀 Avaliar Redação", type="primary")

    with col2:
        if btn_corrigir:
            if not tema_input:
                st.warning("Informe o tema da redação antes de continuar.")
            elif not texto_digitado.strip() and not imagens:
                st.warning("Insira o texto, o arquivo ou pelo menos uma foto da redação.")
            else:
                with st.spinner("Analisando competências C1 a C5..."):
                    try:
                        resultado = avaliar_redacao(tema_input, texto_digitado, imagens, api_key_manual)
                        # Guarda também as fotos: a aba "Ajustar a minha redação" as reutiliza.
                        st.session_state["ultima_avaliacao"] = {
                            "tema": tema_input,
                            "texto": texto_digitado,
                            "imagens": imagens,
                            "res": resultado
                        }
                        # Versão nova = os campos da aba de ajuste recarregam com os dados atuais.
                        st.session_state["versao_avaliacao"] = st.session_state.get("versao_avaliacao", 0) + 1

                        texto_para_banco = texto_digitado.strip()
                        if not texto_para_banco:
                            texto_para_banco = f"[{len(imagens)} foto(s) da folha de redação]"

                        db = SessionLocal()
                        novo_registro = RedacaoRecord(
                            tema=tema_input,
                            texto_original=texto_para_banco,
                            nota_total=resultado.get("nota_total", 0),
                            c1=resultado.get("c1", 0),
                            c2=resultado.get("c2", 0),
                            c3=resultado.get("c3", 0),
                            c4=resultado.get("c4", 0),
                            c5=resultado.get("c5", 0),
                            parecer=resultado.get("parecer", ""),
                            trechos_problemas=resultado.get("trechos_problemas", ""),
                            redacao_modelo=resultado.get("redacao_modelo", "")
                        )
                        db.add(novo_registro)
                        db.commit()
                        db.close()
                        
                        st.success("Avaliação concluída e registrada no histórico!")
                    except Exception as e:
                        st.error(f"Erro na avaliação: {e}")

        if st.session_state["ultima_avaliacao"]:
            res = st.session_state["ultima_avaliacao"]["res"]
            st.metric("Nota Total", f"{res.get('nota_total', 0)} / 1000 pts")
            
            st.subheader("Notas por Competência")
            df_comp = pd.DataFrame({
                "Competência": ["C1 (Norma Culta)", "C2 (Estrutura/Tema)", "C3 (Argumentação)", "C4 (Coesão)", "C5 (Intervenção)"],
                "Nota": [res.get("c1",0), res.get("c2",0), res.get("c3",0), res.get("c4",0), res.get("c5",0)]
            })
            st.bar_chart(df_comp.set_index("Competência"))

with aba2:
    st.header("Diagnóstico Detalhado & Sugestões")
    if st.session_state["ultima_avaliacao"]:
        res = st.session_state["ultima_avaliacao"]["res"]
        st.markdown("### Parecer Geral")
        st.write(res.get("parecer", "Sem detalhes disponíveis."))
        
        st.markdown("### ⚠️ Pontos de Atenção & Reescrita")
        st.info(res.get("trechos_problemas", "Nenhum ponto gravíssimo detectado."))
    else:
        st.info("Execute uma avaliação na aba 'Nova Avaliação' para visualizar o parecer completo.")

with aba3:
    # Simulador e redação divididos em duas frentes (ver views/simulador.py):
    # gerar um texto novo ou evoluir a redação escrita pelo próprio aluno.
    render_aba_simulador()

with aba4:
    st.header("Histórico de Redações")
    try:
        db = SessionLocal()
        registros = db.query(RedacaoRecord).order_by(RedacaoRecord.id.desc()).all()
        db.close()
        
        if registros:
            dados = []
            for r in registros:
                dados.append({
                    "ID": r.id,
                    "Data": r.data_criacao.strftime("%d/%m/%Y %H:%M"),
                    "Tema": r.tema,
                    "Nota Total": r.nota_total,
                    "C1": r.c1, "C2": r.c2, "C3": r.c3, "C4": r.c4, "C5": r.c5
                })
            st.dataframe(pd.DataFrame(dados), width="stretch")
        else:
            st.info("Nenhuma redação registrada no banco até o momento.")
    except Exception as e:
        st.warning("Banco de dados ainda sem dados salvos.")
