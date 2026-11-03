"""Envia as indicações do dia por Telegram para quem cadastrou o chat_id.

Uso:
    export TMDB_API_KEY=...
    export TELEGRAM_BOT_TOKEN=...   # criado com o @BotFather
    python send_daily.py

Agende com cron (ex.: todo dia às 8h):
    0 8 * * * cd /caminho/projeto && python send_daily.py
"""
import os

import requests

from app import db, filmes_do_dia

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def enviar(chat_id, texto):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": texto},
        timeout=10,
    ).raise_for_status()


def main():
    if not TOKEN:
        raise SystemExit("Defina TELEGRAM_BOT_TOKEN.")
    with db() as c:
        usuarios = c.execute(
            "SELECT id, username, telegram_chat_id FROM users WHERE telegram_chat_id IS NOT NULL"
        ).fetchall()
    for u in usuarios:
        filmes = filmes_do_dia(u["id"], [])
        linhas = [f"🎬 Filmes do dia para {u['username']}:\n"]
        for f in filmes:
            onde = ", ".join(f["onde"]) if f["onde"] else "sem streaming no BR"
            linhas.append(f"• {f['title']} ({(f.get('release_date') or '')[:4]}) ★ {f['vote_average']:.1f}\n  📺 {onde}")
        try:
            enviar(u["telegram_chat_id"], "\n".join(linhas))
        except requests.RequestException as e:
            print(f"Falha ao enviar para {u['username']}: {e}")


if __name__ == "__main__":
    main()
