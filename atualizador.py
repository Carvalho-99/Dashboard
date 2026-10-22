"""Checagem, download e instalação de nova versão do Organizador Financeiro."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

import versao


LIMITE_MANIFESTO = 65536  # bytes; um manifesto de verdade tem poucas centenas

# Teto do que o pacote pode render ao ser descompactado. Um ZIP pequeno pode
# declarar terabytes; sem teto, a extração enche o disco da pessoa.
LIMITE_EXTRACAO = 1536 * 1024 * 1024


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
        declarado = 0
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
            declarado += max(0, int(getattr(info, 'file_size', 0) or 0))
            if declarado > LIMITE_EXTRACAO:
                raise ValueError('pacote grande demais para ser instalado')
        faltando = [i for i in versao.ITENS_DO_PROGRAMA if i not in topo]
        if faltando:
            raise ValueError(f'pacote incompleto, faltam: {", ".join(faltando)}')
        try:
            escrito = 0
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
                        escrito += len(bloco)
                        if escrito > LIMITE_EXTRACAO:
                            # o tamanho declarado mentiu: para na hora
                            raise ValueError('pacote grande demais para ser instalado')
                        saida.write(bloco)
        except (OSError, zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError) as e:
            # entrada corrompida, criptografada, conflito de nomes (a e a/b) etc.
            raise ValueError(f'falha ao extrair o pacote: {e}')
    for item in versao.ITENS_DO_PROGRAMA:
        if not (raiz / item).exists():
            raise ValueError(f'item ausente após extração: {item}')
    return destino


# ── Troca dos arquivos ───────────────────────────────────────────────────────

PORTA = 5050                 # onde o app atende; o auxiliar confirma a troca aqui
ESPERA_FECHAR = 60           # segundos esperando o app encerrar
ESPERA_RESPONDER = 90        # segundos esperando a versão nova atender na porta


def pasta_do_app():
    """Pasta onde o programa está instalado (mesma regra do versao.py)."""
    return Path(versao._pasta_do_programa())


def copiar_banco(pasta_app, versao_atual):
    """Copia financas.db para financas.db.bak-<versao> e devolve o caminho novo.

    Devolve None quando não existe banco. Nunca sobrescreve um backup anterior:
    ele pode ser a única cópia boa que a pessoa tem, então o repetido ganha
    sufixo numérico. O original não é tocado, só lido.
    """
    pasta_app = Path(pasta_app)
    banco = pasta_app / 'financas.db'
    if not banco.is_file():
        return None
    destino = pasta_app / f'financas.db.bak-{versao_atual}'
    n = 2
    while destino.exists():
        destino = pasta_app / f'financas.db.bak-{versao_atual}-{n}'
        n += 1
        if n > 999:
            raise OSError('backups do banco demais na pasta')
    shutil.copy2(banco, destino)
    return destino


def _ps(valor):
    """Escapa um valor para dentro de 'apóstrofos' no PowerShell."""
    return str(valor).replace("'", "''")


# Corpo fixo do auxiliar. O cabeçalho com os caminhos é gerado em
# gerar_script_troca. Mexe só nos nomes de $itens: nada de pasta inteira.
CORPO_TROCA = r'''
function Anotar($msg) {
  try { Add-Content -LiteralPath $log -Value ("{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg) } catch { }
}

function Caminho($item) { Join-Path $pastaApp $item }

function ExeDoApp {
  $e = Caminho $exeApp
  if (Test-Path -LiteralPath $e) { return $e }
  return Caminho $exeAlternativo
}

function Abrir {
  $e = ExeDoApp
  if (Test-Path -LiteralPath $e) {
    try { return (Start-Process -FilePath $e -WorkingDirectory $pastaApp -PassThru) }
    catch { Anotar "nao consegui abrir o programa: $_" }
  } else {
    Anotar 'o executavel nao esta na pasta'
  }
  return $null
}

function Responde {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri ("http://127.0.0.1:{0}/" -f $porta)
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

function Restaurar {
  # devolve cada .old ao nome original; segue em frente se um item falhar
  foreach ($item in $itens) {
    $atual = Caminho $item
    $velho = "$atual.old"
    try {
      if (Test-Path -LiteralPath $velho) {
        if (Test-Path -LiteralPath $atual) { Remove-Item -LiteralPath $atual -Recurse -Force }
        Move-Item -LiteralPath $velho -Destination $atual -Force
        Anotar "devolvido: $item"
      }
    } catch { Anotar "falha ao devolver $item : $_" }
  }
}

function ApagarTemporario {
  # nao da para apagar a pasta de dentro dela: deixa um cmd solto fazendo isso
  try {
    Start-Process -FilePath 'cmd.exe' -WindowStyle Hidden -WorkingDirectory $env:TEMP `
      -ArgumentList '/c', ('ping -n 5 127.0.0.1 >nul & rd /s /q "' + $raizTemp + '"')
  } catch { }
}

Anotar "esperando o programa (pid $pidApp) encerrar"
$limite = (Get-Date).AddSeconds($esperaFechar)
while ((Get-Date) -lt $limite) {
  if (-not (Get-Process -Id $pidApp -ErrorAction SilentlyContinue)) { break }
  Start-Sleep -Milliseconds 400
}
if (Get-Process -Id $pidApp -ErrorAction SilentlyContinue) {
  Anotar 'o programa nao encerrou; nada foi alterado'
  ApagarTemporario
  exit 1
}
Start-Sleep -Milliseconds 800

# sobra de uma tentativa anterior: se o item esta no lugar, a sobra e lixo;
# se o item faltou, a sobra e a unica copia e volta para o lugar
foreach ($item in $itens) {
  $atual = Caminho $item
  $velho = "$atual.old"
  if (Test-Path -LiteralPath $velho) {
    try {
      if (Test-Path -LiteralPath $atual) {
        Remove-Item -LiteralPath $velho -Recurse -Force
        Anotar "sobra anterior apagada: $item"
      } else {
        Move-Item -LiteralPath $velho -Destination $atual -Force
        Anotar "sobra anterior devolvida: $item"
      }
    } catch { Anotar "nao deu para tratar a sobra de $item : $_" }
  }
}

try {
  foreach ($item in $itens) {
    if (-not (Test-Path -LiteralPath (Join-Path $pastaNova $item))) { throw "falta no pacote novo: $item" }
  }
  # move de lado (nao apaga): e isso que permite voltar atras
  foreach ($item in $itens) {
    $atual = Caminho $item
    if (Test-Path -LiteralPath $atual) { Move-Item -LiteralPath $atual -Destination "$atual.old" -Force }
  }
  foreach ($item in $itens) {
    Copy-Item -LiteralPath (Join-Path $pastaNova $item) -Destination (Caminho $item) -Recurse -Force
  }
  Anotar 'arquivos novos no lugar'
} catch {
  Anotar "falha na troca: $_"
  Restaurar
  Abrir | Out-Null
  exit 1
}

$novo = Abrir
$ok = $false
$limite = (Get-Date).AddSeconds($esperaResponder)
while (($novo -ne $null) -and ((Get-Date) -lt $limite)) {
  if (Responde) { $ok = $true; break }
  if ($novo.HasExited) {
    # caiu sozinho: uma ultima chance de responder, senao volta atras ja
    Start-Sleep -Seconds 2
    if (Responde) { $ok = $true }
    Anotar 'a versao nova encerrou sozinha'
    break
  }
  Start-Sleep -Seconds 2
}

if ($ok) {
  Anotar 'versao nova respondeu; apagando a anterior'
  foreach ($item in $itens) {
    $velho = (Caminho $item) + '.old'
    try {
      if (Test-Path -LiteralPath $velho) { Remove-Item -LiteralPath $velho -Recurse -Force }
    } catch { Anotar "sobrou $item.old : $_" }
  }
  ApagarTemporario
  exit 0
}

Anotar 'versao nova nao respondeu; voltando para a anterior'
if ($novo -ne $null) {
  try { if (-not $novo.HasExited) { Stop-Process -Id $novo.Id -Force } } catch { }
}
Start-Sleep -Milliseconds 1500
Restaurar
Abrir | Out-Null
# ficar sem programa nenhum e o pior desfecho possivel: confere e insiste
$voltou = $false
$limite = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $limite) {
  if (Responde) { $voltou = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $voltou) {
  Anotar 'a anterior tambem nao respondeu; abrindo mais uma vez'
  Start-Sleep -Seconds 2
  Abrir | Out-Null
}
Anotar ('versao anterior de volta (respondeu: ' + $voltou + ')')
exit 1
'''


def gerar_script_troca(pid, pasta_app, pasta_nova, raiz_temp=None):
    """Escreve o .ps1 que troca os arquivos e devolve o caminho dele.

    O auxiliar mora numa pasta temporária: a pasta do programa é justamente o
    que vai ser reescrito, e o auxiliar não pode ser um dos arquivos trocados.
    """
    pasta_app = Path(pasta_app).resolve()
    pasta_nova = Path(pasta_nova).resolve()
    if raiz_temp is None:
        raiz_temp = Path(tempfile.mkdtemp(prefix='orgfin_troca_'))
    raiz_temp = Path(raiz_temp).resolve()
    raiz_temp.mkdir(parents=True, exist_ok=True)
    if raiz_temp == pasta_app or pasta_app in raiz_temp.parents:
        raise ValueError('o auxiliar não pode ficar dentro da pasta do programa')
    if pasta_nova == pasta_app or pasta_app in pasta_nova.parents:
        raise ValueError('o pacote novo não pode estar dentro da pasta do programa')
    itens = ', '.join("'" + _ps(i) + "'" for i in versao.ITENS_DO_PROGRAMA)
    script = raiz_temp / 'trocar_arquivos.ps1'
    if script.name in versao.ITENS_DO_PROGRAMA:
        raise ValueError('o auxiliar não pode ter o nome de um item do programa')
    cabecalho = (
        '# Auxiliar de atualizacao do Organizador Financeiro (arquivo gerado).\n'
        '# Roda sozinho depois que o programa fecha e mexe apenas nos itens de $itens.\n'
        "$ErrorActionPreference = 'Stop'\n"
        f'$pidApp          = {int(pid)}\n'
        f"$pastaApp        = '{_ps(pasta_app)}'\n"
        f"$pastaNova       = '{_ps(pasta_nova)}'\n"
        f"$raizTemp        = '{_ps(raiz_temp)}'\n"
        f"$exeApp          = '{_ps(versao.ITENS_DO_PROGRAMA[0])}'\n"
        f"$exeAlternativo  = '{_ps(versao.ITENS_DO_PROGRAMA[1])}'\n"
        f'$porta           = {int(PORTA)}\n'
        f'$esperaFechar    = {int(ESPERA_FECHAR)}\n'
        f'$esperaResponder = {int(ESPERA_RESPONDER)}\n'
        f'$itens           = @({itens})\n'
        "$log             = Join-Path $raizTemp 'troca.log'\n"
    )
    # BOM: sem ele o PowerShell 5.1 lê o arquivo como ANSI e erra os acentos
    script.write_text(cabecalho + CORPO_TROCA, encoding='utf-8-sig')
    return script


def _flags_auxiliar():
    """Sem janela e em grupo próprio: o auxiliar sobrevive ao fim do app.

    DETACHED_PROCESS não serve aqui: sem console o powershell.exe sai com
    código 0 sem rodar linha nenhuma, e a atualização não aconteceria.
    """
    flags = 0
    for nome in ('CREATE_NO_WINDOW', 'CREATE_NEW_PROCESS_GROUP'):
        flags |= getattr(subprocess, nome, 0)
    return flags


def _disparar_auxiliar(script):
    """Sobe o auxiliar solto do app: ele precisa sobreviver ao encerramento."""
    return subprocess.Popen(
        ['powershell.exe', '-NoProfile', '-NonInteractive',
         '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', str(script)],
        cwd=tempfile.gettempdir(),     # nunca a pasta do app nem a temporária
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=_flags_auxiliar(),
    )


def aplicar_atualizacao(manifesto, pasta_app=None, pid=None, raiz_temp=None):
    """Baixa, confere, extrai, guarda o banco e dispara a troca dos arquivos.

    A ordem é obrigatória: baixar → conferir hash → extrair. Pacote com hash
    diferente do publicado é recusado antes de ser aberto.

    Cada tentativa usa uma pasta temporária nova, apagada inteira em qualquer
    falha: extração pela metade nunca vira pacote bom. Enquanto o auxiliar não
    sobe, nada na instalação é alterado — só aparece a cópia do banco.

    Levanta exceção se algo falhar. Devolve o caminho do auxiliar disparado.
    """
    pasta_app = Path(pasta_app) if pasta_app else pasta_do_app()
    pid = os.getpid() if pid is None else int(pid)
    raiz = Path(raiz_temp) if raiz_temp else Path(tempfile.gettempdir())
    raiz.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='orgfin_atualizacao_', dir=str(raiz)))
    try:
        pacote = baixar_pacote(manifesto, temp)
        if not conferir_hash(pacote, manifesto.get('sha256', '')):
            raise ValueError('pacote baixado não confere com o hash publicado')
        pasta_nova = extrair_pacote(pacote, temp / 'novo')
        copiar_banco(pasta_app, versao.VERSAO)
        script = gerar_script_troca(pid, pasta_app, pasta_nova, raiz_temp=temp)
        _disparar_auxiliar(script)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return script
