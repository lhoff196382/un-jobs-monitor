#!/usr/bin/env python3
"""
Interface web local para gerenciar as fontes de vagas.
Execute: python manage_web.py
Acesse:  http://localhost:5000
"""

import json
import subprocess
import sys
from pathlib import Path
from flask import Flask, request, redirect, url_for, flash

CONFIG_FILE = Path("config.json")

app = Flask(__name__)
app.secret_key = "onu-monitor-local"


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def git_push(name: str) -> str:
    try:
        subprocess.run(["git", "add", "config.json"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore: atualiza fontes via interface web — {name}"],
            check=True, capture_output=True,
        )
        subprocess.run(["git", "push"], check=True, capture_output=True)
        return "ok"
    except subprocess.CalledProcessError as e:
        return e.stderr.decode(errors="replace") if e.stderr else str(e)


HTML_BASE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor ONU Brasil — Gerenciar Fontes</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:Arial,sans-serif;background:#f4f6f9;color:#333}}
  header{{background:#004b91;color:#fff;padding:18px 32px;display:flex;align-items:center;gap:12px}}
  header h1{{font-size:1.2rem;font-weight:700}}
  header span{{font-size:.85rem;opacity:.8}}
  .container{{max-width:860px;margin:32px auto;padding:0 16px}}
  .card{{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.1);padding:24px;margin-bottom:24px}}
  h2{{font-size:1rem;color:#004b91;margin-bottom:16px;border-bottom:2px solid #e8edf2;padding-bottom:8px}}
  table{{width:100%;border-collapse:collapse;font-size:.9rem}}
  th{{background:#f0f4f8;padding:10px 12px;text-align:left;font-weight:600;color:#555}}
  td{{padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top}}
  tr:last-child td{{border:none}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:600}}
  .on{{background:#d4edda;color:#1a6b30}}
  .off{{background:#f8d7da;color:#721c24}}
  .btn{{display:inline-block;padding:6px 14px;border-radius:5px;font-size:.82rem;
        font-weight:600;text-decoration:none;border:none;cursor:pointer;line-height:1.4}}
  .btn-edit{{background:#e8f0fe;color:#1a73e8}}
  .btn-del{{background:#fce8e6;color:#c5221f}}
  .btn-add{{background:#004b91;color:#fff;padding:9px 20px;font-size:.9rem}}
  .btn-add:hover{{background:#003870}}
  form label{{display:block;font-size:.85rem;font-weight:600;margin-bottom:4px;color:#555}}
  form input,form textarea{{width:100%;padding:8px 10px;border:1px solid #ccc;border-radius:5px;
                             font-size:.9rem;margin-bottom:14px}}
  form input:focus,form textarea:focus{{outline:none;border-color:#004b91}}
  .form-row{{display:flex;gap:16px}}
  .form-row>div{{flex:1}}
  .flash{{padding:10px 16px;border-radius:5px;margin-bottom:16px;font-size:.88rem}}
  .flash.ok{{background:#d4edda;color:#1a6b30}}
  .flash.err{{background:#f8d7da;color:#721c24}}
  .hint{{font-size:.78rem;color:#888;margin-top:-10px;margin-bottom:14px}}
  .url-cell{{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .empty{{color:#999;text-align:center;padding:20px;font-size:.9rem}}
</style>
</head>
<body>
<header>
  <div>
    <h1>Monitor ONU Brasil</h1>
    <span>Gerenciador de fontes de vagas</span>
  </div>
</header>
<div class="container">
{flash_html}
{content}
</div>
</body></html>"""


def render(content: str, messages: list = None) -> str:
    flash_html = ""
    if messages:
        for msg, kind in messages:
            flash_html += f'<div class="flash {kind}">{msg}</div>'
    return HTML_BASE.format(content=content, flash_html=flash_html)


@app.route("/")
def index():
    config = load_config()
    sources = config.get("custom_sources", [])

    rows = ""
    for i, s in enumerate(sources):
        status = '<span class="badge on">Ativo</span>' if s.get("enabled", True) else '<span class="badge off">Inativo</span>'
        kw = ", ".join(s.get("keywords", [])) or "<em style='color:#aaa'>globais</em>"
        rows += f"""
        <tr>
          <td><strong>{s['name']}</strong></td>
          <td class="url-cell"><a href="{s['url']}" target="_blank" title="{s['url']}">{s['url']}</a></td>
          <td>{kw}</td>
          <td>{status}</td>
          <td style="white-space:nowrap">
            <a class="btn btn-edit" href="/edit/{i}">Editar</a>
            &nbsp;
            <form method="post" action="/delete/{i}" style="display:inline"
                  onsubmit="return confirm('Remover esta fonte?')">
              <button class="btn btn-del" type="submit">Remover</button>
            </form>
          </td>
        </tr>"""

    table = f"""
      <table>
        <thead><tr>
          <th>Nome</th><th>URL</th><th>Keywords</th><th>Status</th><th>Ações</th>
        </tr></thead>
        <tbody>{rows if rows else '<tr><td colspan="5" class="empty">Nenhuma fonte cadastrada ainda.</td></tr>'}</tbody>
      </table>"""

    content = f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2 style="border:none;margin:0">Fontes customizadas ({len(sources)})</h2>
      <a class="btn btn-add" href="/add">+ Adicionar fonte</a>
    </div>
    <div class="card">{table}</div>
    <p style="font-size:.8rem;color:#999;text-align:center">
      Após salvar, clique em <strong>Sincronizar com GitHub</strong> para aplicar nas próximas varreduras.
    </p>
    <div style="text-align:center;margin-top:12px">
      <form method="post" action="/sync">
        <button class="btn btn-add" type="submit">Sincronizar com GitHub</button>
      </form>
    </div>"""

    return render(content)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        url  = request.form.get("url",  "").strip()
        kw   = request.form.get("keywords", "").strip()
        notes = request.form.get("notes", "").strip()
        enabled = request.form.get("enabled") == "on"

        if not name or not url:
            return render(add_form(), [("Nome e URL são obrigatórios.", "err")])
        if not url.startswith("http"):
            return render(add_form(), [("URL deve começar com http:// ou https://", "err")])

        config = load_config()
        urls_existentes = [s["url"] for s in config.get("custom_sources", [])]
        if url in urls_existentes:
            return render(add_form(), [("Esta URL já está cadastrada.", "err")])

        kw_list = [k.strip() for k in kw.split(",") if k.strip()]
        config.setdefault("custom_sources", []).append({
            "name": name, "url": url, "enabled": enabled,
            "notes": notes, "keywords": kw_list,
        })
        # Remove exemplo padrão
        config["custom_sources"] = [
            s for s in config["custom_sources"]
            if "Remova ou substitua" not in s.get("name", "")
        ]
        save_config(config)
        return redirect(url_for("index") + "?msg=add")

    return render(add_form())


def add_form(data: dict = None, idx: int = None) -> str:
    d = data or {}
    action = f"/edit/{idx}" if idx is not None else "/add"
    title  = "Editar fonte" if idx is not None else "Adicionar nova fonte"
    checked = "checked" if d.get("enabled", True) else ""
    return f"""
    <div class="card">
      <h2>{title}</h2>
      <form method="post" action="{action}">
        <label>Nome do site ou organismo *</label>
        <input name="name" value="{d.get('name','')}" placeholder="Ex: IBGE Consultores" required>

        <label>URL da página de vagas *</label>
        <input name="url" type="url" value="{d.get('url','')}" placeholder="https://..." required>

        <label>Palavras-chave específicas <em style="font-weight:400">(separadas por vírgula)</em></label>
        <input name="keywords" value="{', '.join(d.get('keywords', []))}"
               placeholder="consultor, contrato, brasil">
        <p class="hint">Deixe em branco para usar as palavras-chave globais do config.json</p>

        <label>Observações</label>
        <input name="notes" value="{d.get('notes','')}">

        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:18px">
          <input type="checkbox" name="enabled" {checked} style="width:auto;margin:0">
          Fonte ativa
        </label>

        <div style="display:flex;gap:12px">
          <button class="btn btn-add" type="submit">Salvar</button>
          <a class="btn" href="/" style="background:#eee;color:#333">Cancelar</a>
        </div>
      </form>
    </div>"""


@app.route("/edit/<int:idx>", methods=["GET", "POST"])
def edit(idx: int):
    config = load_config()
    sources = config.get("custom_sources", [])
    if idx >= len(sources):
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        url  = request.form.get("url",  "").strip()
        kw   = request.form.get("keywords", "").strip()
        notes = request.form.get("notes", "").strip()
        enabled = request.form.get("enabled") == "on"

        if not name or not url:
            return render(add_form(sources[idx], idx), [("Nome e URL são obrigatórios.", "err")])

        kw_list = [k.strip() for k in kw.split(",") if k.strip()]
        sources[idx] = {"name": name, "url": url, "enabled": enabled,
                        "notes": notes, "keywords": kw_list}
        config["custom_sources"] = sources
        save_config(config)
        return redirect(url_for("index"))

    return render(add_form(sources[idx], idx))


@app.route("/delete/<int:idx>", methods=["POST"])
def delete(idx: int):
    config = load_config()
    sources = config.get("custom_sources", [])
    if idx < len(sources):
        sources.pop(idx)
        config["custom_sources"] = sources
        save_config(config)
    return redirect(url_for("index"))


@app.route("/sync", methods=["POST"])
def sync():
    config = load_config()
    result = git_push("interface web")
    if result == "ok":
        msgs = [("Sincronizado com GitHub com sucesso! As mudanças entrarão na próxima varredura.", "ok")]
    else:
        msgs = [(f"Erro ao sincronizar: {result[:200]}", "err")]
    return render(index_content(config), msgs)


def index_content(config):
    return redirect(url_for("index"))


if __name__ == "__main__":
    print("=" * 52)
    print("  Monitor ONU Brasil — Interface de Gerenciamento")
    print("  Acesse: http://localhost:5000")
    print("  Para encerrar: Ctrl+C")
    print("=" * 52)
    app.run(debug=False, port=5000)
