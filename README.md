# 📝 Corretor ENEM Pro

Plataforma em **Streamlit** para avaliação de redações no modelo oficial do ENEM, com correção por
Inteligência Artificial (Google Gemini), diagnóstico detalhado por competência e simulador de redações.

> Projeto pessoal de estudo: envia a redação (texto, arquivo ou fotos da folha), recebe nota de 0 a 1000
> nas 5 competências, comentários e sugestões de melhoria — e acompanha a evolução ao longo do tempo.

---

## ✨ Funcionalidades

- **Nova Avaliação**
  - Entrada por **texto digitado**, **arquivo** (`.docx`, `.txt`, `.pdf`) ou **fotos da folha**
    (upload múltiplo ou câmera do celular).
  - Leitura automática do **tema** a partir da 1ª página fotografada.
  - Suporte a redações de **várias folhas** (as fotos são avaliadas juntas, em ordem).
- **Diagnóstico & Correções**
  - Nota por competência (C1 a C5), nota final e comentários do corretor de IA.
  - Destaque de trechos problemáticos e sugestões de reescrita.
- **Simulador & Redação Modelo**
  - **Ajustar a minha redação**: a IA reescreve a redação do aluno preservando as ideias originais.
  - **Gerar redação nova**: redação calibrada por nota-alvo (0–200 em cada competência), com
    personalização de vocabulário, estilo argumentativo, repertório sociocultural e tom da proposta
    de intervenção.
  - Download do resultado em **`.docx`** (formatado em normas ABNT/ENEM), **`.doc`** e **`.txt`**.
- **Histórico e Evolução**
  - Persistência em SQLite e gráficos de evolução das notas.

---

## 🧱 Tecnologias

| Camada | Tecnologia |
|---|---|
| Interface | Streamlit |
| IA | Google Gemini (`google-genai`) |
| Banco de dados | SQLite + SQLAlchemy |
| Leitura de arquivos | `pypdf`, `python-docx` |
| Imagens | Pillow |
| Gráficos | Plotly, pandas |

---

## 📂 Estrutura do projeto

```
.
├── app.py                     # Roteador principal (4 abas)
├── database/
│   └── models.py              # Modelos SQLAlchemy + init_db()
├── services/
│   ├── ai_evaluator.py        # Correção, geração e reescrita via Gemini
│   ├── parser_service.py      # Extração de texto (.docx/.txt/.pdf) e MIME
│   └── documento_service.py   # Exportação .docx / .doc / .txt
├── views/
│   └── simulador.py           # Aba do simulador (2 sub-abas)
├── data/                      # Banco SQLite local (não versionado)
├── requirements.txt
├── DEPLOY_GUIDE.md            # Guia de deploy no Streamlit Community Cloud
└── .env.example               # Modelo das variáveis de ambiente
```

---

## 🚀 Como rodar localmente

### 1. Clone o repositório

```bash
git clone https://github.com/jumazuweb/ENEM_Redacao.git
cd ENEM_Redacao
```

### 2. Crie e ative o ambiente virtual

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure a chave da API

Copie o arquivo de exemplo e preencha com a sua chave do
[Google AI Studio](https://aistudio.google.com/apikey):

```bash
# Windows
copy .env.example .env
# Linux / macOS
cp .env.example .env
```

Conteúdo do `.env`:

```dotenv
GEMINI_API_KEY=sua_chave_aqui
GEMINI_MODEL=gemini-3.1-flash-lite
```

> 🔒 O arquivo `.env` está no `.gitignore` e **nunca** deve ser enviado ao GitHub.

Alternativa: use `./.streamlit/secrets.toml` com `GEMINI_API_KEY = "sua_chave"` (também ignorado).

### 5. Execute o app

```bash
streamlit run app.py
```

O navegador abre em `http://localhost:8501`.

Para usar outra porta (caso a 8501 esteja ocupada):

```bash
streamlit run app.py --server.port 8502
```

---

## ☁️ Deploy

O passo a passo completo para publicar gratuitamente no **Streamlit Community Cloud** está em
[`DEPLOY_GUIDE.md`](DEPLOY_GUIDE.md). Resumo:

1. Faça login em [share.streamlit.io](https://share.streamlit.io/) com a conta do GitHub.
2. **New app** → repositório `ENEM_Redacao`, branch `main`, arquivo `app.py`.
3. Em **Advanced settings → Secrets**, adicione:
   ```toml
   GEMINI_API_KEY = "sua_chave_aqui"
   ```
4. **Deploy**.

---

## 🗄️ Banco de dados

O banco fica em `data/redacoes.db` (SQLite) e é criado automaticamente no primeiro uso —
a pasta `data/` é versionada via `.gitkeep`, mas o arquivo `.db` não.

Para começar do zero, basta apagar `data/redacoes.db`.

---

## 🔧 Scripts de diagnóstico

Na raiz existem três utilitários para checar a configuração da IA:

| Script | O que faz | Efeito colateral |
|---|---|---|
| `_diag_env.py` | Grava/atualiza `GEMINI_MODEL` no `.env` e imprime apenas os **nomes** das variáveis (nunca os valores) | ⚠️ **Altera o `.env`** — o modelo é forçado para o valor fixo no script |
| `_diag_api.py` | Executa uma avaliação real e uma geração de redação com a chave do `.env`, mostrando notas e contagens | ⚠️ **Consome tokens** da API do Gemini |
| `_diag_modelos.py` | Lista os modelos com `flash` no nome disponíveis para a sua chave | Apenas leitura |

```bash
python _diag_modelos.py      # seguro: só lista modelos
python _diag_api.py          # cuidado: faz 2 chamadas reais
python _diag_env.py          # cuidado: reescreve o GEMINI_MODEL no .env
```

---

## ⚠️ Avisos

- As notas são **estimativas geradas por IA** e não substituem a correção de um professor.
- O uso da API do Gemini está sujeito aos limites e à política de preços do Google.
