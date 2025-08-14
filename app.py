from flask import Flask, render_template, request, redirect, session, jsonify, send_file, url_for, flash
import pymysql
import os, shutil, zipfile, tempfile
import toml
import subprocess
import sys
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DB_CONFIG = dict(host='localhost', user='RatisWu', password='sherlock0301', db='uqms_db')

def get_conn():
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)

# ------------------ 使用者系統 ------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        if cur.fetchone():
            flash("使用者已存在")
            return redirect('/register')
        else:
            cur.execute("INSERT INTO users (username, password_hash) VALUES (%s,%s)", (username, generate_password_hash(password)))
            conn.commit()
    
        conn.close()
        return redirect('/login')
    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect('/')
        return "帳號或密碼錯誤"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ------------------ 主頁 ------------------
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('index.html', username=session['username'])

# ------------------ API 提供 AJAX 狀態 ------------------
@app.route('/api/status')
def api_status():
    if 'user_id' not in session:
        return jsonify({'error': 'not logged in'}), 401

    conn = get_conn()
    cur = conn.cursor()
    # 儀器
    cur.execute("SELECT name, ip FROM instruments WHERE locked_by IS NOT NULL")
    instruments = cur.fetchall()
    # 使用者的實驗
    cur.execute("SELECT id, output_dir, created_at FROM experiments WHERE user_id=%s", (session['user_id'],))
    experiments = cur.fetchall()
    conn.close()

    return jsonify({
        'instruments': instruments,
        'experiments': experiments
    })

# ------------------ 上傳 TOML 並執行 ------------------
@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return redirect('/login')
    file = request.files['toml_file']
    if not file:
        return "沒有檔案"
    
    save_path = os.path.join('experiments', file.filename)
    file.save(save_path)


    # 解析 TOML
    data = toml.load(save_path)
    output_dir = data['Readout']['output']
    os.makedirs(output_dir, exist_ok=True)

    # 鎖定儀器
    conn = get_conn()
    cur = conn.cursor()
    for hw_name, hw in data['Hardware'].items():
        name = hw_name
        ip = hw['address']
        cur.execute("SELECT * FROM instruments WHERE ip=%s", (ip,))
        existing = cur.fetchone()
        if existing:
            if existing['locked_by'] is not None:
                conn.close()
                return f"{name}:{ip} 已被佔用"
            cur.execute("UPDATE instruments SET locked_by=%s WHERE id=%s", (session['user_id'], existing['id']))
        else:
            cur.execute("INSERT INTO instruments (name, ip, locked_by) VALUES (%s,%s,%s)", (name, ip, session['user_id']))
    conn.commit()

    # 記錄實驗
    cur.execute("INSERT INTO experiments (user_id, output_dir) VALUES (%s,%s)", (session['user_id'], output_dir))
    exp_id = cur.lastrowid
    conn.commit()
    conn.close()

    # 執行 Python 檔案 (保證同環境)
    python_exec = sys.executable
    subprocess.Popen([python_exec, 'experiment.py', save_path])

    return redirect('/')

# ------------------ AJAX 下載 ZIP ------------------
@app.route('/download_ajax/<int:exp_id>', methods=['POST'])
def download_ajax(exp_id):
    if 'user_id' not in session:
        return jsonify({'error': 'not logged in'}), 401

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM experiments WHERE id=%s AND user_id=%s", (exp_id, session['user_id']))
    exp = cur.fetchone()
    if not exp:
        conn.close()
        return jsonify({'error':'experiment not found'}), 404
    output_dir = exp['output_dir']

    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    with zipfile.ZipFile(tmp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), output_dir))

    # 釋放儀器
    cur.execute("UPDATE instruments SET locked_by=NULL WHERE locked_by=%s", (session['user_id'],))
    conn.commit()
    conn.close()

    return jsonify({'zip_path': tmp_zip.name, 'filename': os.path.basename(output_dir)+'.zip'})

@app.route('/fetch_zip')
def fetch_zip():
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return '檔案不存在', 404
    resp = send_file(path, as_attachment=True)
    os.remove(path)
    return resp

# ------------------ 啟動 ------------------
if __name__ == '__main__':
    os.makedirs('experiments', exist_ok=True)
    app.run(host='0.0.0.0', port=7133, debug=True)
