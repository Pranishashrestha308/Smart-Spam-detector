import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from io import BytesIO
from flask import Flask, render_template, request, redirect, Response
import joblib
import sqlite3
import csv
import io
from database import create_database

from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "development-key-only"
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, id, username, email, password_hash):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, username, email, password_hash FROM users WHERE id = ?",
        (user_id,)
    )

    user_data = cursor.fetchone()
    conn.close()

    if user_data:
        return User(*user_data)

    return None

# Load the trained machine learning model
model = joblib.load("model/spam_model.pkl")
vectorizer = joblib.load("model/vectorizer.pkl")

# Create the database
create_database()


def save_prediction(message, prediction, probability, user_id):
    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO predictions
        (message, prediction, probability, user_id)
        VALUES (?, ?, ?, ?)
    """, (message, prediction, probability, user_id))

    conn.commit()
    conn.close()


@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email or not password:
            message = "Please fill in all fields."

        elif len(password) < 8:
            message = "Password must be at least 8 characters."

        else:
            try:
                conn = sqlite3.connect("spam_history.db")
                cursor = conn.cursor()

                password_hash = generate_password_hash(password)

                cursor.execute("""
                    INSERT INTO users (username, email, password_hash)
                    VALUES (?, ?, ?)
                """, (username, email, password_hash))

                conn.commit()
                conn.close()

                return redirect("/login")

            except sqlite3.IntegrityError:
                conn.close()
                message = "Username or email already exists."

    return render_template("register.html", message=message)



@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        conn = sqlite3.connect("spam_history.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, username, email, password_hash
            FROM users
            WHERE email = ?
        """, (email,))

        user_data = cursor.fetchone()
        conn.close()

        if user_data and check_password_hash(user_data[3], password):
            user = User(*user_data)
            login_user(user)
            return redirect("/")

        message = "Invalid email or password."

    return render_template("login.html", message=message)
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    message = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip()

        conn = sqlite3.connect("spam_history.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            return redirect("/reset_password/" + str(user[0]))

        message = "Email address not found."

    return render_template(
        "forgot_password.html",
        message=message
    )
@app.route("/reset_password/<int:user_id>", methods=["GET", "POST"])
def reset_password(user_id):
    message = ""

    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE id = ?",
        (user_id,)
    )
    user = cursor.fetchone()

    if not user:
        conn.close()
        return "User not found."

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(new_password) < 8:
            message = "Password must be at least 8 characters."

        elif new_password != confirm_password:
            message = "Passwords do not match."

        else:
            password_hash = generate_password_hash(new_password)

            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id)
            )

            conn.commit()
            conn.close()

            return redirect("/login")

    conn.close()

    return render_template(
        "reset_password.html",
        message=message
    )
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    message = ""

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        conn = sqlite3.connect("spam_history.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (current_user.id,)
        )
        password_hash = cursor.fetchone()[0]

        if not check_password_hash(password_hash, current_password):
            message = "Current password is incorrect."

        elif len(new_password) < 8:
            message = "New password must be at least 8 characters."

        elif new_password != confirm_password:
            message = "New passwords do not match."

        else:
            new_hash = generate_password_hash(new_password)

            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, current_user.id)
            )
            conn.commit()
            message = "Password changed successfully!"

        conn.close()

    return render_template(
        "profile.html",
        username=current_user.username,
        email=current_user.email,
        message=message
    )

@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    prediction = None
    probability = None
    message = ""

    if request.method == "POST":
        message = request.form["message"].strip()

        if message:
            transformed_message = vectorizer.transform([message])

            result = model.predict(transformed_message)[0]

            spam_probability = model.predict_proba(
                transformed_message
            )[0][1]

            prediction = "SPAM" if result == 1 else "NORMAL"

            probability = round(spam_probability * 100, 2)

            # Save the prediction in SQLite
            save_prediction(message, prediction, probability, current_user.id)

    return render_template(
        "index.html",
        prediction=prediction,
        probability=probability,
        message=message
    )


@app.route("/history")
@login_required
def history():
    search = request.args.get("search", "").strip()
    filter_type = request.args.get("filter", "ALL")

    conn = sqlite3.connect("spam_history.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM predictions WHERE user_id = ? AND message LIKE ?"
    params = [current_user.id, f"%{search}%"]

    if filter_type in ["SPAM", "NORMAL"]:
        query += " AND prediction = ?"
        params.append(filter_type)

    query += " ORDER BY id ASC"

    cursor.execute(query, params)
    records = cursor.fetchall()
    conn.close()

    return render_template(
        "history.html",
        records=records,
        search=search,
        filter_type=filter_type
    )

@app.route("/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_record(record_id):
    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM predictions WHERE id = ? AND user_id = ?",
        (record_id, current_user.id)
    )

    conn.commit()
    conn.close()

    return redirect("/history")


@app.route("/export")
@login_required
def export():
    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, message, prediction, probability, created_at
        FROM predictions
        WHERE user_id = ?
        ORDER BY id ASC
    """, (current_user.id,))

    records = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Record ID",
        "Message",
        "Prediction",
        "Probability",
        "Date and Time"
    ])

    writer.writerows(records)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=spam_history.csv"
        }
    )


@app.route("/export_excel")
@login_required
def export_excel():
    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, message, prediction, probability, created_at
        FROM predictions
        WHERE user_id = ?
        ORDER BY id ASC
    """, (current_user.id,))

    records = cursor.fetchall()
    conn.close()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Spam History"

    headers = [
        "Record ID",
        "Message",
        "Prediction",
        "Probability",
        "Date and Time"
    ]

    sheet.append(headers)

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="1E293B"
    )
    header_font = Font(color="FFFFFF", bold=True)

    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )

    for record in records:
        sheet.append(list(record))

    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=True
            )

        if row[2].value == "SPAM":
            row[2].font = Font(color="DC2626", bold=True)

        elif row[2].value == "NORMAL":
            row[2].font = Font(color="15803D", bold=True)

    widths = [12, 55, 16, 16, 24]

    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[
            get_column_letter(index)
        ].width = width

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 25

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
            "attachment; filename=spam_history.xlsx"
        }
    )



@app.route("/export_pdf")
@login_required
def export_pdf():
    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, message, prediction, probability, created_at
        FROM predictions
        WHERE user_id = ?
        ORDER BY id ASC
    """, (current_user.id,))

    records = cursor.fetchall()
    conn.close()

    output = io.BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=25,
        leftMargin=25,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()

    title = Paragraph(
        "<b>Smart Spam Detector - Prediction History</b>",
        styles["Title"]
    )

    elements = [title, Spacer(1, 20)]

    data = [[
        "Record ID",
        "Message",
        "Prediction",
        "Probability",
        "Date and Time"
    ]]

    for index, record in enumerate(records, start=1):
        data.append([
            str(index),
            Paragraph(str(record[1]), styles["BodyText"]),
            str(record[2]),
            str(record[3]) + "%",
            str(record[4])
        ])

    table = Table(
        data,
        colWidths=[55, 300, 80, 75, 120],
        repeatRows=1
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F1F5F9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    elements.append(table)

    document.build(elements)

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
            "attachment; filename=spam_history.pdf"
        }
    )



@app.route("/dashboard")
@login_required
def dashboard():
    conn = sqlite3.connect("spam_history.db")
    cursor = conn.cursor()

    # Get recent activity for logged-in user
    cursor.execute("""
        SELECT id, message, prediction, probability, created_at
        FROM predictions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (current_user.id,))
    recent_records = cursor.fetchall()

    # Total messages
    cursor.execute("""
        SELECT COUNT(*) FROM predictions
        WHERE user_id = ?
    """, (current_user.id,))
    total = cursor.fetchone()[0]

    # Spam messages
    cursor.execute("""
        SELECT COUNT(*) FROM predictions
        WHERE prediction = 'SPAM' AND user_id = ?
    """, (current_user.id,))
    spam_count = cursor.fetchone()[0]

    # Normal messages
    cursor.execute("""
        SELECT COUNT(*) FROM predictions
        WHERE prediction = 'NORMAL' AND user_id = ?
    """, (current_user.id,))
    normal_count = cursor.fetchone()[0]

    conn.close()

    # Spam percentage
    spam_percentage = (
        round((spam_count / total) * 100, 2)
        if total > 0 else 0
    )

    # Normal percentage
    normal_percentage = (
        round((normal_count / total) * 100, 2)
        if total > 0 else 0
    )

    return render_template(
        "dashboard.html",
        total=total,
        spam_count=spam_count,
        normal_count=normal_count,
        spam_percentage=spam_percentage,
        normal_percentage=normal_percentage,
        recent_records=recent_records
    )


if __name__ == "__main__":
    print(app.url_map)
    app.run(debug=True)
