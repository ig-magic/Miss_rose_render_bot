#!/usr/bin/env python3

help_texts = {
    "main": """
🌹 **Miss Rose - Command Categories**

Select a category below to see available commands:

• **User Management** - Ban, mute, kick, warn users
• **Admin Tools** - Promote, demote, admin management  
• **Welcome & Rules** - Greet new members, set rules
• **Locks & Filters** - Content control and auto-responses
• **Logging** - Track admin actions and events
• **Federation** - Cross-group ban management
• **Settings** - Configure bot behavior
• **Utilities** - Info, reports, and other tools
    """,
    "users": """
👥 **User Management Commands**

**Moderation:**
• `/ban <user> [reason]` - Ban a user permanently
• `/tban <user> <time> [reason]` - Temporarily ban (4m, 3h, 6d, 5w)
• `/mute <user> [reason]` - Mute a user permanently
• `/tmute <user> <time> [reason]` - Temporarily mute
• `/kick <user> [reason]` - Remove user (can rejoin)
• `/unban <user>` - Unban a user
• `/unmute <user>` - Unmute a user

**Warnings:**
• `/warn <user> [reason]` - Warn a user (3 warns = ban)
• `/unwarn <user>` - Remove all warnings
• `/warns [user]` - Check warnings
    """,
    "admin": """
🛡️ **Admin Management Commands**

**Admin Control:**
• `/promote <user> [title]` - Promote user to admin
• `/demote <user>` - Remove admin status
• `/admins` - List all group admins
• `/adminlist` - Same as /admins

**Permissions:**
Admin commands require administrator privileges in the group.
    """,
    "welcome": """
📝 **Welcome & Rules Commands**

**Welcome System:**
• `/setwelcome <message>` - Set welcome message
• `/setgoodbye <message>` - Set goodbye message
• `/cleanwelcome <on/off>` - Auto-delete welcome messages

**Rules:**
• `/setrules <text>` - Set group rules
• `/rules` - Show group rules
• `/privaterules <on/off>` - Send rules privately

**Variables:** `{first}`, `{last}`, `{fullname}`, `{username}`, `{mention}`, `{id}`, `{chatname}`
    """,
    "locks": """
🔒 **Locks & Filters Commands**

**Content Locks:**
• `/lock <type>` - Lock content type
• `/unlock <type>` - Unlock content type
• `/locks` - Show locked content

**Lock Types:** `all`, `media`, `sticker`, `gif`, `url`, `bots`, `forward`, `game`, `location`

**Custom Filters:**
• `/filter <trigger> <response>` - Add auto-response
• `/stop <trigger>` - Remove filter
• `/filters` - List all filters
    """,
    "logging": """
📊 **Logging Commands**

**Admin Logging:**
• `/setlog` - Set log channel (use in private)
• All admin actions are automatically logged

**Log Categories:**
• User moderation (bans, mutes, kicks)
• Admin actions (promote, demote)
• Setting changes
• Reports and warnings
    """,
    "federation": """
🌐 **Federation Commands**

**Federation Management:**
• `/newfed <name>` - Create new federation
• `/joinfed <fed_id>` - Join group to federation
• `/leavefed` - Leave current federation
• `/fedinfo` - Show federation info

**Cross-Group Bans:**
Federation bans are automatically shared across all member groups.
    """,
    "settings": """
⚙️ **Settings Commands**

**Bot Behavior:**
• `/silent <on/off>` - Enable silent admin actions
• `/cleanservice <on/off>` - Delete service messages
• `/cleanwelcome <on/off>` - Auto-delete welcome messages
• `/privaterules <on/off>` - Send rules privately

**Command Control:**
• `/disable <command>` - Disable command for users
• `/enable <command>` - Re-enable command
• `/disabled` - List disabled commands

**Import/Export:**
• `/export` - Export group settings
• `/import` - Import group settings (owner only)
    """,
    "utils": """
🔧 **Utility Commands**

**Information:**
• `/info [user]` - Get user information
• `/id` - Get chat/user IDs
• `/rules` - Show group rules

**User Actions:**
• `/report` - Report message to admins (reply to message)
• `/kickme` - Remove yourself from group

**Bot Info:**
• `/start` - Bot introduction
• `/help` - This help menu
• `/version` - Bot version info
    """
}

support_text = """
💬 **Support & Information**

**Bot Features:**
• 60+ working commands
• Advanced group moderation
• Anti-spam protection
• Custom filters and locks
• Federation system
• Admin logging
• Import/export settings

**Need Help?**
• Use `/help` for command list
• Commands work with replies, mentions, or user IDs
• Most commands require admin privileges

**Tips:**
• Start with `/setrules` and `/setwelcome`
• Enable logging with `/setlog`
• Use locks to control content
• Create filters for auto-responses

Made with ❤️ for better group management!
"""