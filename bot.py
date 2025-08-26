import os
import slack
from flask import Flask, request
from slackeventsapi import SlackEventAdapter
from dotenv import load_dotenv
import json

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import requests

#Slack request verification for interactions
import hashlib
import hmac

import time
from datetime import datetime, timedelta, timezone

# Load .env variables
load_dotenv()

# Create Flask app
app = Flask(__name__)

DATA_FILE = os.getenv("ROUND_TABLE_DATA_FILE", "rotation_data.json")

# Set up Slack event adapter for receiving actions via endpoint /slack/events
slack_event_adapter = SlackEventAdapter(
    os.environ['SIGNING_SECRET'], '/slack/events', app
)

# Create Slack client
client = slack.WebClient(token=os.environ['SLACK_TOKEN'])

# Get bot user ID
BOT_ID = client.api_call("auth.test")["user_id"]


# 🔹 TEST ROUTE: Sends a message to a Slack channel
@app.route("/test", methods=["GET"])
def test_message():
    client.chat_postMessage(
        channel="#test",  # Replace with your channel or use a channel ID
        text="Hello from your Slackbot! 🎉"
    )
    return "Message sent!", 200


# Read rotation data from JSON file
def load_rotation_data():
    # with open("rotation_data.json", "r") as file:
    #     return json.load(file)
    path = DATA_FILE
    if not os.path.exists(path):
        # fall back to example if no private file
        if os.path.exists("rotation_data.json.example"):
            with open("rotation_data.json.example", "r") as file:
                return json.load(file)
        return {"members": [], "current_index": 0}
    with open(path, "r") as file:
        return json.load(file)
    
# Save rotation data back to the file
def save_rotation_data(data):
    # with open("rotation_data.json", "w") as file:
    #     json.dump(data, file, indent=2)
    path = DATA_FILE
    with open(path, "w") as file:
        json.dump(data, file, indent=2)



# import pytz; TZ = pytz.timezone("America/Vancouver")

TZ = timezone.utc
scheduler = BackgroundScheduler(timezone=TZ)
scheduler.start()


REMINDER_HOUR = int(os.environ.get("REMINDER_HOUR", 16))  # 16:00 UTC (~9am PT)
REMINDER_MIN  = int(os.environ.get("REMINDER_MIN", 0))

def rotate_to_next_and_notify():
    """Advance to the next person in rotation and notify them."""
    data = load_rotation_data()
    if not data.get("members"):
        return None
    data["current_index"] = (data["current_index"] + 1) % len(data["members"])
    save_rotation_data(data)
    return notify_current_user()  # this will DM the new current user

def _anchor_datetimes(first_tuesday: datetime):
    """Return the first Monday (reminder) and first Wednesday (rotate) datetimes at the configured time."""
    tues = first_tuesday.astimezone(TZ).replace(second=0, microsecond=0)
    mon  = (tues - timedelta(days=1)).replace(hour=REMINDER_HOUR, minute=REMINDER_MIN)
    wed  = (tues + timedelta(days=1)).replace(hour=REMINDER_HOUR, minute=REMINDER_MIN)

    now = datetime.now(TZ)
    while mon <= now:
        # move both anchors forward in lockstep (2-week cadence)
        mon += timedelta(weeks=2)
        wed += timedelta(weeks=2)
    return mon, wed

def schedule_biweekly_roundtable():
    first_tuesday = datetime(2025, 8, 12, 9, 0, tzinfo=TZ)
    first_mon, first_wed = _anchor_datetimes(first_tuesday)

    def monday_reminder():
        notify_current_user()

    def wednesday_rotate_and_notify():
        rotate_to_next_and_notify()

    scheduler.add_job(
        monday_reminder,
        trigger="interval",
        weeks=2,
        next_run_time=first_mon,
        id="biweekly_monday_reminder",
        replace_existing=True,
    )

    scheduler.add_job(
        wednesday_rotate_and_notify,
        trigger="interval",
        weeks=2,
        next_run_time=first_wed,
        id="biweekly_wednesday_rotate",
        replace_existing=True,
    )

schedule_biweekly_roundtable()


def notify_current_user():
    data = load_rotation_data()
    index = data["current_index"]
    current_user = data["members"][index]

    dm = client.conversations_open(users=current_user)
    dm_channel = dm["channel"]["id"]

    client.chat_postMessage(
        channel=dm_channel,
        text=f"👋 Hey <@{current_user}>!\n Just a reminder that it's your turn this week to attend the roundtable meeting. 🗓️"
    )

    # TIME UNTIL FOLLOWUP IS SENT AFTER NOTIFY
    run_time = datetime.now() + timedelta(seconds=2)
    scheduler.add_job(func=call_followup, trigger="date", run_date=run_time)

    return current_user

# message sent before the meeting to the user 
@app.route("/notify", methods=["GET"])
def notify_route():
    user = notify_current_user()
    return f"Notification sent to <@{user}>.", 200


#message sent after the meeting:
@app.route("/followup", methods=["GET"])
def followup_user():
    data = load_rotation_data()
    index = data["current_index"]
    current_user = data["members"][index]

    dm = client.conversations_open(users=current_user)
    dm_channel = dm["channel"]["id"]

    client.chat_postMessage(
        channel=dm_channel,
        text="Meeting check-in time!",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Hi <@{current_user}>! \nDid you attend your roundtable meeting?"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Yes ✅"},
                        "style": "primary",
                        "value": current_user,
                        "action_id": "attended_yes"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "No ❌"},
                        "style": "danger",
                        "value": current_user,
                        "action_id": "attended_no"
                    }
                ]
            }
        ]
    )

    return f"Follow-up sent to <@{current_user}>.", 200


@app.route("/slack/interactions", methods=["POST"])
def handle_interactions():
    # Validate Slack signature
    slack_signature = request.headers.get('X-Slack-Signature')
    slack_request_timestamp = request.headers.get('X-Slack-Request-Timestamp')

    print("🔐 Slack Signature:", slack_signature)
    print("🕒 Slack Timestamp:", slack_request_timestamp)

    if abs(time.time() - int(slack_request_timestamp)) > 60 * 5:
        return "Ignored (timestamp too old)", 403  # prevent replay attacks

    sig_basestring = f"v0:{slack_request_timestamp}:{request.get_data(as_text=True)}"
    my_signature = 'v0=' + hmac.new(
        os.environ["SIGNING_SECRET"].encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(my_signature, slack_signature):
        return "Invalid signature", 403

    # ✅ Passed validation, continue
    payload = json.loads(request.form["payload"])
    action_id = payload["actions"][0]["action_id"]
    user_id = payload["user"]["id"]

    if action_id == "attended_yes":
        data = load_rotation_data()
        if data["members"][data["current_index"]] == user_id:
            data["current_index"] = (data["current_index"] + 1) % len(data["members"])
            save_rotation_data(data)
            client.chat_postMessage(
                channel=user_id,
                text="✅ Great, you're marked as attended! You've been rotated out."
            )

            # TIME UNTIL THE NEXT PERSON IN ROTATION IS NOTIFIED - if rotation occured 
            #time.sleep(10)
            #notify_current_user()

        else:
            client.chat_postMessage(
                channel=user_id,
                text="You’re not the one currently in the rotation. No changes made."
            )

    elif action_id == "attended_no":
        client.chat_postMessage(
            channel=user_id,
            text="❌ No problem! You’ll stay in the rotation for next time."
        )
        

    # TIME UNTIL THE NEXT PERSON IN ROTATION IS NOTIFIED 
    # time.sleep(10)
    # notify_current_user()

    run_at = datetime.now(TZ) + timedelta(seconds=10)
    scheduler.add_job(
        func=notify_current_user,
        trigger="date",
        run_date=run_at,
        id=f"notify_next_{int(run_at.timestamp())}",   # unique id
        replace_existing=False
    )
    return "", 200


#LOCAL HOST SETUP - USE WHEN SERVER DOWN
# def call_notify():
#     print("📤 Running notify...")
#     requests.get("http://localhost:5002/notify")

# def call_followup():
#     print("📤 Running follow-up...")
#     requests.get("http://localhost:5002/followup")

@app.route("/start-roundtable", methods=["POST"])
def start_roundtable():
    print("✅ Slash command received!")

    # Optionally trigger logic here (like notify)
    notify_current_user()

    return "✅ Roundtable started and person notified!", 200

@app.get("/healthz")
def healthz():
    return "ok", 200

# 🔸 Entry point
# if __name__ == "__main__":
#     app.run(debug=True, port=5002)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))  # fallback to 5002 locally
    app.run(host="0.0.0.0", port=port)