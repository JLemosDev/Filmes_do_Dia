import os
import random
import sqlite3
from datetime import date

import requests
from flask import (Flask, render_template_string, request, make_response,
                   session, redirect, url_for, flash)
from werkzeug.security import generate_password_hash, check_password_hash

TMDB_KEY = os.environ.get("TMDB_API_KEY", "")
BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w342"
DB = os.environ.get("DB_PATH", "filmes.db")
REGIAO = "BR"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")
_cache = {}


# ---------- banco ----------
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pw_hash TEXT NOT NULL,
            telegram_chat_id TEXT
        );
        CREATE TABLE IF NOT EXISTS lista(
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('watched','want')),
            title TEXT,
            poster_path TEXT,
            PRIMARY KEY(user_id, movie_id)
        );
        """)


# ---------- TMDB ----------
def tmdb(path, **params):
    params.update(api_key=TMDB_KEY, language="pt-BR")
    r = requests.get(f"{BASE}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def generos():
    if "generos" not in _cache:
        _cache["generos"] = tmdb("/genre/movie/list")["genres"]
    return _cache["generos"]


def onde_assistir(movie_id):
    chave = ("prov", movie_id, date.today().isoformat())
    if chave not in _cache:
        try:
            res = tmdb(f"/movie/{movie_id}/watch/providers")["results"]
            _cache[chave] = [p["provider_name"] for p in res.get(REGIAO, {}).get("flatrate", [])]
        except requests.RequestException:
            _cache[chave] = []
    return _cache[chave]


def vistos_do_usuario(user_id):
    if not user_id:
        return []
    with db() as c:
        rows = c.execute("SELECT movie_id FROM lista WHERE user_id=? AND status='watched'",
                         (user_id,)).fetchall()
    return [r["movie_id"] for r in rows]


def filmes_do_dia(user_id, ids_generos, qtd=5):
    """Mesmo dia + usuário + gêneros = mesmas indicações."""
    chave = (date.today().isoformat(), user_id, tuple(sorted(ids_generos)))
    if chave in _cache:
        return _cache[chave]

    rng = random.Random(str(chave))
    vistos = set(vistos_do_usuario(user_id))
    candidatos = {}

    # 1) similaridade: recomendações a partir de filmes que o usuário já assistiu
    if vistos:
        for sid in rng.sample(sorted(vistos), min(3, len(vistos))):
            for f in tmdb(f"/movie/{sid}/recommendations")["results"]:
                candidatos[f["id"]] = f

    # 2) complemento/fallback: filmes bem avaliados
    if len(candidatos) < qtd * 2:
        dados = tmdb(
            "/discover/movie",
            with_genres=",".join(map(str, ids_generos)),
            sort_by="vote_average.desc",
            **{"vote_count.gte": 500},
            page=rng.randint(1, 10),
        )
        for f in dados["results"]:
            candidatos.setdefault(f["id"], f)

    lista = [
        f for f in candidatos.values()
        if f.get("poster_path") and f["id"] not in vistos
        and (not ids_generos or set(ids_generos) & set(f.get("genre_ids", [])))
    ]
    lista.sort(key=lambda f: f["id"])
    rng.shuffle(lista)
    escolhidos = lista[:qtd]
    for f in escolhidos:
        f["onde"] = onde_assistir(f["id"])
    _cache[chave] = escolhidos
    return escolhidos


def limpar_cache_usuario(user_id):
    for k in [k for k in _cache if isinstance(k, tuple) and len(k) == 3 and k[1] == user_id]:
        del _cache[k]


# ---------- templates ----------
HEAD = """
<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Filmes do Dia</title>
<style>
  body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:24px}
  a{color:#f5c518} nav{margin-bottom:20px} nav a{margin-right:14px}
  button{background:#e50914;color:#fff;border:0;padding:6px 12px;border-radius:6px;cursor:pointer}
  button.sec{background:#333}
  input[type=text],input[type=password]{padding:8px;border-radius:6px;border:1px solid #444;background:#1c1c1c;color:#eee}
  label{display:inline-block;margin:4px 10px 4px 0}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:20px}
  .card{background:#1c1c1c;border-radius:10px;overflow:hidden}
  .card img{width:100%;display:block}.card .in{padding:12px}
  .nota{color:#f5c518;font-weight:bold}small{color:#aaa}
  .msg{background:#333;padding:8px 12px;border-radius:6px;margin-bottom:12px}
  form.inline{display:inline}
</style></head><body>
<nav>
  <a href="{{ url_for('index') }}">🎬 Hoje</a>
  {% if user %}
    <a href="{{ url_for('minha_lista') }}">Minha lista</a>
    <span>Olá, {{ user }}</span> <a href="{{ url_for('logout') }}">Sair</a>
  {% else %}
    <a href="{{ url_for('login') }}">Entrar</a><a href="{{ url_for('register') }}">Criar conta</a>
  {% endif %}
</nav>
{% for m in get_flashed_messages() %}<div class="msg">{{ m }}</div>{% endfor %}
"""
FOOT = "</body></html>"

CARD = """
{% macro card(f, acoes=True) %}
<div class="card">
  <img src="{{ img }}{{ f.poster_path }}" alt="{{ f.title }}">
  <div class="in">
    <b>{{ f.title }}</b><br>
    {% if f.vote_average is defined %}<span class="nota">★ {{ "%.1f"|format(f.vote_average) }}</span>
    <small>{{ (f.release_date or '')[:4] }}</small>{% endif %}
    {% if f.overview %}<p><small>{{ f.overview[:130] }}{{ "…" if f.overview|length > 130 }}</small></p>{% endif %}
    {% if f.onde is defined %}
      <p><small>📺 {{ f.onde|join(", ") if f.onde else "Sem streaming no Brasil" }}</small></p>
    {% endif %}
    {% if user and acoes %}
    <form class="inline" method="post" action="{{ url_for('marcar') }}">
      <input type="hidden" name="movie_id" value="{{ f.id }}">
      <input type="hidden" name="title" value="{{ f.title }}">
      <input type="hidden" name="poster_path" value="{{ f.poster_path }}">
      <button name="status" value="watched">Já assisti</button>
      <button class="sec" name="status" value="want">Quero ver</button>
    </form>
    {% endif %}
  </div>
</div>
{% endmacro %}
"""

PAGINA = HEAD + CARD + """
<h1>🎬 Filmes do dia — {{ hoje }}</h1>
<form method="get" style="margin-bottom:24px">
  {% for g in generos %}
    <label><input type="checkbox" name="g" value="{{ g.id }}" {{ "checked" if g.id in sel }}> {{ g.name }}</label>
  {% endfor %}
  <br><button>Atualizar indicações</button>
</form>
{% if not user %}<p><small>Entre na sua conta para receber indicações baseadas nos filmes que você já assistiu.</small></p>{% endif %}
{% if erro %}<p>{{ erro }}</p>{% endif %}
<div class="grid">{% for f in filmes %}{{ card(f) }}{% endfor %}</div>
""" + FOOT

AUTH = HEAD + """
<h1>{{ titulo }}</h1>
<form method="post">
  <p><input type="text" name="username" placeholder="Usuário" required></p>
  <p><input type="password" name="password" placeholder="Senha" required></p>
  <button>{{ titulo }}</button>
</form>
""" + FOOT

LISTA = HEAD + CARD + """
<h1>Minha lista</h1>
<h2>Quero ver</h2>
<div class="grid">
  {% for f in want %}
  <div>{{ card(f, False) }}
    <form method="post" action="{{ url_for('marcar') }}" style="margin-top:6px">
      <input type="hidden" name="movie_id" value="{{ f.id }}">
      <button name="status" value="watched">Já assisti</button>
      <button class="sec" name="status" value="remove">Remover</button>
    </form></div>
  {% else %}<p><small>Vazio.</small></p>{% endfor %}
</div>
<h2>Já assisti</h2>
<div class="grid">
  {% for f in watched %}
  <div>{{ card(f, False) }}
    <form method="post" action="{{ url_for('marcar') }}" style="margin-top:6px">
      <input type="hidden" name="movie_id" value="{{ f.id }}">
      <button class="sec" name="status" value="remove">Remover</button>
    </form></div>
  {% else %}<p><small>Vazio.</small></p>{% endfor %}
</div>
<h2>Telegram</h2>
<form method="post" action="{{ url_for('telegram') }}">
  <input type="text" name="chat_id" placeholder="Seu chat_id do Telegram" value="{{ chat_id or '' }}">
  <button>Salvar</button>
  <p><small>Fale com @userinfobot no Telegram para descobrir seu chat_id e inicie uma conversa com o bot do projeto.</small></p>
</form>
""" + FOOT


def ctx(**kw):
    return dict(user=session.get("username"), img=IMG, **kw)


def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def w(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*a, **k)
    return w


# ---------- rotas ----------
@app.route("/")
def index():
    if not TMDB_KEY:
        return "Defina a variável de ambiente TMDB_API_KEY.", 500

    sel = request.args.getlist("g", type=int)
    if not sel and "g" not in request.args:
        sel = [int(x) for x in request.cookies.get("generos", "").split(",") if x.isdigit()]

    erro, filmes, todos = None, [], []
    try:
        filmes = filmes_do_dia(session.get("user_id"), sel)
        todos = generos()
    except requests.RequestException as e:
        erro = f"Erro ao consultar o TMDB: {e}"

    resp = make_response(render_template_string(
        PAGINA, **ctx(filmes=filmes, generos=todos, sel=sel,
                      hoje=date.today().strftime("%d/%m/%Y"), erro=erro)))
    if "g" in request.args:
        resp.set_cookie("generos", ",".join(map(str, sel)), max_age=60 * 60 * 24 * 365)
    return resp


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"]
        try:
            with db() as c:
                cur = c.execute("INSERT INTO users(username, pw_hash) VALUES(?,?)",
                                (u, generate_password_hash(p)))
            session.update(user_id=cur.lastrowid, username=u)
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("Usuário já existe.")
    return render_template_string(AUTH, **ctx(titulo="Criar conta"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        with db() as c:
            row = c.execute("SELECT * FROM users WHERE username=?",
                            (request.form["username"].strip(),)).fetchone()
        if row and check_password_hash(row["pw_hash"], request.form["password"]):
            session.update(user_id=row["id"], username=row["username"])
            return redirect(url_for("index"))
        flash("Usuário ou senha inválidos.")
    return render_template_string(AUTH, **ctx(titulo="Entrar"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/marcar", methods=["POST"])
@login_required
def marcar():
    uid = session["user_id"]
    mid = int(request.form["movie_id"])
    status = request.form["status"]
    with db() as c:
        if status == "remove":
            c.execute("DELETE FROM lista WHERE user_id=? AND movie_id=?", (uid, mid))
        elif status in ("watched", "want"):
            c.execute("""INSERT INTO lista(user_id, movie_id, status, title, poster_path)
                         VALUES(?,?,?,?,?)
                         ON CONFLICT(user_id, movie_id) DO UPDATE SET status=excluded.status""",
                      (uid, mid, status, request.form.get("title"), request.form.get("poster_path")))
    limpar_cache_usuario(uid)
    return redirect(request.referrer or url_for("index"))


@app.route("/lista")
@login_required
def minha_lista():
    uid = session["user_id"]
    with db() as c:
        rows = c.execute("SELECT * FROM lista WHERE user_id=?", (uid,)).fetchall()
        chat = c.execute("SELECT telegram_chat_id FROM users WHERE id=?", (uid,)).fetchone()[0]
    conv = lambda r: {"id": r["movie_id"], "title": r["title"], "poster_path": r["poster_path"]}
    return render_template_string(LISTA, **ctx(
        want=[conv(r) for r in rows if r["status"] == "want"],
        watched=[conv(r) for r in rows if r["status"] == "watched"],
        chat_id=chat))


@app.route("/telegram", methods=["POST"])
@login_required
def telegram():
    with db() as c:
        c.execute("UPDATE users SET telegram_chat_id=? WHERE id=?",
                  (request.form["chat_id"].strip() or None, session["user_id"]))
    flash("Telegram salvo.")
    return redirect(url_for("minha_lista"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
