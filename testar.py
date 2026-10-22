"""Testa todas as rotas do Organizador Financeiro."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import app as flask_app
from datetime import datetime

# Banco temporário para o teste
test_db = tempfile.mktemp(suffix='_test.db')
flask_app.DATABASE = test_db
flask_app.app.config['TESTING'] = True
flask_app.app.config['WTF_CSRF_ENABLED'] = False
flask_app.init_db()

client = flask_app.app.test_client()
results = []
now = datetime.now()

def check(name, method, url, data=None):
    try:
        if method == 'GET':
            r = client.get(url, follow_redirects=True)
        else:
            r = client.post(url, data=data, follow_redirects=True)
        ok = r.status_code < 400
        results.append((name, 'PASS' if ok else 'FAIL', r.status_code))
        return r
    except Exception as e:
        results.append((name, f'ERRO: {e}', 0))
        return None

def db_query(sql, params=()):
    with flask_app.app.app_context():
        conn = flask_app.get_db()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows

# ── Usuários ──────────────────────────────────────────────────────────────────
check('GET  /users',         'GET',  '/users')
check('POST /users/add (1)', 'POST', '/users/add', {'name': 'Bruno',   'color': '#3b82f6'})
check('POST /users/add (2)', 'POST', '/users/add', {'name': 'Melissa', 'color': '#ec4899'})

users = db_query("SELECT id FROM users ORDER BY id")
uid1 = users[0]['id']; uid2 = users[1]['id']

check('GET  /switch user',  'GET', f'/switch/{uid1}')
check('GET  /switch todos', 'GET', '/switch/0')

# ── Rendas ────────────────────────────────────────────────────────────────────
check('GET  /incomes',           'GET',  '/incomes')
check('GET  /incomes/add',       'GET',  '/incomes/add')
check('POST /incomes/add salary','POST', '/incomes/add',
      {'name':'Salário','amount':'3000','day_of_month':'5','type':'salary','notes':'','owner_id':str(uid1)})
check('POST /incomes/add vale',  'POST', '/incomes/add',
      {'name':'Vale','amount':'500','day_of_month':'20','type':'vale','notes':'','owner_id':str(uid1)})

incomes = db_query("SELECT id FROM incomes ORDER BY id")
inc_id = incomes[0]['id']

check('GET  /incomes/edit',  'GET',  f'/incomes/edit/{inc_id}')
check('POST /incomes/edit',  'POST', f'/incomes/edit/{inc_id}',
      {'name':'Salário Bruno','amount':'3000','day_of_month':'5','type':'salary','notes':'','owner_id':str(uid1)})
check('POST /incomes/delete','POST', f'/incomes/delete/{incomes[1]["id"]}')

# ── Contas ────────────────────────────────────────────────────────────────────
check('GET  /bills',         'GET',  '/bills')
check('GET  /bills/add',     'GET',  '/bills/add')
check('POST /bills/add (1)', 'POST', '/bills/add',
      {'name':'Aluguel','amount':'1200','due_day':'10','category':'moradia',
       'priority':'1','is_recurring':'on','notes':'','owner_id':str(uid1)})
check('POST /bills/add (2)', 'POST', '/bills/add',
      {'name':'Netflix','amount':'45','due_day':'15','category':'lazer',
       'priority':'4','is_recurring':'on','notes':'','owner_id':str(uid1)})
check('POST /bills/add (encerramento)', 'POST', '/bills/add',
      {'name':'Parcela carro','amount':'300','due_day':'8','category':'transporte',
       'priority':'2','is_recurring':'on','notes':'','owner_id':str(uid1),
       'has_end_date':'on','end_month':'8','end_year':'2026'})

bills = db_query("SELECT id FROM bills ORDER BY id")
bill_id1 = bills[0]['id']; bill_id2 = bills[1]['id']; bill_id3 = bills[2]['id']

check('GET  /bills/edit',  'GET',  f'/bills/edit/{bill_id1}')
check('POST /bills/edit',  'POST', f'/bills/edit/{bill_id1}',
      {'name':'Aluguel','amount':'1250','due_day':'10','category':'moradia',
       'priority':'1','is_recurring':'on','notes':'editado','owner_id':str(uid1)})

# ── Parcelas ──────────────────────────────────────────────────────────────────
check('POST /bills/add (parcelado)', 'POST', '/bills/add',
      {'name':'Financiamento','amount':'500','due_day':'20','category':'financeiro',
       'priority':'2','is_recurring':'on','notes':'','owner_id':str(uid1),
       'has_installments':'on','total_installments':'3'})

bills2 = db_query("SELECT id FROM bills ORDER BY id")
bill_installment_id = bills2[-1]['id']

# ── Pagamentos ─────────────────────────────────────────────────────────────────
check('POST /pay/quick',    'POST', '/pay/quick',
      {'bill_id':str(bill_id1),'month':str(now.month),'year':str(now.year)})
check('POST /unpay',        'POST', '/unpay',
      {'bill_id':str(bill_id1),'month':str(now.month),'year':str(now.year)})
check('POST /pay (modal)',  'POST', '/pay',
      {'bill_id':str(bill_id1),'month':str(now.month),'year':str(now.year),
       'amount_paid':'1250','paid_date':f'{now.year}-{now.month:02d}-10','income_source':'Salário Bruno'})
check('POST /pay/all',      'POST', '/pay/all',
      {'month':str(now.month),'year':str(now.year)})
# adiantar 2 meses do financiamento
next_month = now.month % 12 + 1
next_year  = now.year + (1 if now.month == 12 else 0)
after_month = next_month % 12 + 1
after_year  = next_year + (1 if next_month == 12 else 0)
check('POST /pay/advance',  'POST', '/pay/advance',
      {'bill_id':str(bill_installment_id),
       'months[]':[str(next_month),str(after_month)],
       'years[]':[str(next_year),str(after_year)],
       'amounts[]':['500.00','510.00']})

# ── Dashboard / Planejador / Sugestões ────────────────────────────────────────
check('GET  /',            'GET', '/')
check('GET  /planner',     'GET', '/planner')
check('GET  /suggestions', 'GET', '/suggestions')
check('GET  /suggestions?month=12', 'GET', f'/suggestions?month=12&year={now.year}')

# ── Casais ────────────────────────────────────────────────────────────────────
check('GET  /couple (sem casal)', 'GET', '/couple')
check('GET  /couples',            'GET', '/couples')
check('POST /couples/add',        'POST', '/couples/add',
      {'name':'Bruno & Melissa','member_ids':[str(uid1),str(uid2)]})

couples = db_query("SELECT id FROM couples ORDER BY id")
couple_id = couples[0]['id']

check('GET  /switch-couple', 'GET', f'/switch-couple/{couple_id}')
check('GET  /couple (com casal)', 'GET', '/couple')

# Conta compartilhada do casal
check('POST /bills/add (casal)', 'POST', '/bills/add',
      {'name':'Supermercado','amount':'800','due_day':'5','category':'alimentacao',
       'priority':'2','is_recurring':'on','notes':'','owner_id':f'couple_{couple_id}'})

check('GET  /couple (com conta)', 'GET', '/couple')

# ── Histórico / Configurações ─────────────────────────────────────────────────
check('GET  /history',    'GET',  '/history')
check('GET  /settings',   'GET',  '/settings')
check('POST /settings',   'POST', '/settings',
      {'reserve_amount':'400','savings_goal':'300'})

# ── API ───────────────────────────────────────────────────────────────────────
check('GET  /api/chart-data', 'GET', '/api/chart-data')

# ── Delete ────────────────────────────────────────────────────────────────────
check('POST /bills/delete',   'POST', f'/bills/delete/{bill_id3}')
check('POST /couples/delete', 'POST', f'/couples/delete/{couple_id}')
check('POST /users/delete',   'POST', f'/users/delete/{uid2}')

# ── Formato pt-BR ─────────────────────────────────────────────
def check_eq(name, got, want):
    ok = got == want
    results.append((name, 'PASS' if ok else f'FAIL: {got!r} != {want!r}', '-'))

# Regressao: valor com separador de milhar precisa ser salvo certo.
# Antes, float('4.500,00'.replace(',','.')) estourava com erro 500.
check('POST /bills/add (milhar)', 'POST', '/bills/add',
      {'name':'Aluguel caro','amount':'4.500,00','due_day':'5','category':'moradia',
       'priority':'1','is_recurring':'on','notes':'','owner_id':str(uid1)})
_milhar = db_query("SELECT amount FROM bills WHERE name = 'Aluguel caro'")
check_eq('milhar salvo como 4500', _milhar[0]['amount'] if _milhar else None, 4500.0)

check('POST /incomes/add (milhar)', 'POST', '/incomes/add',
      {'name':'Salario alto','amount':'12.345,67','day_of_month':'5',
       'type':'salary','notes':'','owner_id':str(uid1)})
_sal = db_query("SELECT amount FROM incomes WHERE name = 'Salario alto'")
check_eq('renda milhar salva', _sal[0]['amount'] if _sal else None, 12345.67)

check_eq('brl centavos',      flask_app.format_brl(300),       '300,00')
check_eq('brl milhar',        flask_app.format_brl(4500),      '4.500,00')
check_eq('brl milhao',        flask_app.format_brl(1234567.89), '1.234.567,89')
check_eq('brl quebrado',      flask_app.format_brl(1234.5),    '1.234,50')
check_eq('brl zero',          flask_app.format_brl(0),         '0,00')
check_eq('brl None',          flask_app.format_brl(None),      '0,00')
check_eq('brl negativo',      flask_app.format_brl(-1234.56),  '-1.234,56')
check_eq('brl arredonda',     flask_app.format_brl(0.005),     '0,01')
check_eq('mes janeiro',       flask_app.MESES_PT[1],           'Janeiro')
check_eq('mes outubro',       flask_app.MESES_PT[10],          'Outubro')
check_eq('mes dezembro',      flask_app.MESES_PT[12],          'Dezembro')

# ── Limpeza ────────────────────────────────────────────────────────────────────
try:
    os.unlink(test_db)
except Exception:
    pass

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
        print(f"  XX {name}: {status} (HTTP {code})")
else:
    print(f"\n  Nenhuma falha encontrada.")
print(f"{'='*62}\n")
