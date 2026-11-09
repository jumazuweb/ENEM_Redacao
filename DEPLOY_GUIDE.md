# 🚀 Guia Completo de Execução e Deploy Gratuito

Este guia orienta a execução do **Corretor ENEM Pro** no VS Code e a publicação do aplicativo no **Streamlit Community Cloud** (100% gratuito) para acesso remoto.

---

## 💻 1. Rodando no VS Code

1. Abra a pasta descompactada no **VS Code**.
2. Abra o terminal integrado (`Ctrl + ~`) e crie o ambiente virtual:
   ```bash
   python -m venv venv
   ```
3. Ative o ambiente virtual:
   - **Windows:** `venv\Scripts\activate`
   - **Linux/Mac:** `source venv/bin/activate`
4. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
5. Inicie a aplicação localmente:
   ```bash
   streamlit run app.py
   ```

---

## 🐙 2. Passo a Passo: Enviar para o GitHub

1. Acesse o [GitHub](https://github.com/) e crie um novo repositório (ex: `corretor-redacao-enem`).
2. No terminal do VS Code, na pasta do projeto, execute em ordem:
   ```bash
   git init
   git add .
   git commit -m "Versão inicial do aplicativo Corretor ENEM"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/NOME_DO_REPOSITORIO.git
   git push -u origin main
   ```
   *(Substitua `SEU_USUARIO` e `NOME_DO_REPOSITORIO` pelos seus dados reais do GitHub).*

---

## 🌐 3. Deploy Gratuito no Streamlit Community Cloud

O **Streamlit Community Cloud** é a hospedagem ideal, gratuita e nativa para apps Streamlit.

1. Acesse [share.streamlit.io](https://share.streamlit.io/) e faça login usando sua conta do **GitHub**.
2. Clique no botão **"New app"** (Novo aplicativo).
3. Preencha as configurações:
   - **Repository:** Escolha o repositório `corretor-redacao-enem`.
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. **Configuração da API Key (Importante):**
   - Clique em **"Advanced settings..."** (Configurações Avançadas).
   - Na seção **Secrets**, insira a chave da API do Gemini:
     ```toml
     GEMINI_API_KEY = "SUA_CHAVE_GEMINI_AQUI"
     ```
5. Clique em **"Deploy!"**.

Após o processamento (1 a 2 minutos), um link público será gerado (ex: `https://corretor-enem.streamlit.app`). Você poderá compartilhar esse link com sua filha para que ela utilize a plataforma de qualquer navegador ou dispositivo!
