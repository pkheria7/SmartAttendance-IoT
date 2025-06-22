from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
import os
import pandas as pd
from fpdf import FPDF
from datetime import datetime, timedelta
from firebase_admin import db
from collections import defaultdict, Counter
import firebase_admin
from firebase_admin import credentials, db
import json
from io import BytesIO
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.dates import DateFormatter
import base64
#from templates import analytics, dashboard, login, students, student_detail, reports, settings

# Initialize Firebase
cred = credentials.Certificate("iot-smart-attendance-cfd49-firebase-adminsdk-fbsvc-63f16e561b.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://iot-smart-attendance-cfd49-default-rtdb.firebaseio.com'
})

app = Flask(__name__)
app.secret_key = 'supersecret_enhanced_attendance_2024'

# Configuration
USERNAME = "admin"
PASSWORD = "1234"
status_file = "E:\\Smart-Attendence-System\\status.txt"
data_file = "E:\\Smart-Attendence-System\\MAIN Programs\\PC\\attendance_data\\attendance.csv"

# Helper Functions
def generate_chart(chart_type='attendance_trend'):
    """Generate different types of charts based on the selected type"""
    stats = calculate_attendance_stats()
    attendance_matrix, all_names, dates_list = get_attendance_data()
    
    plt.figure(figsize=(12, 6))
    
    if chart_type == 'attendance_trend':
        # Attendance trend over time (existing functionality)
        if not stats['attendance_trends']:
            return None
        
        dates = [item['date'] for item in stats['attendance_trends']]
        rates = [item['rate'] for item in stats['attendance_trends']]
        
        plt.plot(dates, rates, marker='o', linewidth=2, markersize=4)
        plt.title('Attendance Trend (Last 30 Days)', fontsize=16, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Attendance Rate (%)', fontsize=12)
        plt.xticks(rotation=45)
        
    elif chart_type == 'daily_counts':
        # Number of students per day
        if not dates_list:
            return None
            
        # Get last 14 days for better visibility
        recent_dates = dates_list[-14:] if len(dates_list) >= 14 else dates_list
        counts = []
        
        for date in recent_dates:
            present_count = 0
            for name in all_names:
                if attendance_matrix[name].get(date, {}).get("status") == "P":
                    present_count += 1
            counts.append(present_count)
        
        plt.bar(recent_dates, counts, color='skyblue')
        plt.title('Daily Student Attendance Count', fontsize=16, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Number of Students Present', fontsize=12)
        plt.xticks(rotation=45)
        
    elif chart_type == 'student_comparison':
        # Top 10 and bottom 10 students by attendance rate
        if not all_names:
            return None
            
        # Calculate attendance rates for each student
        student_rates = {}
        for name in all_names:
            present_days = sum(1 for date in dates_list 
                            if attendance_matrix[name].get(date, {}).get("status") == "P")
            attendance_rate = (present_days / len(dates_list) * 100) if dates_list else 0
            student_rates[name] = attendance_rate
        
        # Sort students by attendance rate
        sorted_students = sorted(student_rates.items(), key=lambda x: x[1], reverse=True)
        
        # Get top 10 and bottom 10 (or fewer if less than 20 total)
        num_to_show = min(10, len(sorted_students) // 2)
        top_students = sorted_students[:num_to_show]
        bottom_students = sorted_students[-num_to_show:]
        
        # Plot
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Top students
        names = [s[0] for s in top_students]
        rates = [s[1] for s in top_students]
        ax1.barh(names, rates, color='green')
        ax1.set_title('Top Attendance Rates', fontsize=14)
        ax1.set_xlim(0, 100)
        
        # Bottom students
        names = [s[0] for s in bottom_students]
        rates = [s[1] for s in bottom_students]
        ax2.barh(names, rates, color='salmon')
        ax2.set_title('Lowest Attendance Rates', fontsize=14)
        ax2.set_xlim(0, 100)
        
        plt.tight_layout()
        
    elif chart_type == 'weekday_analysis':
        # Attendance patterns by day of week
        if not dates_list:
            return None
            
        # Convert date strings to datetime objects
        weekday_counts = [0] * 7
        weekday_totals = [0] * 7
        
        for date in dates_list:
            try:
                dt = datetime.fromisoformat(date)
                weekday = dt.weekday()  # 0 = Monday, 6 = Sunday
                
                present_count = 0
                for name in all_names:
                    if attendance_matrix[name].get(date, {}).get("status") == "P":
                        present_count += 1
                
                weekday_counts[weekday] += present_count
                weekday_totals[weekday] += len(all_names)
            except:
                continue
        
        # Calculate average attendance rate for each weekday
        weekday_rates = [
            (count / total * 100) if total > 0 else 0 
            for count, total in zip(weekday_counts, weekday_totals)
        ]
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        plt.bar(days, weekday_rates, color='purple')
        plt.title('Attendance Rate by Day of Week', fontsize=16, fontweight='bold')
        plt.xlabel('Day of Week', fontsize=12)
        plt.ylabel('Average Attendance Rate (%)', fontsize=12)
        plt.ylim(0, 100)
    
    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    chart_data = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    return chart_data


def get_attendance_data():
    """Fetch and process attendance data from Firebase"""
    attendance_ref = db.reference('attendance')
    attendance_data = attendance_ref.get() or {}
    
    names_set = set()
    dates_list = sorted(attendance_data.keys())
    attendance_matrix = defaultdict(dict)
    
    for date in dates_list:
        daily_data = attendance_data.get(date, {})
        for name, details in daily_data.items():
            if isinstance(details, dict) and details.get("status") == "P":
                attendance_matrix[name][date] = {
                    "status": "P",
                    "time": details.get("time", "Unknown")
                }
                names_set.add(name)
    
    all_names = sorted(list(names_set))
    return attendance_matrix, all_names, dates_list

def calculate_attendance_stats():
    """Calculate comprehensive attendance statistics"""
    attendance_matrix, all_names, dates_list = get_attendance_data()
    
    stats = {
        'total_students': len(all_names),
        'total_days': len(dates_list),
        'daily_stats': {},
        'student_stats': {},
        'overall_attendance_rate': 0,
        'attendance_trends': []
    }
    
    # Daily statistics
    for date in dates_list:
        present_count = 0
        for name in all_names:
            if attendance_matrix[name].get(date, {}).get("status") == "P":
                present_count += 1
        
        stats['daily_stats'][date] = {
            'present': present_count,
            'absent': len(all_names) - present_count,
            'attendance_rate': (present_count / len(all_names) * 100) if all_names else 0
        }
    
    # Student statistics
    for name in all_names:
        present_days = sum(1 for date in dates_list 
                          if attendance_matrix[name].get(date, {}).get("status") == "P")
        absent_days = len(dates_list) - present_days
        attendance_rate = (present_days / len(dates_list) * 100) if dates_list else 0
        
        stats['student_stats'][name] = {
            'present_days': present_days,
            'absent_days': absent_days,
            'attendance_rate': round(attendance_rate, 2),
            'recent_attendance': []
        }
        
        # Get recent 7 days attendance
        recent_dates = dates_list[-7:] if len(dates_list) >= 7 else dates_list
        for date in recent_dates:
            status = attendance_matrix[name].get(date, {}).get("status", "A")
            stats['student_stats'][name]['recent_attendance'].append({
                'date': date,
                'status': status
            })
    
    # Overall attendance rate
    if stats['total_students'] > 0 and stats['total_days'] > 0:
        total_possible = stats['total_students'] * stats['total_days']
        total_present = sum(stats['student_stats'][name]['present_days'] for name in all_names)
        stats['overall_attendance_rate'] = round((total_present / total_possible * 100), 2)
    
    # Attendance trends (last 30 days)
    recent_dates = dates_list[-30:] if len(dates_list) >= 30 else dates_list
    for date in recent_dates:
        if date in stats['daily_stats']:
            stats['attendance_trends'].append({
                'date': date,
                'rate': stats['daily_stats'][date]['attendance_rate']
            })
    
    return stats

def generate_attendance_chart():
    """Generate attendance trend chart"""
    return generate_chart('attendance_trend')
    
    # if not stats['attendance_trends']:
    #     return None
    
    # plt.figure(figsize=(12, 6))
    # dates = [item['date'] for item in stats['attendance_trends']]
    # rates = [item['rate'] for item in stats['attendance_trends']]
    
    # plt.plot(dates, rates, marker='o', linewidth=2, markersize=4)
    # plt.title('Attendance Trend (Last 30 Days)', fontsize=16, fontweight='bold')
    # plt.xlabel('Date', fontsize=12)
    # plt.ylabel('Attendance Rate (%)', fontsize=12)
    # plt.xticks(rotation=45)
    # plt.grid(True, alpha=0.3)
    # plt.tight_layout()
    
    # # Convert to base64
    # buffer = BytesIO()
    # plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    # buffer.seek(0)
    # chart_data = base64.b64encode(buffer.getvalue()).decode()
    # plt.close()
    
    return chart_data

# Routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == USERNAME and request.form['password'] == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/dashboard')
@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        # Try to get status from Firebase
        status = db.reference('status').get()
        
        # If Firebase status is available, update local file
        if status is not None:
            with open(status_file, 'w') as f:
                f.write(status)
        else:
            # Fall back to local file
            with open(status_file, 'r') as f:
                status = f.read().strip()
    except:
        status = "off"
    
    stats = calculate_attendance_stats()
    chart_data = generate_attendance_chart()
    
    return render_template('dashboard.html', 
                         status=status, 
                         stats=stats,
                         chart_data=chart_data)


@app.route('/students')
def students():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    stats = calculate_attendance_stats()
    return render_template('students.html', stats=stats)

@app.route('/student/<name>')
def student_detail(name):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    stats = calculate_attendance_stats()
    if name not in stats['student_stats']:
        return redirect(url_for('students'))
    
    student_data = stats['student_stats'][name]
    return render_template('student_detail.html', 
                         name=name, 
                         student_data=student_data)

@app.route('/reports')
def reports():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    stats = calculate_attendance_stats()
    return render_template('reports.html', stats=stats)

@app.route('/settings')
def settings():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        with open(status_file, 'r') as f:
            status = f.read().strip()
    except:
        status = "off"
    
    return render_template('settings.html', status=status)

@app.route('/toggle/<state>')
def toggle(state):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    valid_states = ['on', 'off']
    if state not in valid_states:
        return redirect(url_for('dashboard'))
    
    # Update local status file
    with open(status_file, 'w') as f:
        f.write(state)
    
    # Update Firebase status
    try:
        status_ref = db.reference('status')
        status_ref.set(state)
        print(f"Status updated in Firebase: {state}")
    except Exception as e:
        print(f"Failed to update status in Firebase: {e}")
    
    return redirect(url_for('dashboard'))
    return redirect(url_for('dashboard'))

@app.route('/status')
def status():
    try:
        # Try to get status from Firebase first
        firebase_status = db.reference('status').get()
        
        # If Firebase status is available, update local file to keep in sync
        if firebase_status is not None:
            with open(status_file, 'w') as f:
                f.write(firebase_status)
            return firebase_status
        
        # Fall back to local file if Firebase fails
        with open(status_file, 'r') as f:
            local_status = f.read().strip()
            return local_status
    except:
        # If all else fails, return "off" as default
        return "off"

@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    data = request.get_json()
    name = data.get("name")
    timestamp = data.get("timestamp")

    if not name or not timestamp or name.strip().lower() == "unknown":
        return jsonify({"error": "Invalid or unknown name"}), 400

    date_col = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").date().isoformat()
    time_str = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")

    # Save to Firebase
    attendance_ref = db.reference(f'attendance/{date_col}/{name}')
    attendance_ref.set({
        "status": "P",
        "time": time_str,
        "timestamp": timestamp
    })

    print(f"Marked {name} as present on {date_col} at {time_str}")
    return jsonify({"message": "Attendance recorded successfully"}), 200

@app.route('/download_pdf')
def download_pdf():
    try:
        attendance_matrix, all_names, dates_list = get_attendance_data()
        
        # Create DataFrame
        df_rows = []
        for name in all_names:
            row = [name]
            for date in dates_list:
                status = attendance_matrix[name].get(date, {}).get("status", "A")
                row.append(status)
            df_rows.append(row)
        
        df = pd.DataFrame(df_rows, columns=["Name"] + dates_list)
        
        # Save CSV
        os.makedirs("attendance_data", exist_ok=True)
        df.to_csv("E:\\Smart-Attendence-System\\MAIN Programs\\PC\\attendance_data\\attendance.csv", index=False)
        
        # Generate PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        
        # Title
        pdf.cell(0, 10, "Smart Attendance System - Report", ln=True, align='C')
        pdf.ln(5)
        
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align='C')
        pdf.ln(10)
        
        # Statistics
        stats = calculate_attendance_stats()
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Summary Statistics:", ln=True)
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 6, f"Total Students: {stats['total_students']}", ln=True)
        pdf.cell(0, 6, f"Total Days: {stats['total_days']}", ln=True)
        pdf.cell(0, 6, f"Overall Attendance Rate: {stats['overall_attendance_rate']}%", ln=True)
        pdf.ln(10)
        
        # Attendance table
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 10, "Attendance Records:", ln=True)
        pdf.set_font("Arial", size=8)
        
        # Table headers
        col_count = len(df.columns)
        col_width = 190 / col_count if col_count > 0 else 190
        
        for col in df.columns:
            pdf.cell(col_width, 8, str(col)[:10], border=1, align='C')
        pdf.ln()
        
        # Table rows
        for _, row in df.iterrows():
            for item in row:
                pdf.cell(col_width, 8, str(item)[:10], border=1, align='C')
            pdf.ln()
        
        output_path = "E:\\Smart-Attendence-System\\MAIN Programs\\PC\\attendance_data\\attendance_report.pdf"
        pdf.output(output_path)
        
        return send_file(output_path, as_attachment=True, download_name=f"attendance_report_{datetime.now().strftime('%Y%m%d')}.pdf")
    
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return jsonify({"error": "Failed to generate PDF"}), 500

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    
    stats = calculate_attendance_stats()
    return jsonify(stats)

@app.route('/api/student/<name>')
def api_student(name):
    """API endpoint for individual student data"""
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    
    stats = calculate_attendance_stats()
    if name not in stats['student_stats']:
        return jsonify({"error": "Student not found"}), 404
    
    return jsonify(stats['student_stats'][name])

@app.route('/analytics', methods=['GET', 'POST'])
def analytics():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    stats = calculate_attendance_stats()
    chart_type = request.args.get('chart_type', 'attendance_trend')
    chart_data = generate_chart(chart_type)
    
    return render_template('analytics.html', 
                         stats=stats,
                         chart_data=chart_data,
                         selected_chart=chart_type)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/monthly_report', methods=['GET', 'POST'])
def monthly_report():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Default to current month if not specified
    today = datetime.now()
    selected_month = request.args.get('month', today.month)
    selected_year = request.args.get('year', today.year)
    
    try:
        selected_month = int(selected_month)
        selected_year = int(selected_year)
    except:
        selected_month = today.month
        selected_year = today.year
    
    # Get attendance data
    attendance_matrix, all_names, dates_list = get_attendance_data()
    
    # Filter data for the selected month
    filtered_dates = []
    monthly_data = {}
    
    for date in dates_list:
        try:
            date_obj = datetime.fromisoformat(date)
            if date_obj.month == selected_month and date_obj.year == selected_year:
                filtered_dates.append(date)
                
                # Add data for this date
                for name in all_names:
                    if name not in monthly_data:
                        monthly_data[name] = {'present': 0, 'absent': 0, 'dates': {}}
                    
                    status = attendance_matrix[name].get(date, {}).get("status", "A")
                    if status == "P":
                        monthly_data[name]['present'] += 1
                    else:
                        monthly_data[name]['absent'] += 1
                    
                    monthly_data[name]['dates'][date] = status
        except:
            continue
    
    # Calculate monthly statistics
    month_name = datetime(selected_year, selected_month, 1).strftime('%B')
    total_days = len(filtered_dates)
    
    # Calculate overall attendance rate
    if total_days > 0 and all_names:
        total_present = sum(data['present'] for data in monthly_data.values())
        total_possible = total_days * len(all_names)
        overall_rate = (total_present / total_possible) * 100 if total_possible > 0 else 0
    else:
        overall_rate = 0
    
    stats = {
        'month_name': month_name,
        'year': selected_year,
        'total_days': total_days,
        'student_count': len(all_names),
        'overall_rate': overall_rate,
        'student_data': monthly_data,
        'dates': sorted(filtered_dates)
    }
    
    # Handle export request
    if request.args.get('export') == 'pdf':
        return generate_monthly_report_pdf(stats)
    
    return render_template('monthly_report.html',
                         stats=stats,
                         selected_month=selected_month,
                         selected_year=selected_year)


@app.route('/student_report/<name>', methods=['GET'])
def student_report(name):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Get attendance data
    attendance_matrix, all_names, dates_list = get_attendance_data()
    
    if name not in all_names:
        return redirect(url_for('students'))
    
    # Get date range parameters
    today = datetime.now()
    end_date = request.args.get('end_date', today.strftime('%Y-%m-%d'))
    start_date = request.args.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    
    # Filter data based on date range
    filtered_dates = []
    attendance_data = []
    
    try:
        start_date_obj = datetime.fromisoformat(start_date)
        end_date_obj = datetime.fromisoformat(end_date)
        
        for date in dates_list:
            try:
                date_obj = datetime.fromisoformat(date)
                if start_date_obj <= date_obj <= end_date_obj:
                    filtered_dates.append(date)
                    
                    status = attendance_matrix[name].get(date, {}).get("status", "A")
                    attendance_data.append({
                        'date': date,
                        'status': status,
                        'day_of_week': date_obj.strftime('%A')
                    })
            except:
                continue
    except:
        # Fall back to all dates if there's an issue with the date range
        for date in dates_list:
            filtered_dates.append(date)
            status = attendance_matrix[name].get(date, {}).get("status", "A")
            try:
                date_obj = datetime.fromisoformat(date)
                day_of_week = date_obj.strftime('%A')
            except:
                day_of_week = "Unknown"
                
            attendance_data.append({
                'date': date,
                'status': status,
                'day_of_week': day_of_week
            })
    
    # Calculate statistics
    total_days = len(filtered_dates)
    present_days = sum(1 for item in attendance_data if item['status'] == "P")
    absent_days = total_days - present_days
    attendance_rate = (present_days / total_days * 100) if total_days > 0 else 0
    
    # Calculate attendance by day of week
    day_stats = {day: {'total': 0, 'present': 0} for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']}
    
    for item in attendance_data:
        day = item['day_of_week']
        if day in day_stats:
            day_stats[day]['total'] += 1
            if item['status'] == "P":
                day_stats[day]['present'] += 1
    
    for day, data in day_stats.items():
        if data['total'] > 0:
            data['rate'] = (data['present'] / data['total']) * 100
        else:
            data['rate'] = 0
    
    student_stats = {
        'name': name,
        'total_days': total_days,
        'present_days': present_days,
        'absent_days': absent_days,
        'attendance_rate': attendance_rate,
        'attendance_data': sorted(attendance_data, key=lambda x: x['date']),
        'day_stats': day_stats,
        'start_date': start_date,
        'end_date': end_date
    }
    
    # Handle export request
    if request.args.get('export') == 'pdf':
        return generate_student_report_pdf(student_stats)
    
    return render_template('student_report.html', 
                         stats=student_stats)

def generate_monthly_report_pdf(stats):
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Set up header
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Monthly Attendance Report: {stats['month_name']} {stats['year']}", ln=True, align="C")
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        # Summary statistics
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Summary Statistics:", ln=True)
        pdf.set_font("Arial", size=10)
        
        pdf.cell(60, 8, f"Total Students: {stats['student_count']}", ln=False)
        pdf.cell(60, 8, f"School Days: {stats['total_days']}", ln=False)
        pdf.cell(60, 8, f"Overall Attendance: {stats['overall_rate']:.2f}%", ln=True)
        pdf.ln(5)
        
        # Calendar view
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Daily Attendance Rates:", ln=True)
        pdf.set_font("Arial", size=8)
        
        # Sort dates
        sorted_dates = sorted(stats['dates'])
        
        # Create a calendar-like view
        date_count = len(sorted_dates)
        if date_count > 0:
            cols = min(7, date_count)  # Maximum 7 columns
            rows = (date_count + cols - 1) // cols
            
            col_width = 180 / cols
            
            # Date headers
            for i in range(min(cols, date_count)):
                if i < date_count:
                    date_str = sorted_dates[i]
                    try:
                        date_obj = datetime.fromisoformat(date_str)
                        display_date = date_obj.strftime('%d')
                    except:
                        display_date = date_str[-2:]
                    pdf.cell(col_width, 8, display_date, border=1, align="C")
            pdf.ln()
            
            # Attendance rates for each date
            for i in range(min(cols, date_count)):
                if i < date_count:
                    date_str = sorted_dates[i]
                    present_count = sum(1 for name, data in stats['student_data'].items() 
                                      if date_str in data['dates'] and data['dates'][date_str] == "P")
                    rate = (present_count / stats['student_count'] * 100) if stats['student_count'] > 0 else 0
                    pdf.cell(col_width, 8, f"{rate:.1f}%", border=1, align="C")
            pdf.ln(15)
        
        # Student attendance table
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Student Attendance Records:", ln=True)
        pdf.set_font("Arial", size=8)
        
        # Table headers
        pdf.cell(50, 8, "Name", border=1, align="C")
        pdf.cell(30, 8, "Present", border=1, align="C")
        pdf.cell(30, 8, "Absent", border=1, align="C")
        pdf.cell(30, 8, "Attendance Rate", border=1, align="C")
        pdf.cell(30, 8, "Trend", border=1, align="C")
        pdf.ln()
        
        # Table data - sort by attendance rate
        sorted_students = sorted(
            [(name, data) for name, data in stats['student_data'].items()],
            key=lambda x: x[1]['present'] / (x[1]['present'] + x[1]['absent']) if (x[1]['present'] + x[1]['absent']) > 0 else 0,
            reverse=True
        )
        
        for name, data in sorted_students:
            total_days = data['present'] + data['absent']
            rate = (data['present'] / total_days * 100) if total_days > 0 else 0
            
            pdf.cell(50, 8, name[:25], border=1)
            pdf.cell(30, 8, str(data['present']), border=1, align="C")
            pdf.cell(30, 8, str(data['absent']), border=1, align="C")
            pdf.cell(30, 8, f"{rate:.2f}%", border=1, align="C")
            
            # Simple trend indicator
            if rate >= 90:
                trend = "Excellent"
            elif rate >= 75:
                trend = "Good"
            elif rate >= 60:
                trend = "Average"
            else:
                trend = "Poor"
            
            pdf.cell(30, 8, trend, border=1, align="C")
            pdf.ln()
        
        # Output to memory
        output_path = f"E:\\Smart-Attendence-System\\MAIN Programs\\PC\\attendance_data\\monthly_report_{stats['month_name']}_{stats['year']}.pdf"
        pdf.output(output_path)
        
        return send_file(
            output_path, 
            as_attachment=True, 
            download_name=f"monthly_report_{stats['month_name']}_{stats['year']}.pdf"
        )
        
    except Exception as e:
        print(f"Error generating monthly report PDF: {e}")
        return jsonify({"error": "Failed to generate PDF"}), 500


def generate_student_report_pdf(stats):
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Set up header
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Student Attendance Report: {stats['name']}", ln=True, align="C")
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        # Date range
        pdf.set_font("Arial", "I", 10)
        pdf.cell(0, 8, f"Period: {stats['start_date']} to {stats['end_date']}", ln=True, align="C")
        
        # Summary statistics
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Summary Statistics:", ln=True)
        pdf.set_font("Arial", size=10)
        
        pdf.cell(60, 8, f"Total Days: {stats['total_days']}", ln=False)
        pdf.cell(60, 8, f"Present: {stats['present_days']} days", ln=False)
        pdf.cell(60, 8, f"Absent: {stats['absent_days']} days", ln=True)
        
        pdf.cell(0, 8, f"Overall Attendance Rate: {stats['attendance_rate']:.2f}%", ln=True)
        pdf.ln(5)
        
        # Day of week analysis
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Day of Week Analysis:", ln=True)
        pdf.set_font("Arial", size=10)
        
        # Table headers
        days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        col_width = 180 / 7  # 7 days a week
        
        for day in days_of_week:
            pdf.cell(col_width, 8, day[:3], border=1, align="C")
        pdf.ln()
        
        # Attendance rates by day
        for day in days_of_week:
            day_data = stats['day_stats'][day]
            rate = day_data['rate'] if day_data['total'] > 0 else 0
            pdf.cell(col_width, 8, f"{rate:.1f}%", border=1, align="C")
        pdf.ln(15)
        
        # Attendance records
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Attendance Records:", ln=True)
        pdf.set_font("Arial", size=8)
        
        # Table headers
        pdf.cell(40, 8, "Date", border=1, align="C")
        pdf.cell(30, 8, "Day", border=1, align="C")
        pdf.cell(30, 8, "Status", border=1, align="C")
        pdf.ln()
        
        # Table data
        for record in stats['attendance_data']:
            date_str = record['date']
            day = record['day_of_week']
            status = "Present" if record['status'] == "P" else "Absent"
            
            pdf.cell(40, 8, date_str, border=1)
            pdf.cell(30, 8, day[:3], border=1, align="C")
            pdf.cell(30, 8, status, border=1, align="C")
            pdf.ln()
        
        # Output to memory
        output_path = f"E:\\Smart-Attendence-System\\MAIN Programs\\PC\\attendance_data\\student_report_{stats['name']}.pdf"
        pdf.output(output_path)
        
        return send_file(
            output_path, 
            as_attachment=True, 
            download_name=f"student_report_{stats['name']}_{stats['start_date']}_to_{stats['end_date']}.pdf"
        )
        
    except Exception as e:
        print(f"Error generating student report PDF: {e}")
        return jsonify({"error": "Failed to generate PDF"}), 500
 
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)    
