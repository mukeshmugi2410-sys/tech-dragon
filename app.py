from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from datetime import datetime, date
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads', 'documents')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max limit

# Database connection function
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",  # Update with your MySQL password
        database="hrms"
    )

# Inject 'now' and 'notification_count' into all templates
@app.context_processor
def inject_globals():
    context = {'now': datetime.now()}
    if 'user_id' in session:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = 0", (session['user_id'],))
        result = cursor.fetchone()
        context['notification_count'] = result['count'] if result else 0
        conn.close()
    return context

def log_audit(action, details=None):
    if 'user_id' in session:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, details, ip_address)
                VALUES (%s, %s, %s, %s)
            """, (session['user_id'], action, details, request.remote_addr))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Audit log error: {e}")



# Home page
@app.route('/')
def home():
    return render_template('home.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['role'] = user['role']
            
            # Get employee info if exists
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM employees WHERE user_id = %s", (user['id'],))
            employee = cursor.fetchone()
            conn.close()
            
            if employee:
                session['emp_id'] = employee['id']
                session['dept_id'] = employee['department_id']
                session['position'] = employee['position']
            
            log_audit('Login', f"User {user['email']} logged in successfully")
            flash('Login successful!', 'success')
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'hr':
                return redirect(url_for('hr_dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid email or password!', 'danger')
    
    return render_template('login.html')

# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
        
        # Insert user
        cursor.execute("""
            INSERT INTO users (name, email, password, role) 
            VALUES (%s, %s, %s, %s)
        """, (name, email, password, role))
        
        user_id = cursor.lastrowid
        
        # Assign default department based on role
        if role == 'hr':
            cursor.execute("SELECT id FROM departments WHERE name = 'Human Resources'")
        elif role == 'employee':
            cursor.execute("SELECT id FROM departments WHERE name = 'IT'")
        else:
            cursor.execute("SELECT id FROM departments LIMIT 1")
        
        dept_result = cursor.fetchone()
        dept_id = dept_result[0] if dept_result else 1
        
        # Insert employee record
        cursor.execute("""
            INSERT INTO employees (user_id, name, email, department_id, role) 
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, name, email, dept_id, role))
        
        conn.commit()
        conn.close()
        
        # We can't log audit here easily because user isn't logged in, but we could log system action if we wanted.
        # For now, let's skip or log as 'System' if we had a way.
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Logout
@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_audit('Logout', f"User {session.get('user_email')} logged out")
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

# Forgot Password
@app.route('/forgot-password')
def forgot_password():
    return render_template('forgot_password.html')

# Terms & Conditions
@app.route('/terms')
def terms():
    return render_template('terms.html')

# Privacy Policy
@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

# Change Password
@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('New passwords do not match!', 'danger')
            return redirect(url_for('change_password'))
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE id = %s", (session['user_id'],))
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password'], current_password):
            hashed_password = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, session['user_id']))
            conn.commit()
            log_audit('Change Password', f"User {session['user_email']} changed password")
            flash('Password updated successfully!', 'success')
            conn.close()
            return redirect(url_for('profile'))
        else:
            conn.close()
            flash('Incorrect current password!', 'danger')
            
    return render_template('change_password.html')

# ========== ADMIN ROUTES ==========

# Admin Dashboard
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get statistics
    cursor.execute("SELECT COUNT(*) as count FROM employees WHERE role = 'employee'")
    total_employees = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM employees WHERE role = 'hr'")
    total_hr = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM departments")
    total_departments = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE date = CURDATE()")
    today_attendance = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM leave_requests WHERE status = 'pending'")
    pending_leaves = cursor.fetchone()['count']
    
    conn.close()
    
    return render_template('admin_dash.html',
                         total_employees=total_employees,
                         total_hr=total_hr,
                         total_departments=total_departments,
                         today_attendance=today_attendance,
                         pending_leaves=pending_leaves)

# Admin - Employees Management
@app.route('/admin/employees')
def admin_employees():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.*, d.name as department_name, u.email as user_email
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN users u ON e.user_id = u.id
        WHERE e.role = 'employee'
    """)
    employees = cursor.fetchall()
    
    cursor.execute("SELECT id, name FROM departments")
    departments = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin_employees.html',
                         employees=employees,
                         departments=departments)

# Admin - Add Employee
@app.route('/admin/employees/add', methods=['POST'])
def add_employee():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    name = request.form['name']
    email = request.form['email']
    phone = request.form.get('phone', '')
    department_id = request.form.get('department_id')
    position = request.form.get('position', 'Staff')
    salary = request.form.get('salary', 0)
    joining_date = request.form.get('date_of_joining') or date.today()
    emergency_contact = request.form.get('emergency_contact', '')
    address = request.form.get('address', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create user account
    password = generate_password_hash('password123')
    cursor.execute("""
        INSERT INTO users (name, email, password, role)
        VALUES (%s, %s, %s, 'employee')
    """, (name, email, password))
    user_id = cursor.lastrowid
    
    # Create employee record
    cursor.execute("""
        INSERT INTO employees (user_id, name, email, phone, department_id, position, salary, joining_date, emergency_contact, address, role)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'employee')
    """, (user_id, name, email, phone, department_id, position, salary, joining_date, emergency_contact, address))
    
    conn.commit()
    conn.close()
    
    log_audit('Add User', f"Added employee {name} ({email})")
    
    flash('Employee added successfully!', 'success')
    return redirect(url_for('admin_employees'))

# Admin - Edit Employee
@app.route('/admin/employees/edit/<int:emp_id>', methods=['POST'])
def edit_employee(emp_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    name = request.form['name']
    phone = request.form['phone']
    department_id = request.form['department_id']
    position = request.form.get('position', '')
    salary = request.form['salary']
    address = request.form.get('address', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE employees 
        SET name = %s, phone = %s, department_id = %s, position = %s, salary = %s, address = %s
        WHERE id = %s
    """, (name, phone, department_id, position, salary, address, emp_id))
    
    conn.commit()
    conn.close()
    
    flash('Employee updated successfully!', 'success')
    return redirect(url_for('admin_employees'))

# Admin - Delete Employee
@app.route('/admin/employees/delete/<int:emp_id>')
def delete_employee(emp_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user_id before deleting
    cursor.execute("SELECT user_id FROM employees WHERE id = %s", (emp_id,))
    result = cursor.fetchone()
    
    if result:
        user_id = result[0]
        # Delete employee
        cursor.execute("DELETE FROM employees WHERE id = %s", (emp_id,))
        # Delete user
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    
    conn.commit()
    conn.close()
    
    log_audit('Delete User', f"Deleted employee ID {emp_id}")

    flash('Employee deleted successfully!', 'success')
    return redirect(url_for('admin_employees'))

# Admin - HR Managers
@app.route('/admin/hr-managers')
def admin_hr_managers():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.*, d.name as department_name, u.email as user_email
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN users u ON e.user_id = u.id
        WHERE e.role = 'hr'
    """)
    hr_managers = cursor.fetchall()
    
    cursor.execute("SELECT id, name FROM departments")
    departments = cursor.fetchall()
    
    conn.close()
    
    return render_template('hr_managers.html',
                         hr_managers=hr_managers,
                         departments=departments)

# Admin - Add HR Manager
@app.route('/admin/hr-managers/add', methods=['POST'])
def add_hr_manager():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    name = request.form['name']
    email = request.form['email']
    phone = request.form.get('phone', '')
    department_id = request.form.get('department_id')
    address = request.form.get('address', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create user account
    password = generate_password_hash('hrpassword123')
    cursor.execute("""
        INSERT INTO users (name, email, password, role)
        VALUES (%s, %s, %s, 'hr')
    """, (name, email, password))
    user_id = cursor.lastrowid
    
    # Create HR manager record
    cursor.execute("""
        INSERT INTO employees (user_id, name, email, phone, department_id, address, role)
        VALUES (%s, %s, %s, %s, %s, %s, 'hr')
    """, (user_id, name, email, phone, department_id, address))
    
    conn.commit()
    conn.close()
    
    flash('HR Manager added successfully!', 'success')
    return redirect(url_for('admin_hr_managers'))

# Admin - Delete HR Manager
@app.route('/admin/hr-managers/delete/<int:hr_id>')
def delete_hr_manager(hr_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user_id before deleting
    cursor.execute("SELECT user_id FROM employees WHERE id = %s", (hr_id,))
    result = cursor.fetchone()
    
    if result:
        user_id = result[0]
        # Delete HR manager record
        cursor.execute("DELETE FROM employees WHERE id = %s", (hr_id,))
        # Delete user record
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    
    conn.commit()
    conn.close()
    
    flash('HR Manager deleted successfully!', 'success')
    return redirect(url_for('admin_hr_managers'))

# Admin - Departments Management
@app.route('/admin/departments')
def admin_departments():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get departments with employee count
    cursor.execute("""
        SELECT d.*, 
               (SELECT COUNT(*) FROM employees e WHERE e.department_id = d.id) as employee_count
        FROM departments d
    """)
    departments = cursor.fetchall()
    
    # Get total employees for utilization calc
    cursor.execute("SELECT COUNT(*) as count FROM employees")
    total_employees = cursor.fetchone()['count']
    
    conn.close()
    
    return render_template('department_management.html',
                         departments=departments,
                         total_employees=total_employees or 1) # avoid div by zero

# Admin - Add Department
@app.route('/admin/departments/add', methods=['POST'])
def add_department():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    name = request.form['name']
    manager_id = request.form.get('manager_id')
    budget = request.form.get('budget')
    location = request.form.get('location')
    description = request.form.get('description')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO departments (name, manager_id, budget, location, description) 
        VALUES (%s, %s, %s, %s, %s)
    """, (name, manager_id if manager_id else None, budget, location, description))
    
    conn.commit()
    conn.close()
    
    log_audit('Add Department', f"Created department {name}")
    flash('Department added successfully!', 'success')
    return redirect(url_for('admin_departments'))

# Admin - Edit Department
@app.route('/admin/departments/edit/<int:dept_id>', methods=['POST'])
def edit_department(dept_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    name = request.form['name']
    manager_id = request.form.get('manager_id')
    budget = request.form.get('budget')
    location = request.form.get('location')
    description = request.form.get('description')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE departments 
        SET name = %s, manager_id = %s, budget = %s, location = %s, description = %s
        WHERE id = %s
    """, (name, manager_id if manager_id else None, budget, location, description, dept_id))
    
    conn.commit()
    conn.close()
    
    log_audit('Edit Department', f"Updated department {dept_id}")
    flash('Department updated successfully!', 'success')
    return redirect(url_for('admin_departments'))

# Admin - Delete Department
@app.route('/admin/departments/delete/<int:dept_id>')
def delete_department(dept_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if there are employees in this department
    cursor.execute("SELECT COUNT(*) FROM employees WHERE department_id = %s", (dept_id,))
    count = cursor.fetchone()[0]
    
    if count > 0:
        flash('Cannot delete department with employees! Move them first.', 'danger')
    else:
        cursor.execute("DELETE FROM departments WHERE id = %s", (dept_id,))
        log_audit('Delete Department', f"Deleted department {dept_id}")
        flash('Department deleted successfully!', 'success')
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_departments'))



# Set Salary
@app.route('/admin/salary')
def set_salary():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.*, d.name as department
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        WHERE e.role = 'employee'
    """)
    employees = cursor.fetchall()
    
    conn.close()
    
    return render_template('set_salary.html', employees=employees)

@app.route('/admin/payroll/set-salary', methods=['POST'])
def update_salary():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates_count = 0
    
    try:
        for key, value in request.form.items():
            if key.startswith('salary_'):
                emp_id = key.split('_')[1]
                new_salary = value
                
                cursor.execute("""
                    UPDATE employees 
                    SET salary = %s
                    WHERE id = %s
                """, (new_salary, emp_id))
                updates_count += 1
        
        conn.commit()
        if updates_count > 0:
            log_audit('Update Salary', f"Updated salaries for {updates_count} employees")
            flash(f'Successfully updated salaries for {updates_count} employees!', 'success')
        else:
            flash('No salary changes were made.', 'info')
            
    except Exception as e:
        conn.rollback()
        print(f"Salary update error: {e}")
        flash('An error occurred while updating salaries.', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('set_salary'))

# Admin - Attendance
@app.route('/admin/attendance')
def admin_attendance():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    filter_date = request.args.get('date', date.today().isoformat())
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.name, e.position, d.name as department, a.check_in, a.check_out, a.status
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN attendance a ON e.id = a.employee_id AND a.date = %s
        ORDER BY d.name, e.name
    """, (filter_date,))
    attendance_list = cursor.fetchall()
    
    # Statistics
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN a.status = 'present' THEN 1 END) as present,
            COUNT(CASE WHEN a.status = 'absent' THEN 1 END) as absent,
            COUNT(CASE WHEN a.status = 'half_day' THEN 1 END) as half_day,
            COUNT(CASE WHEN a.status = 'leave' THEN 1 END) as on_leave
        FROM employees e
        LEFT JOIN attendance a ON e.id = a.employee_id AND a.date = %s
    """, (filter_date,))
    stats = cursor.fetchone()
    
    conn.close()
    
    return render_template('hr_attendance.html',
                         attendance_list=attendance_list,
                         stats=stats,
                         filter_date=filter_date,
                         is_admin=True)

# Admin - Leave Requests
@app.route('/admin/leave-requests')
def admin_leave_requests():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT lr.*, e.name as employee_name, e.position, d.name as department,
               DATEDIFF(lr.end_date, lr.start_date) + 1 as total_days
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        LEFT JOIN departments d ON e.department_id = d.id
        WHERE lr.status = 'pending'
        ORDER BY lr.start_date DESC
    """)
    leave_requests = cursor.fetchall()
    
    # Calculate global stats for admin
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN lr.status = 'pending' THEN 1 END) as pending,
            COUNT(CASE WHEN lr.status = 'approved' THEN 1 END) as approved,
            COUNT(CASE WHEN lr.status = 'rejected' THEN 1 END) as rejected
        FROM leave_requests lr
    """)
    leave_stats = cursor.fetchone()
    
    conn.close()
    
    return render_template('hr_leave_requests.html', 
                         leave_requests=leave_requests, 
                         leave_stats=leave_stats,
                         is_admin=True)

# Admin - Payroll
@app.route('/admin/payroll')
def admin_payroll():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT p.*, e.name, e.position, d.name as department
        FROM payroll p
        JOIN employees e ON p.employee_id = e.id
        LEFT JOIN departments d ON e.department_id = d.id
        WHERE DATE_FORMAT(p.month_year, '%Y-%m') = %s
        ORDER BY d.name, e.name
    """, (month,))
    slips = cursor.fetchall()
    
    conn.close()
    
    return render_template('hr_payroll_slips.html', slips=slips, selected_month=month, is_admin=True)

# ========== HR ROUTES ==========

# HR Dashboard
@app.route('/hr/dashboard')
def hr_dashboard():
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    dept_id = session.get('dept_id', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Department employees count
    cursor.execute("""
        SELECT COUNT(*) as count FROM employees 
        WHERE department_id = %s AND role = 'employee'
    """, (dept_id,))
    dept_employees = cursor.fetchone()['count']
    
    # Today's attendance count
    cursor.execute("""
        SELECT COUNT(*) as count FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        WHERE a.date = CURDATE() AND e.department_id = %s
    """, (dept_id,))
    today_attendance = cursor.fetchone()['count']
    
    # Pending leaves
    cursor.execute("""
        SELECT COUNT(*) as count FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        WHERE lr.status = 'pending' AND e.department_id = %s
    """, (dept_id,))
    pending_leaves = cursor.fetchone()['count']
    
    # Department attendance
    cursor.execute("""
        SELECT e.name, a.check_in, a.check_out, a.status
        FROM employees e
        LEFT JOIN attendance a ON e.id = a.employee_id AND a.date = CURDATE()
        WHERE e.department_id = %s
        LIMIT 5
    """, (dept_id,))
    dept_attendance = cursor.fetchall()
    
    conn.close()
    
    return render_template('hr_dash.html',
                         dept_employees=dept_employees,
                         today_attendance=today_attendance,
                         pending_leaves=pending_leaves,
                         dept_attendance=dept_attendance)

# HR - Employees List
@app.route('/hr/employees')
def hr_employees():
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    dept_id = session.get('dept_id', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.*, d.name as department_name
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        WHERE e.department_id = %s AND e.role = 'employee'
    """, (dept_id,))
    employees = cursor.fetchall()
    
    conn.close()
    
    return render_template('employees.html', employees=employees)

# HR - Update Employee
@app.route('/hr/employees/update/<int:emp_id>', methods=['POST'])
def hr_update_employee(emp_id):
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    phone = request.form['phone']
    address = request.form['address']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE employees 
        SET phone = %s, address = %s
        WHERE id = %s
    """, (phone, address, emp_id))
    
    conn.commit()
    conn.close()
    
    flash('Employee details updated successfully!', 'success')
    return redirect(url_for('hr_employees'))

# HR - Attendance
@app.route('/hr/attendance')
def hr_attendance():
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    dept_id = session.get('dept_id', 0)
    filter_date = request.args.get('date', date.today().isoformat())
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.name, e.position, a.check_in, a.check_out, a.status
        FROM employees e
        LEFT JOIN attendance a ON e.id = a.employee_id AND a.date = %s
        WHERE e.department_id = %s
        ORDER BY e.name
    """, (filter_date, dept_id))
    attendance_list = cursor.fetchall()
    
    # Statistics
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN a.status = 'present' THEN 1 END) as present,
            COUNT(CASE WHEN a.status = 'absent' THEN 1 END) as absent,
            COUNT(CASE WHEN a.status = 'half_day' THEN 1 END) as half_day,
            COUNT(CASE WHEN a.status = 'leave' THEN 1 END) as on_leave
        FROM employees e
        LEFT JOIN attendance a ON e.id = a.employee_id AND a.date = %s
        WHERE e.department_id = %s
    """, (filter_date, dept_id))
    stats = cursor.fetchone()
    
    conn.close()
    
    return render_template('hr_attendance.html',
                         attendance_list=attendance_list,
                         stats=stats,
                         filter_date=filter_date)

# HR - Manual Attendance
@app.route('/hr/attendance/manual', methods=['GET', 'POST'])
def hr_manual_attendance():
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    dept_id = session.get('dept_id', 0)
    
    if request.method == 'POST':
        employee_id = request.form['employee_id']
        att_date = request.form['date']
        check_in = request.form.get('check_in')
        check_out = request.form.get('check_out')
        status = request.form['status']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if record exists
        cursor.execute("""
            SELECT id FROM attendance 
            WHERE employee_id = %s AND date = %s
        """, (employee_id, att_date))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE attendance 
                SET check_in = %s, check_out = %s, status = %s
                WHERE id = %s
            """, (check_in, check_out, status, existing[0]))
        else:
            cursor.execute("""
                INSERT INTO attendance (employee_id, date, check_in, check_out, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (employee_id, att_date, check_in, check_out, status))
        
        conn.commit()
        conn.close()
        
        flash('Attendance updated successfully!', 'success')
        return redirect(url_for('hr_manual_attendance'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, position 
        FROM employees 
        WHERE department_id = %s
    """, (dept_id,))
    employees = cursor.fetchall()
    
    conn.close()
    
    return render_template('hr_manual_attendance.html', employees=employees)

# HR - Leave Requests
@app.route('/hr/leave-requests')
def hr_leave_requests():
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    dept_id = session.get('dept_id', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT lr.*, e.name as employee_name, e.position, d.name as department,
               DATEDIFF(lr.end_date, lr.start_date) + 1 as total_days
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        LEFT JOIN departments d ON e.department_id = d.id
        WHERE e.department_id = %s AND lr.status = 'pending'
        ORDER BY lr.start_date DESC
    """, (dept_id,))
    leave_requests = cursor.fetchall()

    # Calculate stats for the department
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN lr.status = 'pending' THEN 1 END) as pending,
            COUNT(CASE WHEN lr.status = 'approved' THEN 1 END) as approved,
            COUNT(CASE WHEN lr.status = 'rejected' THEN 1 END) as rejected
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        WHERE e.department_id = %s
    """, (dept_id,))
    leave_stats = cursor.fetchone()
    
    conn.close()
    
    return render_template('hr_leave_requests.html', 
                         leave_requests=leave_requests,
                         leave_stats=leave_stats)

# HR - Leave Action
@app.route('/hr/leave/action/<int:leave_id>', methods=['POST'])
def hr_leave_action(leave_id):
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    action = request.form['action']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if action == 'approve':
        cursor.execute("""
            UPDATE leave_requests 
            SET status = 'approved', approved_by = %s, approved_date = NOW()
            WHERE id = %s
        """, (session['user_id'], leave_id))
        flash('Leave approved successfully!', 'success')
        log_audit('Leave Action', f"Approved leave request {leave_id}")
    elif action == 'reject':
        cursor.execute("""
            UPDATE leave_requests 
            SET status = 'rejected', approved_by = %s, approved_date = NOW()
            WHERE id = %s
        """, (session['user_id'], leave_id))
        flash('Leave rejected!', 'success')
        log_audit('Leave Action', f"Rejected leave request {leave_id}")
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('hr_leave_requests'))

# HR - Payroll Slips
@app.route('/hr/payroll')
def hr_payroll_slips():
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    
    dept_id = session.get('dept_id', 0)
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT p.*, e.name, e.position
        FROM payroll p
        JOIN employees e ON p.employee_id = e.id
        WHERE e.department_id = %s
        AND DATE_FORMAT(p.month_year, '%Y-%m') = %s
    """, (dept_id, month))
    slips = cursor.fetchall()
    
    conn.close()
    
    return render_template('hr_payroll_slips.html', slips=slips, selected_month=month)

# ========== EMPLOYEE ROUTES ==========

# Employee Dashboard
@app.route('/employee/dashboard')
def employee_dashboard():
    if 'user_id' not in session or session['role'] != 'employee':
        return redirect(url_for('login'))
    
    emp_id = session.get('emp_id', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Today's status
    cursor.execute("""
        SELECT status FROM attendance 
        WHERE employee_id = %s AND date = CURDATE()
    """, (emp_id,))
    today_status = cursor.fetchone()
    
    # Present days this month
    cursor.execute("""
        SELECT COUNT(*) as count FROM attendance 
        WHERE employee_id = %s 
        AND MONTH(date) = MONTH(CURDATE())
        AND status = 'present'
    """, (emp_id,))
    present_days = cursor.fetchone()['count']
    
    # Recent attendance
    cursor.execute("""
        SELECT date, check_in, check_out, status
        FROM attendance 
        WHERE employee_id = %s 
        ORDER BY date DESC 
        LIMIT 5
    """, (emp_id,))
    recent_attendance = cursor.fetchall()
    
    conn.close()
    
    stats = {
        'today_status': today_status['status'] if today_status else 'Not Marked',
        'present_days': present_days
    }
    
    return render_template('employee_dash.html',
                         stats=stats,
                         recent_attendance=recent_attendance)

# Mark Attendance
@app.route('/attendance/mark', methods=['GET', 'POST'])
def mark_attendance():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    emp_id = session.get('emp_id', 0)
    today = date.today()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Check today's record
    cursor.execute("""
        SELECT * FROM attendance 
        WHERE employee_id = %s AND date = %s
    """, (emp_id, today))
    today_record = cursor.fetchone()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'check_in':
            check_in_time = datetime.now().strftime('%H:%M:%S')
            
            if today_record:
                flash('Already checked in today!', 'warning')
            else:
                cursor.execute("""
                    INSERT INTO attendance (employee_id, date, check_in, status)
                    VALUES (%s, %s, %s, 'present')
                """, (emp_id, today, check_in_time))
                flash('Checked in successfully!', 'success')
        
        elif action == 'check_out':
            if today_record and not today_record['check_out']:
                check_out_time = datetime.now().strftime('%H:%M:%S')
                cursor.execute("""
                    UPDATE attendance 
                    SET check_out = %s
                    WHERE id = %s
                """, (check_out_time, today_record['id']))
                flash('Checked out successfully!', 'success')
            elif today_record and today_record['check_out']:
                flash('Already checked out today!', 'warning')
        
        conn.commit()
        return redirect(url_for('mark_attendance'))
    
    # Attendance history
    cursor.execute("""
        SELECT date, check_in, check_out, status, 
               TIMESTAMPDIFF(HOUR, check_in, check_out) as total_hours
        FROM attendance 
        WHERE employee_id = %s 
        ORDER BY date DESC 
        LIMIT 10
    """, (emp_id,))
    attendance_history = cursor.fetchall()
    
    # Calculate Monthly Summary
    current_month = date.today().month
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN status = 'Present' THEN 1 END) as present_days,
            COUNT(CASE WHEN status = 'Absent' THEN 1 END) as absent_days,
            SUM(TIMESTAMPDIFF(HOUR, check_in, check_out)) as total_hours
        FROM attendance 
        WHERE employee_id = %s AND MONTH(date) = %s
    """, (emp_id, current_month))
    summary_data = cursor.fetchone()
    
    monthly_summary = {
        'present_days': summary_data['present_days'] if summary_data else 0,
        'absent_days': summary_data['absent_days'] if summary_data else 0,
        'total_hours': summary_data['total_hours'] if summary_data and summary_data['total_hours'] else 0,
        'overtime_hours': 0 # simplified for now
    }
    
    conn.close()
    
    return render_template('mark_attendance.html',
                         today_record=today_record,
                         attendance_history=attendance_history,
                         today=today,
                         monthly_summary=monthly_summary)

# Apply Leave
@app.route('/leave/apply', methods=['GET', 'POST'])
def apply_leave():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    emp_id = session.get('emp_id', 0)
    
    if request.method == 'POST':
        leave_type = request.form.get('leave_type')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        reason = request.form.get('reason')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, reason, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        """, (emp_id, leave_type, start_date, end_date, reason))
        
        conn.commit()
        conn.close()
        
        flash('Leave application submitted successfully!', 'success')
        return redirect(url_for('my_leaves'))
    
    return render_template('apply_leave.html')

# My Leaves
@app.route('/leave/my-leaves')
def my_leaves():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    emp_id = session.get('emp_id', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT * FROM leave_requests 
        WHERE employee_id = %s 
        ORDER BY start_date DESC
    """, (emp_id,))
    leaves = cursor.fetchall()
    
    conn.close()
    
    return render_template('my_leaves.html', leaves=leaves)

# My Payroll Slips
@app.route('/payroll/my-slips')
def my_payroll_slips():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    emp_id = session.get('emp_id', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT p.*, e.name
        FROM payroll p
        JOIN employees e ON p.employee_id = e.id
        WHERE p.employee_id = %s
        ORDER BY p.month_year DESC
    """, (emp_id,))
    slips = cursor.fetchall()
    
    conn.close()
    
    return render_template('my_payroll_slips.html', slips=slips)

# Profile
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    emp_id = session.get('emp_id', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT e.*, d.name as department_name
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        WHERE e.id = %s
    """, (emp_id,))
    profile = cursor.fetchone()
    
    conn.close()
    
    return render_template('profile.html', profile=profile)

# Update Profile
@app.route('/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    emp_id = session.get('emp_id', 0)
    phone = request.form['phone']
    address = request.form['address']
    emergency_contact = request.form.get('emergency_contact', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE employees 
        SET phone = %s, address = %s, emergency_contact = %s
        WHERE id = %s
    """, (phone, address, emergency_contact, emp_id))
    
    conn.commit()
    conn.close()
    
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('profile'))

# ========== RUN APP ==========


# ========== DOCUMENT MANAGEMENT ==========

@app.route('/documents')
@app.route('/employee/documents')
@app.route('/hr/documents')
def documents():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    role = session['role']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if role == 'admin' and request.path == '/documents': # Admin viewing their own or all? Let's say own for generic route
         # If admin wants to see all, they go to /admin/documents
         pass
         
    # Get user's documents
    cursor.execute("SELECT * FROM documents WHERE user_id = %s ORDER BY uploaded_at DESC", (user_id,))
    my_docs = cursor.fetchall()
    
    # If admin, get list of users for upload dropdown
    all_users = []
    if role == 'admin':
        cursor.execute("SELECT id, name, role FROM users ORDER BY name")
        all_users = cursor.fetchall()
        
    conn.close()
    
    return render_template('documents.html', documents=my_docs, is_admin=(role=='admin'), all_users=all_users)

@app.route('/admin/documents')
def admin_documents():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT d.*, u.name as user_name, u.role as user_role 
        FROM documents d 
        JOIN users u ON d.user_id = u.id 
        ORDER BY d.uploaded_at DESC
    """)
    all_docs = cursor.fetchall()
    
    cursor.execute("SELECT id, name, role FROM users ORDER BY name")
    all_users = cursor.fetchall()
    
    conn.close()
    
    return render_template('documents.html', documents=all_docs, is_admin=True, all_users=all_users)

@app.route('/documents/upload', methods=['POST'])
def upload_document():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.referrer)
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.referrer)
        
    if file:
        title = request.form['title']
        doc_type = request.form['type']
        
        # If admin is uploading for someone else
        user_id = session['user_id']
        if session['role'] == 'admin' and request.form.get('user_id'):
            user_id = request.form['user_id']
            
        filename = secure_filename(file.filename)
        # Add timestamp to filename to avoid duplicates
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S_')
        filename = timestamp + filename
        
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (user_id, title, type, file_path) 
            VALUES (%s, %s, %s, %s)
        """, (user_id, title, doc_type, filename))
        conn.commit()
        conn.close()
        
        log_audit('Upload Document', f"Uploaded document {filename} for user {user_id}")
        
        flash('Document uploaded successfully!', 'success')
        
    return redirect(request.referrer)

@app.route('/documents/delete/<int:doc_id>')
def delete_document(doc_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM documents WHERE id = %s", (doc_id,))
    doc = cursor.fetchone()
    
    if doc:
        # Check permission: Admin can delete any, User can delete own
        if session['role'] == 'admin' or doc['user_id'] == session['user_id']:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], doc['file_path']))
            except:
                pass # File might be missing
            
            cursor.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            conn.commit()
            log_audit('Delete Document', f"Deleted document {doc_id} ({doc['file_path']})")
            flash('Document deleted successfully!', 'success')
        else:
            flash('Permission denied!', 'danger')
            
    conn.close()
    return redirect(request.referrer)

# ========== PERFORMANCE MANAGEMENT ==========

@app.route('/admin/performance')
@app.route('/hr/performance')
def performance_reviews():
    if 'user_id' not in session or session['role'] not in ['admin', 'hr']:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT pr.*, e.name as employee_name, e.department_id, d.name as department_name, u.name as reviewer_name
        FROM performance_reviews pr
        JOIN employees e ON pr.employee_id = e.id
        LEFT JOIN departments d ON e.department_id = d.id
        JOIN users u ON pr.reviewer_id = u.id
        ORDER BY pr.review_date DESC
    """)
    reviews = cursor.fetchall()
    
    cursor.execute("SELECT id, name FROM employees WHERE role = 'employee' ORDER BY name")
    employees = cursor.fetchall()
    
    conn.close()
    
    return render_template('performance.html', reviews=reviews, employees=employees, is_admin=True)

@app.route('/employee/performance')
def my_performance():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    emp_id = session.get('emp_id')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT pr.*, u.name as reviewer_name
        FROM performance_reviews pr
        JOIN users u ON pr.reviewer_id = u.id
        WHERE pr.employee_id = %s
        ORDER BY pr.review_date DESC
    """, (emp_id,))
    reviews = cursor.fetchall()
    
    conn.close()
    
    return render_template('performance.html', reviews=reviews, is_admin=False)

@app.route('/performance/add', methods=['POST'])
def add_performance_review():
    if 'user_id' not in session or session['role'] not in ['admin', 'hr']:
        return redirect(url_for('login'))
        
    employee_id = request.form['employee_id']
    review_date = request.form['review_date']
    rating = request.form['rating']
    comments = request.form['comments']
    promotion = 1 if 'promotion_suggested' in request.form else 0
    reviewer_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO performance_reviews (employee_id, reviewer_id, review_date, rating, comments, promotion_suggested)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (employee_id, reviewer_id, review_date, rating, comments, promotion))
    
    conn.commit()
    conn.close()
    
    log_audit('Add Performance Review', f"Added review for employee {employee_id}")
    
    flash('Performance review added!', 'success')
    return redirect(request.referrer)

# ========== NOTIFICATIONS ==========

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    notifs = cursor.fetchall()
    
    # Mark all as read
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()
    
    return render_template('notifications.html', notifications=notifs)

# ========== AUDIT LOGS ==========

@app.route('/admin/audit-logs')
def audit_logs():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT a.*, u.name as user_name, u.role as user_role
        FROM audit_logs a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.timestamp DESC
        LIMIT 100
    """)
    logs = cursor.fetchall()
    
    conn.close()
    
    return render_template('audit_logs.html', logs=logs)

# ========== REPORTS ==========

@app.route('/admin/reports')
def admin_reports():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('reports.html')

@app.route('/hr/reports')
def hr_reports():
    if 'user_id' not in session or session['role'] != 'hr':
        return redirect(url_for('login'))
    return render_template('reports.html')

@app.route('/download/report/<type>')
def download_report(type):
    if 'user_id' not in session or session['role'] not in ['admin', 'hr']:
        return redirect(url_for('login'))
    
    import csv
    import io
    from flask import make_response

    output = io.StringIO()
    writer = csv.writer(output)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    filename = f"{type}_report_{date.today()}.csv"
    
    if type == 'employees':
        cursor.execute("SELECT e.name, e.email, e.position, d.name as department, e.salary, e.joining_date FROM employees e LEFT JOIN departments d ON e.department_id = d.id")
        data = cursor.fetchall()
        writer.writerow(['Name', 'Email', 'Position', 'Department', 'Salary', 'Joining Date'])
        for row in data:
            writer.writerow([row['name'], row['email'], row['position'], row['department'], row['salary'], row['joining_date']])
            
    elif type == 'attendance':
        cursor.execute("SELECT e.name, a.date, a.check_in, a.check_out, a.status FROM attendance a JOIN employees e ON a.employee_id = e.id ORDER BY a.date DESC LIMIT 1000")
        data = cursor.fetchall()
        writer.writerow(['Name', 'Date', 'Check In', 'Check Out', 'Status'])
        for row in data:
            writer.writerow([row['name'], row['date'], row['check_in'], row['check_out'], row['status']])
            
    elif type == 'payroll':
        cursor.execute("SELECT e.name, p.month_year, p.basic_salary, p.net_salary, p.status FROM payroll p JOIN employees e ON p.employee_id = e.id ORDER BY p.month_year DESC LIMIT 1000")
        data = cursor.fetchall()
        writer.writerow(['Name', 'Month', 'Basic Salary', 'Net Salary', 'Status'])
        for row in data:
            writer.writerow([row['name'], row['month_year'], row['basic_salary'], row['net_salary'], row['status']])
            
    conn.close()
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-type"] = "text/csv"
    return response

# ========== RUN APP ==========

if __name__ == '__main__':
    app.run(debug=True, port=5000)