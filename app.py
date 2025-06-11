import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message
from sqlalchemy.sql import func
from datetime import datetime
import csv
import io
import uuid

app = Flask(__name__)

# Load environment variables from Render
DATABASE_URL = os.environ.get('Database_url')
SECRET_KEY = os.environ.get('SECRET_KEY')

if not DATABASE_URL:
    raise RuntimeError("Database_url environment variable not set")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable not set")

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = SECRET_KEY

db = SQLAlchemy(app)
migrate = Migrate(app, db)  # Initialize Flask-Migrate

# Mail config (update if needed)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='cokereafor@alxafrica.com',
    MAIL_PASSWORD='moqancerplnpisro',
)
mail = Mail(app)

ADMIN_PASSWORD = "alx_admin_2025_peer_finder"

class QueueEntry(db.Model):
    __tablename__ = 'queue'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String, nullable=False)
    phone = db.Column(db.String, nullable=False)
    email = db.Column(db.String, nullable=False)
    cohort = db.Column(db.String, nullable=False)
    assessment_week = db.Column(db.String, nullable=False)
    language = db.Column(db.String, nullable=False)
    submitted = db.Column(db.String, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=func.now())
    matched = db.Column(db.Boolean, nullable=False, default=False)
    matched_at = db.Column(db.DateTime, nullable=True)
    group_size = db.Column(db.Integer, nullable=False)
    group_id = db.Column(db.String, nullable=True)
    unpair_reason = db.Column(db.String, nullable=True)

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String)
    feedback = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False, default=func.now())

def send_match_email(group_members):
    with app.app_context():
        for member in group_members:
            msg = Message(
                subject="You Have Been Matched!",
                sender=app.config['MAIL_USERNAME'],
                recipients=[member.email],
            )
            peers = [f"{m.name} (WhatsApp: {m.phone})" for m in group_members if m.id != member.id]
            peers_text = "\n".join(peers) if peers else "No peers found."
            msg.body = f"""Hello {member.name},

You have been matched with the following peer(s):
{peers_text}

Please contact your peer(s) now!

Best regards,
Peer Matching Team
"""
            try:
                mail.send(msg)
            except Exception as e:
                print(f"Failed to send email to {member.email}: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/join', methods=['POST'])
def join_queue():
    try:
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip().lower()
        cohort = request.form.get('cohort', '').strip()
        assessment_week = request.form.get('assessment_week', '').strip()
        language = request.form.get('language', '').strip()
        group_size = request.form.get('group_size', '').strip()
        submitted = request.form.get('submitted', '').strip()
        disclaimer_agree = request.form.get('disclaimer_agree')

        if not (name and phone and email and cohort and assessment_week and language and group_size and submitted):
            return render_template('index.html', error="Please fill all fields correctly.")
        if not disclaimer_agree:
            return render_template('index.html', error="You must accept the disclaimer to continue.")
        if not phone.startswith('+') or len(phone) < 7:
            return render_template('index.html', error="Please enter a valid international phone number.")
        if language not in ['English', 'French', 'Arabic', 'Swahili']:
            return render_template('index.html', error="Please select a valid language.")
        try:
            group_size_int = int(group_size)
        except (ValueError, TypeError):
            return render_template('index.html', error="Invalid group size.")

        existing = QueueEntry.query.filter(
            ((QueueEntry.phone == phone) | (QueueEntry.email == email)) &
            (QueueEntry.cohort == cohort) &
            (QueueEntry.assessment_week == assessment_week) &
            (QueueEntry.language == language)
        ).first()
        if existing:
            if existing.matched:
                group_members = QueueEntry.query.filter_by(group_id=existing.group_id).all()
                return render_template('already_matched.html', user=existing, group_members=group_members)
            else:
                return render_template('already_in_queue.html', user_id=existing.id)

        new_user = QueueEntry(
            name=name,
            phone=phone,
            email=email,
            cohort=cohort,
            assessment_week=assessment_week,
            language=language,
            group_size=group_size_int,
            submitted=submitted,
            matched=False
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('waiting', user_id=new_user.id))
    except Exception as e:
        app.logger.error(f"Error in join_queue: {e}")
        return render_template('index.html', error="An unexpected error occurred. Please try again.")

@app.route('/waiting/<user_id>')
def waiting(user_id):
    return render_template('waiting.html', user_id=user_id)

@app.route('/match', methods=['POST'])
def match_users():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400

    combos = db.session.query(
        QueueEntry.cohort, QueueEntry.assessment_week, QueueEntry.language, QueueEntry.group_size
    ).filter_by(matched=False).distinct().all()
    for cohort, week, language, group_size in combos:
        eligible = QueueEntry.query.filter_by(
            matched=False,
            cohort=cohort,
            assessment_week=week,
            language=language,
            group_size=group_size
        ).all()
        while len(eligible) >= group_size:
            group = eligible[:group_size]
            group_id = f"group-{uuid.uuid4()}"
            now = datetime.utcnow()
            for member in group:
                member.matched = True
                member.group_id = group_id
                member.matched_at = now
            db.session.commit()
            send_match_email(group)
            eligible = eligible[group_size:]

    user = QueueEntry.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.matched:
        group_members = QueueEntry.query.filter_by(group_id=user.group_id).all()
        return jsonify({
            'matched': True,
            'group_id': user.group_id,
            'members': [
                {'name': m.name, 'phone': m.phone, 'email': m.email, 'id': m.id}
                for m in group_members
            ]
        })
    else:
        return jsonify({'matched': False})

@app.route('/matched/<user_id>')
def matched(user_id):
    user = QueueEntry.query.get(user_id)
    if not user:
        return "User not found", 404
    if not user.matched:
        return redirect(url_for('waiting', user_id=user_id))
    group_members = QueueEntry.query.filter_by(group_id=user.group_id).all()
    return render_template('matched.html', user=user, group_members=group_members)

@app.route('/check', methods=['GET', 'POST'])
def check_match():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        if not user_id:
            return render_template('check.html', error="Please enter your ID.")
        user = QueueEntry.query.get(user_id)
        if not user:
            return render_template('check.html', error="ID not found. Please check and try again.")
        if user.matched:
            group_members = QueueEntry.query.filter_by(group_id=user.group_id).all()
            return render_template('check.html', matched=True, group_members=group_members, user=user)
        else:
            return render_template('check.html', matched=False, user=user)
    else:
        return render_template('check.html')

@app.route('/unpair', methods=['POST'])
def unpair():
    user_id = request.form.get('user_id')
    reason = request.form.get('reason', '').strip()
    user = QueueEntry.query.get(user_id)
    if not user or not reason:
        return jsonify({'error': 'User ID and reason are required'}), 400
    user.matched = False
    user.group_id = None
    user.unpair_reason = reason
    user.matched_at = None
    db.session.commit()
    return jsonify({'success': True})

@app.route('/download/queue', methods=['GET', 'POST'])
def download_queue():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                'id', 'name', 'phone', 'email', 'cohort', 'assessment_week', 'language',
                'submitted', 'timestamp', 'matched', 'matched_at', 'group_size', 'group_id', 'unpair_reason'
            ])
            for entry in QueueEntry.query.all():
                writer.writerow([
                    entry.id, entry.name, entry.phone, entry.email, entry.cohort, entry.assessment_week, entry.language,
                    entry.submitted, entry.timestamp, entry.matched, entry.matched_at, entry.group_size, entry.group_id, entry.unpair_reason
                ])
            output.seek(0)
            return send_file(io.BytesIO(output.getvalue().encode()), as_attachment=True, download_name='peerfinder_queue.csv', mimetype='text/csv')
        else:
            flash("Incorrect password. Access denied.")
            return redirect(url_for('download_queue'))
    return render_template('password_prompt.html', file_type='Queue Data')

@app.route('/download/feedback', methods=['GET', 'POST'])
def download_feedback():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['id', 'user_id', 'feedback', 'timestamp'])
            for entry in Feedback.query.all():
                writer.writerow([entry.id, entry.user_id, entry.feedback, entry.timestamp])
            output.seek(0)
            return send_file(io.BytesIO(output.getvalue().encode()), as_attachment=True, download_name='peerfinder_feedback.csv', mimetype='text/csv')
        else:
            flash("Incorrect password. Access denied.")
            return redirect(url_for('download_feedback'))
    return render_template('password_prompt.html', file_type='Feedback Data')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
