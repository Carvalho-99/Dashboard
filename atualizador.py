"""Checagem de nova versão do Organizador Financeiro (só consulta, não baixa nada)."""
import json
import urllib.request

import versao


def checar_atualizacao(url, timeout=3.0):
    """Devolve o manifesto se a versão publicada for maior que a instalada, senão None.

    Nunca levanta: qualquer falha (rede, DNS, timeout, status, JSON ruim) vira None.
    """
    try:
        if not url:
            return None
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            manifesto = json.loads(resp.read().decode('utf-8-sig'))
        if not isinstance(manifesto, dict):
            return None
        for campo in ('versao', 'url', 'sha256'):
            valor = manifesto.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                return None
        if versao.comparar_versoes(manifesto['versao'], versao.VERSAO) == 1:
            return manifesto
        return None
    except Exception:
        return None
