"""
Comprehensive test suite for Version 1.0 of Telegram Link & Welcome Bot
Tests:
1. Version 1.0 Default: Approval mode is ON by default (direct link hidden/never exposed directly)
2. Request creation and Admin notification
3. Admin approval flow & private link delivery
4. Exact welcome greeting ("lehari me apka sawagat h! kya chahiye aapko?")
5. Supergroup ChatMemberUpdated join handling
6. Service message (new_chat_members) join handling
7. De-duplication cache preventing duplicate welcomes
"""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

import database
import config
import bot


class TestVersionOnePointZero(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.test_db = "test_v1.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        database.DB_PATH = self.test_db
        database.init_db(self.test_db)
        bot._welcomed_cache.clear()
        self.orig_admin_ids = config.ADMIN_IDS
        config.ADMIN_IDS = [999999999]

    def tearDown(self):
        database.DB_PATH = "bot.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        config.ADMIN_IDS = self.orig_admin_ids

    async def test_01_v1_approval_mode_default_on(self):
        """In Version 1.0, approval mode must be enabled by default to prevent direct link exposure."""
        self.assertTrue(database.is_approval_required(self.test_db), "Approval mode should be ON by default in v1.0")

    async def test_02_link_not_exposed_on_selection(self):
        """When a user selects an option, the direct link is NOT exposed; an admin approval request is created."""
        opt_id = database.add_option("Confidential Course", "https://secret.com/course", "Full secret course", self.test_db)

        mock_user = MagicMock(id=111, first_name="Aakash", username="aakash_99", last_name="")
        mock_chat = MagicMock(type="private", id=111)

        mock_update = MagicMock()
        mock_update.effective_user = mock_user
        mock_update.effective_chat = mock_chat
        mock_update.message.reply_html = AsyncMock()

        mock_context = MagicMock()
        mock_context.bot.get_me = AsyncMock(return_value=MagicMock(username="Hamza_lehariwale_007bot"))
        mock_context.bot.send_message = AsyncMock()

        # Execute process_link_request
        await bot.process_link_request(mock_update, mock_context, opt_id, mock_user)

        # 1. User message must NOT contain the secret URL
        user_sent_text = mock_update.message.reply_html.call_args[0][0]
        self.assertNotIn("https://secret.com/course", user_sent_text, "Direct link was exposed to the user!")
        self.assertIn("Request Submitted", user_sent_text)

        # 2. Database request was created
        req = database.get_link_request(1, self.test_db)
        self.assertIsNotNone(req)
        self.assertEqual(req["status"], "pending")
        self.assertEqual(req["user_id"], 111)

        # 3. Admin received notification with Approve button
        mock_context.bot.send_message.assert_called_once()
        admin_call_kwargs = mock_context.bot.send_message.call_args[1]
        self.assertIn("Nayi Link Request Aayi Hai", admin_call_kwargs["text"])
        self.assertIn("Confidential Course", admin_call_kwargs["text"])

    async def test_03_admin_approval_delivers_link_to_user(self):
        """When admin approves the request, the user receives the link in their private chat."""
        opt_id = database.add_option("VIP Material", "https://vip.example.com", "VIP Access", self.test_db)
        req_id = database.create_link_request(222, "rohit", "Rohit", opt_id, self.test_db)

        # Simulate admin clicking Approve button
        mock_query = MagicMock()
        mock_query.from_user.id = 999999999  # configured admin ID
        mock_query.data = f"appr_req:{req_id}"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()

        mock_update = MagicMock(callback_query=mock_query)
        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        # Temporarily ensure admin check passes
        orig_admin_ids = config.ADMIN_IDS
        config.ADMIN_IDS = [999999999]
        try:
            await bot.handle_admin_request_action(mock_update, mock_context)
        finally:
            config.ADMIN_IDS = orig_admin_ids

        # 1. Check database status is approved
        req = database.get_link_request(req_id, self.test_db)
        self.assertEqual(req["status"], "approved")

        # 2. Check link was delivered to the user (chat_id = 222)
        mock_context.bot.send_message.assert_called_once()
        user_call = mock_context.bot.send_message.call_args[1]
        self.assertEqual(user_call["chat_id"], 222)
        self.assertIn("https://vip.example.com", user_call["text"])
        self.assertIn("Aapki Request Approve Ho Gayi", user_call["text"])

    async def test_04_welcome_message_content(self):
        """Verify the exact welcome text: 'lehari me apka sawagat h! kya chahiye aapko?'"""
        mock_user = MagicMock(id=333, first_name="Vikas", username="vikas_v", last_name="", is_bot=False)
        mock_context = MagicMock()
        mock_context.bot.get_me = AsyncMock(return_value=MagicMock(username="Hamza_lehariwale_007bot"))
        mock_context.bot.send_message = AsyncMock()

        await bot.greet_user_in_chat(chat_id=-100999, user=mock_user, context=mock_context, in_group=True)

        # Call 1: To the group with welcome message
        self.assertEqual(mock_context.bot.send_message.call_count, 2)
        group_call = mock_context.bot.send_message.call_args_list[0][1]
        self.assertEqual(group_call["chat_id"], -100999)
        self.assertIn("lehari me apka sawagat h! kya chahiye aapko?", group_call["text"])
        self.assertIn("Vikas", group_call["text"])

        # Call 2: To the Admin PRIVATELY with OSINT report
        admin_call = mock_context.bot.send_message.call_args_list[1][1]
        self.assertEqual(admin_call["chat_id"], 999999999)
        self.assertIn("Private OSINT Intelligence Report", admin_call["text"])

    async def test_05_chat_member_updated_join_event(self):
        """Simulate Supergroup ChatMemberUpdated join event."""
        mock_user = MagicMock(id=444, first_name="Karan", username="karan_k", last_name="", is_bot=False)

        mock_update = MagicMock()
        mock_update.chat_member.chat.id = -100888
        mock_update.chat_member.old_chat_member.status = "left"
        mock_update.chat_member.new_chat_member.status = "member"
        mock_update.chat_member.new_chat_member.user = mock_user

        mock_context = MagicMock()
        mock_context.bot.get_me = AsyncMock(return_value=MagicMock(username="Hamza_lehariwale_007bot"))
        mock_context.bot.send_message = AsyncMock()

        await bot.chat_member_welcome_handler(mock_update, mock_context)

        # Call 1: To the group with welcome message
        self.assertEqual(mock_context.bot.send_message.call_count, 2)
        group_call = mock_context.bot.send_message.call_args_list[0][1]
        self.assertEqual(group_call["chat_id"], -100888)
        self.assertIn("lehari me apka sawagat h! kya chahiye aapko?", group_call["text"])
        self.assertIn("Karan", group_call["text"])

        # Call 2: To the Admin PRIVATELY with OSINT report
        admin_call = mock_context.bot.send_message.call_args_list[1][1]
        self.assertEqual(admin_call["chat_id"], 999999999)
        self.assertIn("Private OSINT Intelligence Report", admin_call["text"])

    async def test_06_warn_three_times_and_kick(self):
        """Verify /warn increments warning count and on the 3rd warning kicks the user."""
        chat_id = -1005555
        target_user = MagicMock(id=666, first_name="Troublemaker", username="bad_user", last_name="")
        admin_user = MagicMock(id=999999999, first_name="Admin", username="admin_user", last_name="")

        mock_chat = MagicMock(type="supergroup", id=chat_id)
        # Ensure target is not an admin
        mock_chat.get_member = AsyncMock(return_value=MagicMock(status="member"))

        mock_context = MagicMock()
        mock_context.bot.id = 888888888
        mock_context.bot.ban_chat_member = AsyncMock()
        mock_context.bot.unban_chat_member = AsyncMock()
        mock_context.args = []

        # Warn 1
        mock_update1 = MagicMock()
        mock_update1.effective_chat = mock_chat
        mock_update1.effective_user = admin_user
        mock_update1.message.reply_to_message.from_user = target_user
        mock_update1.message.reply_html = AsyncMock()

        orig_admin_ids = config.ADMIN_IDS
        config.ADMIN_IDS = [999999999]
        try:
            await bot.warn_command(mock_update1, mock_context)
            self.assertEqual(database.get_warnings(chat_id, target_user.id, self.test_db), 1)
            text1 = mock_update1.message.reply_html.call_args[0][0]
            self.assertIn("Warning [1/3]", text1)
            mock_context.bot.ban_chat_member.assert_not_called()

            # Warn 2
            mock_update2 = MagicMock()
            mock_update2.effective_chat = mock_chat
            mock_update2.effective_user = admin_user
            mock_update2.message.reply_to_message.from_user = target_user
            mock_update2.message.reply_html = AsyncMock()

            await bot.warn_command(mock_update2, mock_context)
            self.assertEqual(database.get_warnings(chat_id, target_user.id, self.test_db), 2)
            text2 = mock_update2.message.reply_html.call_args[0][0]
            self.assertIn("Warning [2/3]", text2)
            mock_context.bot.ban_chat_member.assert_not_called()

            # Warn 3 -> triggers kick
            mock_update3 = MagicMock()
            mock_update3.effective_chat = mock_chat
            mock_update3.effective_user = admin_user
            mock_update3.message.reply_to_message.from_user = target_user
            mock_update3.message.reply_html = AsyncMock()

            await bot.warn_command(mock_update3, mock_context)
            # Warnings should be reset upon kick
            self.assertEqual(database.get_warnings(chat_id, target_user.id, self.test_db), 0)
            text3 = mock_update3.message.reply_html.call_args[0][0]
            self.assertIn("3 Warnings Reached!", text3)
            self.assertIn("remove/kick", text3)

            # Bot ban & unban (kick) called
            mock_context.bot.ban_chat_member.assert_called_once_with(chat_id=chat_id, user_id=target_user.id)
            mock_context.bot.unban_chat_member.assert_called_once_with(chat_id=chat_id, user_id=target_user.id)
        finally:
            config.ADMIN_IDS = orig_admin_ids

    async def test_07_unwarn_removes_warning(self):
        """Verify /unwarn decrements warning count."""
        chat_id = -1006666
        target_user = MagicMock(id=777, first_name="UserToForgive", username="forgive_me", last_name="")
        admin_user = MagicMock(id=999999999, first_name="Admin", username="admin_user", last_name="")

        # Add 2 warnings
        database.add_warning(chat_id, target_user.id, self.test_db)
        database.add_warning(chat_id, target_user.id, self.test_db)
        self.assertEqual(database.get_warnings(chat_id, target_user.id, self.test_db), 2)

        mock_chat = MagicMock(type="supergroup", id=chat_id)
        mock_context = MagicMock()
        mock_update = MagicMock()
        mock_update.effective_chat = mock_chat
        mock_update.effective_user = admin_user
        mock_update.message.reply_to_message.from_user = target_user
        mock_update.message.reply_html = AsyncMock()

        orig_admin_ids = config.ADMIN_IDS
        config.ADMIN_IDS = [999999999]
        try:
            await bot.unwarn_command(mock_update, mock_context)
            self.assertEqual(database.get_warnings(chat_id, target_user.id, self.test_db), 1)
            text = mock_update.message.reply_html.call_args[0][0]
            self.assertIn("1 warning removed", text)
        finally:
            config.ADMIN_IDS = orig_admin_ids

    async def test_08_course_query_replies_mt_kr_lala(self):
        """Verify that course queries in group chat get replied with 'mt kr lala'."""
        mock_user = MagicMock(id=9999, first_name="Student", username="learner", is_bot=False)
        mock_chat = MagicMock(type="supergroup", id=-1007777)
        mock_context = MagicMock()

        # Course query test message
        mock_message_course = MagicMock()
        mock_message_course.text = "bhai koi cohort 2.0 ya web dev course hai kya?"
        mock_message_course.reply_text = AsyncMock()

        mock_update = MagicMock()
        mock_update.message = mock_message_course
        mock_update.effective_message = mock_message_course
        mock_update.effective_chat = mock_chat
        mock_update.effective_user = mock_user

        await bot.course_query_handler(mock_update, mock_context)
        mock_message_course.reply_text.assert_called_once_with("mt kr lala")

        # Non-course query test message (should NOT trigger)
        mock_message_normal = MagicMock()
        mock_message_normal.text = "good morning everyone"
        mock_message_normal.caption = None
        mock_message_normal.reply_text = AsyncMock()

        mock_update_normal = MagicMock()
        mock_update_normal.message = mock_message_normal
        mock_update_normal.effective_message = mock_message_normal
        mock_update_normal.effective_chat = mock_chat
        mock_update_normal.effective_user = mock_user

        await bot.course_query_handler(mock_update_normal, mock_context)
        mock_message_normal.reply_text.assert_not_called()

    async def test_09_user_leave_osint_card(self):
        """Verify that when a user leaves the group, an OSINT/Public Info card is posted."""
        chat_id = -1004444
        mock_leaving_user = MagicMock()
        mock_leaving_user.id = 876543210
        mock_leaving_user.first_name = "Vikram"
        mock_leaving_user.last_name = "Rathore"
        mock_leaving_user.full_name = "Vikram Rathore"
        mock_leaving_user.username = "vikram_osint"
        mock_leaving_user.is_bot = False
        mock_leaving_user.is_premium = True
        mock_leaving_user.language_code = "en"

        mock_update = MagicMock()
        mock_update.chat_member.chat.id = chat_id
        mock_update.chat_member.old_chat_member.status = "member"
        mock_update.chat_member.new_chat_member.status = "left"
        mock_update.chat_member.new_chat_member.user = mock_leaving_user

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        # Call chat_member_welcome_handler (handles both join and leave)
        await bot.chat_member_welcome_handler(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args[1]

        # Verify OSINT card is delivered PRIVATELY to Admin, NOT to the public group!
        self.assertEqual(call_kwargs["chat_id"], 999999999)
        card_text = call_kwargs["text"]
        self.assertIn("Private OSINT Intelligence Report", card_text)
        self.assertIn("Vikram Rathore", card_text)
        self.assertIn("876543210", card_text)
        self.assertIn("@vikram_osint", card_text)
        self.assertIn("Yes ⭐", card_text)
        self.assertIn("Est. Account Age", card_text)
        # Verify OSINT social search buttons attached
        self.assertIsNotNone(call_kwargs.get("reply_markup"))

    async def test_10_must_read_rules_button_in_menu(self):
        """Verify version 1.1: 'Must Read Rules' button is present alongside cohort links."""
        # 1. Private chat keyboard
        kb_private = bot.build_user_menu_keyboard(is_admin_user=False, in_group=False)
        buttons_private = [btn for row in kb_private.inline_keyboard for btn in row]
        rules_btn_private = next((b for b in buttons_private if "Must Read Rules" in b.text), None)
        self.assertIsNotNone(rules_btn_private)
        self.assertEqual(rules_btn_private.callback_data, "view_rules")

        # 2. Group keyboard (deep link to DM)
        kb_group = bot.build_user_menu_keyboard(is_admin_user=False, in_group=True, bot_username="Hamza_lehariwale_007bot")
        buttons_group = [btn for row in kb_group.inline_keyboard for btn in row]
        rules_btn_group = next((b for b in buttons_group if "Must Read Rules" in b.text), None)
        self.assertIsNotNone(rules_btn_group)
        self.assertIn("start=rules", rules_btn_group.url)

    async def test_11_rules_handlers_and_customization(self):
        """Verify /rules command, /setrules customization, and callback handler."""
        # 1. View rules via callback
        mock_query = MagicMock()
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update = MagicMock(callback_query=mock_query)
        mock_context = MagicMock()

        await bot.view_rules_callback_handler(mock_update, mock_context)
        mock_query.edit_message_text.assert_called_once()
        text_arg = mock_query.edit_message_text.call_args[1]["text"]
        self.assertIn("COMMUNITY MUST-READ RULES", text_arg)

        # 2. Update rules via /setrules (as Admin)
        admin_user = MagicMock(id=999999999)
        mock_msg = MagicMock()
        mock_msg.reply_html = AsyncMock()
        mock_admin_update = MagicMock(effective_user=admin_user, message=mock_msg)
        mock_admin_context = MagicMock(args=["Rule 1: Be nice.", "Rule 2: No spam."])

        await bot.setrules_command(mock_admin_update, mock_admin_context)
        self.assertIn("Rule 1: Be nice. Rule 2: No spam.", database.get_rules())

        # Reset to default
        database.set_rules(database.DEFAULT_RULES)


if __name__ == "__main__":
    unittest.main()

