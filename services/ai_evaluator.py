import json
import os
import time
import streamlit as st
from google import genai
from google.genai import types

# --------------------------------------------------------------------------- #
# Carregamento do .env
# --------------------------------------------------------------------------- #
try:  # python-dotenv é opcional: sem ele, apenas as variáveis de ambiente valem
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover
    _load_dotenv = None

RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_ENV = os.path.join(RAIZ_PROJETO, ".env")

# override=False: uma variável já definida no ambiente (ex.: Streamlit Cloud)
# tem prioridade sobre o arquivo .env local.
ENV_CARREGADO = False
if _load_dotenv is not None and os.path.isfile(CAMINHO_ENV):
    try:
        ENV_CARREGADO = bool(_load_dotenv(dotenv_path=CAMINHO_ENV, override=False))
    except Exception:
        ENV_CARREGADO = False


def _limpar_valor(valor) -> str:
    """Remove espaços, aspas e comentários acidentais vindos do .env ou da interface."""
    if not valor:
        return ""
    texto = str(valor).strip()
    # remove aspas envolvendo o valor
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in ("'", '"'):
        texto = texto[1:-1]
    # remove comentário no fim da linha: "chave  # comentario"
    if " #" in texto:
        texto = texto.split(" #", 1)[0]
    return texto.strip()


def obter_api_key() -> str:
    """Retorna a chave do Gemini na ordem de prioridade:
    1) Secrets do Streamlit Cloud, 2) variáveis de ambiente / arquivo .env.
    """
    # st.secrets levanta StreamlitSecretNotFoundError quando não existe secrets.toml,
    # por isso a leitura é protegida: ausência de secrets não deve derrubar o app.
    try:
        if "GEMINI_API_KEY" in st.secrets:
            chave = _limpar_valor(st.secrets["GEMINI_API_KEY"])
            if chave:
                return chave
    except Exception:
        pass

    return _limpar_valor(os.environ.get("GEMINI_API_KEY", ""))


def normalizar_imagens(imagens):
    """Transforma as entradas aceitas em uma lista de tuplas (bytes, mime_type).

    Aceita: None, bytes avulsos, lista de bytes, lista de (bytes, mime)
    ou lista de dicts {"data": ..., "mime_type": ...}.
    """
    if not imagens:
        return []

    # Um único arquivo enviado como bytes
    if isinstance(imagens, (bytes, bytearray)):
        return [(bytes(imagens), "image/jpeg")]

    normalizadas = []
    for item in imagens:
        if isinstance(item, dict):
            dados = item.get("data") or item.get("bytes")
            mime = item.get("mime_type") or "image/jpeg"
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            dados, mime = item[0], item[1]
        else:
            dados, mime = item, "image/jpeg"

        if dados:
            normalizadas.append((bytes(dados), mime or "image/jpeg"))

    return normalizadas


# --------------------------------------------------------------------------- #
# Opções de personalização da redação modelo (aba "Simulador & Redação Modelo")
# --------------------------------------------------------------------------- #
# Modelo usado pelo app. Pode ser trocado sem alterar código, via variável de
# ambiente ou .env:  GEMINI_MODEL=gemini-3.8-flash
MODELO_PADRAO = "gemini-3.8-flash"

# Se o modelo configurado não existir mais para a sua chave, tentamos estes em ordem.
MODELOS_FALLBACK = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]

# Retentativas em caso de sobrecarga (503/429) antes de desistir.
TENTATIVAS_POR_MODELO = 3
ESPERA_ENTRE_TENTATIVAS = 2.0  # segundos (multiplicado pelo número da tentativa)


def obter_modelo() -> str:
    """Nome do modelo, lido do ambiente a cada chamada (.env ou GEMINI_MODEL)."""
    return _limpar_valor(os.environ.get("GEMINI_MODEL", "")) or MODELO_PADRAO


# Mantido por compatibilidade com código que importe o nome antigo.
MODELO_GEMINI = MODELO_PADRAO

OPCOES_VOCABULARIO = [
    "Padrão ENEM",
    "Erudito/Formal",
    "Acessível e Direto",
]

OPCOES_ESTILO_ARGUMENTACAO = [
    "Mais Criativo/Inovador",
    "Tradicional/Clássico",
    "Crítico e Persuasivo",
]

OPCOES_REPERTORIO = [
    "Filosofia/Sociologia",
    "História/Fatos Históricos",
    "Literatura/Artes",
    "Constituição/Leis",
]

OPCOES_TOM_INTERVENCAO = [
    "Solução Governamental Direta",
    "Ação Conjunta (Escola + Família + Mídia)",
    "Foco em Tecnologia e Inovação",
]

# Conteúdo das competências do ENEM usado para calibrar o texto gerado.
DESCRICAO_COMPETENCIAS = {
    "c1": "C1 — Domínio da norma padrão: gramática, ortografia, concordância, pontuação e escolha vocabular.",
    "c2": "C2 — Compreensão do tema e estrutura dissertativo-argumentativa com repertório sociocultural legítimo e produtivo.",
    "c3": "C3 — Projeto de texto e argumentação: seleção e organização de argumentos em defesa de um ponto de vista.",
    "c4": "C4 — Coesão textual: conectivos inter e intraparágrafos e articulação sem repetições prejudiciais.",
    "c5": "C5 — Proposta de intervenção com os cinco elementos: agente, ação, meio/modo, detalhamento e efeito.",
}


def _descrever_nivel(nota) -> str:
    """Converte a nota de uma competência (0-200) no nível descritivo do ENEM."""
    try:
        nota = int(round(float(nota)))
    except (TypeError, ValueError):
        nota = 0

    if nota <= 0:
        return "nível 0 (texto anulado ou assunto não tratado)"
    if nota <= 40:
        return "nível 1 (muito insuficiente, com falhas graves e recorrentes)"
    if nota <= 80:
        return "nível 2 (insuficiente, com problemas frequentes)"
    if nota <= 120:
        return "nível 3 (mediano: atende parcialmente, com desvios pontuais)"
    if nota <= 160:
        return "nível 4 (bom: domínio consistente com desvios isolados)"
    return "nível 5 (excelente: domínio pleno e recorrente)"


def _instrucoes_competencias(competencias: dict) -> str:
    """Monta a lista de metas de qualidade por competência para o prompt."""
    linhas = []
    for chave in ("c1", "c2", "c3", "c4", "c5"):
        nota = competencias.get(chave, 160)
        linhas.append(
            f"- {DESCRICAO_COMPETENCIAS[chave]} Meta: {nota}/200 — {_descrever_nivel(nota)}."
        )
    return "\n".join(linhas)


def _extrair_json(texto: str) -> dict:
    """Faz o parse tolerante de JSON devolvido pelo modelo.

    O Gemini às vezes devolve o JSON dentro de cercas ```json``` ou precedido de
    uma frase. Tentamos, em ordem: parse direto, remoção das cercas e recorte
    do primeiro "{" até o último "}".
    """
    if not texto or not texto.strip():
        raise ValueError("A IA não retornou conteúdo.")

    candidatos = [texto.strip()]

    sem_cercas = texto.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    if sem_cercas not in candidatos:
        candidatos.append(sem_cercas)

    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio != -1 and fim > inicio:
        recorte = texto[inicio : fim + 1].strip()
        if recorte not in candidatos:
            candidatos.append(recorte)

    ultimo_erro = None
    for candidato in candidatos:
        try:
            dados = json.loads(candidato)
        except json.JSONDecodeError as erro:
            ultimo_erro = erro
            continue
        if isinstance(dados, dict):
            return dados

    raise ValueError(f"A IA retornou um JSON inválido: {ultimo_erro}")


def _erro_modelo_indisponivel(erro: Exception) -> bool:
    """Detecta 404/NOT_FOUND (modelo descontinuado) para acionar o fallback."""
    texto = f"{type(erro).__name__}: {erro}".lower()
    marcadores = ("404", "not_found", "no longer available", "not found", "is not supported")
    return any(marcador in texto for marcador in marcadores)


def _erro_temporario(erro: Exception) -> bool:
    """Detecta sobrecarga, limite de uso ou falha de rede — vale a pena tentar de novo."""
    texto = f"{type(erro).__name__}: {erro}".lower()
    marcadores = (
        "503",
        "429",
        "500",
        "502",
        "504",
        "unavailable",
        "overloaded",
        "high demand",
        "rate limit",
        "resource_exhausted",
        "deadline",
        "timeout",
        "temporarily",
        # falhas de rede (conexão derrubada no meio da requisição)
        "connection",
        "winerror",
        "readerror",
        "remotedisconnected",
        "protocolerror",
        "ssl",
    )
    return any(marcador in texto for marcador in marcadores)


def _chamar_modelo(api_key: str, contents, temperature: float = 0.2) -> dict:
    """Chama o Gemini exigindo JSON e devolve o dicionário já parseado.

    Resiliência em duas camadas:
    - 404/NOT_FOUND (modelo descontinuado): tenta o próximo de MODELOS_FALLBACK.
    - 503/429 (sobrecarga ou limite): aguarda e repete no mesmo modelo.
    """
    modelo_configurado = obter_modelo()
    ordem = [modelo_configurado] + [m for m in MODELOS_FALLBACK if m != modelo_configurado]

    client = genai.Client(api_key=api_key)
    ultimo_erro = None

    for indice, modelo in enumerate(ordem):
        for tentativa in range(1, TENTATIVAS_POR_MODELO + 1):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                    ),
                )
                return _extrair_json(getattr(response, "text", ""))
            except Exception as erro:
                ultimo_erro = erro

                if _erro_modelo_indisponivel(erro):
                    # Modelo aposentado: nem adianta repetir, vai para o próximo
                    break

                if _erro_temporario(erro) and tentativa < TENTATIVAS_POR_MODELO:
                    time.sleep(ESPERA_ENTRE_TENTATIVAS * tentativa)
                    continue

                if _erro_temporario(erro) and indice < len(ordem) - 1:
                    # Sobrecarga persistente neste modelo: tenta o próximo
                    break

                raise

    if ultimo_erro is not None and _erro_modelo_indisponivel(ultimo_erro):
        raise ValueError(
            f"Nenhum modelo Gemini disponível para esta chave. "
            f"Testei: {', '.join(ordem)}. Defina outro em GEMINI_MODEL no arquivo .env. "
            f"Último erro: {ultimo_erro}"
        ) from ultimo_erro

    raise ValueError(
        f"O serviço do Gemini está instável no momento (sobrecarga). "
        f"Tente novamente em alguns instantes. Último erro: {ultimo_erro}"
    ) from ultimo_erro


def avaliar_redacao(tema: str, texto: str, imagens=None, api_key_manual: str = "", imagem_bytes=None):
    api_key = _limpar_valor(api_key_manual) or obter_api_key()

    if not api_key:
        raise ValueError(
            "Chave de API do Gemini não encontrada. Coloque GEMINI_API_KEY no arquivo .env, "
            "configure nos Secrets do Streamlit Cloud ou informe no aplicativo."
        )

    imagens_norm = normalizar_imagens(imagens)
    if imagem_bytes:
        imagens_norm.extend(normalizar_imagens(imagem_bytes))

    if imagens_norm:
        instrucao_entrada = (
            f"O aluno enviou {len(imagens_norm)} foto(s) da folha oficial de redação.\n"
            "Transcreva com atenção o que está escrito à mão (a caligrafia pode variar) e avalie "
            "o texto contido nas imagens. Caso a transcrição auxiliar tenha sido enviada, use-a "
            "como apoio para conferir palavras duvidosas, mas prevaleça sempre o que está na foto. "
            "Não penalize a caligrafia em si; considere apenas aspectos de legibilidade que "
            "prejudiquem a leitura.\n"
        )
    else:
        instrucao_entrada = ""

    texto_para_prompt = texto.strip() if texto and texto.strip() else "(não informado — use as imagens da folha)"

    prompt = f"""
Você é um corretor oficial e rigoroso de redações do ENEM.
Tema da Redação: {tema}

Analise o texto fornecido abaixo com base estritamente nas 5 competências oficiais do ENEM (cada uma vale de 0 a 200 pontos, totalizando até 1000 pontos).

Formato de resposta obrigatório: JSON puro exatamente com este esquema:
{{
  "nota_total": <numero>,
  "c1": <0 a 200>,
  "c2": <0 a 200>,
  "c3": <0 a 200>,
  "c4": <0 a 200>,
  "c5": <0 a 200>,
  "parecer": "Análise detalhada geral do texto...",
  "trechos_problemas": "Liste os principais desvios gramaticais, falhas argumentativas ou ausência de elementos na proposta de intervenção, indicando o trecho original e a sugestão de correção.",
  "redacao_modelo": "Escreva um exemplo de redação Nota 1000/referência excelente sobre este tema para servir de inspiração."
}}

{instrucao_entrada}
Texto da Redação (transcrição ou observações):
{texto_para_prompt}
"""

    contents = [prompt]
    for dados, mime in imagens_norm:
        contents.append(
            types.Part.from_bytes(
                data=dados,
                mime_type=mime,
            )
        )

    return _chamar_modelo(api_key, contents, temperature=0.2)


def gerar_redacao_customizada(
    tema: str,
    competencias: dict | None = None,
    vocabulario: str = "Padrão ENEM",
    estilo_argumentacao: str = "Tradicional/Clássico",
    repertorio: str = "Filosofia/Sociologia",
    tom_intervencao: str = "Solução Governamental Direta",
    diretrizes_extras: str = "",
    parecer_base: str = "",
    api_key_manual: str = "",
) -> dict:
    """Gera uma redação modelo com estilo ajustável e qualidade calibrada pela nota alvo.

    Args:
        tema: Tema da redação.
        competencias: Notas-alvo por competência, ex. {"c1": 200, ..., "c5": 200}.
        vocabulario: Uma das OPCOES_VOCABULARIO.
        estilo_argumentacao: Uma das OPCOES_ESTILO_ARGUMENTACAO.
        repertorio: Uma das OPCOES_REPERTORIO.
        tom_intervencao: Uma das OPCOES_TOM_INTERVENCAO.
        diretrizes_extras: Instruções livres do usuário.
        parecer_base: Parecer de uma correção anterior, usado como contexto.
        api_key_manual: Chave informada na interface (tem prioridade).

    Returns:
        dict com "redacao", "checklist_c5", "repertorio_utilizado",
        "justificativa_nota", "nota_alvo" e "parametros".
    """
    api_key = _limpar_valor(api_key_manual) or obter_api_key()
    if not api_key:
        raise ValueError(
            "Chave de API do Gemini não encontrada. Coloque GEMINI_API_KEY no arquivo .env, "
            "configure nos Secrets do Streamlit Cloud ou informe no aplicativo."
        )

    competencias = {**{"c1": 200, "c2": 200, "c3": 200, "c4": 200, "c5": 200}, **(competencias or {})}
    try:
        nota_total = int(sum(int(round(float(competencias[c]))) for c in ("c1", "c2", "c3", "c4", "c5")))
    except (TypeError, ValueError, KeyError):
        nota_total = 1000

    vocabulario = vocabulario if vocabulario in OPCOES_VOCABULARIO else "Padrão ENEM"
    estilo_argumentacao = (
        estilo_argumentacao
        if estilo_argumentacao in OPCOES_ESTILO_ARGUMENTACAO
        else "Tradicional/Clássico"
    )
    repertorio = repertorio if repertorio in OPCOES_REPERTORIO else "Filosofia/Sociologia"
    tom_intervencao = (
        tom_intervencao if tom_intervencao in OPCOES_TOM_INTERVENCAO else "Solução Governamental Direta"
    )

    guia_estilos = {
        "Padrão ENEM": (
            "Vocabulário formal e objetivo, no registro esperado pelo corretor do ENEM. "
            "Use termos técnicos apenas quando necessários à argumentação."
        ),
        "Erudito/Formal": (
            "Vocabulário erudito e denso, com construções sintáticas sofisticadas e precisas. "
            "Mantenha a clareza: erudição não pode virar obscuridade nem prolixidade."
        ),
        "Acessível e Direto": (
            "Vocabulário claro e direto, frases mais curtas e ideias explícitas. "
            "Simplicidade sem perder o registro formal exigido pela norma padrão."
        ),
    }

    guia_argumentacao = {
        "Mais Criativo/Inovador": (
            "Construa uma linha de raciocínio original: aproximações inesperadas entre repertórios, "
            "analogias bem fundamentadas e um ângulo de análise pouco óbvio, sempre sustentado por "
            "evidências. Originalidade não pode custar coerência."
        ),
        "Tradicional/Clássico": (
            "Siga o modelo consagrado de quatro parágrafos: introdução com repertório e tese dividida "
            "em duas problemáticas, dois desenvolvimentos com tópico frasal + repertório + análise, "
            "e conclusão com proposta de intervenção completa."
        ),
        "Crítico e Persuasivo": (
            "Assuma posicionamento crítico explícito, denuncie causas estruturais do problema e use "
            "um encadeamento argumentativo que leve o leitor à conclusão. Critique com dados e "
            "repertório, nunca com opinião solta."
        ),
    }

    guia_repertorio = {
        "Filosofia/Sociologia": (
            "Priorize filósofos e sociólogos (ex.: Bauman, Foucault, Hannah Arendt, Durkheim, "
            "Marx, Kant, Djamila Ribeiro). Traga o conceito e explique sua relação com o tema."
        ),
        "História/Fatos Históricos": (
            "Priorize fatos históricos, processos e marcos datados (ex.: Constituição de 1988, "
            "ditadura militar, Revolução Industrial, abolição, formação do Estado brasileiro). "
            "Contextualize a data e a consequência para o presente."
        ),
        "Literatura/Artes": (
            "Priorize obras literárias, autores, filmes, séries, músicas, peças e movimentos "
            "artísticos (ex.: Machado de Assis, Graciliano Ramos, Carolina Maria de Jesus, "
            "Vidas Secas, Distopia). Explique a obra em uma frase e conecte ao tema."
        ),
        "Constituição/Leis": (
            "Priorize dispositivos legais e institucionais (ex.: Constituição Federal de 1988, "
            "art. 5º, art. 6º, art. 205, art. 227; ECA; Lei Maria da Penha; Lei de Diretrizes e "
            "Bases da Educação; Declaração Universal dos Direitos Humanos). Cite o dispositivo "
            "e explique o que ele garante."
        ),
    }

    guia_intervencao = {
        "Solução Governamental Direta": (
            "O agente principal deve ser o poder público (Governo Federal, Ministério, Secretaria, "
            "Prefeitura), com ação regulatória, orçamentária ou de fiscalização."
        ),
        "Ação Conjunta (Escola + Família + Mídia)": (
            "A intervenção deve envolver coordenação entre escola, família e mídia/redes sociais, "
            "explicitando o papel de cada um e como atuam juntos."
        ),
        "Foco em Tecnologia e Inovação": (
            "A intervenção deve usar soluções tecnológicas (plataformas digitais, aplicativos, "
            "IA, dados, automação), explicando o meio técnico e quem opera a solução."
        ),
    }

    contexto_extra = ""
    if parecer_base and parecer_base.strip():
        contexto_extra += (
            "\nContexto de uma correção anterior do aluno (use para evoluir o texto, "
            "corrigindo os pontos fracos citados):\n"
            f"{parecer_base.strip()}\n"
        )
    if diretrizes_extras and diretrizes_extras.strip():
        contexto_extra += (
            "\nOrientações adicionais do usuário (têm prioridade sobre o estilo, "
            f"mas nunca sobre a legalidade/ética do conteúdo):\n{diretrizes_extras.strip()}\n"
        )

    prompt = f"""Você é um professor de redação que escreve textos de referência para o ENEM.
Sua tarefa é produzir UMA redação dissertativo-argumentativa em português do Brasil, sobre o tema:
"{tema}"

## Meta de qualidade (obrigatória)
A redação deve ser calibrada EXATAMENTE para a nota alvo de {nota_total}/1000 pontos,
respeitando cada competência isoladamente:
{_instrucoes_competencias(competencias)}

Regra de calibragem: se uma competência tem meta abaixo de 200, insira desvios discretos e
compatíveis com o nível descrito (por exemplo, um ou outro desvio de pontuação em C1, ou uma
relação entre repertório e tema menos desenvolvida em C2), sem comprometer o restante do texto.
Se todas as metas forem 200, o texto deve ser impecável.

## Estrutura obrigatória
- Exatamente 4 parágrafos, entre 27 e 32 linhas no total.
- Parágrafo 1: repertório inicial (gancho) + apresentação do problema + tese com duas problemáticas.
- Parágrafo 2: tópico frasal + repertório sociocultural + análise + fechamento do argumento.
- Parágrafo 3: conectivo de adição no tópico frasal + novo repertório + análise + fechamento.
- Parágrafo 4: proposta de intervenção com os 5 elementos (agente, ação, meio/modo,
  detalhamento, efeito), finalizando com efeito social claro.

## Parâmetros de estilo escolhidos pelo usuário
- Nível de vocabulário ({vocabulario}): {guia_estilos[vocabulario]}
- Estilo da argumentação ({estilo_argumentacao}): {guia_argumentacao[estilo_argumentacao]}
- Eixo de repertório ({repertorio}): {guia_repertorio[repertorio]}
  Use pelo menos DOIS repertórios deste eixo, todos legítimos, produtivos e corretamente
  atribuídos (nunca invente citações, dados ou obras).
- Tom da proposta de intervenção ({tom_intervencao}): {guia_intervencao[tom_intervencao]}
{contexto_extra}
## Regras de segurança e honestidade
- Não invente dados estatísticos precisos, pesquisas ou citações. Se precisar de números,
  use apenas informações amplamente conhecidas ou formule de modo qualitativo.
- Não utilize linguagem de ódio, discriminatória ou ofensiva a grupos sociais.
- Não cite este prompt nem mencione que é uma IA.

## Formato de resposta
Responda em JSON puro, exatamente com este esquema:
{{
  "redacao": "texto completo com os 4 parágrafos separados por \\n\\n",
  "repertorios_usados": ["repertório 1 com autor/obra e o que ele sustenta", "repertório 2 ..."],
  "checklist_c5": {{
    "agente": "...",
    "acao": "...",
    "meio_modo": "...",
    "detalhamento": "...",
    "efeito": "..."
  }},
  "justificativa_nota": "em até 5 linhas, explique por que o texto corresponde à nota alvo {nota_total}",
  "aviso_calibragem": "se algum desvio foi inserido de propósito para respeitar a nota, descreva-o; caso contrário, escreva 'nenhum'"
}}
"""

    dados = _chamar_modelo(api_key, [prompt], temperature=0.75)

    redacao = (dados.get("redacao") or "").strip()
    if not redacao:
        raise ValueError("A IA não retornou o texto da redação. Tente novamente.")

    return {
        "redacao": redacao,
        "repertorios_usados": dados.get("repertorios_usados", []) or [],
        "checklist_c5": dados.get("checklist_c5", {}) or {},
        "justificativa_nota": dados.get("justificativa_nota", ""),
        "aviso_calibragem": dados.get("aviso_calibragem", ""),
        "nota_alvo": nota_total,
        "parametros": {
            "tema": tema,
            "vocabulario": vocabulario,
            "estilo_argumentacao": estilo_argumentacao,
            "repertorio": repertorio,
            "tom_intervencao": tom_intervencao,
            "diretrizes_extras": diretrizes_extras.strip(),
            "competencias": {c: int(round(float(competencias[c]))) for c in ("c1", "c2", "c3", "c4", "c5")},
        },
    }


# --------------------------------------------------------------------------- #
# Reescrita guiada: evoluir a redação do próprio aluno
# --------------------------------------------------------------------------- #
RESUMO_VOCABULARIO = {
    "Padrão ENEM": "mantenha o registro formal e objetivo esperado pelo corretor do ENEM",
    "Erudito/Formal": "eleva a densidade lexical, sem perder a clareza",
    "Acessível e Direto": "privilegia clareza e frases mais curtas, sem informalidade",
}

RESUMO_ARGUMENTACAO = {
    "Mais Criativo/Inovador": "busque um ângulo de análise mais original, sustentado por evidências",
    "Tradicional/Clássico": "conserve a estrutura consagrada de quatro parágrafos",
    "Crítico e Persuasivo": "deixe a postura crítica explícita, fundamentada em dados e repertório",
}

RESUMO_REPERTORIO = {
    "Filosofia/Sociologia": "repertórios de filósofos e sociólogos, com conceito explicado",
    "História/Fatos Históricos": "fatos históricos datados e sua consequência para o presente",
    "Literatura/Artes": "obras literárias, filmes, músicas ou movimentos artísticos",
    "Constituição/Leis": "dispositivos legais e institucionais, com o que cada um garante",
}

RESUMO_INTERVENCAO = {
    "Solução Governamental Direta": "agente principal no poder público, com ação concreta",
    "Ação Conjunta (Escola + Família + Mídia)": "coordenação entre escola, família e mídia",
    "Foco em Tecnologia e Inovação": "soluções tecnológicas, explicitando o meio técnico",
}


def _normalizar_notas(dados) -> dict:
    """Padroniza o dicionário de notas devolvido pelo modelo."""
    dados = dados if isinstance(dados, dict) else {}
    notas = {}
    for chave in ("c1", "c2", "c3", "c4", "c5"):
        try:
            notas[chave] = int(round(float(dados.get(chave, 0) or 0)))
        except (TypeError, ValueError):
            notas[chave] = 0

    soma = sum(notas.values())
    try:
        notas["total"] = int(round(float(dados.get("total", soma) or soma)))
    except (TypeError, ValueError):
        notas["total"] = soma

    return notas


def evoluir_redacao_usuario(
    tema: str,
    texto: str = "",
    imagens=None,
    competencias: dict | None = None,
    vocabulario: str = "Padrão ENEM",
    estilo_argumentacao: str = "Tradicional/Clássico",
    repertorio: str = "Filosofia/Sociologia",
    tom_intervencao: str = "Solução Governamental Direta",
    diretrizes_extras: str = "",
    preservar_estilo: bool = True,
    parecer_base: str = "",
    api_key_manual: str = "",
) -> dict:
    """Reescreve a redação do aluno elevando cada competência até a nota-alvo.

    Diferente de ``gerar_redacao_customizada``, aqui o texto de partida é o do
    aluno: as ideias, os argumentos e a linha de raciocínio dele devem ser
    mantidos, e a IA apenas corrige desvios e desenvolve o que faltava.

    Args:
        tema: Tema da redação.
        texto: Texto digitado/extraído da redação do aluno (pode vir vazio se
            houver imagens).
        imagens: Fotos da folha em qualquer formato aceito por
            ``normalizar_imagens``.
        competencias: Notas-alvo por competência, ex. ``{"c1": 160, ...}``.
        vocabulario: Uma das OPCOES_VOCABULARIO.
        estilo_argumentacao: Uma das OPCOES_ESTILO_ARGUMENTACAO.
        repertorio: Uma das OPCOES_REPERTORIO.
        tom_intervencao: Uma das OPCOES_TOM_INTERVENCAO.
        diretrizes_extras: Instruções livres do usuário.
        preservar_estilo: Se True, mantém ao máximo a voz e as escolhas do aluno.
        parecer_base: Parecer de uma correção anterior, usado como contexto.
        api_key_manual: Chave informada na interface (tem prioridade).

    Returns:
        dict com ``redacao_revisada``, ``diagnostico``, ``mudancas``,
        ``notas_estimadas_originais``, ``notas_estimadas_revisadas``,
        ``checklist_c5``, ``repertorios_adicionados``, ``nota_alvo`` e ``parametros``.
    """
    api_key = _limpar_valor(api_key_manual) or obter_api_key()
    if not api_key:
        raise ValueError(
            "Chave de API do Gemini não encontrada. Coloque GEMINI_API_KEY no arquivo .env, "
            "configure nos Secrets do Streamlit Cloud ou informe no aplicativo."
        )

    texto = (texto or "").strip()
    imagens_norm = normalizar_imagens(imagens)
    if not texto and not imagens_norm:
        raise ValueError("Envie o texto da redação ou pelo menos uma foto da folha.")

    competencias = {**{"c1": 200, "c2": 200, "c3": 200, "c4": 200, "c5": 200}, **(competencias or {})}
    try:
        nota_total = int(sum(int(round(float(competencias[c]))) for c in ("c1", "c2", "c3", "c4", "c5")))
    except (TypeError, ValueError, KeyError):
        nota_total = 1000

    vocabulario = vocabulario if vocabulario in OPCOES_VOCABULARIO else "Padrão ENEM"
    estilo_argumentacao = (
        estilo_argumentacao
        if estilo_argumentacao in OPCOES_ESTILO_ARGUMENTACAO
        else "Tradicional/Clássico"
    )
    repertorio = repertorio if repertorio in OPCOES_REPERTORIO else "Filosofia/Sociologia"
    tom_intervencao = (
        tom_intervencao if tom_intervencao in OPCOES_TOM_INTERVENCAO else "Solução Governamental Direta"
    )

    if imagens_norm:
        instrucao_entrada = (
            f"O aluno enviou {len(imagens_norm)} foto(s) da folha oficial.\n"
            "Transcreva com atenção o texto manuscrito antes de reescrever (a caligrafia pode variar). "
            "Quando houver transcrição digitada junto, use-a para conferir palavras duvidosas, mas "
            "prevaleça o que está na foto. A caligrafia em si não é avaliada.\n"
        )
    else:
        instrucao_entrada = ""

    texto_para_prompt = texto if texto else "(não informado — use as imagens da folha)"

    diretriz_preservacao = (
        "PRESERVE ao máximo as ideias, os argumentos, os exemplos, os repertórios e a voz do aluno: "
        "não troque a linha de raciocínio dele por outra, reescreva apenas o que for necessário para "
        "corrigir desvios e completar o que falta. O resultado deve ser reconhecível como a redação DELE, "
        "só que melhor."
        if preservar_estilo
        else
        "Você pode reorganizar livremente os argumentos e reescrever parágrafos inteiros, mantendo "
        "apenas o tema e o ponto de vista defendido pelo aluno."
    )

    contexto_extra = ""
    if parecer_base and parecer_base.strip():
        contexto_extra += (
            "\nParecer de uma correção anterior do próprio aluno (use como diagnóstico de partida):\n"
            f"{parecer_base.strip()}\n"
        )
    if diretrizes_extras and diretrizes_extras.strip():
        contexto_extra += (
            "\nOrientações adicionais do usuário (prioridade sobre o estilo, nunca sobre a ética):\n"
            f"{diretrizes_extras.strip()}\n"
        )

    prompt = f"""Você é um professor de redação do ENEM especializado em reescrita guiada.
O aluno escreveu uma redação sobre o tema:
"{tema}"

Sua tarefa NÃO é criar uma redação nova do zero: é EVOLUIR a redação do aluno,
mantendo o que ele já construiu e elevando o texto até a nota-alvo.

## Meta de qualidade (obrigatória)
O texto revisado deve ser calibrado para {nota_total}/1000 pontos, respeitando cada competência:
{_instrucoes_competencias(competencias)}

## Regra central
{diretriz_preservacao}

## O que corrigir
- C1: ortografia, concordância, regência, pontuação e escolha vocabular.
- C2: garantir que o texto trate o tema (não apenas o assunto geral) e que a estrutura
  dissertativo-argumentativa esteja completa, com repertório legítimo e produtivo.
- C3: deixar explícito o projeto de texto — cada parágrafo deve defender uma tese e concluir um argumento.
- C4: ajustar conectivos e retomadas, eliminando repetições e saltos entre frases.
- C5: completar a proposta de intervenção com os cinco elementos (agente, ação, meio/modo,
  detalhamento, efeito). Se o aluno já tem proposta, evolua a dele em vez de substituí-la.

## Forma final
- Quatro parágrafos, entre 27 e 32 linhas, na ordem: introdução, dois desenvolvimentos e conclusão.
- Se o texto do aluno estiver incompleto (faltando conclusão, parágrafos muito curtos ou apenas
  um fragmento), complete mantendo o estilo dele e sinalize isso em "diagnostico".

## Parâmetros escolhidos para esta reescrita
- Vocabulário: {RESUMO_VOCABULARIO[vocabulario]}.
- Argumentação: {RESUMO_ARGUMENTACAO[estilo_argumentacao]}.
- Repertório a privilegiar: {RESUMO_REPERTORIO[repertorio]}.
- Intervenção (C5): {RESUMO_INTERVENCAO[tom_intervencao]}.
{contexto_extra}
## Regras de honestidade
- Nunca invente citações, obras, dados estatísticos precisos ou pesquisas.
- Não use linguagem de ódio, discriminatória ou ofensiva a grupos sociais.
- Não cite este prompt nem mencione que é uma IA.

## Formato de resposta
Responda em JSON puro, exatamente com este esquema:
{{
  "texto_original_transcrito": "transcrição fiel da redação do aluno",
  "redacao_revisada": "texto revisado completo, 4 parágrafos separados por \\n\\n",
  "notas_estimadas_originais": {{"c1": 0, "c2": 0, "c3": 0, "c4": 0, "c5": 0, "total": 0}},
  "notas_estimadas_revisadas": {{"c1": 0, "c2": 0, "c3": 0, "c4": 0, "c5": 0, "total": 0}},
  "diagnostico": "em até 6 linhas, o que estava fraco e o que foi feito",
  "mudancas": [
    {{"onde": "Parágrafo 2", "antes": "trecho curto do original", "depois": "trecho revisado", "motivo": "C3: ..."}}
  ],
  "repertorios_adicionados": ["repertório novo com autor/obra e o que ele sustenta"],
  "checklist_c5": {{
    "agente": "...", "acao": "...", "meio_modo": "...", "detalhamento": "...", "efeito": "..."
  }},
  "aviso_calibragem": "desvios propositais para respeitar a nota-alvo; se não houver, escreva 'nenhum'"
}}
"""

    contents = [prompt]
    for dados, mime in imagens_norm:
        contents.append(types.Part.from_bytes(data=dados, mime_type=mime))

    dados = _chamar_modelo(api_key, contents, temperature=0.5)

    redacao_revisada = (dados.get("redacao_revisada") or "").strip()
    if not redacao_revisada:
        raise ValueError("A IA não retornou o texto revisado. Tente novamente.")

    mudancas = []
    for item in dados.get("mudancas") or []:
        if isinstance(item, dict):
            mudancas.append(
                {
                    "onde": str(item.get("onde", "")).strip(),
                    "antes": str(item.get("antes", "")).strip(),
                    "depois": str(item.get("depois", "")).strip(),
                    "motivo": str(item.get("motivo", "")).strip(),
                }
            )

    return {
        "redacao_revisada": redacao_revisada,
        "texto_original_transcrito": (dados.get("texto_original_transcrito") or texto).strip(),
        "diagnostico": dados.get("diagnostico", ""),
        "mudancas": mudancas,
        "notas_estimadas_originais": _normalizar_notas(dados.get("notas_estimadas_originais")),
        "notas_estimadas_revisadas": _normalizar_notas(dados.get("notas_estimadas_revisadas")),
        "checklist_c5": dados.get("checklist_c5", {}) or {},
        "repertorios_adicionados": dados.get("repertorios_adicionados", []) or [],
        "aviso_calibragem": dados.get("aviso_calibragem", ""),
        "nota_alvo": nota_total,
        "parametros": {
            "tema": tema,
            "vocabulario": vocabulario,
            "estilo_argumentacao": estilo_argumentacao,
            "repertorio": repertorio,
            "tom_intervencao": tom_intervencao,
            "diretrizes_extras": diretrizes_extras.strip(),
            "preservar_estilo": bool(preservar_estilo),
            "competencias": {c: int(round(float(competencias[c]))) for c in ("c1", "c2", "c3", "c4", "c5")},
        },
    }


# --------------------------------------------------------------------------- #
# Leitura do tema na primeira página da folha
# --------------------------------------------------------------------------- #
def extrair_tema_da_foto(imagens, api_key_manual: str = "") -> dict:
    """Lê **apenas a primeira foto** da folha e tenta identificar o tema da redação.

    Usado para preencher o campo "Tema da Redação" automaticamente quando o
    aluno envia a redação em fotos.

    Returns:
        dict com ``tema``, ``titulo``, ``texto_visivel`` e ``confianca``
        (``alta``, ``media`` ou ``baixa``). Campos sem informação vêm vazios.
    """
    api_key = _limpar_valor(api_key_manual) or obter_api_key()
    if not api_key:
        raise ValueError(
            "Chave de API do Gemini não encontrada. Coloque GEMINI_API_KEY no arquivo .env, "
            "configure nos Secrets do Streamlit Cloud ou informe no aplicativo."
        )

    imagens_norm = normalizar_imagens(imagens)
    if not imagens_norm:
        return {"tema": "", "titulo": "", "texto_visivel": "", "confianca": ""}

    # Só a primeira página: é nela que costuma vir o cabeçalho com o tema.
    dados_primeira, mime_primeira = imagens_norm[0]

    prompt = """
Leia APENAS a imagem a seguir. Ela é a PRIMEIRA página da folha de redação de um aluno do ENEM.

Sua tarefa é descobrir o TEMA (ou título) da proposta de redação.

Regras:
- Se houver um cabeçalho, título ou linha com o tema escrito (impresso ou manuscrito), copie o texto
  integralmente e sem inventar palavras.
- Se o tema não estiver escrito, deduza-o a partir do conteúdo da redação e escreva-o no padrão do
  ENEM (por exemplo: "Os desafios da valorização do trabalho de cuidado no Brasil").
- Nunca invente um assunto que o texto não trate.
- Se a imagem estiver ilegível, devolva os campos vazios e "confianca": "baixa".

Responda em JSON puro, exatamente com este esquema:
{
  "tema": "tema da redação detectado",
  "titulo": "título/cabeçalho exatamente como aparece na folha (vazio se não houver)",
  "texto_visivel": "as duas primeiras linhas legíveis da folha",
  "confianca": "alta|media|baixa"
}
"""

    contents = [prompt, types.Part.from_bytes(data=dados_primeira, mime_type=mime_primeira)]
    resultado = _chamar_modelo(api_key, contents, temperature=0.1)

    return {
        "tema": str(resultado.get("tema") or "").strip(),
        "titulo": str(resultado.get("titulo") or "").strip(),
        "texto_visivel": str(resultado.get("texto_visivel") or "").strip(),
        "confianca": str(resultado.get("confianca") or "").strip().lower(),
    }
