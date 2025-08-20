# Roundtable Bot (nwPlus)

A Slack reminder bot designed for **one team’s roundtable meetings**.  
It ensures fair rotation of meeting attendance by tracking who went last, sending reminders, and rotating responsibility.

- ⏰ Sends a reminder to the **current person** on the team before each meeting  
- ✅ After the meeting, they **click a Slack button** to confirm attendance  
- 🔁 If they attended, the bot **rotates to the next teammate**  
- 🚫 If they didn’t, the same person remains assigned until they attend  
- 🗂️ **State is stored in JSON**, with **members tracked by Slack IDs** for reliability  
- 🐍 Built using **Python** and the **Slack API**

---

## ✨ Features

- Single-team rotation logic  
- Automated reminders in a Slack channel  
- One-click confirmation buttons (Slack interactive messages)  
- Persistent state stored locally in JSON  
- Uses **Slack IDs** for members (so @mentions stay accurate even if usernames change)  

---

## 🧠 How It Works

1. The team members are stored in `team.json` as Slack IDs.  
2. Before each meeting, the bot posts a reminder tagging the **current person**.  
3. The person clicks **“I attended”** after the meeting.  
4. If clicked, the bot rotates to the next teammate.  
5. If not, the same person remains responsible for the next meeting.  

---

## 🔧 Tech Stack

- **Python 3.10+**  
- **Flask** → lightweight server for handling Slack event requests  
- **Slack SDK (slack, slackeventsapi, SlackEventAdapter)** → Slack API + event handling  
- **APScheduler** → scheduling reminders and rotations  
- **python-dotenv** → managing environment variables securely  
- **JSON** → storing rotation state and team members (via Slack IDs)  
- **Requests / hashlib / hmac** → Slack request verification + API calls  

## 🗂️ Data Model

**`team.json`**
```json
{
  "channel_id": "C0123456789",
  "members": ["U01AAAAAAA", "U01BBBBBBB", "U01CCCCCCC"],
  "current_index": 0
}


