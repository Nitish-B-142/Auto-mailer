import os
import csv
import sqlite3
import smtplib
import urllib.request
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# Configuration & Environment Variables
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
INST_EMAIL = os.environ.get('INST_EMAIL')
INST_PASS = os.environ.get('INST_PASS')
PERS_EMAIL = os.environ.get('PERS_EMAIL')
PERS_PASS = os.environ.get('PERS_PASS')
SHEET_CSV_URL = os.environ.get('SHEET_CSV_URL')

DB_FILE = 'tracking.db'

def setup_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracking (
            email TEXT PRIMARY KEY,
            status TEXT,
            last_action_timestamp TEXT
        )
    ''')
    conn.commit()
    return conn

def send_email(sender_email, sender_pass, recipient_email, cc_email, subject, body_text):
    if not sender_email or not sender_pass:
        print(f"Missing credentials for {sender_email}. Cannot send email to {recipient_email}")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    if cc_email:
        msg['Cc'] = cc_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body_text, 'plain'))

    recipients = [recipient_email]
    if cc_email:
        recipients.append(cc_email)

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(sender_email, sender_pass)
        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email to {recipient_email}: {e}")
        return False

def main():
    if not SHEET_CSV_URL:
        print("SHEET_CSV_URL environment variable not set. Please set it to the published Google Sheet CSV URL.")
        # Fallback to local csv if url is not set (for testing)
        if not os.path.exists('profs.csv'):
             return
        with open('profs.csv', 'r', encoding='utf-8') as f:
             content = f.read()
    else:
        try:
            req = urllib.request.Request(SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req)
            content = response.read().decode('utf-8')
        except Exception as e:
            print(f"Failed to fetch CSV from Google Sheets: {e}")
            return

    conn = setup_db()
    cursor = conn.cursor()

    reader = csv.DictReader(StringIO(content))
    
    for row in reader:
        # Flexible key matching to support Google Forms default column names
        name_key = next((k for k in row.keys() if k and 'name' in k.lower()), None)
        email_key = next((k for k in row.keys() if k and 'email' in k.lower()), None)
        topic_key = next((k for k in row.keys() if k and 'topic' in k.lower()), None)
        status_key = next((k for k in row.keys() if k and 'status' in k.lower()), None)

        name = row.get(name_key, '').strip() if name_key else ''
        email = row.get(email_key, '').strip() if email_key else ''
        topic = row.get(topic_key, '').strip() if topic_key else ''
        manual_status = row.get(status_key, '').strip().upper() if status_key else ''

        if not email:
            continue

        cursor.execute("SELECT status, last_action_timestamp FROM tracking WHERE email = ?", (email,))
        record = cursor.fetchone()
        now = datetime.now()

        # If user marked as REPLIED in the Google Sheet, override the DB
        if 'REPLIED' in manual_status or 'STOP' in manual_status:
            if not record or record[0] != 'REPLIED':
                if not record:
                    cursor.execute(
                        "INSERT INTO tracking (email, status, last_action_timestamp) VALUES (?, ?, ?)",
                        (email, 'REPLIED', now.isoformat())
                    )
                else:
                    cursor.execute(
                        "UPDATE tracking SET status = ?, last_action_timestamp = ? WHERE email = ?",
                        ('REPLIED', now.isoformat(), email)
                    )
                conn.commit()
                print(f"Updated {email} to REPLIED from Google Sheet override.")
            continue # Skip further processing for this email

        if not record:
            # Not in DB - send Initial Mail
            subject = f"Inquiry regarding Internship Opportunities - {topic}"
            body = f"Dear Prof. {name},\n\nI am a student very interested in your research on {topic}. I would like to inquire about potential internship opportunities in your lab.\n\nBest regards,\n[Your Name]"
            
            print(f"Sending Initial Mail to {email}...")
            success = send_email(INST_EMAIL, INST_PASS, email, PERS_EMAIL, subject, body)
            if success:
                cursor.execute(
                    "INSERT INTO tracking (email, status, last_action_timestamp) VALUES (?, ?, ?)",
                    (email, 'SENT', now.isoformat())
                )
                conn.commit()
        else:
            status, last_action_str = record
            
            if status == 'REPLIED':
                continue

            last_action = datetime.fromisoformat(last_action_str)
            if now - last_action >= timedelta(hours=48):
                # Time to send a gentle reminder
                if status == 'SENT':
                    reminder_count = 1
                elif status.startswith('REMINDER_'):
                    reminder_count = int(status.split('_')[1]) + 1
                else:
                    continue

                if reminder_count <= 3:
                    subject = f"Gentle Follow-up: Internship Opportunities - {topic}"
                    body = f"Dear Prof. {name},\n\nI am writing to gently follow up on my previous email regarding research opportunities in {topic}. I remain very interested in your work.\n\nBest regards,\n[Your Name]"
                    
                    print(f"Sending Reminder #{reminder_count} to {email}...")
                    success = send_email(PERS_EMAIL, PERS_PASS, email, None, subject, body)
                    if success:
                        new_status = f'REMINDER_{reminder_count}'
                        cursor.execute(
                            "UPDATE tracking SET status = ?, last_action_timestamp = ? WHERE email = ?",
                            (new_status, now.isoformat(), email)
                        )
                        conn.commit()
                else:
                    print(f"Max reminders (3) already sent to {email}.")
    
    conn.close()

if __name__ == '__main__':
    main()