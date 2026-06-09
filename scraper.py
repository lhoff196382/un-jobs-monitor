#!/usr/bin/env python3
"""
Monitor de Vagas ONU - Brasil
Verifica vagas de emprego e consultoria em organismos da ONU para o Brasil.
"""

import json
import os
import hashlib
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CONFIG_FILE = "config.json"
SEEN_FILE = "seen_jobs.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
REQUEST_TIMEOUT = 30


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_seen() -> set:
    if not Path(SEEN_FILE).exists():
        return set()
    with open(SEEN_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("ids", []))


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"ids": sorted(seen), "updated": datetime.utcnow().isoformat()}, f, indent=2)


def job_id(title: str, url: str, source: str) -> str:
    raw = f"{source}|{title}|{url}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def contains_keyword(text: str, keywords: list) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [ERRO] Falha ao acessar {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Parsers específicos por site
# ---------------------------------------------------------------------------

def parse_undp(soup: BeautifulSoup, source: dict) -> list[dict]:
    jobs = []
    rows = soup.select("table tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        link = row.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if href and not href.startswith("http"):
            href = "https://jobs.undp.org/" + href.lstrip("/")
        if title:
            jobs.append({"title": title, "url": href, "source": source["name"]})
    return jobs


def parse_unicef(soup: BeautifulSoup, source: dict) -> list[dict]:
    jobs = []
    for item in soup.select("li.job-listing, div.job-listing, article.job"):
        link = item.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if href and not href.startswith("http"):
            href = "https://jobs.unicef.org" + href
        if title:
            jobs.append({"title": title, "url": href, "source": source["name"]})
    return jobs


def parse_generic(soup: BeautifulSoup, source: dict, keywords: list) -> list[dict]:
    """
    Parser genérico: coleta todos os <a> cuja âncora contenha keywords relevantes
    ou que estejam dentro de contêineres de vaga típicos.
    """
    jobs = []
    seen_hrefs = set()

    # Tenta seletores comuns de listagem de vagas
    selectors = [
        "li.job", "li.vacancy", "li.position", "li.listing",
        "div.job", "div.vacancy", "div.position",
        "tr.job", "tr.vacancy",
        "article.job", "article.vacancy",
        ".job-title a", ".vacancy-title a", ".position-title a",
    ]
    candidates = []
    for sel in selectors:
        candidates.extend(soup.select(sel))

    # Fallback: todos os links da página
    if not candidates:
        candidates = soup.find_all("a", href=True)

    for el in candidates:
        link = el if el.name == "a" else el.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or len(title) < 6:
            continue
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        if not href.startswith("http"):
            base = "/".join(source["url"].split("/")[:3])
            href = base + "/" + href.lstrip("/")
        if contains_keyword(title, keywords):
            jobs.append({"title": title, "url": href, "source": source["name"]})

    return jobs


def scrape_source(source: dict, keywords: list) -> list[dict]:
    print(f"  Verificando: {source['name']}")
    soup = fetch_page(source["url"])
    if soup is None:
        return []

    name_lower = source["name"].lower()
    if "undp" in name_lower:
        jobs = parse_undp(soup, source)
    elif "unicef" in name_lower or "un women" in name_lower:
        jobs = parse_unicef(soup, source)
    else:
        jobs = parse_generic(soup, source, keywords)

    # Filtra por keywords no título quando o parser não filtrou
    filtered = [j for j in jobs if contains_keyword(j["title"], keywords)] or jobs[:20]
    print(f"    -> {len(filtered)} vaga(s) encontrada(s)")
    return filtered


# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------

def build_html_email(new_jobs: list[dict], run_date: str) -> str:
    rows = ""
    for j in new_jobs:
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            <a href="{j['url']}" style="color:#1a73e8;font-weight:bold;">{j['title']}</a>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#555;">{j['source']}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:750px;margin:auto;">
      <h2 style="color:#004b91;">🌐 Novas Vagas ONU – Brasil</h2>
      <p>Relatório gerado em <strong>{run_date}</strong></p>
      <p>Foram encontradas <strong>{len(new_jobs)}</strong> nova(s) vaga(s) / consultoria(s):</p>
      <table width="100%" cellspacing="0" style="border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#004b91;color:#fff;">
            <th style="padding:10px;text-align:left;">Título</th>
            <th style="padding:10px;text-align:left;">Organismo</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:24px;font-size:12px;color:#999;">
        Monitoramento automático · GitHub Actions ·
        Para adicionar fontes edite <code>config.json</code> no repositório.
      </p>
    </body></html>
    """


def send_email(subject: str, html_body: str, cfg: dict) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_addr = os.environ.get("EMAIL_TO") or cfg["email"]["to"]

    if not to_addr:
        print("[AVISO] EMAIL_TO não configurado. E-mail não enviado.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_addr, msg.as_string())

    print(f"[OK] E-mail enviado para {to_addr}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"=== Monitor ONU Brasil — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ===")

    config = load_config()
    seen = load_seen()
    keywords = config.get("keywords", [])
    sources = [s for s in config["sources"] if s.get("enabled", True)]

    all_jobs: list[dict] = []
    for source in sources:
        jobs = scrape_source(source, keywords)
        all_jobs.extend(jobs)
        time.sleep(2)  # pausa educada entre requisições

    # Identifica vagas novas
    new_jobs = []
    updated_seen = set(seen)
    for job in all_jobs:
        jid = job_id(job["title"], job["url"], job["source"])
        if jid not in seen:
            job["id"] = jid
            new_jobs.append(job)
            updated_seen.add(jid)

    save_seen(updated_seen)
    print(f"\nTotal de vagas novas: {len(new_jobs)}")

    if not new_jobs:
        print("Nenhuma vaga nova encontrada. E-mail não enviado.")
        return

    run_date = datetime.now().strftime("%d/%m/%Y às %H:%M")
    prefix = config["email"]["subject_prefix"]
    subject = f"{prefix} {len(new_jobs)} nova(s) vaga(s) encontrada(s) — {run_date}"
    html = build_html_email(new_jobs, run_date)

    # Exibe no log (útil para depuração no Actions)
    print("\n--- Vagas novas ---")
    for j in new_jobs:
        print(f"  [{j['source']}] {j['title']}")
        print(f"    {j['url']}")

    try:
        send_email(subject, html, config)
    except KeyError as e:
        print(f"[AVISO] Variável de ambiente ausente: {e}. E-mail não enviado.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar e-mail: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
