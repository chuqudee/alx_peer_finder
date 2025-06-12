import os
import uuid
import io
from flask import Flask, request, jsonify, render_template, redirect, url_for
import dropbox
import pandas as pd
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

DROPBOX_ACCESS_TOKEN = os.environ.get('DROPBOX_ACCESS_TOKEN')
if not DROPBOX_ACCESS_TOKEN:
    raise Exception("DROPBOX_ACCESS_TOKEN environment variable not set")

dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
CSV_PATH = '/students.csv'

def download_csv():
    try:
        metadata, res = dbx.files_download(CSV_PATH)
        csv_content = res.content.decode('utf-8')
        df = pd.read_csv(io.StringIO(csv_content))
        # Normalize matched column to boolean
        if 'matched' in df.columns:
            df['matched'] = df['matched'].astype(str).str.upper() == 'TRUE'
        else:
            df['matched'] = False
        return df
    except dropbox.exceptions.ApiError as e:
        # If file not found, return empty DataFrame with expected columns
        columns = ['id', 'name', 'phone', 'email', 'cohort', 'assessment_week', 'language',
                   'timestamp', 'matched', 'group_size', 'group_id', 'unpair_reason']
        return pd.DataFrame(columns=columns)

def upload_csv(df):
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    dbx.files_upload(csv_buffer.read().encode('utf-8'), CSV_PATH, mode=dropbox.files.WriteMode.overwrite)

def find_existing(df, phone, email, cohort, assessment_week, language):
    mask = (
        ((df['phone'] == phone) | (df['email'] == email)) &
        (df['cohort'] == cohort) &
        (df['assessment_week'] == assessment_week) &
        (df['language'] == language)
    )
    matches = df[mask]
    if not matches.empty:
        return matches.index[0]
    return None

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

    try:
        group_size_int = int(group_size)
    except ValueError:
        return render_template('index.html', error="Invalid group size.")

    df = download_csv()

    existing_idx = find_existing(df, phone, email, cohort, assessment_week, language)

    if existing_idx is not None:
        existing_record = df.loc[existing_idx]
        if existing_record['matched']:
            group_id = existing_record['group_id']
            group_members = df[df['group_id'] == group_id]
            return render_template('already_matched.html', user=existing_record, group_members=group_members.to_dict(orient='records'))
        else:
            return render_template('already_in_queue.html', user_id=existing_record['id'])

    new_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    new_row = {
        'id': new_id,
        'name': name,
        'phone': phone,
        'email': email,
        'cohort': cohort,
        'assessment_week': assessment_week,
        'language': language,
        'timestamp': timestamp,
        'matched': False,
        'group_size': group_size_int,
        'group_id': '',
        'unpair_reason': ''
    }
    df = df.append(new_row, ignore_index=True)
    upload_csv(df)
    return redirect(url_for('waiting', user_id=new_id))

@app.route('/waiting/<user_id>')
def waiting(user_id):
    return render_template('waiting.html', user_id=user_id)

@app.route('/match', methods=['POST'])
def match_users():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400

    df = download_csv()

    cohorts = df['cohort'].dropna().unique()
    weeks = df['assessment_week'].dropna().unique()

    updated = False

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
                    if len(set(group['id'])) < group_size:
                        eligible = eligible.iloc[group_size:]
                        continue
                    group_id = f"group-{uuid.uuid4()}"
                    df.loc[group.index, 'matched'] = True
                    df.loc[group.index, 'group_id'] = group_id
                    updated = True
                    eligible = eligible.iloc[group_size:]

    if updated:
        upload_csv(df)

    user = df[df['id'] == user_id]
    if user.empty:
        return jsonify({'error': 'User not found'}), 404

    user = user.iloc[0]
    if user['matched']:
        group_id = user['group_id']
        group_members = df[df['group_id'] == group_id]
        return jsonify({
            'matched': True,
            'group_id': group_id,
            'members': group_members.to_dict(orient='records')
        })
    else:
        return jsonify({'matched': False})

@app.route('/matched/<user_id>')
def matched(user_id):
    df = download_csv()
    user = df[df['id'] == user_id]
    if user.empty:
        return "User not found", 404
    user = user.iloc[0]
    if not user['matched']:
        return redirect(url_for('waiting', user_id=user_id))
    group_id = user['group_id']
    group_members = df[df['group_id'] == group_id]
    return render_template('matched.html', user=user, group_members=group_members.to_dict(orient='records'))

@app.route('/check', methods=['GET', 'POST'])
def check_match():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        if not user_id:
            return render_template('check.html', error="Please enter your ID.")

        df = download_csv()
        user = df[df['id'] == user_id]
        if user.empty:
            return render_template('check.html', error="ID not found. Please check and try again.")

        user = user.iloc[0]
        if user['matched']:
            group_id = user['group_id']
            group_members = df[df['group_id'] == group_id]
            return render_template('check.html', matched=True, group_members=group_members.to_dict(orient='records'), user=user)
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

    df = download_csv()
    user_idx = df.index[df['id'] == user_id]
    if user_idx.empty:
        return jsonify({'error': 'User not found'}), 404

    idx = user_idx[0]
    df.at[idx, 'matched'] = False
    df.at[idx, 'group_id'] = ''
    df.at[idx, 'unpair_reason'] = reason
    upload_csv(df)
    return jsonify({'success': True})

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/admin/download_csv')
def download_csv_route():
    df = download_csv()
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    return Response(
        csv_buffer,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=students.csv"}
    )

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

if __name__ == '__main__':
    app.run(debug=True)
