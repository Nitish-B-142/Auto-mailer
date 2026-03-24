import os
import csv
import time
import sqlite3
import smtplib
import logging
import urllib.request
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration & Environment Variables
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
INST_EMAIL = os.environ.get('INST_EMAIL')
INST_PASS = os.environ.get('INST_PASS')
PERS_EMAIL = os.environ.get('PERS_EMAIL')
PERS_PASS = os.environ.get('PERS_PASS')
SHEET_CSV_URL = os.environ.get('SHEET_CSV_URL')

DB_FILE = 'tracking.db'
INITIAL_TEMPLATE = 'initial_email.txt'
FOLLOWUP_TEMPLATE = 'followup_email.txt'
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds

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

def fetch_csv_with_retry(url):
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed to fetch CSV: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    return None

def load_template(file_path, default_text, **kwargs):
    """Loads a template file and formats it with provided kwargs."""
    content = default_text
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading template {file_path}: {e}")
    
    try:
        return content.format(**kwargs)
    except Exception as e:
        logger.error(f"Error formatting template {file_path}: {e}")
        return content

def send_email(sender_email, sender_pass, recipient_email, cc_email, subject, body_text):
    if not sender_email or not sender_pass:
        logger.error(f"Missing credentials for {sender_email or 'unknown'}. Cannot send email.")
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
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(sender_email, sender_pass)
            server.sendmail(sender_email, recipients, msg.as_string())
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(f"Authentication failed for {sender_email}. Check APP_PASS.")
    except smtplib.SMTPRecipientsRefused:
        logger.error(f"Recipient refused: {recipient_email}")
    except Exception as e:
        logger.error(f"Error sending email to {recipient_email}: {e}")
    return False

def main():
    content = None
    if not SHEET_CSV_URL:
        logger.warning("SHEET_CSV_URL environment variable not set. Attempting to use local 'profs.csv'.")
        if os.path.exists('profs.csv'):
            try:
                with open('profs.csv', 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Failed to read local 'profs.csv': {e}")
                return
        else:
            logger.error("No CSV source available. Set SHEET_CSV_URL or provide 'profs.csv'.")
            return
    else:
        content = fetch_csv_with_retry(SHEET_CSV_URL)
        if not content:
            logger.error("Failed to fetch CSV data after retries.")
            return

    conn = setup_db()
    try:
        cursor = conn.cursor()
        reader = csv.DictReader(StringIO(content))
        
        for row in reader:
            # Flexible key matching
            name_key = next((k for k in row.keys() if k and 'name' in k.lower()), None)
            email_key = next((k for k in row.keys() if k and 'email' in k.lower()), None)
            topic_key = next((k for k in row.keys() if k and 'topic' in k.lower()), None)
            status_key = next((k for k in row.keys() if k and 'status' in k.lower()), None)

            name = row.get(name_key, '').strip() if name_key else ''
            email = row.get(email_key, '').strip() if email_key else ''
            topic = row.get(topic_key, '').strip() if topic_key else ''
            manual_status = row.get(status_key, '').strip().upper() if status_key else ''

            if not email or "@" not in email:
                logger.debug(f"Skipping row with invalid email: {email}")
                continue

            cursor.execute("SELECT status, last_action_timestamp FROM tracking WHERE email = ?", (email,))
            record = cursor.fetchone()
            now = datetime.now()

            # Manual Status Override
            if 'REPLIED' in manual_status or 'STOP' in manual_status:
                if not record or record[0] != 'REPLIED':
                    cursor.execute(
                        "INSERT OR REPLACE INTO tracking (email, status, last_action_timestamp) VALUES (?, ?, ?)",
                        (email, 'REPLIED', now.isoformat())
                    )
                    conn.commit()
                    logger.info(f"Updated {email} to REPLIED (Manual Override).")
                continue

            if not record:
                # Initial Email
                subject = f"Inquiry regarding Internship Opportunities - {topic}"
                default_body = "Dear Prof. {name},\n\nI am a student very interested in your research on {topic}. I would like to inquire about potential internship opportunities in your lab.\n\nBest regards,\n[Your Name]"
                body = load_template(INITIAL_TEMPLATE, default_body, name=name or 'Researcher', topic=topic)
                
                logger.info(f"Sending Initial Mail to {email}...")
                if send_email(INST_EMAIL, INST_PASS, email, PERS_EMAIL, subject, body):
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
                    if status == 'SENT':
                        reminder_count = 1
                    elif status.startswith('REMINDER_'):
                        reminder_count = int(status.split('_')[1]) + 1
                    else:
                        continue

                    if reminder_count <= 3:
                        subject = f"Gentle Follow-up: Internship Opportunities - {topic}"
                        default_body = "Dear Prof. {name},\n\nI am writing to gently follow up on my previous email regarding research opportunities in {topic}. I remain very interested in your work.\n\nBest regards,\n[Your Name]"
                        body = load_template(FOLLOWUP_TEMPLATE, default_body, name=name or 'Researcher', topic=topic)
                        
                        logger.info(f"Sending Reminder #{reminder_count} to {email}...")
                        if send_email(PERS_EMAIL, PERS_PASS, email, None, subject, body):
                            cursor.execute(
                                "UPDATE tracking SET status = ?, last_action_timestamp = ? WHERE email = ?",
                                (f'REMINDER_{reminder_count}', now.isoformat(), email)
                            )
                            conn.commit()
                    else:
                        logger.debug(f"Max reminders reached for {email}.")
    finally:
        conn.close()

if __name__ == '__main__':
    main()