from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, flash
import pandas as pd
from datetime import datetime
import uuid
import os
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = 'some_secret_key'  # Required for flashing messages

CSV_PATH = 'queue.csv'
FEEDBACK_CSV_PATH = 'feedback.csv'  # Assuming feedback stored here

ADMIN_PASSWORD = "alx_admin_2025_peer_finder"

app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='cokereafor@alxafrica.com',  # Your email here
    MAIL_PASSWORD='moqancerplnpisro',          # Your password or app password here
)
mail = Mail(app)

COLUMNS = [
    'id', 'name', 'phone', 'email', 'cohort', 'assessment_week', 'language',
    'timestamp', 'matched', 'group_size', 'group_id', 'unpair_reason'
]

if not os.path.exists(CSV_PATH):
    pd.DataFrame(columns=COLUMNS).to_csv(CSV_PATH, index=False)

def read_queue():
    return pd.read_csv(CSV_PATH)

def save_queue(df):
    df.to_csv(CSV_PATH, index=False)

def send_match_email(group_members):
    with app.app_context():
        for member in group_members:
            msg = Message(
                subject="You Have Been Matched!",
                sender=app.config['MAIL_USERNAME'],
                recipients=[member['email']],
            )
            peers = [f"{m['name']} (WhatsApp: {m['phone']})" for m in group_members if m['id'] != member['id']]
            peers_text = "\n".join(peers) if peers else "No peers found."
            msg.body = f"""Hello {member['name']},

You have been matched with the following peer(s):
{peers_text}

Please contact your peer(s) now!

Best regards,
Peer Matching Team
"""
            try:
                mail.send(msg)
                print(f"Email sent to {member['email']}")
            except Exception as e:
                print(f"Failed to send email to {member['email']}: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/join', methods=['POST'])
def join_queue():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip().lower()
    cohort = request.form.get('cohort', '').strip()
    assessment_week = request.form.get('assessment_week', '').strip()
    language = request.form.get('language', '').strip()
    group_size = request.form.get('group_size', '').strip()

    if not (name and phone and email and cohort and assessment_week and language and group_size):
        return render_template('index.html', error="Please fill all fields correctly.")

    if not phone.startswith('+') or len(phone) < 7:
        return render_template('index.html', error="Please enter a valid international phone number.")

    if language not in ['English', 'French', 'Arabic', 'Swahili']:
        return render_template('index.html', error="Please select a valid language.")

    df = read_queue()

    existing = df[
        ((df['phone'] == phone) | (df['email'] == email)) &
        (df['cohort'] == cohort) &
        (df['assessment_week'] == assessment_week) &
        (df['language'] == language)
    ]
    if not existing.empty:
        user = existing.iloc[0]
        if user['matched']:
            group_id = user['group_id']
            group_members = df[df['group_id'] == group_id][['name', 'phone', 'email', 'id']].to_dict('records')
            return render_template('already_matched.html', user=user, group_members=group_members)
        else:
            return render_template('already_in_queue.html', user_id=user['id'])

    new_user = {
        'id': str(uuid.uuid4()),
        'name': name,
        'phone': phone,
        'email': email,
        'cohort': cohort,
        'assessment_week': assessment_week,
        'language': language,
        'timestamp': datetime.now().isoformat(),
        'matched': False,
        'group_size': int(group_size),
        'group_id': '',
        'unpair_reason': ''
    }

    df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
    save_queue(df)
    return redirect(url_for('waiting', user_id=new_user['id']))

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

@app.route('/waiting/<user_id>')
def waiting(user_id):
    return render_template('waiting.html', user_id=user_id)

@app.route('/match', methods=['POST'])
def match_users():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400

    df = read_queue()
    cohorts = df['cohort'].dropna().unique()
    weeks = df['assessment_week'].dropna().unique()
    for cohort in cohorts:
        for week in weeks:
            for group_size in [2, 5]:
                eligible = df[
                    (df['matched'] == False) &
                    (df['cohort'] == cohort) &
                    (df['assessment_week'] == week) &
                    (df['group_size'] == group_size)
                ]
                while len(eligible) >= group_size:
                    group = eligible.iloc[:group_size]
                    if group['id'].nunique() < group_size:
                        eligible = eligible.iloc[group_size:]
                        continue
                    group_id = f"group-{uuid.uuid4()}"
                    df.loc[df['id'].isin(group['id']), 'matched'] = True
                    df.loc[df['id'].isin(group['id']), 'group_id'] = group_id
                    save_queue(df)
                    group_members = df[df['group_id'] == group_id][['name', 'phone', 'email', 'id']].to_dict('records')
                    send_match_email(group_members)
                    eligible = eligible.iloc[group_size:]

    user = df[df['id'] == user_id]
    if user.empty:
        return jsonify({'error': 'User not found'}), 404
    user = user.iloc[0]
    if user['matched']:
        group_id = user['group_id']
        group_members = df[df['group_id'] == group_id][['name', 'phone', 'email', 'id']].to_dict('records')
        return jsonify({
            'matched': True,
            'group_id': group_id,
            'members': group_members
        })
    else:
        return jsonify({'matched': False})

@app.route('/matched/<user_id>')
def matched(user_id):
    df = read_queue()
    user = df[df['id'] == user_id]
    if user.empty:
        return "User not found", 404
    user = user.iloc[0]
    if not user['matched']:
        return redirect(url_for('waiting', user_id=user_id))
    group_id = user['group_id']
    group_members = df[df['group_id'] == group_id][['name', 'phone', 'email', 'id']].to_dict('records')
    return render_template('matched.html', user=user, group_members=group_members)

@app.route('/check', methods=['GET', 'POST'])
def check_match():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        if not user_id:
            return render_template('check.html', error="Please enter your ID.")

        df = read_queue()
        user = df[df['id'] == user_id]
        if user.empty:
            return render_template('check.html', error="ID not found. Please check and try again.")

        user = user.iloc[0]
        if user['matched']:
            group_id = user['group_id']
            group_members = df[df['group_id'] == group_id][['name', 'phone', 'email', 'id']].to_dict('records')
            return render_template('check.html', matched=True, group_members=group_members, user=user)
        else:
            return render_template('check.html', matched=False, user=user)
    else:
        return render_template('check.html')

@app.route('/unpair', methods=['POST'])
def unpair():
    user_id = request.form.get('user_id')
    reason = request.form.get('reason', '').strip()
    if not user_id or not reason:
        return jsonify({'error': 'User ID and reason are required'}), 400
    df = read_queue()
    idx = df[df['id'] == user_id].index
    if len(idx) == 0:
        return jsonify({'error': 'User not found'}), 404
    df.at[idx[0], 'matched'] = False
    df.at[idx[0], 'group_id'] = ''
    df.at[idx[0], 'unpair_reason'] = reason
    save_queue(df)
    return jsonify({'success': True})

# Password-protected download for queue CSV
@app.route('/download/queue', methods=['GET', 'POST'])
def download_queue():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            if not os.path.exists(CSV_PATH):
                return "No queue data available.", 404
            return send_file(CSV_PATH, as_attachment=True, download_name='peerfinder_queue.csv', mimetype='text/csv')
        else:
            flash("Incorrect password. Access denied.")
            return redirect(url_for('download_queue'))
    return render_template('password_prompt.html', file_type='Queue Data')

# Password-protected download for feedback CSV
@app.route('/download/feedback', methods=['GET', 'POST'])
def download_feedback():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            if not os.path.exists(FEEDBACK_CSV_PATH):
                return "No feedback data available.", 404
            return send_file(FEEDBACK_CSV_PATH, as_attachment=True, download_name='peerfinder_feedback.csv', mimetype='text/csv')
        else:
            flash("Incorrect password. Access denied.")
            return redirect(url_for('download_feedback'))
    return render_template('password_prompt.html', file_type='Feedback Data')

@app.route('/admin')
def admin():
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(debug=True)
