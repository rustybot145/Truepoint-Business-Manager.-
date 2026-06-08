from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
import sqlite3
import csv
import io
import os
from datetime import datetime, date, timedelta

app = Flask(__name__)
DATABASE = 'agency.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT DEFAULT '',
            email TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            client_id INTEGER,
            client_name TEXT DEFAULT '',
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            duration INTEGER DEFAULT 60,
            notes TEXT DEFAULT '',
            meeting_link TEXT DEFAULT '',
            completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            receipt_note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            client_name TEXT NOT NULL,
            project_name TEXT NOT NULL,
            amount REAL NOT NULL,
            date_sent TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT DEFAULT 'unpaid',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL
        );
    ''')
    conn.commit()
    conn.close()


def migrate_db():
    """Add columns introduced after initial schema creation."""
    conn = get_db()
    for sql in [
        "ALTER TABLE expenses ADD COLUMN is_recurring INTEGER DEFAULT 0",
        "ALTER TABLE expenses ADD COLUMN recurring_interval TEXT DEFAULT 'monthly'",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass
    conn.commit()
    conn.close()


def auto_update_overdue(conn):
    today = date.today().isoformat()
    conn.execute(
        "UPDATE invoices SET status = 'overdue' WHERE status = 'unpaid' AND due_date < ?",
        (today,)
    )
    conn.commit()


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    conn = get_db()
    auto_update_overdue(conn)
    today = date.today()
    week_end = (today + timedelta(days=7)).isoformat()
    month_start = today.replace(day=1).isoformat()

    upcoming = conn.execute(
        '''SELECT m.*, c.company FROM meetings m
           LEFT JOIN clients c ON m.client_id = c.id
           WHERE m.date BETWEEN ? AND ? AND m.completed = 0
           ORDER BY m.date, m.time LIMIT 8''',
        (today.isoformat(), week_end)
    ).fetchall()

    monthly_income = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM invoices WHERE status='paid' AND date_sent>=? AND date_sent<=?",
        (month_start, today.isoformat())
    ).fetchone()['t']

    monthly_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM expenses WHERE date>=? AND date<=?",
        (month_start, today.isoformat())
    ).fetchone()['t']

    outstanding = conn.execute(
        "SELECT * FROM invoices WHERE status IN ('unpaid','overdue') ORDER BY due_date LIMIT 8"
    ).fetchall()

    total_clients = conn.execute("SELECT COUNT(*) AS c FROM clients").fetchone()['c']
    active_projects = conn.execute(
        "SELECT COUNT(*) AS c FROM invoices WHERE status != 'paid'"
    ).fetchone()['c']

    overdue_count = conn.execute(
        "SELECT COUNT(*) AS c FROM invoices WHERE status='overdue'"
    ).fetchone()['c']
    overdue_amount = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM invoices WHERE status='overdue'"
    ).fetchone()['t']

    monthly_profit = round(monthly_income - monthly_expenses, 2)

    # 6-month chart data
    chart_labels, chart_income, chart_expenses = [], [], []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        ms = date(y, m, 1)
        me = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        inc = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS t FROM invoices WHERE status='paid' AND date_sent>=? AND date_sent<?",
            (ms.isoformat(), me.isoformat())
        ).fetchone()['t']
        exp = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS t FROM expenses WHERE date>=? AND date<?",
            (ms.isoformat(), me.isoformat())
        ).fetchone()['t']
        chart_labels.append(ms.strftime('%b'))
        chart_income.append(round(inc, 2))
        chart_expenses.append(round(exp, 2))

    conn.close()
    return render_template('dashboard.html',
        upcoming=upcoming,
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_profit=monthly_profit,
        outstanding=outstanding,
        total_clients=total_clients,
        active_projects=active_projects,
        overdue_count=overdue_count,
        overdue_amount=overdue_amount,
        chart_labels=chart_labels,
        chart_income=chart_income,
        chart_expenses=chart_expenses,
        today=today
    )


# ─── MEETINGS ────────────────────────────────────────────────────────────────

@app.route('/meetings')
def meetings():
    conn = get_db()
    clients = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    all_meetings = conn.execute(
        '''SELECT m.*, c.company FROM meetings m
           LEFT JOIN clients c ON m.client_id = c.id
           ORDER BY m.date DESC, m.time DESC'''
    ).fetchall()
    conn.close()
    return render_template('meetings.html', meetings=all_meetings, clients=clients)


@app.route('/api/meetings', methods=['POST'])
def api_create_meeting():
    d = request.json or {}
    if not d.get('title') or not d.get('date') or not d.get('time'):
        return jsonify({'error': 'Title, date, and time are required'}), 400
    conn = get_db()
    cur = conn.execute(
        '''INSERT INTO meetings (title, client_id, client_name, date, time, duration, notes, meeting_link)
           VALUES (?,?,?,?,?,?,?,?)''',
        (d['title'], d.get('client_id') or None, d.get('client_name', ''),
         d['date'], d['time'], int(d.get('duration', 60)),
         d.get('notes', ''), d.get('meeting_link', ''))
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/meetings/<int:mid>', methods=['PUT'])
def api_update_meeting(mid):
    d = request.json or {}
    conn = get_db()
    conn.execute(
        '''UPDATE meetings SET title=?,client_id=?,client_name=?,date=?,time=?,
           duration=?,notes=?,meeting_link=?,completed=? WHERE id=?''',
        (d['title'], d.get('client_id') or None, d.get('client_name', ''),
         d['date'], d['time'], int(d.get('duration', 60)),
         d.get('notes', ''), d.get('meeting_link', ''), int(d.get('completed', 0)), mid)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/meetings/<int:mid>', methods=['DELETE'])
def api_delete_meeting(mid):
    conn = get_db()
    conn.execute("DELETE FROM meetings WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/meetings/<int:mid>/complete', methods=['POST'])
def api_complete_meeting(mid):
    conn = get_db()
    conn.execute("UPDATE meetings SET completed=1 WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─── EXPENSES ────────────────────────────────────────────────────────────────

@app.route('/expenses')
def expenses():
    conn = get_db()
    filter_month = request.args.get('month', date.today().strftime('%Y-%m'))
    try:
        fy, fm = map(int, filter_month.split('-'))
        ms = date(fy, fm, 1)
        me = date(fy + 1, 1, 1) if fm == 12 else date(fy, fm + 1, 1)
    except Exception:
        ms = date.today().replace(day=1)
        me = date.today().replace(day=1) + timedelta(days=32)
        me = me.replace(day=1)

    all_expenses = conn.execute(
        "SELECT * FROM expenses WHERE date>=? AND date<? ORDER BY date DESC",
        (ms.isoformat(), me.isoformat())
    ).fetchall()

    category_totals = conn.execute(
        "SELECT category, COALESCE(SUM(amount),0) AS total FROM expenses WHERE date>=? AND date<? GROUP BY category ORDER BY total DESC",
        (ms.isoformat(), me.isoformat())
    ).fetchall()

    monthly_total = sum(r['total'] for r in category_totals)

    # Subscriptions: unique recurring expenses with this-month status
    cur_month_start = date.today().replace(day=1).isoformat()
    subscriptions = conn.execute(
        '''SELECT description, amount, category, recurring_interval,
                  MAX(date) AS last_logged,
                  MAX(CASE WHEN date >= ? THEN 1 ELSE 0 END) AS logged_this_month,
                  MAX(id) AS latest_id
           FROM expenses
           WHERE is_recurring = 1
           GROUP BY description, recurring_interval
           ORDER BY description''',
        (cur_month_start,)
    ).fetchall()

    conn.close()
    return render_template('expenses.html',
        expenses=all_expenses,
        category_totals=category_totals,
        monthly_total=monthly_total,
        filter_month=filter_month,
        subscriptions=subscriptions
    )


@app.route('/api/expenses', methods=['POST'])
def api_create_expense():
    d = request.json or {}
    if not d.get('date') or not d.get('amount') or not d.get('category'):
        return jsonify({'error': 'Date, amount, and category are required'}), 400
    try:
        amount = float(d['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'Amount must be a positive number'}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO expenses (date,amount,category,description,receipt_note,is_recurring,recurring_interval) VALUES (?,?,?,?,?,?,?)",
        (d['date'], amount, d['category'], d.get('description', ''), d.get('receipt_note', ''),
         1 if d.get('is_recurring') else 0, d.get('recurring_interval', 'monthly'))
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/expenses/<int:eid>', methods=['PUT'])
def api_update_expense(eid):
    d = request.json or {}
    try:
        amount = float(d['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'Amount must be a positive number'}), 400
    conn = get_db()
    conn.execute(
        "UPDATE expenses SET date=?,amount=?,category=?,description=?,receipt_note=?,is_recurring=?,recurring_interval=? WHERE id=?",
        (d['date'], amount, d['category'], d.get('description', ''), d.get('receipt_note', ''),
         1 if d.get('is_recurring') else 0, d.get('recurring_interval', 'monthly'), eid)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/expenses/<int:eid>', methods=['DELETE'])
def api_delete_expense(eid):
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/expenses/<int:eid>/relog', methods=['POST'])
def api_relog_expense(eid):
    conn = get_db()
    orig = conn.execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone()
    if not orig:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    cur = conn.execute(
        "INSERT INTO expenses (date,amount,category,description,receipt_note,is_recurring,recurring_interval) VALUES (?,?,?,?,?,?,?)",
        (date.today().isoformat(), orig['amount'], orig['category'],
         orig['description'], orig['receipt_note'], 1, orig['recurring_interval'])
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/expenses/export')
def api_export_expenses():
    conn = get_db()
    rows = conn.execute("SELECT date,amount,category,description,receipt_note FROM expenses ORDER BY date DESC").fetchall()
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Amount', 'Category', 'Description', 'Receipt Note'])
    for r in rows:
        w.writerow([r['date'], f"{r['amount']:.2f}", r['category'], r['description'], r['receipt_note']])
    buf.seek(0)
    return send_file(
        io.BytesIO(buf.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'expenses_{date.today().isoformat()}.csv'
    )


# ─── FINANCES / INVOICES ─────────────────────────────────────────────────────

@app.route('/finances')
def finances():
    conn = get_db()
    auto_update_overdue(conn)
    today = date.today()

    invoices = conn.execute(
        '''SELECT i.*, c.company FROM invoices i
           LEFT JOIN clients c ON i.client_id = c.id
           ORDER BY i.date_sent DESC'''
    ).fetchall()

    clients = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()

    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM invoices WHERE status='paid'"
    ).fetchone()['t']

    outstanding_balance = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM invoices WHERE status IN ('unpaid','overdue')"
    ).fetchone()['t']

    overdue_total = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM invoices WHERE status='overdue'"
    ).fetchone()['t']

    # 6-month P&L data
    monthly_data = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        ms = date(y, m, 1)
        me = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        inc = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS t FROM invoices WHERE status='paid' AND date_sent>=? AND date_sent<?",
            (ms.isoformat(), me.isoformat())
        ).fetchone()['t']
        exp = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS t FROM expenses WHERE date>=? AND date<?",
            (ms.isoformat(), me.isoformat())
        ).fetchone()['t']
        monthly_data.append({
            'month': ms.strftime('%b %Y'),
            'income': round(inc, 2),
            'expenses': round(exp, 2),
            'profit': round(inc - exp, 2)
        })

    conn.close()
    return render_template('finances.html',
        invoices=invoices,
        clients=clients,
        total_revenue=total_revenue,
        outstanding_balance=outstanding_balance,
        overdue_total=overdue_total,
        monthly_data=monthly_data
    )


@app.route('/api/invoices', methods=['POST'])
def api_create_invoice():
    d = request.json or {}
    required = ['client_name', 'project_name', 'amount', 'date_sent', 'due_date']
    if not all(d.get(f) for f in required):
        return jsonify({'error': 'All fields are required'}), 400
    try:
        amount = float(d['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'Amount must be a positive number'}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO invoices (client_id,client_name,project_name,amount,date_sent,due_date,status) VALUES (?,?,?,?,?,?,?)",
        (d.get('client_id') or None, d['client_name'], d['project_name'],
         amount, d['date_sent'], d['due_date'], d.get('status', 'unpaid'))
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/invoices/<int:iid>', methods=['PUT'])
def api_update_invoice(iid):
    d = request.json or {}
    try:
        amount = float(d['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'Amount must be a positive number'}), 400
    conn = get_db()
    conn.execute(
        "UPDATE invoices SET client_id=?,client_name=?,project_name=?,amount=?,date_sent=?,due_date=?,status=? WHERE id=?",
        (d.get('client_id') or None, d['client_name'], d['project_name'],
         amount, d['date_sent'], d['due_date'], d['status'], iid)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/invoices/<int:iid>', methods=['DELETE'])
def api_delete_invoice(iid):
    conn = get_db()
    conn.execute("DELETE FROM invoices WHERE id=?", (iid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/invoices/<int:iid>/status', methods=['POST'])
def api_update_invoice_status(iid):
    d = request.json or {}
    status = d.get('status')
    if status not in ('paid', 'unpaid', 'overdue'):
        return jsonify({'error': 'Invalid status'}), 400
    conn = get_db()
    conn.execute("UPDATE invoices SET status=? WHERE id=?", (status, iid))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ─── CLIENTS ─────────────────────────────────────────────────────────────────

@app.route('/clients')
def clients():
    conn = get_db()
    rows = conn.execute(
        '''SELECT c.*,
               COUNT(DISTINCT i.id) AS invoice_count,
               COALESCE(SUM(CASE WHEN i.status='paid' THEN i.amount ELSE 0 END),0) AS total_paid,
               COUNT(DISTINCT m.id) AS meeting_count
           FROM clients c
           LEFT JOIN invoices i ON c.id = i.client_id
           LEFT JOIN meetings m ON c.id = m.client_id
           GROUP BY c.id ORDER BY c.name'''
    ).fetchall()
    conn.close()
    return render_template('clients.html', clients=rows)


@app.route('/clients/<int:cid>')
def client_detail(cid):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    if not client:
        return redirect(url_for('clients'))
    invoices = conn.execute(
        "SELECT * FROM invoices WHERE client_id=? ORDER BY date_sent DESC", (cid,)
    ).fetchall()
    meetings = conn.execute(
        "SELECT * FROM meetings WHERE client_id=? ORDER BY date DESC", (cid,)
    ).fetchall()
    conn.close()
    return render_template('client_detail.html', client=client, invoices=invoices, meetings=meetings)


@app.route('/api/clients', methods=['GET'])
def api_get_clients():
    conn = get_db()
    rows = conn.execute("SELECT id, name, company FROM clients ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/clients', methods=['POST'])
def api_create_client():
    d = request.json or {}
    if not d.get('name'):
        return jsonify({'error': 'Client name is required'}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO clients (name,company,email,phone,notes) VALUES (?,?,?,?,?)",
        (d['name'], d.get('company', ''), d.get('email', ''), d.get('phone', ''), d.get('notes', ''))
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/clients/<int:cid>', methods=['PUT'])
def api_update_client(cid):
    d = request.json or {}
    if not d.get('name'):
        return jsonify({'error': 'Client name is required'}), 400
    conn = get_db()
    conn.execute(
        "UPDATE clients SET name=?,company=?,email=?,phone=?,notes=? WHERE id=?",
        (d['name'], d.get('company', ''), d.get('email', ''), d.get('phone', ''), d.get('notes', ''), cid)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/clients/<int:cid>', methods=['DELETE'])
def api_delete_client(cid):
    conn = get_db()
    conn.execute("DELETE FROM clients WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


if __name__ == '__main__':
    init_db()
    migrate_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
