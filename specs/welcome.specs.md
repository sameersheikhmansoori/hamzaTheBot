# Welcome System Specification (welcome.specs.md)

## Objective
Automatically greet every user who arrives or joins the community with the exact custom greeting:
`👋 [User Name], lehari me apka sawagat h! kya chahiye aapko?`
and display available link options.

---

## 1. Triggers & Event Handlers

### A. Group / Supergroup Joins
1. **ChatMemberUpdated Event (`ChatMemberHandler.CHAT_MEMBER`):**
   - Catches new joins in Supergroups, large groups, and users joining via invite links.
   - Requires `allowed_updates=Update.ALL_TYPES` in `run_polling`.
   - Condition: `old_status not in [MEMBER, ADMIN, OWNER]` and `new_status in [MEMBER, RESTRICTED]`.
2. **Service Message Event (`filters.StatusUpdate.NEW_CHAT_MEMBERS`):**
   - Catches regular group joins where Telegram sends a service message.
3. **De-duplication Cache:**
   - Prevents sending duplicate greetings if both events fire for the same user within 10 seconds.

### B. Private Chat (Direct Messages)
1. **`/start`, `/links`, `/menu`, `/options` commands:**
   - Displays the greeting with personal options menu.
2. **Any general text message (e.g. "hi", "hello", "link"):**
   - Responds with the greeting and options menu.

---

## 2. Message Template

```html
👋 <b>{user_name}</b>, lehari me apka sawagat h! kya chahiye aapko?

Neeche diye gaye options me se select karein:
```

Attached with an Inline Keyboard containing all options uploaded by the admin.
In groups, buttons use direct deep-linking to private chat (`https://t.me/<bot_username>?start=req_<id>`) so links are delivered privately without group spam.

---

## 3. Telegram Permissions Requirement
For Telegram groups:
- Bot must be added to the group.
- Bot should be promoted to **Administrator** with "Send Messages" permission so Telegram delivers `chat_member` updates in supergroups.
### new version 1.0
 kya tum aisa bna skte ho ki user jb select kre to direct link expose na ho aur request mere pass aye then i will give him 
 ### new version 1.1
 bahi bot me cohort link ka alawa must read rules add kro