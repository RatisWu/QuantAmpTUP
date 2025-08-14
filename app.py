from flask import Flask, render_template, request, redirect, session, jsonify, send_file, url_for, flash
import pymysql
import os, shutil, zipfile, tempfile
import toml
import subprocess
import sys, threading
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_PERMANENT'] = False

DB_CONFIG = dict(host='localhost', user='QuantAmpTUP', password='CCDismyBOSS', db='QuantAmpTUP')

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

# ------------------ LOGOUT ------------------
@app.route('/logout')
def logout():
    session.clear()  # removes all session data
    return redirect('/login')


# ------------------ 主頁 ------------------
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Get the latest experiment of this user
    cur.execute("""
        SELECT * FROM experiments 
        WHERE user_id=%s 
        ORDER BY id DESC 
        LIMIT 1
    """, (session['user_id'],))
    latest_exp = cur.fetchone()
    conn.close()
    
    return render_template('index.html', latest_exp=latest_exp, username=session['username'])

# ------------------ API 提供 AJAX 狀態 ------------------
@app.route('/api/status')
def api_status():
    if 'user_id' not in session:
        return jsonify({'error': 'not logged in'}), 401

    conn = get_conn()
    cur = conn.cursor()
    # 儀器
    cur.execute("SELECT name, ip FROM instruments WHERE user_id IS NOT NULL")
    instruments = cur.fetchall()
    # 使用者的實驗
    cur.execute("SELECT id, output_path, created_at FROM experiments WHERE user_id=%s", (session['user_id'],))
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

    # 取得檔案
    file = request.files.get('toml_file')
    if not file:
        return "沒有檔案"

    save_path = os.path.join('experiments', file.filename)
    os.makedirs('experiments', exist_ok=True)
    file.save(save_path)

    # 解析 TOML
    data = toml.load(save_path)
    output_dir = data['Readout']['output']
    os.makedirs(output_dir, exist_ok=True)

    # 鎖定儀器
    conn = get_conn()
    cur = conn.cursor()
    instrument_ids = []
    for hw_name, hw in data['Hardware'].items():
        name = hw_name
        ip = hw['address']
        cur.execute("SELECT * FROM instruments WHERE ip_address=%s", (ip,))
        existing = cur.fetchone()
        if existing:
            if existing['user_id'] is not None:
                conn.close()
                return f"{name}:{ip} 已被佔用"
            cur.execute("UPDATE instruments SET user_id=%s WHERE id=%s", (session['user_id'], existing['id']))
            instrument_ids.append(existing['id'])
        else:
            cur.execute(
                "INSERT INTO instruments (instrument_name, ip_address, user_id) VALUES (%s,%s,%s)",
                (name, ip, session['user_id'])
            )
            instrument_ids.append(cur.lastrowid)
    conn.commit()

    # 記錄實驗 (加入 toml_path)
    cur.execute(
        "INSERT INTO experiments (user_id, output_path, toml_path) VALUES (%s, %s, %s)",
        (session['user_id'], output_dir, save_path)
    )
    exp_id = cur.lastrowid
    conn.commit()

    # 執行 Python 檔案，並在完成後釋放儀器
    python_exec = sys.executable
    script_path = '/home/ratiswu/Documents/GitHub/QuantAmpTUP/PYs/TWPAFastTUP.py'

    def release_instruments(ids):
        conn2 = get_conn()
        cur2 = conn2.cursor()
        cur2.execute(
            "UPDATE instruments SET user_id=NULL WHERE id IN (%s)" % ",".join(["%s"]*len(ids)),
            ids
        )
        conn2.commit()
        conn2.close()

    def run_experiment():
        subprocess.run([python_exec, script_path, save_path])
        release_instruments(instrument_ids)

    import threading
    threading.Thread(target=run_experiment).start()

    # os.remove(save_path)

    conn.close()
    return redirect('/')



@app.route('/download_ajax/<int:exp_id>', methods=['POST'])
def download_ajax(exp_id):
    if 'user_id' not in session:
        return jsonify({'error': 'not logged in'}), 401

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM experiments WHERE id=%s AND user_id=%s", (exp_id, session['user_id']))
    exp = cur.fetchone()
    conn.close()

    if not exp:
        return jsonify({'error':'experiment not found'}), 404

    output_dir = exp['output_path']  # <-- corrected

    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    with zipfile.ZipFile(tmp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), output_dir))

    return jsonify({'zip_path': tmp_zip.name, 'filename': os.path.basename(output_dir)+'TWPA_TUP.zip'})

@app.route('/download_file')
def download_file():
    file_path = request.args.get('file')
    if not file_path or not os.path.exists(file_path):
        return "File not found", 404
    return send_file(file_path, as_attachment=True)

# ------------------ 啟動 ------------------
if __name__ == '__main__':
    os.makedirs('experiments', exist_ok=True)
    app.run(host='0.0.0.0', port=7133, debug=True)
