"""Testa a versão e a comparação de versões do Organizador Financeiro."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tempfile, threading, hashlib, zipfile, json, shutil, subprocess, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

import versao
import atualizador
import app as flask_app

results = []

def check_eq(name, got, want):
    ok = got == want
    results.append((name, 'PASS' if ok else f'FAIL: {got!r} != {want!r}', '-'))

check_eq('versao igual',        versao.comparar_versoes('1.0.0', '1.0.0'),   0)
check_eq('menor que',           versao.comparar_versoes('1.0.0', '1.0.1'),  -1)
check_eq('maior que',           versao.comparar_versoes('1.2.0', '1.1.9'),   1)
check_eq('10 maior que 9',      versao.comparar_versoes('1.10.0', '1.9.0'),  1)   # string compararia errado
check_eq('campos a menos',      versao.comparar_versoes('1.1', '1.1.0'),     0)
check_eq('lixo vira 0',         versao.comparar_versoes('abc', '1.0.0'),    -1)
check_eq('vazio vira 0',        versao.comparar_versoes('', '0.0.0'),        0)
check_eq('itens do programa',   len(versao.ITENS_DO_PROGRAMA),               4)
check_eq('db fora da lista',    any('financas' in i for i in versao.ITENS_DO_PROGRAMA), False)

# nunca levanta exceção, qualquer entrada
for nome, a, b in [('None', None, '1.0.0'), ('int', 3, '1.0.0'), ('lista', [1], {}),
                   ('negativo', '-1.0.0', '0.0.0'), ('espacos', ' 1.2 .3 ', '1.2.3')]:
    try:
        r = versao.comparar_versoes(a, b)
    except Exception as e:
        r = f'levantou {e!r}'
    results.append((f'sem excecao: {nome}', 'PASS' if r in (-1, 0, 1) else f'FAIL: {r}', '-'))
check_eq('espacos ignorados',   versao.comparar_versoes(' 1.2 .3 ', '1.2.3'), 0)
check_eq('versao instalada',    versao.comparar_versoes(versao.VERSAO, versao.VERSAO), 0)

# manifest_url: variável de ambiente vence; sem nada, cai no padrão
_antes = os.environ.get('ORGFIN_MANIFEST_URL')
os.environ['ORGFIN_MANIFEST_URL'] = 'https://exemplo.test/m.json'
check_eq('manifest via env',    versao.manifest_url(), 'https://exemplo.test/m.json')
os.environ.pop('ORGFIN_MANIFEST_URL')
if not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manifest.txt')):
    check_eq('manifest padrao', versao.manifest_url(), versao.MANIFEST_URL_PADRAO)
if _antes is not None:
    os.environ['ORGFIN_MANIFEST_URL'] = _antes

# ── Checagem do manifesto (servidor HTTP local de teste) ─────────────────────
_resposta = {'status': 200, 'corpo': b''}

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(_resposta['status'])
        self.end_headers()
        self.wfile.write(_resposta['corpo'])
    def log_message(self, *a):
        pass

_srv = HTTPServer(('127.0.0.1', 0), _Handler)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
_URL = f'http://127.0.0.1:{_srv.server_port}/version.json'

def checar_url(url):
    return atualizador.checar_atualizacao(url, timeout=2)

def checar(corpo):
    _resposta.update(status=200, corpo=corpo.encode('utf-8'))
    return checar_url(_URL)

def checar_status(codigo):
    _resposta.update(status=codigo, corpo=b'{"versao":"9.9.9","url":"x","sha256":"y"}')
    return checar_url(_URL)

check_eq('versao nova avisa',      checar('{"versao":"9.9.9","url":"x","sha256":"y"}')  is not None, True)
check_eq('versao igual nao avisa', checar('{"versao":"1.0.0","url":"x","sha256":"y"}')  is None,     True)
check_eq('versao menor nao avisa', checar('{"versao":"0.0.1","url":"x","sha256":"y"}')  is None,     True)
check_eq('json truncado',          checar('{"versao":"9.9')                            is None,     True)
check_eq('sem campo versao',       checar('{"url":"x"}')                               is None,     True)
check_eq('versao nao numerica',    checar('{"versao":"banana","url":"x"}')             is None,     True)
check_eq('sem url nao avisa',      checar('{"versao":"9.9.9"}')                        is None,     True)
check_eq('sem sha256 nao avisa',   checar('{"versao":"9.9.9","url":"x"}')              is None,     True)
check_eq('json nao e objeto',      checar('[1,2]')                                     is None,     True)
check_eq('http 404',               checar_status(404)                                  is None,     True)
check_eq('host inexistente',       checar_url('http://127.0.0.1:1/version.json')       is None,     True)
check_eq('url vazia',              checar_url('')                                      is None,     True)

# esquema e tamanho do manifesto
_tmp_m = tempfile.mkdtemp(prefix='orgfin_manifesto_')
_arq_m = Path(_tmp_m) / 'version.json'
_arq_m.write_text('{"versao":"9.9.9","url":"x","sha256":"y"}', encoding='utf-8')
check_eq('manifesto valido em disco existe', _arq_m.is_file(), True)
check_eq('file:// recusado mesmo valido', checar_url(_arq_m.as_uri()) is None, True)
check_eq('ftp:// recusado',               checar_url('ftp://127.0.0.1/version.json') is None, True)
check_eq('manifesto gigante recusado',
         checar('{"versao":"9.9.9","url":"x","sha256":"y"}' + ' ' * (5 * 1024 * 1024)) is None, True)
check_eq('manifesto no limite aceito',
         checar('{"versao":"9.9.9","url":"x","sha256":"y"}' + ' ' * 1000) is not None, True)

# ── Download, hash e extração ────────────────────────────────────────────────
ITENS = versao.ITENS_DO_PROGRAMA

def montar_zip(caminho, nomes_extra=(), itens=ITENS):
    """ZIP com os itens do programa (+ entradas extras, com nome cru via ZipInfo)."""
    with zipfile.ZipFile(caminho, 'w') as z:
        for item in itens:
            if item == '_internal':
                z.writestr('_internal/base.dll', b'dll')
            else:
                z.writestr(item, b'conteudo ' + item.encode())
        for nome in nomes_extra:
            zi = zipfile.ZipInfo('x')
            zi.filename = nome   # atribuição direta: o construtor trocaria barra invertida por '/'
            z.writestr(zi, b'hostil')
    return caminho

_base = Path(tempfile.mkdtemp(prefix='orgfin_zip_')) / 'a' / 'b'   # pais exclusivos deste teste
_base.mkdir(parents=True)
zip_ok = montar_zip(_base / 'ok.zip')
sha_real = hashlib.sha256(zip_ok.read_bytes()).hexdigest()
zip_truncado = _base / 'cortado.zip'
zip_truncado.write_bytes(zip_ok.read_bytes()[:-20])

check_eq('hash confere',            atualizador.conferir_hash(zip_ok, sha_real),           True)
check_eq('hash nao confere',        atualizador.conferir_hash(zip_ok, 'f' * 64),           False)
check_eq('hash de arquivo cortado', atualizador.conferir_hash(zip_truncado, sha_real),     False)
check_eq('hash insensivel a caixa', atualizador.conferir_hash(zip_ok, sha_real.upper()),   True)
check_eq('hash de arquivo ausente', atualizador.conferir_hash(_base / 'nao_existe.zip', sha_real), False)

_dest = _base / 'extraido'
extraido = atualizador.extrair_pacote(zip_ok, _dest)
check_eq('extrai itens', sorted(p.name for p in extraido.iterdir()) == sorted(ITENS), True)
check_eq('extrai conteudo da subpasta', (extraido / '_internal' / 'base.dll').read_bytes(), b'dll')

def recusa(chamada):
    try:
        chamada()
    except ValueError:
        return True
    except Exception as e:
        return f'outra excecao: {e!r}'
    return False

def extrair_recusa(nome_hostil, tag):
    """Monta ZIP (itens válidos + 1 entrada hostil), confere que o nome hostil
    realmente está no arquivo, e espera ValueError sem nada escrito."""
    zp = montar_zip(_base / f'hostil_{tag}.zip', nomes_extra=[nome_hostil])
    # fixture precisa conter o nome cru nos bytes do arquivo (o zipfile normaliza
    # barras ao LER no Windows, então a prova é nos bytes, não no namelist)
    if nome_hostil.encode() not in zp.read_bytes():
        return 'fixture sanitizada: teste nao prova nada'
    dest = _base / f'dest_{tag}'
    r = recusa(lambda: atualizador.extrair_pacote(zp, dest))
    if r is True and any(dest.rglob('*')):
        return 'recusou mas ja tinha escrito arquivos'
    return r

_B = chr(92)
check_eq('zip-slip recusado',          extrair_recusa('../../fora.txt', 'slip'), True)
check_eq('zip-slip com barra invertida', extrair_recusa('..' + _B + '..' + _B + 'fora.txt', 'slipb'), True)
check_eq('zip-slip no meio do caminho', extrair_recusa('_internal/../../fora.txt', 'slipm'), True)
check_eq('zip absoluto recusado',      extrair_recusa('C:/Windows/fora.txt', 'abs'), True)
check_eq('zip absoluto barra invertida', extrair_recusa('C:' + _B + 'Windows' + _B + 'fora.txt', 'absb'), True)
check_eq('zip absoluto unix recusado', extrair_recusa('/etc/fora.txt', 'absu'), True)
check_eq('zip UNC recusado',           extrair_recusa(_B + _B + 'servidor' + _B + 'pasta' + _B + 'fora.txt', 'unc'), True)
check_eq('nada escrito fora do destino',
         any(p.exists() for p in (_base / 'fora.txt', _base.parent / 'fora.txt', _base.parent.parent / 'fora.txt')), False)

check_eq('entrada "." recusada com ValueError',  extrair_recusa('.', 'ponto'), True)
check_eq('entrada "./" recusada com ValueError', extrair_recusa('./', 'pontobarra'), True)
# conflito de nomes (arquivo e depois pasta de mesmo nome): ValueError, não FileExistsError
_zc = montar_zip(_base / 'conflito.zip', nomes_extra=['LEIA-ME.txt/b'])
check_eq('conflito arquivo/pasta vira ValueError',
         recusa(lambda: atualizador.extrair_pacote(_zc, _base / 'dest_conflito')), True)

def extrair_recusa_conteudo(itens):
    zp = montar_zip(_base / 'incompleto.zip', itens=itens)
    return recusa(lambda: atualizador.extrair_pacote(zp, _base / 'dest_incompleto'))

check_eq('zip sem os itens recusado',  extrair_recusa_conteudo(['leia.txt']), True)
check_eq('zip faltando 1 item recusado', extrair_recusa_conteudo(list(ITENS[:-1])), True)
(_base / 'lixo.zip').write_bytes(b'isto nao e um zip')
check_eq('arquivo nao-zip recusado',   recusa(lambda: atualizador.extrair_pacote(_base / 'lixo.zip', _base / 'dest_lixo')), True)

# baixar_pacote contra o servidor local
_resposta.update(status=200, corpo=zip_ok.read_bytes())
_dir_dl = _base / 'baixado'
baixado = atualizador.baixar_pacote({'url': _URL}, _dir_dl)
check_eq('baixa o pacote inteiro',     baixado.read_bytes() == zip_ok.read_bytes(), True)
check_eq('baixado confere hash',       atualizador.conferir_hash(baixado, sha_real), True)
check_eq('sem .parcial apos sucesso',  list(_dir_dl.glob('*.parcial')), [])
check_eq('file:// no download recusado',
         recusa(lambda: atualizador.baixar_pacote({'url': zip_ok.as_uri()}, _base / 'dl_file')), True)
check_eq('file:// nao criou pacote',   (_base / 'dl_file' / 'pacote.zip').exists(), False)
_resposta.update(status=404, corpo=b'nao achou')
_dir_404 = _base / 'dl_404'
try:
    atualizador.baixar_pacote({'url': _URL}, _dir_404)
    _levantou = False
except Exception:
    _levantou = True
check_eq('http 404 no download levanta', _levantou, True)
check_eq('404 nao deixa pacote nem parcial', list(_dir_404.iterdir()), [])

# teto de descompactacao (limite abaixado so para este teste)
_limite_antes = atualizador.LIMITE_EXTRACAO
atualizador.LIMITE_EXTRACAO = 10
check_eq('pacote grande demais recusado',
         recusa(lambda: atualizador.extrair_pacote(zip_ok, _base / 'dest_bomba')), True)
atualizador.LIMITE_EXTRACAO = _limite_antes
check_eq('pacote grande demais nao escreveu nada', any((_base / 'dest_bomba').rglob('*')), False)
check_eq('limite de extracao restaurado', atualizador.LIMITE_EXTRACAO, _limite_antes)

# ── Cópia do banco antes da troca ────────────────────────────────────────────
def sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()

_pasta_db = _base / 'app_com_banco'
_pasta_db.mkdir()
_db = _pasta_db / 'financas.db'
_db.write_bytes(b'meses de lancamentos do cliente' * 50)
_sha_db = sha(_db)

_bak1 = atualizador.copiar_banco(_pasta_db, '1.0.0')
check_eq('copia o banco',           _bak1.name, 'financas.db.bak-1.0.0')
check_eq('backup na mesma pasta',   _bak1.parent, _pasta_db)
check_eq('backup tem o conteudo',   sha(_bak1), _sha_db)
check_eq('original intacto',        sha(_db) == _sha_db, True)
check_eq('original continua la',    _db.is_file(), True)

_pasta_sem_db = _base / 'app_sem_banco'
_pasta_sem_db.mkdir()
check_eq('sem banco devolve None',  atualizador.copiar_banco(_pasta_sem_db, '1.0.0') is None, True)
check_eq('sem banco nao cria nada', list(_pasta_sem_db.iterdir()), [])

# segunda cópia: o backup anterior pode ser a única cópia boa, então não é
# sobrescrito. O original muda no meio para a prova ser por hash.
_db.write_bytes(b'lancamentos de hoje')
_bak2 = atualizador.copiar_banco(_pasta_db, '1.0.0')
check_eq('nao sobrescreve backup',   _bak1 != _bak2, True)
check_eq('primeiro backup intacto',  sha(_bak1), _sha_db)
check_eq('segundo backup e o atual', sha(_bak2), sha(_db))
check_eq('dois backups na pasta',    len(list(_pasta_db.glob('financas.db.bak-*'))), 2)

# ── Auxiliar de troca ────────────────────────────────────────────────────────
def montar_instalacao(nome):
    """Pasta parecida com uma instalação de verdade: os 4 itens + o banco."""
    p = _base / nome
    p.mkdir()
    for item in ITENS:
        if item == '_internal':
            (p / '_internal').mkdir()
            (p / '_internal' / 'base.dll').write_bytes(b'dll antiga')
        else:
            (p / item).write_bytes(b'versao antiga de ' + item.encode())
    (p / 'financas.db').write_bytes(b'banco do cliente')
    (p / 'meu_backup_pessoal.zip').write_bytes(b'coisa da pessoa')
    return p

def retrato(pasta):
    """Conteúdo inteiro da pasta, para comparar antes e depois."""
    return sorted((str(q.relative_to(pasta)), q.read_bytes() if q.is_file() else None)
                  for q in Path(pasta).rglob('*'))

_inst = montar_instalacao('instalacao')
_antes_inst = retrato(_inst)
_script = atualizador.gerar_script_troca(4321, _inst, extraido, versao_nova='7.7.7')
_texto = _script.read_text(encoding='utf-8-sig')
_destrutivas = [l for l in _texto.splitlines()
                if 'Remove-Item' in l or 'rd /s' in l or 'rmdir' in l]

check_eq('script cita o pid',        str(4321) in _texto, True)
check_eq('script so toca a lista',   all(i in _texto for i in ITENS), True)
check_eq('script nao cita o banco',  'financas.db' not in _texto, True)
check_eq('script e .ps1',            _script.suffix, '.ps1')
check_eq('script fora da pasta do app',
         str(_inst).lower() in str(_script.parent).lower(), False)
check_eq('script nao e item do programa', _script.name in ITENS, False)
check_eq('script espera o pid sair', 'Get-Process -Id $pidApp' in _texto, True)
check_eq('script move de lado',      '"$atual.old"' in _texto, True)
check_eq('script confere a porta',   '5050' in _texto and 'Responde' in _texto, True)
check_eq('script reabre o programa', 'Start-Process -FilePath $e' in _texto, True)
check_eq('script tem reversao',      _texto.count('Restaurar') >= 2, True)
check_eq('tem linha destrutiva',     len(_destrutivas) > 0, True)
check_eq('nada destrutivo na pasta do app',
         any('$pastaApp' in l or str(_inst) in l for l in _destrutivas), False)
check_eq('sem apagar pasta inteira', '-LiteralPath $pastaApp' in _texto, False)
check_eq('gerar script nao mexe na instalacao', retrato(_inst) == _antes_inst, True)
check_eq('gerar script nao criou .old', list(_inst.glob('*.old')), [])
check_eq('auxiliar dentro do app e recusado',
         recusa(lambda: atualizador.gerar_script_troca(1, _inst, extraido, raiz_temp=_inst / 'tmp')), True)
check_eq('pacote dentro do app e recusado',
         recusa(lambda: atualizador.gerar_script_troca(1, _inst, _inst / 'novo')), True)
# guarda nos dois sentidos: o auxiliar apaga $raizTemp inteira no fim
check_eq('app dentro do temporario e recusado',
         recusa(lambda: atualizador.gerar_script_troca(1, _inst, extraido, raiz_temp=_inst.parent)), True)
check_eq('app dentro do pacote e recusado',
         recusa(lambda: atualizador.gerar_script_troca(1, _inst, _inst.parent)), True)

# o lançador (ITENS[0]) morre em 2s por desenho; quem precisa responder é o
# servidor (ITENS[1]). Desistir porque o lançador saiu revertia troca boa.
check_eq('script acompanha o servidor',
         '$exeServidor' in _texto and 'ProcessosServidor' in _texto, True)
check_eq('script nao desiste pelo lancador sair', 'HasExited' in _texto, False)
check_eq('script usa o esperaResponder',    '$esperaResponder' in _texto, True)
check_eq('script tem periodo de graca',     '$esperaGraca' in _texto, True)
_cauda = _texto[_texto.index('nao respondeu; voltando'):]
check_eq('mata o servidor antes de restaurar',
         _cauda.index('MatarServidor') < _cauda.index('Restaurar'), True)

# 200 na porta não prova nada: tem que ser a versão esperada
check_eq('script pergunta a versao',        '/versao' in _texto, True)
check_eq('script exige a versao nova',      'Responde $versaoNova' in _texto, True)
check_eq('script exige a versao antiga na volta', 'Responde $versaoAntiga' in _texto, True)
check_eq('script nao aceita so o 200',      'return ($r.StatusCode -eq 200)' in _texto, False)
check_eq('script cita a versao nova',       "$versaoNova      = '7.7.7'" in _texto, True)
check_eq('script cita a versao instalada',
         f"$versaoAntiga    = '{versao.VERSAO}'" in _texto, True)

# copia tudo como .new ANTES de renomear: a janela sem executável deixa de ser
# a cópia inteira do _internal e passa a ser duas renomeações
check_eq('copia para .new',  "(Caminho $item) + '.new'" in _texto, True)
check_eq('copia antes de renomear',
         _texto.index('Copy-Item -LiteralPath (Join-Path $pastaNova $item)')
         < _texto.index('-Destination "$atual.old"'), True)
check_eq('renomeia o .new para o nome final',
         'Move-Item -LiteralPath "$atual.new" -Destination $atual' in _texto, True)
# Remove-Item falha num .exe em uso; renomear funciona
check_eq('reversao nao apaga o item em uso',
         'Remove-Item -LiteralPath $atual' in _texto, False)
check_eq('reversao descarta renomeando',    'function Descartar' in _texto, True)
# registro onde a pessoa acha
check_eq('log na pasta do programa',
         "$log             = Join-Path $pastaApp 'atualizacao.log'" in _texto, True)
check_eq('log nao fica no temporario',      "Join-Path $raizTemp 'troca.log'" in _texto, False)
check_eq('temporario sempre apagado',       _texto.count('ApagarTemporario') >= 4, True)

# ── Só a versão instalada instala ────────────────────────────────────────────
# Rodando do código-fonte, pasta_do_app() é a pasta do projeto: aplicar a troca
# ali reescreveria o próprio repositório. A suite roda justamente do fonte, então
# o estado natural aqui é "recusa"; os testes do fluxo normal fingem empacotado.
import contextlib

@contextlib.contextmanager
def finge_empacotado():
    anterior = getattr(sys, 'frozen', None)
    sys.frozen = True
    try:
        yield
    finally:
        if anterior is None:
            del sys.frozen
        else:
            sys.frozen = anterior

check_eq('suite roda do codigo-fonte', atualizador.empacotado(), False)
with finge_empacotado():
    check_eq('finge empacotado funciona', atualizador.empacotado(), True)
check_eq('finge empacotado desfaz', atualizador.empacotado(), False)
check_eq('sys.frozen nao sobrou', hasattr(sys, 'frozen'), False)

_espiao_baixar = []
_baixar_real = atualizador.baixar_pacote

def _baixar_espiao(manifesto, destino, **kw):
    _espiao_baixar.append(Path(destino))
    return _baixar_real(manifesto, destino, **kw)

_app_fonte = montar_instalacao('app_fonte')
_antes_fonte = retrato(_app_fonte)
_temp_fonte = _base / 'temp_fonte'
_temp_fonte.mkdir()
_resposta.update(status=200, corpo=zip_ok.read_bytes())
atualizador.baixar_pacote = _baixar_espiao
_r_fonte = recusa(lambda: atualizador.aplicar_atualizacao(
    {'versao': '9.9.9', 'url': _URL, 'sha256': sha_real},
    pasta_app=_app_fonte, pid=1, raiz_temp=_temp_fonte))
atualizador.baixar_pacote = _baixar_real
check_eq('do fonte a troca e recusada',      _r_fonte, True)
check_eq('do fonte nem baixa o pacote',      _espiao_baixar, [])
check_eq('do fonte nao mexe na instalacao',  retrato(_app_fonte) == _antes_fonte, True)
check_eq('do fonte nao copia o banco',       list(_app_fonte.glob('financas.db.bak*')), [])
check_eq('do fonte nao cria temporario',     list(_temp_fonte.iterdir()), [])

# a outra porta de entrada da troca: quem gerar o script na mão e tentar
# disparar o auxiliar também é recusado fora da versão instalada
_pasta_burla = _base / 'burla'
_pasta_burla.mkdir()
_script_burla = atualizador.gerar_script_troca(1, _app_fonte, extraido, raiz_temp=_pasta_burla)
check_eq('disparo do fonte e recusado',
         recusa(lambda: atualizador._disparar_auxiliar(_script_burla)), True)

# ── aplicar_atualizacao: só instala o que confere ────────────────────────────
_espiao_extrair = []
_extrair_real = atualizador.extrair_pacote

def _extrair_espiao(zp, destino):
    _espiao_extrair.append(Path(destino))
    return _extrair_real(zp, destino)

_resposta.update(status=200, corpo=zip_ok.read_bytes())

# 1) hash diferente: recusa antes de abrir o pacote
_app_hash = montar_instalacao('app_hash_errado')
_antes_hash = retrato(_app_hash)
_temp_hash = _base / 'temp_hash'
_temp_hash.mkdir()
atualizador.extrair_pacote = _extrair_espiao
with finge_empacotado():
    _r_hash = recusa(lambda: atualizador.aplicar_atualizacao(
        {'versao': '9.9.9', 'url': _URL, 'sha256': 'f' * 64},
        pasta_app=_app_hash, pid=1, raiz_temp=_temp_hash))
atualizador.extrair_pacote = _extrair_real
check_eq('hash errado aborta',             _r_hash, True)
check_eq('hash errado nem chega a extrair', _espiao_extrair, [])
check_eq('hash errado nao mexe no app',    retrato(_app_hash) == _antes_hash, True)
check_eq('hash errado nao copia o banco',  list(_app_hash.glob('financas.db.bak*')), [])
check_eq('hash errado nao deixa temporario', list(_temp_hash.iterdir()), [])

# 2) pacote hostil com hash certo: a extração recusa e nada é instalado
_zip_hostil = montar_zip(_base / 'hostil_aplicar.zip', nomes_extra=['../../fora.txt'])
_resposta.update(status=200, corpo=_zip_hostil.read_bytes())
_app_hostil = montar_instalacao('app_hostil')
_antes_hostil = retrato(_app_hostil)
_temp_hostil = _base / 'temp_hostil'
_temp_hostil.mkdir()
with finge_empacotado():
    _r_hostil = recusa(lambda: atualizador.aplicar_atualizacao(
        {'versao': '9.9.9', 'url': _URL, 'sha256': sha(_zip_hostil)},
        pasta_app=_app_hostil, pid=1, raiz_temp=_temp_hostil))
check_eq('pacote hostil aborta',              _r_hostil, True)
check_eq('pacote hostil nao mexe no app',     retrato(_app_hostil) == _antes_hostil, True)
check_eq('pacote hostil nao deixa temporario', list(_temp_hostil.iterdir()), [])

# 3) extração que falha no meio da escrita: pasta da tentativa é descartada
# inteira, e a tentativa seguinte usa outra pasta (nunca reaproveita)
_tentativas = []

def _extrair_pela_metade(zp, destino):
    _tentativas.append(Path(destino))
    Path(destino).mkdir(parents=True, exist_ok=True)
    (Path(destino) / 'metade.dll').write_bytes(b'escrita incompleta')
    raise ValueError('falha no meio da escrita')

_resposta.update(status=200, corpo=zip_ok.read_bytes())
_app_meio = montar_instalacao('app_meio')
_antes_meio = retrato(_app_meio)
_temp_meio = _base / 'temp_meio'
_temp_meio.mkdir()
_manifesto_bom = {'versao': '9.9.9', 'url': _URL, 'sha256': sha_real}
atualizador.extrair_pacote = _extrair_pela_metade
with finge_empacotado():
    _r1 = recusa(lambda: atualizador.aplicar_atualizacao(
        _manifesto_bom, pasta_app=_app_meio, pid=1, raiz_temp=_temp_meio))
    _r2 = recusa(lambda: atualizador.aplicar_atualizacao(
        _manifesto_bom, pasta_app=_app_meio, pid=1, raiz_temp=_temp_meio))
atualizador.extrair_pacote = _extrair_real
check_eq('extracao pela metade aborta',    _r1 is True and _r2 is True, True)
check_eq('cada tentativa em pasta nova',
         len(_tentativas) == 2 and _tentativas[0] != _tentativas[1], True)
check_eq('extracao pela metade descartada', list(_temp_meio.iterdir()), [])
check_eq('extracao pela metade nao mexe no app', retrato(_app_meio) == _antes_meio, True)
check_eq('extrair_pacote devolvido ao original', atualizador.extrair_pacote is _extrair_real, True)

# ── Disparo do auxiliar (script inofensivo, só escreve um arquivo) ───────────
# DETACHED_PROCESS faz o powershell.exe sair com 0 sem rodar nada: este teste
# existe para a troca nunca mais sair daqui sem ninguém para executá-la.
_pasta_disparo = _base / 'disparo'
_pasta_disparo.mkdir()
_ps_inofensivo = _pasta_disparo / 'inofensivo.ps1'
_ps_inofensivo.write_text(
    "Set-Content -LiteralPath (Join-Path $PSScriptRoot 'prova.txt') -Value 'rodou' -Encoding utf8\n",
    encoding='utf-8-sig')
_prova = _pasta_disparo / 'prova.txt'
try:
    with finge_empacotado():
        _proc = atualizador._disparar_auxiliar(_ps_inofensivo)
    _proc.wait(timeout=30)
    _rc = _proc.returncode
except Exception as e:
    _rc = f'levantou {e!r}'
check_eq('auxiliar disparado sai bem',   _rc, 0)
check_eq('auxiliar realmente executou',  _prova.is_file() and 'rodou' in _prova.read_text(encoding='utf-8-sig'), True)
check_eq('disparo sem janela',           bool(atualizador._flags_auxiliar() & 0x08000000), True)
check_eq('disparo em grupo proprio',     bool(atualizador._flags_auxiliar() & 0x00000200), True)
check_eq('disparo sem DETACHED_PROCESS', bool(atualizador._flags_auxiliar() & 0x00000008), False)
check_eq('powershell por caminho absoluto',
         atualizador._powershell().lower().endswith('system32\\windowspowershell\\v1.0\\powershell.exe'), True)
check_eq('powershell existe no disco',  Path(atualizador._powershell()).is_file(), True)

# ── O auxiliar rodando de verdade, numa instalação de mentira ────────────────
# Os greps acima não executam nada. Aqui o .ps1 gerado roda de ponta a ponta
# contra uma pasta falsa, com um "servidor" nosso numa porta livre (nunca 5050).

class ServidorFalso:
    """Faz as vezes do app na porta. `versao=None` é o impostor: responde 200
    na raiz e não sabe dizer a versão, como qualquer outro programa faria.

    `certo_apos=N`: as N primeiras perguntas levam a versão errada. Emula a
    máquina lenta (antivírus analisando DLL nova) sem depender de relógio.
    """

    def __init__(self, versao=None, certo_apos=0):
        self.versao = versao
        self.certo_apos = certo_apos
        self.perguntas = 0
        dono = self

        class Alca(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/versao'):
                    if dono.versao is None:
                        self.send_response(404)
                        self.end_headers()
                        return
                    dono.perguntas += 1
                    qual = (dono.versao if dono.perguntas > dono.certo_apos
                            else '0.0.1')
                    corpo = json.dumps({'versao': qual}).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(corpo)))
                    self.end_headers()
                    self.wfile.write(corpo)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ok')

            def log_message(self, *a):
                pass

        self.http = HTTPServer(('127.0.0.1', 0), Alca)
        self.porta = self.http.server_port
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def parar(self):
        try:
            self.http.shutdown()
        except Exception:
            pass

# lançador de mentira: um exe de verdade que abre e fecha na hora, como o
# lançador real (que sai em 2s por desenho)
_EXE_CURTO = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'hostname.exe'

def _lancador(destino, marca):
    """Copia do hostname.exe com uma marca no fim: roda igual e dá para
    distinguir a cópia nova da antiga (o carregador PE ignora o rabo)."""
    destino.write_bytes(_EXE_CURTO.read_bytes() + b'\n@@' + marca)

def montar_fake(nome, marca):
    """Pasta no formato de uma instalação: 4 itens, o banco e um arquivo da pessoa."""
    p = _base / nome
    p.mkdir()
    _lancador(p / ITENS[0], marca)                    # lançador: abre e sai
    (p / ITENS[1]).write_bytes(marca + b' servidor')  # servidor (nao roda, so conteudo)
    (p / '_internal').mkdir()
    (p / '_internal' / 'base.dll').write_bytes(marca + b' dll')
    (p / '_internal' / 'sub').mkdir()
    (p / '_internal' / 'sub' / 'x.pyd').write_bytes(marca + b' pyd')
    (p / 'LEIA-ME.txt').write_bytes(marca + b' leia-me')
    (p / 'financas.db').write_bytes(b'meses de lancamentos' * 40)
    (p / 'meu_backup.zip').write_bytes(b'coisa da pessoa')
    return p

def montar_pacote_novo(nome, marca):
    p = _base / nome
    p.mkdir()
    _lancador(p / ITENS[0], marca)
    (p / ITENS[1]).write_bytes(marca + b' servidor')
    (p / '_internal').mkdir()
    (p / '_internal' / 'base.dll').write_bytes(marca + b' dll')
    (p / '_internal' / 'sub').mkdir()
    (p / '_internal' / 'sub' / 'x.pyd').write_bytes(marca + b' pyd')
    (p / 'LEIA-ME.txt').write_bytes(marca + b' leia-me')
    return p

def conteudos(pasta):
    """Conteúdo de cada um dos 4 itens, para comparar antes e depois."""
    p = Path(pasta)
    return {
        'lancador': (p / ITENS[0]).read_bytes()[-12:],
        'servidor': (p / ITENS[1]).read_bytes(),
        'dll':      (p / '_internal' / 'base.dll').read_bytes(),
        'pyd':      (p / '_internal' / 'sub' / 'x.pyd').read_bytes(),
        'leiame':   (p / 'LEIA-ME.txt').read_bytes(),
    }

def esperar(cond, segundos=25):
    fim = time.time() + segundos
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.3)
    return bool(cond())

def rodar_auxiliar(pasta_app, pasta_nova, raiz, porta, versao_nova, esperas):
    """Gera o .ps1, dispara e espera ele terminar. Devolve (codigo, texto do log)."""
    # pid de um processo curto de verdade: a espera pelo encerramento é exercida
    dorminhoco = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'],
                                  creationflags=0x08000000)
    script = atualizador.gerar_script_troca(
        dorminhoco.pid, pasta_app, pasta_nova, raiz_temp=raiz,
        versao_nova=versao_nova, porta=porta, esperas=esperas)
    with finge_empacotado():
        proc = atualizador._disparar_auxiliar(script)
    try:
        proc.wait(timeout=240)
    except subprocess.TimeoutExpired:
        proc.kill()
        return 'estourou o tempo', ''
    dorminhoco.wait(timeout=30)
    log = Path(pasta_app) / 'atualizacao.log'
    return proc.returncode, (log.read_text(encoding='utf-8', errors='replace') if log.is_file() else '')

# 1) Caminho de sucesso numa máquina lenta: o lançador abre e sai na hora (como
# o real, que sai em 2s por desenho) e o servidor só diz a versão nova na quarta
# pergunta. Se o auxiliar desistisse porque o lançador saiu, esta troca boa
# seria revertida — foi o defeito C1.
_app_ok = montar_fake('e2e_ok', b'ANTIGA')
_novo_ok = montar_pacote_novo('e2e_ok_pacote', b'NOVA')
_antes_ok = conteudos(_app_ok)
_sha_db_ok = sha(_app_ok / 'financas.db')
_raiz_ok = _base / 'e2e_ok_temp'
_srv_ok = ServidorFalso(versao='9.9.9', certo_apos=3)
_cod_ok, _log_ok = rodar_auxiliar(_app_ok, _novo_ok, _raiz_ok, _srv_ok.porta, '9.9.9',
                                  {'fechar': 25, 'responder': 60, 'graca': 40, 'volta': 6})
_srv_ok.parar()
check_eq('e2e sucesso: insistiu depois do lancador sair',
         _srv_ok.perguntas >= 4, True)
_depois_ok = conteudos(_app_ok)

check_eq('e2e sucesso: codigo 0',          _cod_ok, 0)
check_eq('e2e sucesso: lancador novo',     _depois_ok['lancador'].endswith(b'@@NOVA'), True)
check_eq('e2e sucesso: lancador trocou',   _depois_ok['lancador'] != _antes_ok['lancador'], True)
check_eq('e2e sucesso: servidor novo',     _depois_ok['servidor'], b'NOVA servidor')
check_eq('e2e sucesso: dll nova',          _depois_ok['dll'], b'NOVA dll')
check_eq('e2e sucesso: subpasta nova',     _depois_ok['pyd'], b'NOVA pyd')
check_eq('e2e sucesso: leia-me novo',      _depois_ok['leiame'], b'NOVA leia-me')
check_eq('e2e sucesso: nao sobrou .old',   list(_app_ok.glob('*.old')), [])
check_eq('e2e sucesso: nao sobrou .new',   list(_app_ok.glob('*.new')), [])
check_eq('e2e sucesso: banco intacto',     sha(_app_ok / 'financas.db'), _sha_db_ok)
check_eq('e2e sucesso: arquivo da pessoa intacto',
         (_app_ok / 'meu_backup.zip').read_bytes(), b'coisa da pessoa')
check_eq('e2e sucesso: esperou a versao certa',
         'versao 9.9.9 respondeu' in _log_ok, True)
check_eq('e2e sucesso: log na pasta do programa',
         (_app_ok / 'atualizacao.log').is_file(), True)
check_eq('e2e sucesso: temporario apagado',
         esperar(lambda: not _raiz_ok.exists()), True)

# 2) Caminho de reversão com um IMPOSTOR na porta: responde 200 na raiz e não
# sabe dizer a versão (outra cópia instalada, servidor velho, qualquer coisa).
# Antes isso valia como "deu certo" e os .old eram apagados.
_app_rb = montar_fake('e2e_rb', b'ANTIGA')
_novo_rb = montar_pacote_novo('e2e_rb_pacote', b'NOVA')
_antes_rb = conteudos(_app_rb)
_sha_db_rb = sha(_app_rb / 'financas.db')
_raiz_rb = _base / 'e2e_rb_temp'
_srv_rb = ServidorFalso(versao=None)             # impostor
_cod_rb, _log_rb = rodar_auxiliar(_app_rb, _novo_rb, _raiz_rb, _srv_rb.porta, '9.9.9',
                                  {'fechar': 25, 'responder': 14, 'graca': 5, 'volta': 5})
_srv_rb.parar()
_depois_rb = conteudos(_app_rb)

check_eq('e2e reversao: codigo 1',           _cod_rb, 1)
check_eq('e2e reversao: impostor nao conta',
         'nao respondeu' in _log_rb and 'respondeu; apagando' not in _log_rb, True)
check_eq('e2e reversao: conteudo antigo de volta', _depois_rb, _antes_rb)
check_eq('e2e reversao: nao sobrou .old',    list(_app_rb.glob('*.old')), [])
check_eq('e2e reversao: nao sobrou .new',    list(_app_rb.glob('*.new')), [])
check_eq('e2e reversao: banco intacto',      sha(_app_rb / 'financas.db'), _sha_db_rb)
check_eq('e2e reversao: arquivo da pessoa intacto',
         (_app_rb / 'meu_backup.zip').read_bytes(), b'coisa da pessoa')
check_eq('e2e reversao: lancador antigo de volta',
         _depois_rb['lancador'].endswith(b'@@ANTIGA'), True)
check_eq('e2e reversao: log conta a reversao', 'reversao concluida' in _log_rb, True)
check_eq('e2e reversao: temporario apagado',
         esperar(lambda: not _raiz_rb.exists()), True)

_srv.shutdown()

# ── Portão da rota /atualizar: endereço, origem e senha da janela ────────────
flask_app.DATABASE = tempfile.mktemp(suffix='_test.db')
flask_app.app.config['TESTING'] = True
flask_app.init_db()
c = flask_app.app.test_client()
TOKEN = flask_app.TOKEN_ATUALIZACAO
ORIGEM = 'http://localhost'     # host do test_client

def postar(addr='127.0.0.1', origem=ORIGEM, referer=None, token=TOKEN):
    cab = {}
    if origem is not None:
        cab['Origin'] = origem
    if referer is not None:
        cab['Referer'] = referer
    dados = {} if token is None else {'token': token}
    return c.post('/atualizar', environ_base={'REMOTE_ADDR': addr},
                  headers=cab, data=dados)

# o disparo de verdade fica fora do teste: aqui só interessa o portão
_disparos = []
flask_app._disparar_atualizacao = lambda manifesto: _disparos.append(manifesto)

check_eq('celular na rede recusado',    postar(addr='192.168.0.50').status_code, 403)
check_eq('sem token recusado',          postar(token=None).status_code, 403)
check_eq('token vazio recusado',        postar(token='').status_code, 403)
check_eq('token errado recusado',       postar(token='x' * 43).status_code, 403)
check_eq('origem estranha recusada',    postar(origem='http://site.mau').status_code, 403)
check_eq('referer estranho recusado',   postar(origem=None, referer='http://site.mau/x').status_code, 403)
check_eq('sem origem nem referer recusado', postar(origem=None).status_code, 403)
check_eq('origem sem http recusada',    postar(origem='file:///c:/x').status_code, 403)
# compare_digest levanta TypeError fora do ASCII: é recusa, não erro 500
check_eq('token com acento recusado',   postar(token='café' + 'x' * 40).status_code, 403)
check_eq('token com emoji recusado',    postar(token='x' * 40 + '\U0001f600').status_code, 403)
check_eq('nada disparado nas recusas',  _disparos, [])

# rodando do código-fonte (como esta suite): passa o portão e a rota recusa
flask_app._atualizacao = {'versao': '9.9.9', 'url': 'http://x/p.zip', 'sha256': 'y'}
_do_fonte = postar()
_erro_fonte = (_do_fonte.get_json() or {}).get('erro', '')   # pode não ser JSON
check_eq('rota recusa fora da versao instalada', _do_fonte.status_code, 409)
check_eq('rota explica o motivo', 'versão instalada' in _erro_fonte, True)
check_eq('rota do fonte nao disparou',  _disparos, [])
flask_app._atualizacao = None

# daqui para baixo os testes fingem a versão instalada
sys.frozen = True

# token e origem certos, mas nada a instalar: passa o portão e recusa depois
check_eq('sem novidade nao instala',    postar().status_code, 409)
check_eq('ipv6 localhost passa o portao', postar(addr='::1').status_code, 409)
check_eq('referer proprio passa o portao',
         postar(origem=None, referer=ORIGEM + '/bills').status_code, 409)
check_eq('nada disparado sem novidade', _disparos, [])

# caminho feliz
flask_app._atualizacao = {'versao': '9.9.9', 'url': 'http://x/p.zip', 'sha256': 'y'}
_ok = postar()
check_eq('caminho feliz aceito',        _ok.status_code, 200)
check_eq('caminho feliz mostra a pagina', b'Instalando a atualiza' in _ok.data, True)
check_eq('caminho feliz cita a versao nova', b'9.9.9' in _ok.data, True)
check_eq('caminho feliz disparou uma vez', len(_disparos), 1)
check_eq('caminho feliz com o manifesto',
         (_disparos[0] if _disparos else {}).get('versao'), '9.9.9')
check_eq('pagina de espera nao consulta o servidor',
         b'fetch(' not in _ok.data and b'setTimeout' not in _ok.data
         and b'http-equiv="refresh"' not in _ok.data, True)
check_eq('pagina de espera nao pede arquivo externo',
         b'<script' not in _ok.data and b'<link' not in _ok.data, True)
check_eq('segundo clique recusado',     postar().status_code, 409)
check_eq('segundo clique nao disparou', len(_disparos), 1)
flask_app._liberar_atualizacao()
check_eq('token por cabecalho tambem serve',
         c.post('/atualizar', environ_base={'REMOTE_ADDR': '127.0.0.1'},
                headers={'Origin': ORIGEM, 'X-Token-Atualizacao': TOKEN}).status_code, 200)
flask_app._liberar_atualizacao()
check_eq('token e longo',               len(TOKEN) >= 32, True)
flask_app._atualizacao = None

# ── Faixa de aviso na página ─────────────────────────────────────────────────
check_eq('sem aviso sem faixa', b'alerta-atualizacao' in c.get('/').data, False)
flask_app._atualizacao = {'versao': '9.9.9', 'url': 'x', 'sha256': 'y', 'notas': 'Notas de teste'}
_html = c.get('/').data
check_eq('faixa aparece',       b'alerta-atualizacao' in _html and b'9.9.9' in _html, True)
check_eq('faixa mostra notas',  b'Notas de teste' in _html, True)
check_eq('faixa manda a senha', TOKEN.encode() in _html, True)
check_eq('faixa posta por formulario',
         b'<form method="post" action="/atualizar"' in _html, True)
# no celular a faixa avisa, mas sem botao e sem senha
_html_fora = c.get('/', environ_base={'REMOTE_ADDR': '192.168.0.50'}).data
check_eq('faixa aparece no celular',    b'alerta-atualizacao' in _html_fora, True)
check_eq('celular sem botao',           b'btn-atualizar' in _html_fora, False)
check_eq('celular sem a senha',         TOKEN.encode() in _html_fora, False)

# fim do faz de conta: do código-fonte a faixa aparece, mas sem botão
del sys.frozen
_html_fonte = c.get('/').data
check_eq('faixa aparece rodando do fonte', b'alerta-atualizacao' in _html_fonte, True)
check_eq('fonte sem botao',                b'btn-atualizar' in _html_fonte, False)
check_eq('fonte sem a senha',              TOKEN.encode() in _html_fonte, False)
check_eq('fonte explica o motivo',
         'só na versão instalada'.encode() in _html_fonte, True)

flask_app._atualizacao = None
check_eq('sem faixa a senha nao aparece', TOKEN.encode() in c.get('/').data, False)
# ── /versao: é por aqui que o auxiliar sabe quem está atendendo na porta ─────
_r_versao = c.get('/versao')
check_eq('rota /versao responde 200',   _r_versao.status_code, 200)
check_eq('rota /versao diz a versao',   (_r_versao.get_json() or {}).get('versao'), versao.VERSAO)
check_eq('rota /versao e json',         'json' in (_r_versao.headers.get('Content-Type') or ''), True)

# ── Página de espera: sincera sobre o que fazer se nada acontecer ────────────
flask_app._atualizacao = {'versao': '9.9.9', 'url': 'x', 'sha256': 'y'}
sys.frozen = True
_pag = postar()
del sys.frozen
flask_app._liberar_atualizacao()
flask_app._atualizacao = None
check_eq('pagina de espera cita o log',   b'atualizacao.log' in _pag.data, True)
check_eq('pagina de espera diz o prazo',  'cinco minutos'.encode() in _pag.data, True)
check_eq('pagina de espera diz o que fazer',
         'atalho de sempre'.encode() in _pag.data, True)
check_eq('log do app fica na pasta de dados',
         Path(flask_app.ARQUIVO_LOG_ATUALIZACAO).name, 'atualizacao.log')

_js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'script.js'), encoding='utf-8').read()
check_eq('auto-dismiss exclui faixa', ".alert.fade.show:not(.alerta-atualizacao)" in _js, True)

def _imprimir(texto):
    """Imprime sem quebrar o console: cp1252 nao aceita todo caractere."""
    try:
        print(texto)
    except UnicodeEncodeError:
        cod = getattr(sys.stdout, 'encoding', None) or 'ascii'
        print(texto.encode(cod, 'replace').decode(cod, 'replace'))


# ── Resultado ─────────────────────────────────────────────────────────────────
passed  = sum(1 for _, s, _ in results if s == 'PASS')
failed  = [(n, s, c) for n, s, c in results if s != 'PASS']
total   = len(results)

_imprimir(f"\n{'='*62}")
_imprimir(f"  RESULTADO FINAL: {passed}/{total} passaram")
_imprimir(f"{'='*62}")
for name, status, code in results:
    icon = 'OK' if status == 'PASS' else 'XX'
    _imprimir(f"  {icon} {name:<40} {code}")
if failed:
    _imprimir("\n  -- FALHAS --")
    for name, status, code in failed:
        _imprimir(f"  XX {name}: {status}")
else:
    _imprimir("\n  Nenhuma falha encontrada.")
_imprimir(f"{'='*62}\n")
sys.exit(1 if failed else 0)
