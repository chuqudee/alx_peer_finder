import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

# Load Google Sheets credentials from environment variable
GSHEET_CREDENTIALS_JSON = os.environ.get('GSHEET_CREDENTIALS_JSON')
GSHEET_SHEET_ID = os.environ.get('GSHEET_SHEET_ID')

if not GSHEET_CREDENTIALS_JSON or not GSHEET_SHEET_ID:
    raise Exception("Google Sheets credentials or Sheet ID not set in environment variables")

# Parse credentials JSON string
creds_dict = json.loads(GSHEET_CREDENTIALS_JSON)

# Setup Google Sheets API client
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client = gspread.authorize(creds)

# Open the sheet by ID
sheet = client.open_by_key(GSHEET_SHEET_ID).sheet1  # Use first worksheet

# Define expected columns in the sheet header row
SHEET_COLUMNS = [
    'id', 'name', 'phone', 'email', 'cohort', 'assessment_week', 'language',
    'timestamp', 'matched', 'group_size', 'group_id', 'unpair_reason'
]

def normalize_record(r):
    # Normalize matched to boolean
    if isinstance(r.get('matched'), str):
        r['matched'] = r['matched'].strip().upper() == 'TRUE'
    elif not isinstance(r.get('matched'), bool):
        r['matched'] = False

    # Normalize group_size to int
    try:
        r['group_size'] = int(r.get('group_size', 0))
    except Exception:
        r['group_size'] = 0

    # Strip whitespace from cohort and assessment_week
    r['cohort'] = r.get('cohort', '').strip()
    r['assessment_week'] = r.get('assessment_week', '').strip()
    r['language'] = r.get('language', '').strip()
    r['phone'] = r.get('phone', '').strip()
    r['email'] = r.get('email', '').strip().lower()

    # Ensure other keys exist to avoid KeyError
    for key in SHEET_COLUMNS:
        if key not in r:
            r[key] = ''

    return r

def get_all_records():
    try:
        records = sheet.get_all_records()
        normalized = [normalize_record(r) for r in records]
        return normalized
    except Exception as e:
        print(f"Error reading sheet: {e}")
        return []

def append_record(record):
    row = [record.get(col, '') for col in SHEET_COLUMNS]
    try:
        sheet.append_row(row)
    except Exception as e:
        print(f"Error appending to sheet: {e}")

def update_records(records):
    try:
        sheet.resize(rows=1)  # Keep header only
        rows = [[r.get(col, '') for col in SHEET_COLUMNS] for r in records]
        if rows:
            sheet.append_rows(rows)
    except Exception as e:
        print(f"Error updating sheet: {e}")

def find_student_row(records, phone, email, cohort, assessment_week, language):
    for idx, r in enumerate(records, start=2):  # Sheet rows start at 1, header is row 1
        if (r['phone'] == phone or r['email'] == email) and \
           r['cohort'] == cohort and \
           r['assessment_week'] == assessment_week and \
           r['language'] == language:
            return idx
    return None

def update_student_row(row_index, record):
    row = [record.get(col, '') for col in SHEET_COLUMNS]
    try:
        # Update the row in the sheet (columns A to L)
        sheet.update(f'A{row_index}:L{row_index}', [row])
    except Exception as e:
        print(f"Error updating student row: {e}")

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

    records = get_all_records()

    row_index = find_student_row(records, phone, email, cohort, assessment_week, language)

    if row_index:
        existing_record = records[row_index - 2]
        if existing_record['matched']:
            group_id = existing_record['group_id']
            group_members = [r for r in records if r['group_id'] == group_id]
            return render_template('already_matched.html', user=existing_record, group_members=group_members)
        else:
            return render_template('already_in_queue.html', user_id=existing_record['id'])

    # New student, create record
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
        'group_size': group_size_int,
        'group_id': '',
        'unpair_reason': ''
    }

    append_record(new_user)
    return redirect(url_for('waiting', user_id=new_user['id']))

@app.route('/waiting/<user_id>')
def waiting(user_id):
    return render_template('waiting.html', user_id=user_id)

@app.route('/match', methods=['POST'])
def match_users():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400

    records = get_all_records()
    cohorts = list(set(r['cohort'] for r in records if r['cohort']))
    weeks = list(set(r['assessment_week'] for r in records if r['assessment_week']))

    updated = False

    for cohort in cohorts:
        for week in weeks:
            for group_size in [2, 5]:
                eligible = [r for r in records if not r['matched'] and
                            r['cohort'] == cohort and r['assessment_week'] == week and
                            r['group_size'] == group_size]
                while len(eligible) >= group_size:
                    group = eligible[:group_size]
                    if len(set(r['id'] for r in group)) < group_size:
                        eligible = eligible[group_size:]
                        continue
                    group_id = f"group-{uuid.uuid4()}"
                    for r in records:
                        if r['id'] in [g['id'] for g in group]:
                            r['matched'] = True
                            r['group_id'] = group_id
                    updated = True
                    eligible = eligible[group_size:]

    if updated:
        update_records(records)

    user = next((r for r in records if r['id'] == user_id), None)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user['matched']:
        group_id = user['group_id']
        group_members = [r for r in records if r['group_id'] == group_id]
        return jsonify({
            'matched': True,
            'group_id': group_id,
            'members': group_members
        })
    else:
        return jsonify({'matched': False})

@app.route('/matched/<user_id>')
def matched(user_id):
    records = get_all_records()
    user = next((r for r in records if r['id'] == user_id), None)
    if not user:
        return "User not found", 404
    if not user['matched']:
        return redirect(url_for('waiting', user_id=user_id))
    group_id = user['group_id']
    group_members = [r for r in records if r['group_id'] == group_id]
    return render_template('matched.html', user=user, group_members=group_members)

@app.route('/check', methods=['GET', 'POST'])
def check_match():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        if not user_id:
            return render_template('check.html', error="Please enter your ID.")

        records = get_all_records()
        user = next((r for r in records if r['id'] == user_id), None)
        if not user:
            return render_template('check.html', error="ID not found. Please check and try again.")

        if user['matched']:
            group_id = user['group_id']
            group_members = [r for r in records if r['group_id'] == group_id]
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

    records = get_all_records()
    user = next((r for r in records if r['id'] == user_id), None)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    user['matched'] = False
    user['group_id'] = ''
    user['unpair_reason'] = reason

    update_records(records)
    return jsonify({'success': True})

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

if __name__ == '__main__':
    app.run(debug=True)
