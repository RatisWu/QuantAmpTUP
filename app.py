from flask import Flask, render_template, request, redirect, session, jsonify, send_file, url_for, flash
import pymysql
from copy import deepcopy
from datetime import datetime
import os, shutil, zipfile, tempfile
import toml, tomlkit
import subprocess
import sys, threading
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SESSION_PERMANENT'] = False

DB_CONFIG = dict(host='localhost', user='QuantAmpTUP', password='CCDismyBOSS', db='QuantAmpTUP')

def get_conn():
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)

def pre_process(toml_path:str):
    output_folder:str = ''

    # Assuming 'config.toml' is your file
    with open(toml_path, 'r') as file:
        content = file.read()
        sweepLF_config = tomlkit.parse(content)
        sample_name = sweepLF_config['Job_info']['sample']
        output_folder = os.path.join(os.getcwd(),'experiments',f"{sample_name}_job_{datetime.now().strftime('%y%m%d_%H%M%S')}")
        sweepLF_config['Readout']['output'] = output_folder
        x = deepcopy(sweepLF_config)
    
    with open(toml_path, "w") as f: # Open in text write mode
        f.write(tomlkit.dumps(x))

    return output_folder

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
@app.route('/upload_ajax', methods=['POST'])
def upload_ajax():
    if 'user_id' not in session:
        return jsonify({'error': 'not logged in'}), 401

    try:
        file = request.files.get('toml_file')
        if not file:
            return jsonify({'error': 'no file'}), 400

        save_path = os.path.join('experiments', file.filename)
        os.makedirs('experiments', exist_ok=True)
        file.save(save_path)

        
        output_dir = pre_process(save_path)
        os.makedirs(output_dir, exist_ok=True)
        data = toml.load(save_path)
        conn = get_conn()
        cur = conn.cursor()

        # Lock instruments (same logic as before)
        instrument_ids = []
        for hw_name, hw in data['Hardware'].items():
            ip = hw['address']
            cur.execute("SELECT * FROM instruments WHERE ip_address=%s", (ip,))
            existing = cur.fetchone()
            if existing:
                if existing['user_id'] is not None:
                    conn.close()
                    return jsonify({'error': f"{hw_name}:{ip} 已被佔用"}), 400
                cur.execute("UPDATE instruments SET user_id=%s WHERE id=%s", (session['user_id'], existing['id']))
                instrument_ids.append(existing['id'])
            else:
                cur.execute(
                    "INSERT INTO instruments (instrument_name, ip_address, user_id) VALUES (%s,%s,%s)",
                    (hw_name, ip, session['user_id'])
                )
                instrument_ids.append(cur.lastrowid)
        conn.commit()

        # Record experiment with status 'running'
        cur.execute(
            "INSERT INTO experiments (user_id, output_path, toml_path, status) VALUES (%s,%s,%s,%s)",
            (session['user_id'], output_dir, save_path, 'running')
        )
        exp_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        # Run experiment in background
        def run_experiment():
            subprocess.run([sys.executable, '/home/ratiswu/Documents/GitHub/QuantAmpTUP/PYs/TWPAFastTUP.py', save_path],check=True)
            # Update status to 'done' and release instruments
            conn2 = get_conn()
            cur2 = conn2.cursor()
            cur2.execute("UPDATE experiments SET status='done' WHERE id=%s", (exp_id,))
            if instrument_ids:
                cur2.execute(
                    "UPDATE instruments SET user_id=NULL WHERE id IN (%s)" % ",".join(["%s"]*len(instrument_ids)),
                    instrument_ids
                )
            conn2.commit()
            conn2.close()

        threading.Thread(target=run_experiment).start()
        return jsonify({'exp_id': exp_id})
    except subprocess.CalledProcessError as e:
        # Script exited with non-zero code
        conn2 = get_conn()
        cur2 = conn2.cursor()
        cur2.execute("UPDATE experiments SET status='error' WHERE id=%s", (exp_id,))
        if instrument_ids:
            cur2.execute(
                "UPDATE instruments SET user_id=NULL WHERE id IN (%s)" % ",".join(["%s"]*len(instrument_ids)),
                instrument_ids
            )
        conn2.commit()
        conn2.close()
        return jsonify({'error': str(e)}), 500

    except Exception as e:
        # Any Python exception
        conn2 = get_conn()
        cur2 = conn2.cursor()
        cur2.execute("UPDATE experiments SET status='error' WHERE id=%s", (exp_id,))
        if instrument_ids:
            cur2.execute(
                "UPDATE instruments SET user_id=NULL WHERE id IN (%s)" % ",".join(["%s"]*len(instrument_ids)),
                instrument_ids
            )
        conn2.commit()
        conn2.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/exp_status/<int:exp_id>')
def exp_status(exp_id):
    if 'user_id' not in session:
        return jsonify({'error': 'not logged in'}), 401
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT status FROM experiments WHERE id=%s AND user_id=%s", (exp_id, session['user_id']))
    exp = cur.fetchone()
    conn.close()
    if not exp:
        return jsonify({'error':'not found'}), 404
    return jsonify({'status': exp['status']})

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
