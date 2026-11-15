# 🤖 Telegram Option & Link Distributor Bot

A Python-based Telegram bot where an administrator can upload links and organize them into selectable button options. When users select an option, the bot immediately delivers the corresponding link.

---

## ✨ Features

- 🔘 **Interactive Buttons / Options:** Displays clean Inline Keyboard buttons to users on `/start` or `/links`.
- 📩 **Smart Request System:** Users request links via one-tap buttons without exposing links publicly in groups.
- 🔒 **Admin Approval Mode (Optional Toggle):**
  - Instant Mode: User requests link -> Bot immediately sends link in DM.
  - Approval Mode: User requests link -> Admin gets `[ ✅ Approve ]` / `[ ❌ Reject ]` notification -> User gets link upon approval!
- ⚠️ **Warn & Kick Moderation System:**
  - `/warn [reason]` - Warns a user in the group. On the **3rd warning**, the bot automatically kicks the user out of the group.
  - `/unwarn` - Removes 1 warning from a user.
  - `/warns` - Checks current warning count of a user.
- 🛠️ **Full Admin Control Panel (`/admin`):**
  - **Add Link Interactively:** Step-by-step wizard to add button name, link URL, and description.
  - **Quick Add (`/add`):** Fast command syntax: `/add Title | URL | Description`.
  - **Manage & Delete Links:** Review all options and remove links with one click.
  - **Toggle Approval Mode:** Turn admin approval ON or OFF with one tap.
  - **Direct Delivery (`/sendto`):** Send a link directly to a specific user's chat ID.
  - **Analytics:** Tracks total users, link clicks, and access timestamps.
- 💾 **SQLite Database:** Local, persistent storage (`bot.db`) with zero setup or external server dependencies.

---

## 📋 Prerequisites

1. **Python 3.10+** (Tested on Python 3.14)
2. **Telegram Bot Token**: Get one for free from [@BotFather](https://t.me/BotFather) on Telegram.
3. **Your Telegram User ID**: Send `/start` to [@userinfobot](https://t.me/userinfobot) on Telegram to get your numeric ID.

---

## 🚀 Quick Setup & Installation

### 1. Clone or Open the Project Folder
```bash
cd "web dev practice/oAuth2.0"
```

### 2. Create a Virtual Environment & Install Dependencies
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Configure `.env`
Copy the example environment file:
```bash
cp .env.example .env
```
Open `.env` and fill in your values:
```env
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
ADMIN_IDS=123456789
```
> Replace `BOT_TOKEN` with your token from `@BotFather`, and `ADMIN_IDS` with your Telegram user ID from `@userinfobot` (comma-separated if multiple admins).

### 4. Run the Bot
```bash
python bot.py
```

---

## 📖 How It Works

### For Users:
1. User sends `/start` to your bot.
2. The bot greets the user and displays an **Inline Keyboard** with all available options uploaded by the admin (e.g., `👉 Python Tutorial`, `👉 Movie Link`, `👉 Documentation`).
3. When the user taps an option:
   - The bot sends a message with the title, description, and direct clickable link.
   - A direct button `[ 🌐 Open Link Directly ]` is also attached for one-tap opening.
   - User can click `[ ⬅️ Back to Menu ]` to pick another option.

### For Admins:
1. Send `/admin` to open the Admin Dashboard.
2. Click **➕ Add New Link**:
   - The bot will prompt:
     - **Step 1:** Enter option name / button title.
     - **Step 2:** Send the URL (e.g. `https://...` or `t.me/...`).
     - **Step 3:** Send an optional description (or skip).
3. Click **📋 Manage / Delete Links** to view click stats and delete any obsolete options.
4. **Quick Command:**
   ```
   /add Course Material | https://example.com/course | Complete guide
   ```
5. **Send Directly to a Specific User:**
   ```
   /sendto <user_id> <url_or_option_id>
   ```

---

## 📁 Project Structure

```
.
├── bot.py           # Main Telegram bot logic and handlers
├── config.py        # Configuration and admin permissions
├── database.py      # SQLite database models and access queries
├── requirements.txt # Python dependencies
├── .env.example     # Template for bot credentials
└── README.md        # Documentation and usage guide
```
