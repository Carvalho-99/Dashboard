"""Testa a versão e a comparação de versões do Organizador Financeiro."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tempfile, threading, hashlib, zipfile
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
_srv.shutdown()

# ── Origem da rota /atualizar ────────────────────────────────────────────────
flask_app.DATABASE = tempfile.mktemp(suffix='_test.db')
flask_app.app.config['TESTING'] = True
flask_app.init_db()
c = flask_app.app.test_client()
de_fora = c.post('/atualizar', environ_base={'REMOTE_ADDR': '192.168.0.50'})
de_casa = c.post('/atualizar', environ_base={'REMOTE_ADDR': '127.0.0.1'})
de_casa6 = c.post('/atualizar', environ_base={'REMOTE_ADDR': '::1'})
check_eq('celular na rede recusado', de_fora.status_code, 403)
check_eq('localhost aceito',         de_casa.status_code != 403, True)
check_eq('ipv6 localhost aceito',    de_casa6.status_code != 403, True)

# ── Faixa de aviso na página ─────────────────────────────────────────────────
check_eq('sem aviso sem faixa', b'alerta-atualizacao' in c.get('/').data, False)
flask_app._atualizacao = {'versao': '9.9.9', 'url': 'x', 'sha256': 'y', 'notas': 'Notas de teste'}
_html = c.get('/').data
check_eq('faixa aparece',       b'alerta-atualizacao' in _html and b'9.9.9' in _html, True)
check_eq('faixa mostra notas',  b'Notas de teste' in _html, True)
flask_app._atualizacao = None
_js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'script.js'), encoding='utf-8').read()
check_eq('auto-dismiss exclui faixa', ".alert.fade.show:not(.alerta-atualizacao)" in _js, True)

# ── Resultado ─────────────────────────────────────────────────────────────────
passed  = sum(1 for _, s, _ in results if s == 'PASS')
failed  = [(n, s, c) for n, s, c in results if s != 'PASS']
total   = len(results)

print(f"\n{'='*62}")
print(f"  RESULTADO FINAL: {passed}/{total} passaram")
print(f"{'='*62}")
for name, status, code in results:
    icon = 'OK' if status == 'PASS' else 'XX'
    print(f"  {icon} {name:<40} {code}")
if failed:
    print(f"\n  ── FALHAS ──")
    for name, status, code in failed:
        print(f"  XX {name}: {status}")
else:
    print(f"\n  Nenhuma falha encontrada.")
print(f"{'='*62}\n")
sys.exit(1 if failed else 0)
