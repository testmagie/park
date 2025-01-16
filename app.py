from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)  # Corrected to __name__
app.secret_key = "adminsecretkey"

# Database Initialization
def init_db():
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        # Create parking_slots table
        cursor.execute('''
    CREATE TABLE IF NOT EXISTS parking_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slot_number INTEGER UNIQUE NOT NULL,
        vehicle_type TEXT NOT NULL,
        is_occupied INTEGER NOT NULL,  -- Corrected line
        vehicle_number TEXT,
        vehicle_owner TEXT,
        in_time TEXT,
        out_time TEXT,
        payment_status TEXT,
        amount REAL DEFAULT 0
    )
''')

        # Add initial slots if not already present
        cursor.execute('SELECT COUNT(*) FROM parking_slots')
        if cursor.fetchone()[0] == 0:
            for i in range(1, 20):  # Create 20 parking slots
                vehicle_type = 'Car' if i <= 10 else 'Bike'  # 10 for Cars, 10 for Bikes
                cursor.execute('INSERT INTO parking_slots (slot_number, vehicle_type, is_occupied) VALUES (?, ?, ?)',
                               (i, vehicle_type, 0))
        conn.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/slots', methods=['GET', 'POST'])
def show_slots():
    if request.method == 'POST':
        vehicle_type = request.form['vehicle_type']
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT slot_number FROM parking_slots WHERE vehicle_type = ? AND is_occupied = 0''', (vehicle_type,))
            available_slots = cursor.fetchall()
        
        if not available_slots:
            return render_template('index.html', message="No available slots. All slots are booked.")
        
        return render_template('book.html', vehicle_type=vehicle_type, slots=available_slots)
    
    return render_template('index.html')

@app.route('/book', methods=['POST'])
def book_slot():
    vehicle_number = request.form['vehicle_number']
    vehicle_owner = request.form['vehicle_owner']
    slot_number = request.form['slot_number']
    in_time = request.form['in_time']
    out_time = request.form['out_time']
    payment_method = request.form['payment_method']
    
    in_time_dt = datetime.strptime(in_time, '%Y-%m-%dT%H:%M')
    out_time_dt = datetime.strptime(out_time, '%Y-%m-%dT%H:%M')

    if out_time_dt <= in_time_dt + timedelta(hours=1):
        return "Error: Minimum booking time is 1 hour."

    duration = (out_time_dt - in_time_dt).total_seconds() / 3600  # Duration in hours
    amount = duration * 50  # Assuming Rs. 50 per hour

    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute(''' 
            UPDATE parking_slots SET is_occupied = 1, vehicle_number = ?, vehicle_owner = ?, in_time = ?, out_time = ?, payment_status = ?, amount = ?
            WHERE slot_number = ?''',
            (vehicle_number, vehicle_owner, in_time, out_time, payment_method, amount, slot_number)
        )
        conn.commit()
    return render_template('success.html', slot_number=slot_number, amount=amount)

@app.route('/status')
def parking_status():
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT slot_number, is_occupied, vehicle_number, in_time, out_time FROM parking_slots''')
        slots = cursor.fetchall()
    return render_template('status.html', slots=slots)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        password = request.form['password']
        if password != 'admin_password':  # Change this to your password logic
            return "Access Denied", 403

    try:
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute(''' 
                SELECT slot_number, vehicle_type, vehicle_number, vehicle_owner, in_time, out_time, payment_status, amount, is_occupied
                FROM parking_slots
            ''')
            slots = cursor.fetchall()

        return render_template('admin.html', slots=slots)

    except sqlite3.Error as e:
        print(f"Database error occurred: {e}")
        return "Database error. Please check the logs for details."

    except Exception as e:
        print(f"Unexpected error occurred: {e}")
        return "An unexpected error occurred. Please check the logs for details."

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        vehicle_number = request.form['vehicle_number']
        vehicle_owner = request.form['vehicle_owner']
        
        # Check the database for the vehicle's current out_time
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT out_time, amount, is_occupied FROM parking_slots WHERE vehicle_number = ? AND vehicle_owner = ?''',
                           (vehicle_number, vehicle_owner))
            result = cursor.fetchone()
            
        if result:
            out_time_str = result[0]
            amount = result[1]
            is_occupied = result[2]

            # If the slot is occupied
            if is_occupied:
                out_time = datetime.strptime(out_time_str, '%Y-%m-%dT%H:%M')
                current_time = datetime.now()

                # If current time is more than 30 minutes beyond out_time
                if current_time > out_time + timedelta(minutes=30):
                    penalty = amount  # Penalty equals the bill amount if over time
                    return render_template('pay_penalty.html', penalty=penalty, vehicle_number=vehicle_number)
                else:
                    # No penalty, proceed to checkout
                    return redirect(url_for('confirm_checkout', vehicle_number=vehicle_number, vehicle_owner=vehicle_owner))
            else:
                return "This vehicle is not currently parked in the system."

        return "Vehicle not found."
    
    return render_template('checkout.html')

@app.route('/pay_penalty', methods=['POST'])
def pay_penalty():
    vehicle_number = request.form['vehicle_number']
    penalty_amount = float(request.form['penalty_amount'])
    
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        
        # Mark payment as completed
        cursor.execute('''UPDATE parking_slots SET payment_status = "Paid", amount = amount + ? WHERE vehicle_number = ?''',
                       (penalty_amount, vehicle_number))
        conn.commit()
    
    return redirect(url_for('confirm_checkout', vehicle_number=vehicle_number))  # Redirect to confirm checkout page
@app.route('/confirm_checkout')
def confirm_checkout():
    vehicle_number = request.args.get('vehicle_number')
    vehicle_owner = request.args.get('vehicle_owner')
    
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''UPDATE parking_slots SET is_occupied = 0, vehicle_number = NULL, vehicle_owner = NULL, in_time = NULL, out_time = NULL,amount=NULL, payment_status = NULL WHERE vehicle_number = ? AND vehicle_owner = ?''',
                       (vehicle_number, vehicle_owner))
        conn.commit()
    
    return render_template('success1.html', message="Checkout successful! Slot is now free.")

if __name__ == '__main__':  # Corrected to '__main__'
    init_db()  # Initialize database
    app.run(debug=True)