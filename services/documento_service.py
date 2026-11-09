"""Exportação das redações em documentos do Word.

Duas saídas são oferecidas ao usuário:

- ``gerar_docx_redacao``: documento nativo ``.docx`` montado com python-docx,
  já formatado (Times New Roman 12, espaçamento 1,5, texto justificado,
  recuo de primeira linha e margens ABNT 3/2/3/2 cm).
- ``gerar_doc_redacao``: mesmo conteúdo no formato antigo ``.doc``, gerado como
  HTML no dialeto do Word — formato que o Word abre, formata e salva normalmente,
  servindo para quem precisa dessa extensão.

Nenhuma das funções grava arquivos em disco: ambas devolvem ``bytes`` prontos
para o ``st.download_button``.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Iterable, Sequence

FONTE = "Times New Roman"
TAMANHO_FONTE = 12
TAMANHO_TITULO = 14
FATOR_ESPACAMENTO = 1.5
RECUO_PRIMEIRA_LINHA_CM = 1.25
MARGENS_CM = {"top": 3.0, "bottom": 2.0, "left": 3.0, "right": 2.0}


def _paragrafos(texto: str) -> list[str]:
    """Quebra o texto em parágrafos, ignorando linhas em branco."""
    linhas = (texto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return [linha.strip() for linha in linhas if linha.strip()]


def _normalizar_observacoes(observacoes: Iterable[str] | None) -> list[str]:
    if not observacoes:
        return []
    return [str(item).strip() for item in observacoes if str(item).strip()]


def gerar_docx_redacao(
    texto: str,
    tema: str = "",
    titulo: str = "Redação ENEM",
    subtitulo: str = "",
    observacoes: Sequence[str] | None = None,
) -> bytes:
    """Monta um ``.docx`` formatado e devolve os bytes do arquivo."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    doc = Document()

    for secao in doc.sections:
        secao.top_margin = Cm(MARGENS_CM["top"])
        secao.bottom_margin = Cm(MARGENS_CM["bottom"])
        secao.left_margin = Cm(MARGENS_CM["left"])
        secao.right_margin = Cm(MARGENS_CM["right"])

    estilo = doc.styles["Normal"]
    estilo.font.name = FONTE
    estilo.font.size = Pt(TAMANHO_FONTE)
    try:  # garante a mesma fonte em alfabetos não latinos
        estilo.element.rPr.rFonts.set(qn("w:eastAsia"), FONTE)
    except AttributeError:
        pass

    formato = estilo.paragraph_format
    formato.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    formato.space_before = Pt(0)
    formato.space_after = Pt(6)

    def adicionar(
        conteudo: str,
        *,
        negrito: bool = False,
        italico: bool = False,
        tamanho: int | None = None,
        alinhamento=None,
        recuo: bool = False,
    ):
        paragrafo = doc.add_paragraph()
        if alinhamento is not None:
            paragrafo.alignment = alinhamento
        if recuo:
            paragrafo.paragraph_format.first_line_indent = Cm(RECUO_PRIMEIRA_LINHA_CM)
        run = paragrafo.add_run(conteudo)
        run.bold = negrito
        run.italic = italico
        run.font.name = FONTE
        if tamanho:
            run.font.size = Pt(tamanho)
        return paragrafo

    adicionar(titulo, negrito=True, tamanho=TAMANHO_TITULO, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)
    if tema.strip():
        adicionar(f"Tema: {tema.strip()}", negrito=True, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)
    if subtitulo.strip():
        adicionar(subtitulo.strip(), italico=True, tamanho=11, alinhamento=WD_ALIGN_PARAGRAPH.CENTER)

    for paragrafo in _paragrafos(texto):
        adicionar(paragrafo, alinhamento=WD_ALIGN_PARAGRAPH.JUSTIFY, recuo=True)

    itens = _normalizar_observacoes(observacoes)
    if itens:
        adicionar("Notas do simulador", negrito=True, tamanho=11)
        for item in itens:
            documento_item = doc.add_paragraph(item, style="List Bullet")
            documento_item.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in documento_item.runs:
                run.font.name = FONTE
                run.font.size = Pt(10)

    from io import BytesIO

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def gerar_doc_redacao(
    texto: str,
    tema: str = "",
    titulo: str = "Redação ENEM",
    subtitulo: str = "",
    observacoes: Sequence[str] | None = None,
) -> bytes:
    """Monta um arquivo ``.doc`` (HTML no dialeto do Word) e devolve os bytes."""
    partes = [f"<h1>{escape(titulo)}</h1>"]

    if tema.strip():
        partes.append(f'<p class="tema"><b>Tema:</b> {escape(tema.strip())}</p>')
    if subtitulo.strip():
        partes.append(f'<p class="subtitulo">{escape(subtitulo.strip())}</p>')

    for paragrafo in _paragrafos(texto):
        partes.append(f"<p>{escape(paragrafo)}</p>")

    itens = _normalizar_observacoes(observacoes)
    if itens:
        partes.append('<p class="titulo-secao"><b>Notas do simulador</b></p>')
        partes.extend(f'<p class="item">&#8226; {escape(item)}</p>' for item in itens)

    html = f"""<html xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:w="urn:schemas-microsoft-com:office:word"
xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8">
<title>{escape(titulo)}</title>
<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View>
<w:Zoom>100</w:Zoom><w:DoNotOptimizeForBrowser/></w:WordDocument></xml><![endif]-->
<style>
@page WordSection1 {{ size: 21.0cm 29.7cm; margin: 3.0cm 2.0cm 2.0cm 3.0cm; }}
div.WordSection1 {{ page: WordSection1; }}
body {{ font-family: 'Times New Roman', serif; font-size: {TAMANHO_FONTE}pt; }}
h1 {{ font-size: {TAMANHO_TITULO}pt; text-align: center; margin: 0 0 12pt 0; }}
p {{ text-align: justify; text-indent: {RECUO_PRIMEIRA_LINHA_CM}cm;
     line-height: {int(FATOR_ESPACAMENTO * 100)}%; margin: 0 0 6pt 0; }}
p.tema, p.subtitulo {{ text-align: center; text-indent: 0; }}
p.subtitulo {{ font-style: italic; font-size: 11pt; }}
p.titulo-secao {{ text-indent: 0; margin-top: 18pt; }}
p.item {{ text-indent: 0; font-size: 10pt; text-align: left; }}
</style>
</head>
<body>
<div class="WordSection1">
{chr(10).join(partes)}
</div>
</body>
</html>
"""

    # BOM (EF BB BF) ajuda o Word a reconhecer o arquivo como UTF-8.
    return b"\xef\xbb\xbf" + html.encode("utf-8")


def subtitulo_padrao(nota_alvo: int | None = None) -> str:
    """Linha de contexto exibida abaixo do tema (data e nota-alvo)."""
    partes = [f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
    if nota_alvo:
        partes.append(f"nota-alvo {nota_alvo}/1000")
    return " — ".join(partes)
