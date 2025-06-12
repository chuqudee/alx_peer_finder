import os
import uuid
import io
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, Response
import dropbox
import pandas as pd
from flask_mail import Mail, Message

application = Flask(__name__)
#application.secret_key = "e8f3473b716cfe3760fd522e38a3bd5b9909510b0ef003f050e0a445fa3a6e83"

# Flask-Mail configuration
application.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='cokereafor@alxafrica.com',  # Your email here
    MAIL_PASSWORD='moqancerplnpisro',          # Your app password here
)
mail = Mail(application)

DROPBOX_ACCESS_TOKEN = 'sl.u.AFys5DRaycrcUxumYg8KHWR6EdMxU63qRgxqK_koZhGomcaAVz3APCnFNHs0PTMoKBAAPwsq35x7s4RawmRmgmBX9fje-LtbTXcd0MwTnInfQxVg9u7TD7fqzUcXMdDEJrVk5U5_6zYyfQZN9BgiYGpkzwKRr1uk3AiijRkVZdm1jYvfnhlH-Tm6hR1pZ-ySujtpxcSjQXoEJluM-o8J5Ac0MotZrD2_tXyR4b97x9se-YY4oxQbTc0Gao657TYsLpuUxRE8R0RI6CtyjunyMmX4J2tanfEyADigUzi10wVgo0Tio0hMQeLZ2jgKf4TY_H0H3AtPgRIrxTp96qx-vu4ho8FJvuZGbTvgUeIq37M-KTAaIxoMSjTqNtk_Kq9VGt7i6XjHzlmSmVRHM1Dk2QHyM3hDSmBI5xcVJLcs4uaRFZIYi8-M-19nDZghMVyEypLftSE6POaKCtRy-AOH64yAefJezExUG5wLgBLjkuLbRFx4edbk9zRiLOLT7x3xGAxu7hI6WrJG5eNKe85Qc4-_GQvWAROOk6-tySx_GoHie3oShZJqou0c71PR9ra62u5WO0fq_Xw4LYifKOULmgh6wHNmskGwlbhSDjp5fCtS17b_ZcFg637kKEe9uxw2K7ShTGflLB2mu43oMtxOm3yese2z_-6M_J0Yk5O1Rzulfm-AlZnIwmMoHTdJdasrNCbmgZa7kqhlwsSSA47uSWlKC3qIBDhQxAP7Lw2MxJpm-QXmtbZz4b2T2830kGhldr9VSWwQfx8p2Hq_Cqc2_HsJIDGm3JnTv2dU5lsBkBcwIiOFGQLljnmubwlcKcO5SehS2RFpl1azEqQksZopLAu8Mw-b4oam1N2SFVZZbg0I7lQWxlMGtG55ah2rYft39BKll4hllugiJFVGsDvN2ODkoLQ7OoJqAcgMaHB3AObpjuiJyCm93bxkiYVdh8UebFrqk4hhZbAUXoekWiA9GO8F30fWrGjfOlMyA7bi08xl-GrrmrZk9wCQtCjm1XTstbxbKAlWadAmWM507Ny088bZdymL0h6ZYkC_Dh1xqYdk8FM8owUvobObrzdC0Zgs1GR8Jc4ZFOSrlj2p-rJg65bnooGunOdjEbSb40j66b8yGq58I2q3UMg68Q_5TDLGIc-iXmC1z-40ECmPFzlCCsV3HMpPU6TC_66l6iDweCaX4D3OFmXnqwIhElkiEKdeYLcN5P8LLto8E-CxZYPZbapSYx_l_FlfjSbr4rSgCaStBnMx5d0YzZY63eVCyNCiRFqSNuUh49B9outrT-hLDHqXOIUeHosiXKcPjVdqci4wQ1TX6FnnPPIxYJjaBMZ9wnSx1u48TVMqiySAlZZqjP8SQMCrDmmqSfhdqay85KPRGOtLxjjLtmnqOSJFwwtBo2RYI6PPt6uy-Ux0rrA8ECrbPrJxoD1gCWnYcRaaHSYaJpiNG_8cIluT-f1R0K3-gRQ'

#if DROPBOX_ACCESS_TOKEN:
#    print(DROPBOX_ACCESS_TOKEN)
#    raise Exception("DROPBOX_ACCESS_TOKEN environment variable not set")


dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
CSV_PATH = '/students.csv'

def download_csv():
    try:
        metadata, res = dbx.files_download(CSV_PATH)
        csv_content = res.content.decode('utf-8')
        df = pd.read_csv(io.StringIO(csv_content))
        # Ensure phone is string to avoid float formatting issues
        if 'phone' in df.columns:
            df['phone'] = df['phone'].astype(str).str.strip()
        if 'matched' in df.columns:
            df['matched'] = df['matched'].astype(str).str.upper() == 'TRUE'
        else:
            df['matched'] = False
        if 'matched_timestamp' not in df.columns:
            df['matched_timestamp'] = ''
        return df
    except dropbox.exceptions.ApiError:
        columns = ['id', 'name', 'phone', 'email', 'cohort', 'assessment_week', 'language',
                   'timestamp', 'matched', 'group_size', 'group_id', 'unpair_reason', 'matched_timestamp']
        return pd.DataFrame(columns=columns)

def upload_csv(df):
    # Ensure phone column is string before upload to prevent float formatting
    if 'phone' in df.columns:
        df['phone'] = df['phone'].astype(str).str.strip()
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

def send_match_email(user_email, user_name, group_members):
    peer_info = '\n'.join([
        f"Name: {m['name']}, Email: {m['email']}, Phone: {m['phone']}"
        for m in group_members if m['email'] != user_email
    ])
    body = f"""Hi {user_name},

You have been matched with the following peers:

{peer_info}

Best regards,
Peer Finder Team
"""
    msg = Message(
        subject="You've been matched!",
        sender=application.config['MAIL_USERNAME'],
        recipients=[user_email]
    )
    mail.send(msg)

@application.route('/')
def index():
    return render_template('index.html')

@application.route('/join', methods=['POST'])
def join_queue():
    name = request.form.get('name', '').strip()
    phone = str(request.form.get('phone', '').strip())  # Ensure string
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
        'unpair_reason': '',
        'matched_timestamp': ''
    }
    new_row_df = pd.DataFrame([new_row])
    df = pd.concat([df, new_row_df], ignore_index=True)

    # Ensure phone column is string before upload
    df['phone'] = df['phone'].astype(str).str.strip()

    upload_csv(df)
    return redirect(url_for('waiting', user_id=new_id))

@application.route('/waiting/<user_id>')
def waiting(user_id):
    return render_template('waiting.html', user_id=user_id)

@application.route('/match', methods=['POST'])
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
                    now_iso = datetime.utcnow().isoformat()
                    df.loc[group.index, 'matched'] = True
                    df.loc[group.index, 'group_id'] = group_id
                    df.loc[group.index, 'matched_timestamp'] = now_iso
                    updated = True
                    eligible = eligible.iloc[group_size:]

    if updated:
        # Ensure phone column is string before upload
        df['phone'] = df['phone'].astype(str).str.strip()
        upload_csv(df)

    user = df[df['id'] == user_id]
    if user.empty:
        return jsonify({'error': 'User not found'}), 404

    user = user.iloc[0]
    if user['matched']:
        group_id = user['group_id']
        group_members = df[df['group_id'] == group_id]
        members_list = group_members.to_dict(orient='records')
        # Send email to each member with peer info
        for m in members_list:
            send_match_email(m['email'], m['name'], members_list)
        return jsonify({
            'matched': True,
            'group_id': group_id,
            'members': members_list
        })
    else:
        return jsonify({'matched': False})

@application.route('/matched/<user_id>')
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

@application.route('/check', methods=['GET', 'POST'])
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

@application.route('/unpair', methods=['POST'])
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
    df.at[idx, 'matched_timestamp'] = ''

    # Ensure phone column is string before upload
    df['phone'] = df['phone'].astype(str).str.strip()

    upload_csv(df)
    return jsonify({'success': True})

@application.route('/admin')
def admin():
    return render_template('admin.html')

@application.route('/admin/download_csv')
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

@application.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

if __name__ == '__main__':
    application.run()
