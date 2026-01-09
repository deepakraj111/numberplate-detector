from flask import Flask, request, jsonify, render_template
import cv2
import numpy as np
import pytesseract
from PIL import Image
from flask_cors import CORS
import mysql.connector
import re

app = Flask(__name__)
CORS(app)

# Tesseract path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# MySQL database connection
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="ALOKSINGH12102003@#",   # ✅ Replace with your password
    database="number_plate_db"
)
cursor = conn.cursor()

# Detect number plate from image using OpenCV + Tesseract
def detect_plate(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    edged = cv2.Canny(gray, 30, 200)
    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.018 * peri, True)
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            return img[y:y+h, x:x+w]
    return None

@app.route('/')
def index():
    return render_template('app.html')

@app.route('/detect', methods=['POST'])
def detect():
    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400

    file = request.files['image']
    img = Image.open(file.stream).convert('RGB')
    img_np = np.array(img)
    img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    cropped = detect_plate(img_cv)

    if cropped is not None:
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        config = '--psm 7 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        text = pytesseract.image_to_string(thresh, config=config)
        plate_number = re.sub(r'[^A-Z0-9]', '', text.strip().upper())

        if plate_number:
            deduction = 30.00

            cursor.execute("SELECT balance FROM vehicles WHERE plate_number = %s", (plate_number,))
            result = cursor.fetchone()

            if result:
                balance = float(result[0])
                if balance >= deduction:
                    new_balance = balance - deduction
                    cursor.execute("UPDATE vehicles SET balance = %s WHERE plate_number = %s", (new_balance, plate_number))
                    cursor.execute("INSERT INTO transactions (plate_number, deducted_amount, remaining_balance) VALUES (%s, %s, %s)",
                                   (plate_number, deduction, new_balance))
                    conn.commit()

                    return jsonify({
                        'plate_number': plate_number,
                        'message': f'₹{deduction} deducted',
                        'balance': new_balance
                    }), 200
                else:
                    return jsonify({
                        'plate_number': plate_number,
                        'message': 'Insufficient balance',
                        'balance': balance
                    }), 402
            else:
                # New vehicle entry
                new_balance = 100.00 - deduction
                cursor.execute("INSERT INTO vehicles (plate_number, balance) VALUES (%s, %s)", (plate_number, new_balance))
                cursor.execute("INSERT INTO transactions (plate_number, deducted_amount, remaining_balance) VALUES (%s, %s, %s)",
                               (plate_number, deduction, new_balance))
                conn.commit()

                return jsonify({
                    'plate_number': plate_number,
                    'message': f'₹{deduction} deducted from new vehicle (₹100 default)',
                    'balance': new_balance
                }), 201

    return jsonify({'message': 'Plate not detected'}), 404

@app.route('/transactions', methods=['GET'])
def transactions():
    cursor.execute("SELECT * FROM transactions ORDER BY id DESC")
    rows = cursor.fetchall()
    data = []
    for row in rows:
        data.append({
            "id": row[0],
            "plate_number": row[1],
            "deducted_amount": float(row[2]),
            "remaining_balance": float(row[3]),
            "timestamp": str(row[4])
        })
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
