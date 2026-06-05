from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
from datetime import datetime, date
import calendar
import socket
import os
import json

import sys

# Quando empacotado com PyInstaller: templates/static ficam em _MEIPASS,
# o banco de dados fica ao lado do .exe (DATA_DIR)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    DATA_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BASE_DIR

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = 'financeiro_bruno_melissa_2024'

DATABASE = os.path.join(DATA_DIR, 'financas.db')

CATEGORIES = {
    'moradia':     ('Moradia',     'house-door',    '#ef4444'),
    'alimentacao': ('Alimentação', 'basket2',       '#f59e0b'),
    'transporte':  ('Transporte',  'car-front',     '#3b82f6'),
    'saude':       ('Saúde',       'heart-pulse',   '#10b981'),
    'educacao':    ('Educação',    'book',          '#8b5cf6'),
    'lazer':       ('Lazer',       'controller',    '#ec4899'),
    'servicos':    ('Serviços',    'wifi',          '#06b6d4'),
    'financeiro':  ('Financeiro',  'credit-card',   '#f97316'),
    'outros':      ('Outros',      'box-seam',      '#6b7280'),
}

PRIORITIES = {
    1: ('Crítico',    'danger'),
    2: ('Importante', 'warning'),
    3: ('Normal',     'primary'),
    4: ('Opcional',   'secondary'),
}

INCOME_TYPES = {
    'salary': 'Salário',
    'vale':   'Vale',
    'other':  'Outro',
}

USER_COLORS = ['#3b82f6', '#ec4899', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4', '#f97316', '#ef4444']


# ==================== DB ====================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            color      TEXT DEFAULT '#3b82f6',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS couples (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS couple_members (
            couple_id INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            PRIMARY KEY (couple_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS incomes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            amount       REAL    NOT NULL,
            day_of_month INTEGER NOT NULL,
            type         TEXT    DEFAULT 'other',
            notes        TEXT,
            user_id      INTEGER DEFAULT 0,
            active       INTEGER DEFAULT 1,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bills (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            amount       REAL    NOT NULL,
            due_day      INTEGER NOT NULL,
            category     TEXT    DEFAULT 'outros',
            priority     INTEGER DEFAULT 3,
            is_recurring INTEGER DEFAULT 1,
            notes        TEXT,
            user_id      INTEGER DEFAULT 0,
            couple_id    INTEGER DEFAULT NULL,
            active       INTEGER DEFAULT 1,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id       INTEGER,
            bill_name     TEXT,
            amount_paid   REAL,
            paid_date     TEXT,
            month         INTEGER,
            year          INTEGER,
            income_source TEXT,
            notes         TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    ''')

    # Safe migrations for existing databases
    for col_def in [
        ("bills",   "couple_id INTEGER DEFAULT NULL"),
        ("bills",   "user_id INTEGER DEFAULT 0"),
        ("bills",   "end_month INTEGER DEFAULT NULL"),
        ("bills",   "end_year INTEGER DEFAULT NULL"),
        ("bills",   "total_installments INTEGER DEFAULT NULL"),
        ("incomes", "user_id INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {col_def[0]} ADD COLUMN {col_def[1]}")
        except Exception:
            pass

    conn.execute("INSERT OR IGNORE INTO settings VALUES ('reserve_amount', '300')")
    conn.execute("INSERT OR IGNORE INTO settings VALUES ('savings_goal', '0')")
    conn.commit()
    conn.close()


def get_bill_pay_counts(bill_ids):
    if not bill_ids:
        return {}
    conn = get_db()
    ph = ','.join('?' * len(bill_ids))
    rows = conn.execute(
        f"SELECT bill_id, COUNT(*) as cnt FROM payments WHERE bill_id IN ({ph}) GROUP BY bill_id",
        list(bill_ids)
    ).fetchall()
    conn.close()
    return {r['bill_id']: r['cnt'] for r in rows}


def _auto_deactivate_if_done(conn, bill, bill_id):
    """Deactivate bill if all installments have been paid."""
    ti = bill['total_installments']
    if ti:
        total_paid = conn.execute(
            "SELECT COUNT(*) as cnt FROM payments WHERE bill_id=?", (bill_id,)
        ).fetchone()['cnt']
        if total_paid >= ti:
            conn.execute("UPDATE bills SET active=0 WHERE id=?", (bill_id,))


def filter_by_end_date(bills):
    now = datetime.now()
    curr = now.year * 12 + now.month
    result = []
    for b in bills:
        try:
            em, ey = b['end_month'], b['end_year']
        except (KeyError, IndexError):
            result.append(b)
            continue
        if em and ey and (int(ey) * 12 + int(em)) < curr:
            continue
        result.append(b)
    return result


def get_setting(key, default='0'):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(u) if u else None


def get_all_couples():
    conn = get_db()
    couples = conn.execute("SELECT * FROM couples ORDER BY id").fetchall()
    result = []
    for c in couples:
        members = conn.execute(
            "SELECT u.* FROM users u JOIN couple_members cm ON u.id=cm.user_id WHERE cm.couple_id=? ORDER BY u.id",
            (c['id'],)
        ).fetchall()
        d = dict(c)
        d['members']      = [dict(m) for m in members]
        d['member_ids']   = [m['id'] for m in members]
        d['display_name'] = c['name'] or ' & '.join(m['name'] for m in members)
        result.append(d)
    conn.close()
    return result


def current_couple():
    cid = session.get('couple_id')
    if not cid:
        return None
    for c in get_all_couples():
        if c['id'] == cid:
            return c
    return None


def parse_owner(raw):
    """Parse form owner_id: 'couple_X' → (0, X), '5' → (5, None)."""
    raw = str(raw or '0')
    if raw.startswith('couple_'):
        return 0, int(raw.split('_')[1])
    return int(raw), None


@app.context_processor
def inject_globals():
    return {
        'categories':   CATEGORIES,
        'priorities':   PRIORITIES,
        'income_types': INCOME_TYPES,
        'now':          datetime.now(),
        'json':         json,
        'all_users':    get_all_users(),
        'all_couples':  get_all_couples(),
        'cur_user':     current_user(),
        'cur_couple':   current_couple(),
        'session_uid':  session.get('user_id'),
        'session_cid':  session.get('couple_id'),
    }


# ==================== USERS ====================

@app.route('/switch/<int:uid>')
def switch_user(uid):
    if uid == 0:
        session.pop('user_id', None)
    else:
        session['user_id'] = uid
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/users')
def users_page():
    return render_template('users.html',
                           users=get_all_users(),
                           colors=USER_COLORS)


@app.route('/users/add', methods=['POST'])
def add_user():
    name  = request.form['name'].strip()
    color = request.form.get('color', '#3b82f6')
    if name:
        conn = get_db()
        conn.execute("INSERT INTO users(name,color) VALUES(?,?)", (name, color))
        conn.commit()
        conn.close()
        flash(f'Usuário "{name}" criado!', 'success')
    return redirect(url_for('users_page'))


@app.route('/users/delete/<int:uid>', methods=['POST'])
def delete_user(uid):
    conn = get_db()
    u = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
    if u:
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.execute("DELETE FROM couple_members WHERE user_id=?", (uid,))
        conn.commit()
        flash(f'Usuário "{u["name"]}" removido.', 'info')
        if session.get('user_id') == uid:
            session.pop('user_id', None)
    conn.close()
    return redirect(url_for('users_page'))


# ==================== COUPLES ====================

@app.route('/switch-couple/<int:cid>')
def switch_couple(cid):
    if cid == 0:
        session.pop('couple_id', None)
    else:
        session['couple_id'] = cid
    return redirect(request.referrer or url_for('couple'))


@app.route('/couples')
def couples_page():
    return render_template('couples.html',
                           couples=get_all_couples(),
                           users=get_all_users())


@app.route('/couples/add', methods=['POST'])
def add_couple():
    name       = request.form.get('name', '').strip()
    member_ids = [int(x) for x in request.form.getlist('member_ids') if x.isdigit()]

    if not member_ids:
        flash('Selecione pelo menos um membro.', 'warning')
        return redirect(url_for('couples_page'))

    conn = get_db()

    if not name:
        names = conn.execute(
            f"SELECT name FROM users WHERE id IN ({','.join('?'*len(member_ids))})",
            member_ids
        ).fetchall()
        name = ' & '.join(n['name'] for n in names)

    conn.execute("INSERT INTO couples(name) VALUES(?)", (name,))
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for uid in member_ids:
        conn.execute("INSERT OR IGNORE INTO couple_members(couple_id,user_id) VALUES(?,?)", (cid, uid))
    conn.commit()
    conn.close()

    session['couple_id'] = cid
    flash(f'Casal "{name}" criado!', 'success')
    return redirect(url_for('couple'))


@app.route('/couples/delete/<int:cid>', methods=['POST'])
def delete_couple(cid):
    conn = get_db()
    c = conn.execute("SELECT name FROM couples WHERE id=?", (cid,)).fetchone()
    if c:
        conn.execute("DELETE FROM couples WHERE id=?", (cid,))
        conn.execute("DELETE FROM couple_members WHERE couple_id=?", (cid,))
        conn.execute("UPDATE bills SET couple_id=NULL WHERE couple_id=?", (cid,))
        conn.commit()
        flash(f'Casal "{c["name"]}" removido.', 'info')
        if session.get('couple_id') == cid:
            session.pop('couple_id', None)
    conn.close()
    return redirect(url_for('couples_page'))


# ==================== DASHBOARD ====================

@app.route('/')
def dashboard():
    now = datetime.now()
    month, year, today = now.month, now.year, now.day
    uid = session.get('user_id')

    conn = get_db()
    if uid:
        incomes  = conn.execute("SELECT * FROM incomes WHERE active=1 AND (user_id=? OR user_id=0) ORDER BY day_of_month", (uid,)).fetchall()
        bills    = conn.execute("SELECT * FROM bills   WHERE active=1 AND user_id=? ORDER BY priority, due_day", (uid,)).fetchall()
    else:
        incomes  = conn.execute("SELECT * FROM incomes WHERE active=1 ORDER BY day_of_month").fetchall()
        bills    = conn.execute("SELECT * FROM bills   WHERE active=1 ORDER BY priority, due_day").fetchall()

    payments = conn.execute("SELECT * FROM payments WHERE month=? AND year=?", (month, year)).fetchall()
    conn.close()

    bills       = filter_by_end_date(bills)
    paid_ids    = {p['bill_id'] for p in payments}
    payment_map = {p['bill_id']: p for p in payments}
    bill_ids    = {b['id'] for b in bills}
    total_inc  = sum(i['amount'] for i in incomes)
    total_bill = sum(b['amount'] for b in bills)
    total_paid = sum(p['amount_paid'] for p in payments if p['bill_id'] in bill_ids)
    balance    = total_inc - total_bill

    upcoming = [b for b in bills if today <= b['due_day'] <= today + 7 and b['id'] not in paid_ids]
    overdue  = [b for b in bills if b['due_day'] < today              and b['id'] not in paid_ids]

    cat_data = {}
    for b in bills:
        cat_data[b['category']] = cat_data.get(b['category'], 0) + b['amount']

    bills_progress = round(len(paid_ids & bill_ids) / len(bills) * 100) if bills else 0
    installment_ids = [b['id'] for b in bills if b['total_installments']]
    bill_pay_counts = get_bill_pay_counts(installment_ids)

    return render_template('dashboard.html',
        incomes=incomes, bills=bills,
        total_inc=total_inc, total_bill=total_bill,
        total_paid=total_paid, balance=balance,
        paid_ids=paid_ids, payment_map=payment_map,
        upcoming=upcoming, overdue=overdue,
        cat_data=cat_data,
        bills_progress=bills_progress,
        paid_count=len(paid_ids & bill_ids),
        bill_pay_counts=bill_pay_counts,
        month=month, year=year, today=today,
        month_name=calendar.month_name[month],
    )


# ==================== BILLS ====================

@app.route('/bills')
def bills():
    now = datetime.now()
    month, year, today = now.month, now.year, now.day
    uid = session.get('user_id')

    conn = get_db()
    base_q = ("SELECT b.*, u.name as owner_name, u.color as owner_color, "
              "c.name as couple_name "
              "FROM bills b "
              "LEFT JOIN users u ON b.user_id=u.id "
              "LEFT JOIN couples c ON b.couple_id=c.id "
              "WHERE b.active=1 ")

    if uid:
        bills_q = conn.execute(base_q + "AND b.user_id=? ORDER BY b.priority, b.due_day", (uid,)).fetchall()
    else:
        bills_q = conn.execute(base_q + "ORDER BY b.priority, b.due_day").fetchall()

    payments = conn.execute("SELECT * FROM payments WHERE month=? AND year=?", (month, year)).fetchall()
    incomes  = conn.execute("SELECT * FROM incomes WHERE active=1 ORDER BY day_of_month").fetchall()
    conn.close()

    bills_q     = filter_by_end_date(bills_q)
    paid_ids    = {p['bill_id'] for p in payments}
    payment_map = {p['bill_id']: p for p in payments}
    installment_ids = [b['id'] for b in bills_q if b['total_installments']]
    bill_pay_counts = get_bill_pay_counts(installment_ids)

    return render_template('bills.html',
        bills=bills_q, paid_ids=paid_ids, payment_map=payment_map,
        incomes=incomes, bill_pay_counts=bill_pay_counts,
        month=month, year=year, today=today,
        month_name=calendar.month_name[month],
    )


@app.route('/bills/add', methods=['GET', 'POST'])
def add_bill():
    if request.method == 'POST':
        name         = request.form['name'].strip()
        amount       = float(request.form['amount'].replace(',', '.'))
        due_day      = int(request.form['due_day'])
        category     = request.form['category']
        priority     = int(request.form['priority'])
        is_recurring = 1 if request.form.get('is_recurring') else 0
        notes        = request.form.get('notes', '').strip()
        raw_owner    = request.form.get('owner_id', str(session.get('user_id') or 0))
        user_id, couple_id = parse_owner(raw_owner)
        em = request.form.get('end_month', '')
        ey = request.form.get('end_year', '')
        end_month = int(em) if em.isdigit() and request.form.get('has_end_date') else None
        end_year  = int(ey) if ey.isdigit() and request.form.get('has_end_date') else None
        ti = request.form.get('total_installments', '')
        total_installments = int(ti) if ti.isdigit() and int(ti) > 0 and request.form.get('has_installments') else None

        conn = get_db()
        conn.execute(
            "INSERT INTO bills(name,amount,due_day,category,priority,is_recurring,notes,user_id,couple_id,end_month,end_year,total_installments) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, amount, due_day, category, priority, is_recurring, notes, user_id, couple_id, end_month, end_year, total_installments)
        )
        conn.commit()
        conn.close()

        flash(f'Conta "{name}" adicionada!', 'success')
        return redirect(url_for('bills'))

    default_owner = f'couple_{session["couple_id"]}' if session.get('couple_id') else str(session.get('user_id') or 0)
    return render_template('bill_form.html', bill=None, action='add',
                           couples=get_all_couples(), default_owner=default_owner,
                           bill_paid_count=0)


@app.route('/bills/edit/<int:bill_id>', methods=['GET', 'POST'])
def edit_bill(bill_id):
    conn = get_db()
    bill = conn.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
    conn.close()

    if not bill:
        flash('Conta não encontrada.', 'danger')
        return redirect(url_for('bills'))

    if request.method == 'POST':
        name         = request.form['name'].strip()
        amount       = float(request.form['amount'].replace(',', '.'))
        due_day      = int(request.form['due_day'])
        category     = request.form['category']
        priority     = int(request.form['priority'])
        is_recurring = 1 if request.form.get('is_recurring') else 0
        notes        = request.form.get('notes', '').strip()
        raw_owner    = request.form.get('owner_id', '0')
        user_id, couple_id = parse_owner(raw_owner)
        em = request.form.get('end_month', '')
        ey = request.form.get('end_year', '')
        end_month = int(em) if em.isdigit() and request.form.get('has_end_date') else None
        end_year  = int(ey) if ey.isdigit() and request.form.get('has_end_date') else None
        ti = request.form.get('total_installments', '')
        total_installments = int(ti) if ti.isdigit() and int(ti) > 0 and request.form.get('has_installments') else None

        conn = get_db()
        conn.execute(
            "UPDATE bills SET name=?,amount=?,due_day=?,category=?,priority=?,is_recurring=?,notes=?,user_id=?,couple_id=?,end_month=?,end_year=?,total_installments=? WHERE id=?",
            (name, amount, due_day, category, priority, is_recurring, notes, user_id, couple_id, end_month, end_year, total_installments, bill_id)
        )
        conn.commit()
        conn.close()

        flash(f'Conta "{name}" atualizada!', 'success')
        return redirect(url_for('bills'))

    if bill['couple_id']:
        default_owner = f'couple_{bill["couple_id"]}'
    else:
        default_owner = str(bill['user_id'] or 0)

    bill_paid_count = get_bill_pay_counts([bill_id]).get(bill_id, 0)
    return render_template('bill_form.html', bill=bill, action='edit',
                           couples=get_all_couples(), default_owner=default_owner,
                           bill_paid_count=bill_paid_count)


@app.route('/bills/delete/<int:bill_id>', methods=['POST'])
def delete_bill(bill_id):
    conn = get_db()
    bill = conn.execute("SELECT name FROM bills WHERE id=?", (bill_id,)).fetchone()
    if bill:
        conn.execute("UPDATE bills SET active=0 WHERE id=?", (bill_id,))
        conn.commit()
        flash(f'Conta "{bill["name"]}" removida.', 'info')
    conn.close()
    return redirect(url_for('bills'))


# ==================== INCOMES ====================

@app.route('/incomes')
def incomes():
    uid = session.get('user_id')
    conn = get_db()
    base_q = ("SELECT i.*, u.name as owner_name, u.color as owner_color "
              "FROM incomes i LEFT JOIN users u ON i.user_id=u.id "
              "WHERE i.active=1 ")
    if uid:
        rows = conn.execute(base_q + "AND (i.user_id=? OR i.user_id=0) ORDER BY i.day_of_month", (uid,)).fetchall()
    else:
        rows = conn.execute(base_q + "ORDER BY i.day_of_month").fetchall()
    conn.close()
    total = sum(r['amount'] for r in rows)
    return render_template('incomes.html', incomes=rows, total=total)


@app.route('/incomes/add', methods=['GET', 'POST'])
def add_income():
    if request.method == 'POST':
        name         = request.form['name'].strip()
        amount       = float(request.form['amount'].replace(',', '.'))
        day_of_month = int(request.form['day_of_month'])
        itype        = request.form['type']
        notes        = request.form.get('notes', '').strip()
        raw_owner    = request.form.get('owner_id', str(session.get('user_id') or 0))
        user_id, _   = parse_owner(raw_owner)

        conn = get_db()
        conn.execute(
            "INSERT INTO incomes(name,amount,day_of_month,type,notes,user_id) VALUES(?,?,?,?,?,?)",
            (name, amount, day_of_month, itype, notes, user_id)
        )
        conn.commit()
        conn.close()

        flash(f'Renda "{name}" adicionada!', 'success')
        return redirect(url_for('incomes'))

    default_uid = session.get('user_id') or 0
    return render_template('income_form.html', income=None, action='add',
                           default_uid=default_uid)


@app.route('/incomes/edit/<int:income_id>', methods=['GET', 'POST'])
def edit_income(income_id):
    conn = get_db()
    income = conn.execute("SELECT * FROM incomes WHERE id=?", (income_id,)).fetchone()
    conn.close()

    if not income:
        flash('Renda não encontrada.', 'danger')
        return redirect(url_for('incomes'))

    if request.method == 'POST':
        name         = request.form['name'].strip()
        amount       = float(request.form['amount'].replace(',', '.'))
        day_of_month = int(request.form['day_of_month'])
        itype        = request.form['type']
        notes        = request.form.get('notes', '').strip()
        raw_owner    = request.form.get('owner_id', '0')
        user_id, _   = parse_owner(raw_owner)

        conn = get_db()
        conn.execute(
            "UPDATE incomes SET name=?,amount=?,day_of_month=?,type=?,notes=?,user_id=? WHERE id=?",
            (name, amount, day_of_month, itype, notes, user_id, income_id)
        )
        conn.commit()
        conn.close()

        flash(f'Renda "{name}" atualizada!', 'success')
        return redirect(url_for('incomes'))

    return render_template('income_form.html', income=income, action='edit',
                           default_uid=income['user_id'] or 0)


@app.route('/incomes/delete/<int:income_id>', methods=['POST'])
def delete_income(income_id):
    conn = get_db()
    income = conn.execute("SELECT name FROM incomes WHERE id=?", (income_id,)).fetchone()
    if income:
        conn.execute("UPDATE incomes SET active=0 WHERE id=?", (income_id,))
        conn.commit()
        flash(f'Renda "{income["name"]}" removida.', 'info')
    conn.close()
    return redirect(url_for('incomes'))


# ==================== PAYMENTS ====================

@app.route('/pay', methods=['POST'])
def mark_paid():
    bill_id       = int(request.form['bill_id'])
    month         = int(request.form['month'])
    year          = int(request.form['year'])
    amount_paid   = request.form.get('amount_paid', '').replace(',', '.').strip()
    income_source = request.form.get('income_source', '')
    paid_date     = request.form.get('paid_date', date.today().isoformat())
    notes         = request.form.get('notes', '')
    redir         = request.form.get('redirect_to', 'bills')

    conn = get_db()
    bill     = conn.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
    existing = conn.execute(
        "SELECT id FROM payments WHERE bill_id=? AND month=? AND year=?",
        (bill_id, month, year)
    ).fetchone()

    if bill and not existing:
        final_amount = float(amount_paid) if amount_paid else bill['amount']
        conn.execute(
            "INSERT INTO payments(bill_id,bill_name,amount_paid,paid_date,month,year,income_source,notes) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (bill_id, bill['name'], final_amount, paid_date, month, year, income_source, notes)
        )
        _auto_deactivate_if_done(conn, bill, bill_id)
        conn.commit()
        flash(f'"{bill["name"]}" marcada como paga! ✓', 'success')

    conn.close()
    if redir in ('bills', 'couple', 'dashboard'):
        return redirect(url_for(redir))
    return redirect(url_for('bills'))


@app.route('/unpay', methods=['POST'])
def mark_unpaid():
    bill_id = int(request.form['bill_id'])
    month   = int(request.form['month'])
    year    = int(request.form['year'])
    redir   = request.form.get('redirect_to', 'bills')

    conn = get_db()
    conn.execute("DELETE FROM payments WHERE bill_id=? AND month=? AND year=?", (bill_id, month, year))
    conn.commit()
    conn.close()

    flash('Pagamento desmarcado.', 'info')
    if redir in ('bills', 'couple', 'dashboard'):
        return redirect(url_for(redir))
    return redirect(url_for('bills'))


@app.route('/pay/quick', methods=['POST'])
def quick_pay():
    bill_id = int(request.form['bill_id'])
    month   = int(request.form['month'])
    year    = int(request.form['year'])
    redir   = request.form.get('redirect_to', 'bills')

    conn = get_db()
    bill     = conn.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
    existing = conn.execute(
        "SELECT id FROM payments WHERE bill_id=? AND month=? AND year=?",
        (bill_id, month, year)
    ).fetchone()

    if bill and not existing:
        conn.execute(
            "INSERT INTO payments(bill_id,bill_name,amount_paid,paid_date,month,year,income_source,notes) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (bill_id, bill['name'], bill['amount'], date.today().isoformat(), month, year, '', '')
        )
        _auto_deactivate_if_done(conn, bill, bill_id)
        conn.commit()
        flash(f'"{bill["name"]}" marcada como paga! ✓', 'success')

    conn.close()
    if redir in ('bills', 'couple', 'dashboard'):
        return redirect(url_for(redir))
    return redirect(url_for('bills'))


@app.route('/pay/all', methods=['POST'])
def pay_all():
    month = int(request.form['month'])
    year  = int(request.form['year'])
    uid   = session.get('user_id')

    conn = get_db()
    if uid:
        bills_q = conn.execute("SELECT * FROM bills WHERE active=1 AND user_id=?", (uid,)).fetchall()
    else:
        bills_q = conn.execute("SELECT * FROM bills WHERE active=1").fetchall()

    existing = conn.execute(
        "SELECT bill_id FROM payments WHERE month=? AND year=?", (month, year)
    ).fetchall()
    paid_set = {p['bill_id'] for p in existing}
    bills_q  = filter_by_end_date(bills_q)

    count = 0
    for bill in bills_q:
        if bill['id'] not in paid_set:
            conn.execute(
                "INSERT INTO payments(bill_id,bill_name,amount_paid,paid_date,month,year,income_source,notes) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (bill['id'], bill['name'], bill['amount'], date.today().isoformat(), month, year, '', '')
            )
            _auto_deactivate_if_done(conn, bill, bill['id'])
            count += 1

    conn.commit()
    conn.close()
    flash(f'{count} conta(s) marcada(s) como paga(s)!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/pay/advance', methods=['POST'])
def pay_advance():
    bill_id = int(request.form['bill_id'])
    months  = request.form.getlist('months[]')
    years   = request.form.getlist('years[]')
    amounts = request.form.getlist('amounts[]')

    conn = get_db()
    bill = conn.execute("SELECT * FROM bills WHERE id=?", (bill_id,)).fetchone()
    if not bill:
        conn.close()
        flash('Conta não encontrada.', 'danger')
        return redirect(url_for('dashboard'))

    count = 0
    for m_str, y_str, a_str in zip(months, years, amounts):
        m, y = int(m_str), int(y_str)
        a = float(a_str.replace(',', '.')) if a_str.strip() else bill['amount']
        existing = conn.execute(
            "SELECT id FROM payments WHERE bill_id=? AND month=? AND year=?",
            (bill_id, m, y)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO payments(bill_id,bill_name,amount_paid,paid_date,month,year,income_source,notes) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (bill_id, bill['name'], a, date.today().isoformat(), m, y, '', 'adiantado')
            )
            count += 1

    _auto_deactivate_if_done(conn, bill, bill_id)
    conn.commit()
    conn.close()

    flash(f'{count} parcela(s) de "{bill["name"]}" adiantada(s)!', 'success')
    return redirect(url_for('dashboard'))


# ==================== PLANNER ====================

@app.route('/planner')
def planner():
    now   = datetime.now()
    month = int(request.args.get('month', now.month))
    year  = int(request.args.get('year',  now.year))
    uid   = session.get('user_id')

    # Modo simulação: contas adiadas via URL params
    defer_param    = request.args.get('defer', '')
    skip_param     = request.args.get('skip',  '')
    deferred_ids   = set(int(x) for x in defer_param.split(',') if x.isdigit())
    next_month_ids = set(int(x) for x in skip_param.split(',')  if x.isdigit())
    is_simulation  = bool(deferred_ids or next_month_ids)

    conn = get_db()
    if uid:
        incomes_q = conn.execute("SELECT * FROM incomes WHERE active=1 AND (user_id=? OR user_id=0) ORDER BY day_of_month", (uid,)).fetchall()
        bills_q   = conn.execute("SELECT * FROM bills   WHERE active=1 AND user_id=? ORDER BY priority, due_day", (uid,)).fetchall()
    else:
        incomes_q = conn.execute("SELECT * FROM incomes WHERE active=1 ORDER BY day_of_month").fetchall()
        bills_q   = conn.execute("SELECT * FROM bills   WHERE active=1 ORDER BY priority, due_day").fetchall()

    payments = conn.execute("SELECT * FROM payments WHERE month=? AND year=?", (month, year)).fetchall()
    conn.close()

    bills_q  = filter_by_end_date(bills_q)
    paid_ids = {p['bill_id'] for p in payments}
    reserve  = float(get_setting('reserve_amount', '300'))
    goal     = float(get_setting('savings_goal', '0'))

    from planner import SmartPlanner
    plan = SmartPlanner().generate_plan(month, year,
                                        [dict(i) for i in incomes_q],
                                        [dict(b) for b in bills_q],
                                        paid_ids=paid_ids, reserve=reserve, savings_goal=goal,
                                        deferred_ids=deferred_ids,
                                        next_month_ids=next_month_ids)

    return render_template('planner.html',
        plan=plan, incomes=incomes_q, bills=bills_q,
        paid_ids=paid_ids,
        month=month, year=year,
        month_name=calendar.month_name[month],
        months_list=[(m, calendar.month_name[m]) for m in range(1, 13)],
        reserve=reserve, goal=goal,
        deferred_ids=deferred_ids,
        next_month_ids=next_month_ids,
        is_simulation=is_simulation,
        total_steps=len(plan['steps']),
    )


# ==================== COUPLE ====================

@app.route('/couple')
def couple():
    now = datetime.now()
    month, year, today = now.month, now.year, now.day
    couples = get_all_couples()

    # Auto-select if only one couple exists and none is selected
    cid = session.get('couple_id')
    if not cid and len(couples) == 1:
        cid = couples[0]['id']
        session['couple_id'] = cid

    # Picker mode: no couple selected and multiple exist (or none exist)
    if not cid:
        return render_template('couple.html',
            mode='picker', couples=couples,
            month=month, year=year, month_name=calendar.month_name[month],
            months_list=[(m, calendar.month_name[m]) for m in range(1, 13)],
        )

    # Find selected couple
    active_couple = next((c for c in couples if c['id'] == cid), None)
    if not active_couple:
        session.pop('couple_id', None)
        return redirect(url_for('couple'))

    member_ids = active_couple['member_ids']

    conn = get_db()

    # Incomes of all members
    if member_ids:
        ph = ','.join('?' * len(member_ids))
        all_incomes = conn.execute(
            f"SELECT i.*, u.name as owner_name, u.color as owner_color "
            f"FROM incomes i LEFT JOIN users u ON i.user_id=u.id "
            f"WHERE i.active=1 AND i.user_id IN ({ph}) ORDER BY i.day_of_month",
            member_ids
        ).fetchall()
        personal_bills = conn.execute(
            f"SELECT b.*, u.name as owner_name, u.color as owner_color "
            f"FROM bills b LEFT JOIN users u ON b.user_id=u.id "
            f"WHERE b.active=1 AND b.user_id IN ({ph}) ORDER BY b.priority, b.due_day",
            member_ids
        ).fetchall()
    else:
        all_incomes    = []
        personal_bills = []

    shared_bills = conn.execute(
        "SELECT b.*, u.name as owner_name, u.color as owner_color "
        "FROM bills b LEFT JOIN users u ON b.user_id=u.id "
        "WHERE b.active=1 AND b.couple_id=? ORDER BY b.priority, b.due_day",
        (cid,)
    ).fetchall()

    all_bills = list(personal_bills) + list(shared_bills)

    payments = conn.execute(
        "SELECT * FROM payments WHERE month=? AND year=?", (month, year)
    ).fetchall()
    incomes_raw = conn.execute("SELECT * FROM incomes WHERE active=1").fetchall()
    conn.close()

    paid_ids = {p['bill_id'] for p in payments}

    # Per-member stats
    user_bills = {uid: [b for b in personal_bills if b['user_id'] == uid]
                  for uid in member_ids}
    user_incomes = {uid: [i for i in all_incomes if i['user_id'] == uid]
                    for uid in member_ids}

    user_stats = {}
    for m in active_couple['members']:
        ub = user_bills.get(m['id'], [])
        ui = user_incomes.get(m['id'], [])
        inc  = sum(i['amount'] for i in ui)
        bills_sum = sum(b['amount'] for b in ub)
        user_stats[m['id']] = {
            'name':        m['name'],
            'color':       m['color'],
            'income':      inc,
            'bills':       bills_sum,
            'savings':     inc - bills_sum,
            'bills_count': len(ub),
            'paid_count':  sum(1 for b in ub if b['id'] in paid_ids),
        }

    total_income  = sum(i['amount'] for i in all_incomes)
    total_bills   = sum(b['amount'] for b in all_bills)
    shared_total  = sum(b['amount'] for b in shared_bills)

    upcoming = [b for b in all_bills if today <= b['due_day'] <= today + 7 and b['id'] not in paid_ids]
    overdue  = [b for b in all_bills if b['due_day'] < today              and b['id'] not in paid_ids]

    from planner import SmartPlanner
    plan = SmartPlanner().generate_plan(month, year,
                                        [dict(i) for i in all_incomes],
                                        [dict(b) for b in all_bills],
                                        paid_ids=paid_ids,
                                        reserve=float(get_setting('reserve_amount', '300')))

    return render_template('couple.html',
        mode='view',
        active_couple=active_couple, couples=couples,
        all_incomes=all_incomes,
        personal_bills=personal_bills, shared_bills=shared_bills,
        all_bills=all_bills,
        user_bills=user_bills, user_incomes=user_incomes,
        user_stats=user_stats,
        paid_ids=paid_ids,
        plan=plan,
        total_income=total_income, total_bills=total_bills,
        shared_total=shared_total,
        upcoming=upcoming, overdue=overdue,
        month=month, year=year, today=today,
        month_name=calendar.month_name[month],
        months_list=[(m, calendar.month_name[m]) for m in range(1, 13)],
        incomes_all=incomes_raw,
        cid=cid,
    )


# ==================== HISTORY ====================

@app.route('/history')
def history():
    uid = session.get('user_id')
    conn = get_db()
    if uid:
        payments = conn.execute(
            "SELECT p.*, b.category, b.priority FROM payments p "
            "LEFT JOIN bills b ON p.bill_id=b.id "
            "WHERE (b.user_id=? OR b.id IS NULL) "
            "ORDER BY p.year DESC, p.month DESC, p.paid_date DESC",
            (uid,)
        ).fetchall()
    else:
        payments = conn.execute(
            "SELECT p.*, b.category, b.priority FROM payments p "
            "LEFT JOIN bills b ON p.bill_id=b.id "
            "ORDER BY p.year DESC, p.month DESC, p.paid_date DESC"
        ).fetchall()
    conn.close()

    grouped = {}
    for p in payments:
        key = (p['year'], p['month'])
        if key not in grouped:
            grouped[key] = {'payments': [], 'total': 0}
        grouped[key]['payments'].append(p)
        grouped[key]['total'] += p['amount_paid']

    return render_template('history.html', grouped=grouped)


# ==================== SETTINGS ====================

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        set_setting('reserve_amount', request.form.get('reserve_amount', '300'))
        set_setting('savings_goal',   request.form.get('savings_goal',   '0'))
        flash('Configurações salvas!', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html',
        reserve=get_setting('reserve_amount', '300'),
        goal=get_setting('savings_goal', '0'),
    )


# ==================== SUGGESTIONS ====================

@app.route('/suggestions')
def suggestions():
    now   = datetime.now()
    month = int(request.args.get('month', now.month))
    year  = int(request.args.get('year',  now.year))
    uid   = session.get('user_id')

    conn = get_db()
    if uid:
        incomes_q = conn.execute("SELECT * FROM incomes WHERE active=1 AND (user_id=? OR user_id=0) ORDER BY day_of_month", (uid,)).fetchall()
        bills_q   = conn.execute("SELECT * FROM bills   WHERE active=1 AND user_id=? ORDER BY priority, due_day", (uid,)).fetchall()
    else:
        incomes_q = conn.execute("SELECT * FROM incomes WHERE active=1 ORDER BY day_of_month").fetchall()
        bills_q   = conn.execute("SELECT * FROM bills   WHERE active=1 ORDER BY priority, due_day").fetchall()
    conn.close()

    bills_q  = filter_by_end_date(bills_q)
    reserve  = float(get_setting('reserve_amount', '300'))

    from planner import SmartPlanner
    plan = SmartPlanner().generate_plan(month, year,
                                        [dict(i) for i in incomes_q],
                                        [dict(b) for b in bills_q],
                                        paid_ids=set(), reserve=reserve)

    return render_template('suggestions.html',
        plan=plan,
        incomes=incomes_q,
        month=month, year=year,
        month_name=calendar.month_name[month],
        months_list=[(m, calendar.month_name[m]) for m in range(1, 13)],
    )


# ==================== API ====================

@app.route('/api/chart-data')
def api_chart_data():
    uid = session.get('user_id')
    conn = get_db()
    if uid:
        bills = conn.execute("SELECT * FROM bills WHERE active=1 AND user_id=?", (uid,)).fetchall()
    else:
        bills = conn.execute("SELECT * FROM bills WHERE active=1").fetchall()
    conn.close()

    cat_totals = {}
    for b in bills:
        c = b['category']
        cat_totals[c] = cat_totals.get(c, 0) + b['amount']

    labels = [CATEGORIES[c][0] if c in CATEGORIES else c for c in cat_totals]
    values = list(cat_totals.values())
    colors = [CATEGORIES[c][2] if c in CATEGORIES else '#6b7280' for c in cat_totals]
    return jsonify({'labels': labels, 'values': values, 'colors': colors})


# ==================== STARTUP ====================

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


if __name__ == '__main__':
    init_db()
    port   = 5050
    lan_ip = get_lan_ip()

    print("\n" + "="*52)
    print("  ORGANIZADOR FINANCEIRO")
    print("="*52)
    print(f"  PC:      http://localhost:{port}")
    if lan_ip:
        print(f"  Celular: http://{lan_ip}:{port}")
        print(f"  (mesmo WiFi)")
    print("  Pressione Ctrl+C para encerrar")
    print("="*52 + "\n")

    app.run(debug=False, port=port, host='0.0.0.0')
