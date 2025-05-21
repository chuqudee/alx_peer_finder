from flask import Flask, request, jsonify, render_template, redirect, url_for
import pandas as pd
from datetime import datetime
import uuid
import os
from flask_mail import Mail, Message

app = Flask(__name__)
CSV_PATH = 'queue.csv'

# === Flask-Mail Configuration ===
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='',        # <-- YOUR EMAIL HERE
    MAIL_PASSWORD='',  # <-- YOUR PASSWORD HERE
)
mail = Mail(app)

# Initialize CSV file if not exists
if not os.path.exists(CSV_PATH):
    pd.DataFrame(columns=['id', 'name', 'phone', 'email', 'submitted', 'timestamp', 'matched', 'group_size', 'group_id']).to_csv(CSV_PATH, index=False)

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
    submitted = request.form.get('submitted', '').strip().lower()
    group_size = request.form.get('group_size', '').strip()

    # Validate inputs
    if not name or not phone or not email or submitted not in ['yes', 'no'] or group_size not in ['2', '5']:
        return render_template('index.html', error="Please fill all fields correctly.")

    df = read_queue()

    # Check if user already exists by phone or email
    existing = df[(df['phone'] == phone) | (df['email'] == email)]
    if not existing.empty:
        user = existing.iloc[0]
        if user['matched']:
            # User already matched - show matched info page
            group_id = user['group_id']
            group_members = df[df['group_id'] == group_id][['name', 'phone', 'email', 'id']].to_dict('records')
            return render_template('already_matched.html', user=user, group_members=group_members)
        else:
            # User in queue but not matched yet
            return render_template('already_in_queue.html', user_id=user['id'])

    # New user - add to queue
    new_user = {
        'id': str(uuid.uuid4()),
        'name': name,
        'phone': phone,
        'email': email,
        'submitted': submitted.capitalize(),  # Store as 'Yes' or 'No'
        'timestamp': datetime.now().isoformat(),
        'matched': False,
        'group_size': int(group_size),
        'group_id': ''
    }

    df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
    save_queue(df)

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

    df = read_queue()

    # Run matching for each submitted status and group size
    for submitted_status in ['Yes', 'No']:
        for group_size in [2, 5]:
            eligible = df[(df['matched'] == False) & (df['submitted'] == submitted_status) & (df['group_size'] == group_size)]

            # Prevent matching same user twice by ensuring unique IDs
            while len(eligible) >= group_size:
                group = eligible.iloc[:group_size]

                # Extra safety: ensure unique users in group
                if group['id'].nunique() < group_size:
                    # Remove duplicates by id
                    eligible = eligible.iloc[group_size:]
                    continue

                group_id = f"group-{uuid.uuid4()}"
                df.loc[df['id'].isin(group['id']), 'matched'] = True
                df.loc[df['id'].isin(group['id']), 'group_id'] = group_id
                save_queue(df)  # Save immediately

                group_members = df[df['group_id'] == group_id][['name', 'phone', 'email', 'id']].to_dict('records')

                send_match_email(group_members)

                eligible = eligible.iloc[group_size:]

    # Check if requesting user is matched now
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

# New route: check matching status by user ID
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

# Page shown if user tries to join but is already in queue
@app.route('/already_in_queue')
def already_in_queue():
    # This route is used internally from join_queue()
    # You can remove this if you prefer to render inline
    return "You are already in the queue."

if __name__ == '__main__':
    app.run(debug=True)
