"""Baixa as bibliotecas de front-end para static/vendor/ (uso de manutencao).

O app roda offline na maquina do cliente, entao nada pode vir de CDN.
Rode so ao atualizar versoes: venv/Scripts/python.exe baixar_vendor.py
"""
import os
import re
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(BASE, "static", "vendor")

BOOTSTRAP = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist"
ICONES = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font"
CHART = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist"


def baixar(url, destino):
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as r:
        dados = r.read()
    if not dados:
        raise RuntimeError(f"Download vazio: {url}")
    with open(destino, "wb") as f:
        f.write(dados)
    print(f"{len(dados):>8}  {os.path.relpath(destino, BASE)}")
    return dados


def main():
    baixar(f"{BOOTSTRAP}/css/bootstrap.min.css", os.path.join(VENDOR, "bootstrap.min.css"))
    baixar(f"{BOOTSTRAP}/js/bootstrap.bundle.min.js", os.path.join(VENDOR, "bootstrap.bundle.min.js"))
    baixar(f"{CHART}/chart.umd.min.js", os.path.join(VENDOR, "chart.umd.min.js"))
    css = baixar(f"{ICONES}/bootstrap-icons.min.css", os.path.join(VENDOR, "bootstrap-icons.min.css"))

    # Fontes: le os url(...) do proprio CSS, sem presumir nomes
    caminhos = set(re.findall(r'url\(["\']?(?:\./)?(fonts/[^)"\'?#]+)', css.decode("utf-8")))
    if not caminhos:
        raise RuntimeError("Nenhuma fonte encontrada no CSS dos icones")
    for rel in sorted(caminhos):
        baixar(f"{ICONES}/{rel}", os.path.join(VENDOR, *rel.split("/")))


if __name__ == "__main__":
    main()
