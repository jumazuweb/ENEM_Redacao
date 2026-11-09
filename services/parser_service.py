import io
import os

from docx import Document
from pypdf import PdfReader
from PIL import Image

MIMES_POR_EXTENSAO = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
}


def detectar_mime(nome_arquivo: str, dados: bytes) -> str:
    """Descobre o tipo real da imagem a partir da extensão e dos primeiros bytes."""
    extensao = os.path.splitext(nome_arquivo or "")[1].lower()
    if extensao in MIMES_POR_EXTENSAO:
        return MIMES_POR_EXTENSAO[extensao]

    if dados[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def extrair_texto_arquivo(uploaded_file):
    if uploaded_file is None:
        return ""
    
    filename = uploaded_file.name.lower()
    
    if filename.endswith(".txt"):
        return uploaded_file.getvalue().decode("utf-8")
    
    elif filename.endswith(".docx"):
        doc = Document(io.BytesIO(uploaded_file.getvalue()))
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    
    elif filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
        texto = ""
        for page in reader.pages:
            texto += (page.extract_text() or "") + "\n"
        return texto.strip()
        
    elif filename.endswith((".png", ".jpg", ".jpeg")):
        return "[IMAGEM_ENVIADA]"
        
    return ""
