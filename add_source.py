#!/usr/bin/env python3
"""
Lê variáveis de ambiente injetadas pelo GitHub Actions e adiciona
uma nova entrada em custom_sources no config.json.
"""
import json
import os
import sys

CONFIG_FILE = "config.json"

name     = os.environ.get("SOURCE_NAME", "").strip()
url      = os.environ.get("SOURCE_URL", "").strip()
keywords = os.environ.get("SOURCE_KEYWORDS", "").strip()
notes    = os.environ.get("SOURCE_NOTES", "").strip()

if not name or not url:
    print("[ERRO] Nome e URL são obrigatórios.")
    sys.exit(1)

if not url.startswith("http"):
    print(f"[ERRO] URL inválida: {url}")
    sys.exit(1)

with open(CONFIG_FILE, encoding="utf-8") as f:
    config = json.load(f)

# Evita duplicata pela URL
existing_urls = [s["url"] for s in config.get("custom_sources", [])]
if url in existing_urls:
    print(f"[AVISO] URL já cadastrada: {url}")
    sys.exit(0)

kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

new_source = {
    "name": name,
    "url": url,
    "enabled": True,
    "notes": notes,
    "keywords": kw_list,
}

config.setdefault("custom_sources", []).append(new_source)

# Remove o item de exemplo se ainda estiver lá
config["custom_sources"] = [
    s for s in config["custom_sources"]
    if "Remova ou substitua" not in s.get("name", "")
]

with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print(f"[OK] Fonte adicionada: {name} → {url}")
