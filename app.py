import os
import uuid
from datetime import datetime
import csv
import io
from flask import Flask, request, jsonify, render_template, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')  # [1]

# Database configuration (Render internal PostgreSQL) [2]
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable not set")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(32), nullable=False)
    email = db.Column(db.String(128), nullable=False)
    cohort = db.Column(db.String(64), nullable=False)
    assessment_week = db.Column(db.String(64), nullable=False)
    language = db.Column(db.String(32), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    matched = db.Column(db.Boolean, default=False)
    group_size = db.Column(db.Integer, nullable=False)
    group_id = db.Column(db.String(64), default='')
    unpair_reason = db.Column(db.String(256), default='')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'cohort': self.cohort,
            'assessment_week': self.assessment_week,
            'language': self.language,
            'timestamp': self.timestamp.isoformat(),
            'matched': self.matched,
            'group_size': self.group_size,
            'group_id': self.group_id,
            'unpair_reason': self.unpair_reason
        }

def find_existing_student(phone, email, cohort, assessment_week, language):
    return Student.query.filter(
        ((Student.phone == phone) | (Student.email == email)),
        Student.cohort == cohort,
        Student.assessment_week == assessment_week,
        Student.language == language
    ).first()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

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

    existing = find_existing_student(phone, email, cohort, assessment_week, language)

    if existing:
        if existing.matched:
            group_id = existing.group_id
            group_members = Student.query.filter_by(group_id=group_id).all()
            return render_template('already_matched.html', user=existing, group_members=group_members)
        else:
            return render_template('already_in_queue.html', user_id=existing.id)

    new_student = Student(
        id=str(uuid.uuid4()),
        name=name,
        phone=phone,
        email=email,
        cohort=cohort,
        assessment_week=assessment_week,
        language=language,
        timestamp=datetime.utcnow(),
        matched=False,
        group_size=group_size_int,
        group_id='',
        unpair_reason=''
    )
    db.session.add(new_student)
    db.session.commit()
    return redirect(url_for('waiting', user_id=new_student.id))

@app.route('/waiting/<user_id>')
def waiting(user_id):
    return render_template('waiting.html', user_id=user_id)

@app.route('/match', methods=['POST'])
def match_users():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400

    all_students = Student.query.all()
    cohorts = list(set(s.cohort for s in all_students if s.cohort))
    weeks = list(set(s.assessment_week for s in all_students if s.assessment_week))

    updated = False

    for cohort in cohorts:
        for week in weeks:
            for group_size in [2, 5]:
                eligible = [s for s in all_students if not s.matched and
                            s.cohort == cohort and s.assessment_week == week and
                            s.group_size == group_size]
                while len(eligible) >= group_size:
                    group = eligible[:group_size]
                    if len(set(s.id for s in group)) < group_size:
                        eligible = eligible[group_size:]
                        continue
                    group_id = f"group-{uuid.uuid4()}"
                    for s in group:
                        s.matched = True
                        s.group_id = group_id
                        db.session.add(s)
                    db.session.commit()
                    updated = True
                    eligible = eligible[group_size:]

    user = Student.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.matched:
        group_id = user.group_id
        group_members = Student.query.filter_by(group_id=group_id).all()
        return jsonify({
            'matched': True,
            'group_id': group_id,
            'members': [m.to_dict() for m in group_members]
        })
    else:
        return jsonify({'matched': False})

@app.route('/matched/<user_id>')
def matched(user_id):
    user = Student.query.get(user_id)
    if not user:
        return "User not found", 404
    if not user.matched:
        return redirect(url_for('waiting', user_id=user_id))
    group_id = user.group_id
    group_members = Student.query.filter_by(group_id=group_id).all()
    return render_template('matched.html', user=user, group_members=group_members)

@app.route('/check', methods=['GET', 'POST'])
def check_match():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        if not user_id:
            return render_template('check.html', error="Please enter your ID.")

        user = Student.query.get(user_id)
        if not user:
            return render_template('check.html', error="ID not found. Please check and try again.")

        if user.matched:
            group_id = user.group_id
            group_members = Student.query.filter_by(group_id=group_id).all()
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

    user = Student.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    user.matched = False
    user.group_id = ''
    user.unpair_reason = reason
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/admin/download_csv')
def download_csv():
    students = Student.query.all()

    output = io.StringIO()
    writer = csv.writer(output)

    # CSV header
    writer.writerow([
        'id', 'name', 'phone', 'email', 'cohort', 'assessment_week', 'language',
        'timestamp', 'matched', 'group_size', 'group_id', 'unpair_reason'
    ])

    for s in students:
        writer.writerow([
            s.id,
            s.name,
            s.phone,
            s.email,
            s.cohort,
            s.assessment_week,
            s.language,
            s.timestamp.isoformat(),
            s.matched,
            s.group_size,
            s.group_id,
            s.unpair_reason
        ])

    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=students.csv"}
    )

if __name__ == '__main__':
    # Create tables on startup without using before_first_request
    with app.app_context():
        db.create_all()
    app.run(debug=True)
