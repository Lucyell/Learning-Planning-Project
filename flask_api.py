from flask import Flask, request, jsonify, send_from_directory
from project2 import DatabaseManager, GeneratorAgent, FocusManager, ProgressTracker, WeeklyReportGenerator
import os

app = Flask(__name__, static_folder='templates', static_url_path='')

# 初始化组件
db = DatabaseManager()
generator = GeneratorAgent()
focus_manager = FocusManager(db)
progress_tracker = ProgressTracker(db)
report_generator = WeeklyReportGenerator(db, focus_manager)

# 默认访问 login 页面
@app.route('/')
def index():
    return send_from_directory('templates', 'login.html')

# 支持访问所有 HTML 页面
@app.route('/<path:filename>')
def serve_html(filename):
    return send_from_directory('templates', filename)

# --- 以下是 API 接口 ---
@app.route('/api/login_or_register', methods=['POST'])
def login_or_register():
    data = request.json
    user_id = db.add_user(data['username'], data['email'])
    return jsonify({'user_id': user_id})

@app.route('/api/generate_plan', methods=['POST'])
def generate_plan():
    data = request.json
    content = generator.generate_plan(data['subject'], data['days'], data['level'])
    plan_id = db.add_study_plan(data['user_id'], data['subject'], data['days'], data['level'], content)
    return jsonify({'plan_content': content, 'plan_id': plan_id})

@app.route('/api/focus/start', methods=['POST'])
def start_focus():
    data = request.json
    session = focus_manager.start_focus(data['plan_id'], data['day_number'], data['task_name'])
    return jsonify({'status': 'started', 'session': session})

@app.route('/api/focus/end', methods=['POST'])
def end_focus():
    result = focus_manager.end_focus()
    return jsonify({'status': 'ended', 'result': result})

@app.route('/api/weekly_report', methods=['GET'])
def weekly_report():
    user_id = int(request.args.get('user_id'))
    user_plans = db.get_user_plans(user_id)
    if not user_plans:
        return jsonify({'report': '暂无计划'})
    plan_id = user_plans[0].id
    report = report_generator.generate_weekly_report(user_id, plan_id)
    return jsonify({'report': report})

@app.route('/api/progress', methods=['GET'])
def progress():
    user_id = int(request.args.get('user_id'))
    user_plans = db.get_user_plans(user_id)
    if not user_plans:
        return jsonify({})
    plan_id = user_plans[0].id
    return jsonify(progress_tracker.get_plan_progress(plan_id))

if __name__ == '__main__':
    app.run(debug=True)
