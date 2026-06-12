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
from datetime import datetime, timezone
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


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


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
        json.dump({"ids": sorted(seen), "updated": now_utc().isoformat()}, f, indent=2)


def job_id(title: str, url: str, source: str) -> str:
    raw = f"{source}|{title}|{url}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def contains_keyword(text: str, keywords: list) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def fetch_html(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [ERRO] Falha ao acessar {url}: {e}")
        return None


BRAZIL_TERMS = [
    "brazil", "brasil", "brasilia", "brasília", "br ",
    "são paulo", "sao paulo", "rio de janeiro", "recife",
    "salvador", "fortaleza", "manaus", "belo horizonte",
    "curitiba", "porto alegre", "belém", "belem", "goiânia",
    "goiania", "natal", "maceió", "maceio", "teresina",
    "campo grande", "joão pessoa", "joao pessoa", "aracaju",
    "rondônia", "rondonia", "remote (brazil", "remoto (brazil",
    "work from brazil", "home-based (brazil",
]


def _is_brazil(location: str) -> bool:
    loc = location.lower()
    return any(x in loc for x in BRAZIL_TERMS)


# ---------------------------------------------------------------------------
# Fontes fixas — URL já filtra por Brasil, sem filtro de keyword
# ---------------------------------------------------------------------------

def fetch_reliefweb(_keywords: list) -> list[dict]:
    print("  Verificando: ReliefWeb API (Brasil)")
    url = "https://api.reliefweb.int/v1/jobs?appname=un-jobs-monitor"
    payload = {
        "filter": {
            "operator": "AND",
            "conditions": [{"field": "country.name", "value": "Brazil"}]
        },
        "fields": {"include": ["title", "url", "source.name", "city.name", "country.name"]},
        "limit": 50,
        "sort": ["date.created:desc"]
    }
    try:
        resp = requests.post(url, json=payload,
                             headers={**HEADERS, "Content-Type": "application/json"},
                             timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data.get("data", []):
            fields = item.get("fields", {})
            title = fields.get("title", "")
            job_url = fields.get("url", "")
            source_name = fields.get("source", [{}])[0].get("name", "ReliefWeb")
            city = fields.get("city", [{}])[0].get("name", "") if fields.get("city") else ""
            country = fields.get("country", [{}])[0].get("name", "Brazil") if fields.get("country") else "Brazil"
            location = city if city else country
            if title:
                jobs.append({"title": title, "url": job_url,
                             "source": f"ReliefWeb / {source_name}", "location": location})
        print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
        return jobs
    except Exception as e:
        print(f"  [ERRO] ReliefWeb API: {e}")
        return []


def fetch_unjobs_org(_keywords: list) -> list[dict]:
    print("  Verificando: UNJobs.org (agregador ONU)")
    try:
        resp = requests.get("https://unjobs.org/duty_stations/brazil",
                            headers=HEADERS, timeout=60)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [ERRO] UNJobs.org: {e}")
        return []
    if not soup:
        return []
    jobs = []
    for tag in soup.select("div.j, li.j, .job-title, h3 a, h2 a"):
        link = tag if tag.name == "a" else tag.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or len(title) < 6:
            continue
        if not href.startswith("http"):
            href = "https://unjobs.org" + href
        location = "Brazil"
        parent = link.parent
        if parent:
            loc_tag = parent.find(class_=lambda c: c and any(
                x in c for x in ["location", "duty", "city", "place"]))
            if loc_tag:
                location = loc_tag.get_text(strip=True)
            elif "," in title:
                parts = title.rsplit(",", 1)
                if len(parts) == 2 and len(parts[1].strip()) < 40:
                    location = parts[1].strip()
        jobs.append({"title": title, "url": href, "source": "UNJobs.org", "location": location})
    print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
    return jobs


def fetch_undp(_keywords: list) -> list[dict]:
    print("  Verificando: UNDP Jobs (Brasil)")
    soup = fetch_html(
        "https://jobs.undp.org/cj_view_jobs.cfm?curPage=1&f_job_type=0&f_date_submitted=0&f_country=105"
    )
    if not soup:
        return []
    jobs = []
    for row in soup.select("table tr"):
        link = row.find("a", href=True)
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link["href"]
        if not href.startswith("http"):
            href = "https://jobs.undp.org/" + href.lstrip("/")
        if title and len(title) > 6:
            cells = row.find_all("td")
            location = cells[1].get_text(strip=True) if len(cells) > 1 else "Brazil"
            jobs.append({"title": title, "url": href, "source": "UNDP", "location": location})
    print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
    return jobs


# ---------------------------------------------------------------------------
# Parsers específicos para fontes conhecidas
# ---------------------------------------------------------------------------

def fetch_onu_brasil(_keywords: list) -> list[dict]:
    """ONU Brasil — API JSON do site brasil.un.org (somente vagas abertas)."""
    print("  Verificando: ONU Brasil (brasil.un.org)")
    # Tenta endpoint JSON do Drupal Views
    endpoints = [
        "https://brasil.un.org/pt-br/jobs?_format=json",
        "https://brasil.un.org/en/jobs?_format=json",
    ]
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                data = resp.json()
                jobs = []
                items = data if isinstance(data, list) else data.get("rows", data.get("data", []))
                for item in items:
                    title = item.get("title", item.get("name", ""))
                    url = item.get("url", item.get("link", item.get("path", "")))
                    deadline = item.get("field_deadline", item.get("deadline", ""))
                    if not title:
                        continue
                    if not url.startswith("http"):
                        url = "https://brasil.un.org" + url
                    jobs.append({"title": title, "url": url, "source": "ONU Brasil", "location": "Brazil", "deadline": deadline})
                print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
                return jobs
        except Exception:
            pass

    # Fallback: scraping HTML
    soup = fetch_html("https://brasil.un.org/pt-br/jobs")
    if not soup:
        print("    -> 0 vaga(s) encontrada(s)")
        return []

    # Termos que indicam links de navegação (não são vagas)
    NAV_BLOCKLIST = [
        "português", "english", "español", "ver todos", "saiba mais",
        "leia mais", "read more", "see all", "apply now", "login",
        "cadastre", "home", "menu", "contato", "sobre",
    ]

    jobs = []
    seen_hrefs: set[str] = set()

    for link in soup.find_all("a", href=True):
        href  = link["href"]
        title = link.get_text(strip=True)

        # Descarta títulos curtos ou de navegação
        if not title or len(title) < 15:
            continue
        if any(b in title.lower() for b in NAV_BLOCKLIST):
            continue
        if href in seen_hrefs:
            continue
        # Aceita somente links que parecem vagas
        if not any(x in href for x in ["/job", "/vacancy", "/vaga", "/oportunidade", "/node/"]):
            continue

        seen_hrefs.add(href)
        if not href.startswith("http"):
            href = "https://brasil.un.org" + href
        jobs.append({"title": title, "url": href, "source": "ONU Brasil", "location": "Brazil"})

    print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
    return jobs


def fetch_iadb(_keywords: list) -> list[dict]:
    """BID/IADB — vagas no Brasil via API Workday e fallbacks."""
    print("  Verificando: BID/IADB (todas as vagas no Brasil)")

    jobs: list[dict] = []

    # 1) API Workday — padrão usado pelo BID/IADB
    workday_bases = [
        "https://idb.wd1.myworkdayjobs.com",
        "https://idbinvest.wd1.myworkdayjobs.com",
    ]
    for base in workday_bases:
        try:
            api_url = f"{base}/wday/cxs/idb/IDB_External_Careers/jobs"
            payload = {
                "appliedFacets": {"locations": ["Brazil"]},
                "limit": 50, "offset": 0, "searchText": ""
            }
            resp = requests.post(api_url, json=payload,
                                 headers={**HEADERS, "Content-Type": "application/json"},
                                 timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobPostings", []):
                    title    = item.get("title", "")
                    path     = item.get("externalPath", "")
                    location = item.get("locationsText", "Brazil")
                    if title and path:
                        href = base + path
                        if _is_brazil(location):
                            jobs.append({"title": title, "url": href,
                                         "source": "BID/IADB", "location": location})
                if jobs:
                    print(f"    -> {len(jobs)} vaga(s) encontrada(s) [Workday API]")
                    return jobs
        except Exception:
            pass

    # 2) Scraping HTML — jobs.iadb.org (sistema PageUp)
    pageup_urls = [
        "https://jobs.iadb.org/go/All-Jobs/9638000/?q=brazil",
        "https://jobs.iadb.org/go/All-Jobs/9638000/?q=Brasil",
        "https://jobs.iadb.org/go/All-Jobs/9638000/",
    ]
    for url in pageup_urls:
        soup = fetch_html(url)
        if not soup:
            continue
        seen: set[str] = set()
        # Seletores típicos do PageUp ATS
        for link in soup.select("a.job-title, a.position-title, h2 a, h3 a, "
                                ".job-list-item a, td.job-title a, "
                                "a[href*='/job/'], a[href*='/go/']"):
            title = link.get_text(strip=True)
            href  = link.get("href", "")
            if not title or len(title) < 8 or href in seen:
                continue
            # Ignora links de navegação
            if any(x in href.lower() for x in ["login", "register", "profile", "search", "#"]):
                continue
            seen.add(href)
            # Tenta extrair localização do elemento pai
            parent = link.find_parent(["li", "tr", "div", "article"])
            location = ""
            if parent:
                loc_tag = parent.find(class_=lambda c: c and any(
                    x in (c.lower() if c else "") for x in ["location", "city", "country", "local"]))
                if loc_tag:
                    location = loc_tag.get_text(strip=True)
                else:
                    # Tenta achar texto com vírgula que parece cidade/país
                    text = parent.get_text(" ", strip=True)
                    for part in text.split("|"):
                        part = part.strip()
                        if "," in part and len(part) < 50:
                            location = part
                            break
            if not href.startswith("http"):
                href = "https://jobs.iadb.org" + href
            # Inclui se Brasil confirmado ou localização não determinada
            if not location or _is_brazil(location):
                jobs.append({"title": title, "url": href, "source": "BID/IADB",
                             "location": location or "Brazil"})
        if jobs:
            print(f"    -> {len(jobs)} vaga(s) encontrada(s) [PageUp HTML]")
            return jobs

    # Site bloqueia scraper — link direto para consulta manual
    print("    -> BID bloqueia scraper. Incluindo link direto no e-mail.")
    return [{
        "title": "BID/IADB — Ver todas as vagas (filtre por Brazil na busca)",
        "url": "https://jobs.iadb.org/go/All-Jobs/9638000/",
        "source": "BID/IADB",
        "location": "Brazil",
        "_manual": True,
    }]


UNTALENT_BRAZIL_TERMS = BRAZIL_TERMS  # reutiliza lista centralizada


def fetch_untalent(keywords: list) -> list[dict]:
    """UNTalent.org — somente vagas no Brasil, filtradas por keywords da fonte."""
    print("  Verificando: UNTalent.org (Brasil / Consultant / Senior)")

    def extract_location_from_title(title: str) -> str:
        """Extrai localização quando está no título: 'Cargo - Cidade, País'."""
        if " - " in title:
            last_part = title.rsplit(" - ", 1)[-1]
            if "," in last_part:
                return last_part.strip()
        return ""

    def is_brazil_location(location: str) -> bool:
        return any(t in location.lower() for t in UNTALENT_BRAZIL_TERMS)

    def passes_filter(title: str, location: str) -> bool:
        # Rejeita títulos genéricos (muito curtos ou palavra única)
        if len(title) < 20 or " " not in title.strip():
            return False
        # Determina localização: campo location > extraído do título > nenhuma
        loc = location.strip() if location else extract_location_from_title(title)
        # Localização deve ser confirmadamente Brasil — sem confirmação, rejeita
        if not loc or not is_brazil_location(loc):
            return False
        # Título deve conter ao menos uma keyword (se definidas)
        return not keywords or contains_keyword(title, keywords)

    # Tenta API JSON primeiro
    try:
        resp = requests.get(
            "https://untalent.org/api/jobs?location=Brazil&limit=50",
            headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            data = resp.json()
            jobs = []
            items = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
            for item in items:
                title    = item.get("title", item.get("name", ""))
                url      = item.get("url", item.get("link", "https://untalent.org/jobs"))
                location = item.get("location", item.get("duty_station", ""))
                if title and passes_filter(title, location):
                    display_loc = location or extract_location_from_title(title) or "Brazil"
                    jobs.append({"title": title, "url": url, "source": "UNTalent.org", "location": display_loc})
            if jobs:
                print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
                return jobs
    except Exception:
        pass

    # Fallback HTML
    soup = fetch_html("https://untalent.org/jobs?location=Brazil")
    if not soup:
        print("    -> 0 vaga(s) encontrada(s)")
        return []
    jobs = []
    seen_hrefs: set[str] = set()
    for link in soup.select("a.job-link, .job-title a, h3 a, h2 a, a[href*='/jobs/']"):
        title = link.get_text(strip=True)
        href  = link.get("href", "")
        if not href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        if not href.startswith("http"):
            href = "https://untalent.org" + href
        loc = extract_location_from_title(title)
        if passes_filter(title, loc):
            jobs.append({"title": title, "url": href, "source": "UNTalent.org",
                         "location": loc or "Brazil"})
    print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
    return jobs


# Mapa de parsers específicos por nome (case-insensitive)
SPECIFIC_PARSERS = {
    "onu brasil":  fetch_onu_brasil,
    "bid":         fetch_iadb,
    "iadb":        fetch_iadb,
    "unitalent":   fetch_untalent,
    "untalent":    fetch_untalent,
}

# ---------------------------------------------------------------------------
# Parser genérico para URLs manuais
# ---------------------------------------------------------------------------

def fetch_custom_url(source: dict, global_keywords: list) -> list[dict]:
    name_key = source["name"].lower().strip()

    # Fonte marcada como manual: site bloqueia scraping ou usa JavaScript,
    # então o e-mail traz sempre um link direto para a página de vagas
    if source.get("manual"):
        print(f"  {source['name']}: fonte manual — incluindo link direto no e-mail")
        return [{
            "title": f"{source['name']} — Ver vagas no site (link direto)",
            "url": source["url"],
            "source": source["name"],
            "location": "Brasil (verificar no site)",
            "_manual": True,
        }]

    # Keywords da fonte têm prioridade; se vazia, usa as globais
    source_keywords = source.get("keywords") or global_keywords

    # Usa parser específico se disponível, passando keywords da fonte
    for key, parser in SPECIFIC_PARSERS.items():
        if key in name_key:
            return parser(source_keywords)

    print(f"  Verificando: {source['name']} (URL customizada)")
    soup = fetch_html(source["url"])
    if not soup:
        return []

    jobs = []
    seen_hrefs: set[str] = set()
    base_domain = "/".join(source["url"].split("/")[:3])

    selectors = [
        "li.job", "li.vacancy", "li.position", "li.listing",
        "div.job", "div.vacancy", "div.position",
        "tr.job", "tr.vacancy", "article.job", "article.vacancy",
        ".job-title a", ".vacancy-title a", ".position-title a",
        "h2 a", "h3 a", "h4 a",
    ]
    candidates = []
    for sel in selectors:
        candidates.extend(soup.select(sel))
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
            href = base_domain + "/" + href.lstrip("/")
        source_keywords = source.get("keywords", keywords)
        if not source_keywords or contains_keyword(title, source_keywords):
            location = ""
            parent = link.parent
            if parent:
                loc_tag = parent.find(class_=lambda c: c and any(
                    x in c for x in ["location", "duty", "city", "place", "local"]))
                if loc_tag:
                    location = loc_tag.get_text(strip=True)
            jobs.append({"title": title, "url": href, "source": source["name"], "location": location})

    print(f"    -> {len(jobs)} vaga(s) encontrada(s)")
    return jobs


# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------

def build_html_email(new_jobs: list[dict], run_date: str) -> str:
    if new_jobs:
        sorted_jobs = sorted(
            new_jobs,
            key=lambda j: (0 if _is_brazil(j.get("location", "")) else 1, j.get("location", ""))
        )
        rows = ""
        for j in sorted_jobs:
            location = j.get("location", "") or "—"
            if j.get("_manual"):
                rows += f"""
        <tr style="background:#fff8e1;">
          <td colspan="3" style="padding:10px;border-bottom:1px solid #eee;">
            <a href="{j['url']}" style="color:#e65100;font-weight:bold;">
              &#128279; {j['title']}
            </a>
            <span style="font-size:.8rem;color:#888;margin-left:8px;">(verificação manual necessária — site usa JavaScript)</span>
          </td>
        </tr>"""
            else:
                rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            <a href="{j['url']}" style="color:#1a73e8;font-weight:bold;">{j['title']}</a>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#555;">{j['source']}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#444;">{location}</td>
        </tr>"""
        body_content = f"""
      <p>Foram encontradas <strong>{len(new_jobs)}</strong> nova(s) vaga(s) — vagas no Brasil aparecem primeiro:</p>
      <table width="100%" cellspacing="0" style="border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#004b91;color:#fff;">
            <th style="padding:10px;text-align:left;">Título</th>
            <th style="padding:10px;text-align:left;">Organismo / Fonte</th>
            <th style="padding:10px;text-align:left;">Local</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>"""
    else:
        body_content = """
      <p style="padding:16px;background:#f0f4f8;border-left:4px solid #004b91;border-radius:4px;">
        Nenhuma vaga nova encontrada nesta varredura. Os sites monitorados foram verificados
        e não há publicações novas desde o último relatório.
      </p>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:800px;margin:auto;">
      <h2 style="color:#004b91;">Monitoramento ONU - Brasil</h2>
      <p>Relatório gerado em <strong>{run_date}</strong></p>
      {body_content}
      <p style="margin-top:24px;font-size:12px;color:#999;">
        Monitoramento automático · GitHub Actions · a cada 2 dias às 09:00 BRT
      </p>
    </body></html>
    """


def send_email(subject: str, html_body: str, cfg: dict) -> None:
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    smtp_port = int(os.environ.get("SMTP_PORT") or "587")
    smtp_user = (os.environ.get("SMTP_USER") or "").strip()
    smtp_pass = (os.environ.get("SMTP_PASS") or "").strip()
    to_addr   = (os.environ.get("EMAIL_TO")  or cfg["email"]["to"]).strip()

    print(f"[DEBUG] SMTP host={smtp_host!r} port={smtp_port} user={smtp_user!r} to={to_addr!r}")

    if not smtp_host or not smtp_user or not smtp_pass:
        print("[AVISO] Credenciais SMTP incompletas (SMTP_HOST, SMTP_USER ou SMTP_PASS vazios).")
        return
    if not to_addr:
        print("[AVISO] EMAIL_TO não configurado. E-mail não enviado.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
    try:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_addr, msg.as_string())
        print(f"[OK] E-mail enviado para {to_addr}")
    except smtplib.SMTPAuthenticationError:
        print("[ERRO] Autenticação falhou — verifique SMTP_USER e SMTP_PASS.")
        print("       Para Gmail use uma Senha de App em: myaccount.google.com/apppasswords")
        raise
    finally:
        server.quit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"=== Monitor ONU Brasil — {now_utc().strftime('%Y-%m-%d %H:%M UTC')} ===")

    config = load_config()
    seen = load_seen()
    keywords = config.get("keywords", [])

    all_jobs: list[dict] = []

    all_jobs.extend(fetch_reliefweb(keywords))
    time.sleep(2)
    all_jobs.extend(fetch_unjobs_org(keywords))
    time.sleep(2)
    all_jobs.extend(fetch_undp(keywords))
    time.sleep(2)

    for source in config.get("custom_sources", []):
        if not source.get("enabled", True):
            continue
        all_jobs.extend(fetch_custom_url(source, keywords))
        time.sleep(2)

    new_jobs = []
    updated_seen = set(seen)
    for job in all_jobs:
        if job.get("_manual"):          # link fixo — sempre incluir, nunca marcar como visto
            new_jobs.append(job)
            continue
        jid = job_id(job["title"], job["url"], job["source"])
        if jid not in seen:
            job["id"] = jid
            new_jobs.append(job)
            updated_seen.add(jid)

    save_seen(updated_seen)
    print(f"\nTotal de vagas novas: {len(new_jobs)}")

    run_date = datetime.now().strftime("%d/%m/%Y às %H:%M")
    prefix = config["email"]["subject_prefix"]

    if new_jobs:
        subject = f"{prefix} {len(new_jobs)} nova(s) vaga(s) encontrada(s) — {run_date}"
        print("\n--- Vagas novas ---")
        for j in new_jobs:
            print(f"  [{j['source']}] {j['title']} | {j.get('location', '')}")
    else:
        subject = f"{prefix} Sem novas vagas — {run_date}"
        print("Nenhuma vaga nova. Enviando e-mail de status.")

    html = build_html_email(new_jobs, run_date)

    try:
        send_email(subject, html, config)
    except KeyError as e:
        print(f"[AVISO] Variável de ambiente ausente: {e}. E-mail não enviado.")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar e-mail: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
