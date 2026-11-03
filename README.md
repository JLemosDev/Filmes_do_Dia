# Filmes do Dia

Web app em Python (Flask) integrado à API do TMDB que indica 5 filmes por dia.

## Funcionalidades

- Indicações diárias (mudam todo dia, ficam fixas durante o dia)
- Filtro por gênero
- Login e cadastro (SQLite)
- Marcar filmes como "Já assisti" / "Quero ver"
- Recomendação por similaridade: usa `/movie/{id}/recommendations` a partir dos filmes já assistidos e nunca repete os vistos
- Onde assistir (streaming no Brasil) em cada filme
- Envio diário por Telegram

## Como rodar

1. Gere uma API key em https://www.themoviedb.org (Configurações → API).
2. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```
3. Defina as variáveis e execute:
   ```
   # Linux/Mac
   export TMDB_API_KEY=sua_chave
   export SECRET_KEY=uma_string_aleatoria
   # Windows (PowerShell)
   $env:TMDB_API_KEY="sua_chave"
   $env:SECRET_KEY="uma_string_aleatoria"

   python app.py
   ```
4. Abra http://127.0.0.1:5000, crie uma conta e marque alguns filmes como assistidos.

## Telegram

1. Crie um bot com o @BotFather e copie o token.
2. Descubra seu `chat_id` com o @userinfobot e envie uma mensagem ao seu bot.
3. Salve o `chat_id` em "Minha lista" no app.
4. Rode o envio:
   ```
   export TELEGRAM_BOT_TOKEN=seu_token
   python send_daily.py
   ```
5. Agende com cron (todo dia às 8h): `0 8 * * * cd /caminho/projeto && python send_daily.py`

## Estrutura

- `app.py`: app Flask, banco SQLite e integração com o TMDB
- `send_daily.py`: envio diário por Telegram
- `filmes.db`: criado automaticamente na primeira execução
