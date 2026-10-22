"""Checagem de nova versão do Organizador Financeiro (só consulta, não baixa nada)."""
import hashlib
import json
import os
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

import versao


LIMITE_MANIFESTO = 65536  # bytes; um manifesto de verdade tem poucas centenas


def _url_http(url):
    """Só http/https. file://, ftp:// etc. nunca são aceitos."""
    try:
        return urlparse(str(url).strip()).scheme.lower() in ('http', 'https')
    except Exception:
        return False


def checar_atualizacao(url, timeout=3.0):
    """Devolve o manifesto se a versão publicada for maior que a instalada, senão None.

    Nunca levanta: qualquer falha (rede, DNS, timeout, status, JSON ruim) vira None.
    """
    try:
        if not url or not _url_http(url):
            return None
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200 or not _url_http(resp.geturl()):
                return None
            # lê 1 byte a mais para distinguir "cabe no limite" de "passou do limite"
            corpo = resp.read(LIMITE_MANIFESTO + 1)
            if len(corpo) > LIMITE_MANIFESTO:
                return None
            manifesto = json.loads(corpo.decode('utf-8-sig'))
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


# ── Download, hash e extração ────────────────────────────────────────────────

def conferir_hash(caminho, sha256_esperado):
    """True se o SHA-256 do arquivo bate com o esperado (sem diferenciar caixa)."""
    try:
        h = hashlib.sha256()
        with open(caminho, 'rb') as f:
            for bloco in iter(lambda: f.read(1024 * 1024), b''):
                h.update(bloco)
        return h.hexdigest() == str(sha256_esperado).strip().lower()
    except Exception:
        return False


def baixar_pacote(manifesto, destino, timeout=30.0):
    """Baixa o ZIP do manifesto para `destino` (pasta) e devolve o caminho final.

    Grava em 'pacote.zip.parcial' e só renomeia ao terminar: um download
    interrompido nunca parece completo. Levanta exceção em qualquer falha.
    """
    url = manifesto['url']
    if not _url_http(url):
        raise ValueError('endereço do pacote deve ser http ou https')
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    final = destino / 'pacote.zip'          # nome fixo: nunca vem da URL
    parcial = destino / 'pacote.zip.parcial'
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200 or not _url_http(resp.geturl()):
                raise ValueError(f'download recusado (status {resp.status})')
            with open(parcial, 'wb') as f:
                for bloco in iter(lambda: resp.read(1024 * 1024), b''):
                    f.write(bloco)
        os.replace(parcial, final)
    except BaseException:
        try:
            parcial.unlink()
        except OSError:
            pass
        raise
    return final


def _nome_seguro(nome):
    """True se o nome da entrada do ZIP é relativo e não sai da pasta."""
    if not nome or chr(0) in nome or ':' in nome:
        return False
    for classe in (PurePosixPath, PureWindowsPath):
        p = classe(nome)
        if p.is_absolute() or getattr(p, 'drive', '') or getattr(p, 'root', ''):
            return False
        if '..' in p.parts:
            return False
    return True


def extrair_pacote(zip_path, destino):
    """Extrai o ZIP em `destino` e devolve a pasta que contém os itens do programa.

    Valida TODAS as entradas antes de escrever qualquer coisa. Levanta ValueError
    se alguma entrada for absoluta ou cair fora de `destino`, ou se faltar algum
    dos itens de versao.ITENS_DO_PROGRAMA.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    raiz = destino.resolve()
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise ValueError(f'pacote não é um ZIP válido: {e}')
    with zf:
        entradas = zf.infolist()
        topo = set()
        for info in entradas:
            nome = info.filename
            if not _nome_seguro(nome):
                raise ValueError(f'entrada recusada no pacote: {nome!r}')
            try:
                alvo = (raiz / nome).resolve()
            except (OSError, ValueError):
                raise ValueError(f'entrada inválida no pacote: {nome!r}')
            if alvo != raiz and raiz not in alvo.parents:
                raise ValueError(f'entrada fora da pasta de destino: {nome!r}')
            partes = PurePosixPath(nome.replace(chr(92), '/')).parts
            if not partes:   # '.' ou './': sem caminho utilizável
                raise ValueError(f'entrada sem caminho no pacote: {nome!r}')
            topo.add(partes[0])
        faltando = [i for i in versao.ITENS_DO_PROGRAMA if i not in topo]
        if faltando:
            raise ValueError(f'pacote incompleto, faltam: {", ".join(faltando)}')
        try:
            for info in entradas:
                alvo = (raiz / info.filename).resolve()
                if info.is_dir():
                    alvo.mkdir(parents=True, exist_ok=True)
                    continue
                alvo.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as origem, open(alvo, 'wb') as saida:
                    while True:
                        bloco = origem.read(1024 * 1024)
                        if not bloco:
                            break
                        saida.write(bloco)
        except (OSError, zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError) as e:
            # entrada corrompida, criptografada, conflito de nomes (a e a/b) etc.
            raise ValueError(f'falha ao extrair o pacote: {e}')
    for item in versao.ITENS_DO_PROGRAMA:
        if not (raiz / item).exists():
            raise ValueError(f'item ausente após extração: {item}')
    return destino
