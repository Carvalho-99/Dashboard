"""Testa a versão e a comparação de versões do Organizador Financeiro."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import versao

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
