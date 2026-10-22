"""Versão instalada do Organizador Financeiro e comparação de versões.

A versão mora só aqui. Não importa o app.py (ele é quem importa este módulo).
"""
import os
import sys

VERSAO = '1.0.0'

# Endereço do manifesto de atualização. Vazio = sem verificação de atualização.
MANIFEST_URL_PADRAO = ''

# O que faz parte do programa e pode ser trocado na atualização.
# O banco (financas.db) fica de fora de propósito.
ITENS_DO_PROGRAMA = (
    'Organizador Financeiro.exe',
    'OrganizadorFinanceiro.exe',
    '_internal',
    'LEIA-ME.txt',
)


def _pasta_do_programa():
    # mesma regra do DATA_DIR do app.py: ao lado do .exe quando empacotado
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _campos(versao):
    try:
        partes = str(versao).strip().split('.')
    except Exception:
        return [0]
    campos = []
    for p in partes:
        try:
            n = int(p.strip())
        except (ValueError, TypeError):
            n = 0
        campos.append(n if n > 0 else 0)
    return campos


def comparar_versoes(a, b):
    """Retorna -1 se a < b, 0 se iguais, 1 se a > b. Nunca levanta exceção."""
    try:
        ca, cb = _campos(a), _campos(b)
        tam = max(len(ca), len(cb))
        ca += [0] * (tam - len(ca))
        cb += [0] * (tam - len(cb))
        if ca < cb:
            return -1
        if ca > cb:
            return 1
        return 0
    except Exception:
        return 0


def manifest_url():
    """URL do manifesto: variável de ambiente, manifest.txt ao lado do exe, padrão."""
    url = os.environ.get('ORGFIN_MANIFEST_URL', '').strip()
    if url:
        return url
    try:
        caminho = os.path.join(_pasta_do_programa(), 'manifest.txt')
        if os.path.isfile(caminho):
            with open(caminho, encoding='utf-8-sig') as f:
                url = f.read().strip()
            if url:
                return url
    except Exception:
        pass
    return MANIFEST_URL_PADRAO
