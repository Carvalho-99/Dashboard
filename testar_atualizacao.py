"""Testa a versão e a comparação de versões do Organizador Financeiro."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tempfile, threading
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
