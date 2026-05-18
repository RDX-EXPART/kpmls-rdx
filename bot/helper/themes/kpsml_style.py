#!/usr/bin/env python3

class KPSMLStyle:

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def start(client, message)  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    ST_BN1_NAME = '👥 Support Group'
    ST_BN1_URL  = 'https://t.me/fileleechgroup'
    ST_BN2_NAME = '🔔 Updates Channel'
    ST_BN2_URL  = 'https://telegram.me/rdxmovie_hd'

    ST_MSG = '''✨ <b>Welcome to RDX Leech Bot</b> ✨

🚀 <b>Fast  •  Powerful  •  Reliable</b>
├ ⚡ Mirror Direct Links & TG Files
├ 🧲 Torrents & Magnet Links
├ ☁️ Google Drive & Rclone Cloud
╰ 📡 Telegram & DDL Servers

💡 Type {help_command} to explore all commands'''

    ST_BOTPM   = '✅ <b>Bot PM Activated!</b>\n\n<i>All your files and links will be sent right here. Start using now...</i>'
    ST_UNAUTH  = '🚫 <b>Unauthorized Access!</b>\n\n<i>You are not an authorized user.\nDeploy your own <b>RDXMOVIE Mirror-Leech Bot</b> to get started.</i>'

    OWN_TOKEN_GENERATE = '⚠️ <b>Token Mismatch!</b>\n\n<i>This temporary token was not generated for you.\nKindly generate your own token.</i>'
    USED_TOKEN         = '🔁 <b>Token Already Used!</b>\n\n<i>This temporary token has already been activated.\nPlease generate a new one.</i>'
    LOGGED_PASSWORD    = '🔐 <b>Already Logged In via Password!</b>\n\n<i>No need to accept temporary tokens while password login is active.</i>'
    ACTIVATE_BUTTON    = '🔓 Activate Temporary Token'

    TOKEN_MSG = '''🎟️ <b><u>Temporary Login Token Generated!</u></b>

├ 🔑 <b>Temp Token</b> ➜ <code>{token}</code>
╰ ⏳ <b>Validity</b>   ➜ {validity}

⚠️ <i>Do not share this token with anyone.</i>'''

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def token_callback(_, query)  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    ACTIVATED = '✅ <b>Token Activated Successfully!</b>'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def login(_, message)  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    LOGGED_IN    = '✅ <b>Bot is Already Logged In!</b>'
    INVALID_PASS = '❌ <b>Invalid Password!</b>\n\n<i>Please enter the correct password and try again.</i>'
    PASS_LOGGED  = '🔐 <b>Bot Logged In Permanently!</b>\n\n<i>Password authentication successful.</i>'
    LOGIN_USED   = '💡 <b>Login Command Usage:</b>\n\n<code>/cmd [password]</code>'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def log(_, message)  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    LOG_DISPLAY_BT = '📋 View Log File'
    WEB_PASTE_BT   = '🌐 Paste to Web (SB)'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def bot_help(client, message)  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    BASIC_BT  = '📖 Basic'
    USER_BT   = '👤 Users'
    MICS_BT   = '🔧 Misc'
    O_S_BT    = '👑 Owner & Sudos'
    CLOSE_BT  = '❌ Close'

    HELP_HEADER = '''📚 <b><i>Help & Command Guide</i></b>

💡 <i>Tap on any command button to view its detailed description and usage.</i>'''

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def stats(client, message)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    BOT_STATS = '''📊 <b>BOT STATISTICS</b>

⏱️ <b>Bot Uptime</b> ➜ {bot_uptime}

🧠 <b>RAM (Memory)</b>
├ {ram_bar} <code>{ram}%</code>
├ 📈 Used  ➜ {ram_u}
├ 📉 Free  ➜ {ram_f}
╰ 💾 Total ➜ {ram_t}

🔄 <b>Swap Memory</b>
├ {swap_bar} <code>{swap}%</code>
├ 📈 Used  ➜ {swap_u}
├ 📉 Free  ➜ {swap_f}
╰ 💾 Total ➜ {swap_t}

💿 <b>Disk Storage</b>
├ {disk_bar} <code>{disk}%</code>
├ 📖 Total Read  ➜ {disk_read}
├ 📝 Total Write ➜ {disk_write}
├ 📈 Used  ➜ {disk_u}
├ 📉 Free  ➜ {disk_f}
╰ 💾 Total ➜ {disk_t}'''

    SYS_STATS = '''🖥️ <b>SYSTEM INFORMATION</b>

├ ⏱️ OS Uptime  ➜ {os_uptime}
├ 🐧 OS Version ➜ {os_version}
╰ 🔩 OS Arch    ➜ {os_arch}

🌐 <b>Network Statistics</b>
├ ⬆️ Upload      ➜ {up_data}
├ ⬇️ Download    ➜ {dl_data}
├ 📤 Pkts Sent   ➜ {pkt_sent}k
├ 📥 Pkts Recv   ➜ {pkt_recv}k
╰ 📦 Total I/O   ➜ {tl_data}

⚙️ <b>CPU Details</b>
├ {cpu_bar} <code>{cpu}%</code>
├ 📡 Frequency   ➜ {cpu_freq}
├ 📊 Avg Load    ➜ {sys_load}
├ 🔵 P-Cores     ➜ {p_core}
├ 🟡 V-Cores     ➜ {v_core}
├ 🔢 Total Cores ➜ {total_core}
╰ ✅ Usable CPUs ➜ {cpu_use}'''

    REPO_STATS = '''📦 <b>REPOSITORY STATISTICS</b>

├ 🕐 Last Updated    ➜ {last_commit}
├ 🏷️ Current Version ➜ {bot_version}
├ 🚀 Latest Version  ➜ {lat_version}
╰ 📝 Last ChangeLog  ➜ {commit_details}

💬 <b>Remarks</b> ➜ <code>{remarks}</code>'''

    BOT_LIMITS = '''⚖️ <b>BOT LIMITATIONS</b>

├ 🔗 Direct Limit   ➜ {DL} GB
├ 🧲 Torrent Limit  ➜ {TL} GB
├ ☁️ GDrive Limit   ➜ {GL} GB
├ ▶️ YT-DLP Limit   ➜ {YL} GB
├ 🎵 Playlist Limit ➜ {PL}
├ 📦 Mega Limit     ➜ {ML} GB
├ 🔁 Clone Limit    ➜ {CL} GB
╰ 📥 Leech Limit    ➜ {LL} GB

├ ⏳ Token Validity      ➜ {TV}
├ 🕐 User Time Limit     ➜ {UTI} / task
├ 👤 User Parallel Tasks ➜ {UT}
╰ 🤖 Bot Parallel Tasks  ➜ {BT}'''

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def restart(client, message)  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    RESTARTING = '🔄 <i>Restarting bot, please wait...</i>'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def restart_notification()  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    RESTART_SUCCESS = '''✅ <b><i>Restarted Successfully!</i></b>

├ 📅 Date     ➜ {date}
├ 🕐 Time     ➜ {time}
├ 🌍 TimeZone ➜ {timz}
╰ 🏷️ Version  ➜ {version}'''

    RESTARTED = '♻️ <b><i>Bot Has Been Restarted!</i></b>'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def ping(client, message)  ──▶  __main__.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    PING       = '🏓 <i>Pinging server...</i>'
    PING_VALUE = '🏓 <b>Pong!</b>\n\n⚡ <b>Response Time</b> ➜ <code>{value} ms</code>'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def onDownloadStart(self)  ──▶  tasks_listener.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    LINKS_START = '''🚀 <b><i>Task Initiated!</i></b>
├ ⚙️ Mode ➜ {Mode}
╰ 👤 By   ➜ {Tag}\n\n'''

    LINKS_SOURCE = '''🔗 <b>Source Details</b>
╰ 🕐 Added On ➜ {On}
─────────────────────
{Source}
─────────────────────\n\n'''

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def __msg_to_reply(self)  ──▶  pyrogramEngine.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    PM_START    = "🚀 <b><u>Task Started</u></b>\n│\n╰ 🔗 <b>Link</b> ➜ <a href='{msg_link}'>Click Here</a>"
    L_LOG_START = "📥 <b><u>Leech Started</u></b>\n│\n├ 👤 <b>User</b>   ➜ {mention} ( <code>#ID{uid}</code> )\n╰ 🔗 <b>Source</b> ➜ <a href='{msg_link}'>Click Here</a>"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def onUploadComplete()  ──▶  tasks_listener.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    NAME   = '🎬 <b><i>{Name}</i></b>\n│\n'
    SIZE   = '├ 📦 <b>Size</b>    ➜ {Size}\n'
    ELAPSE = '├ ⏱️ <b>Elapsed</b> ➜ {Time}\n'
    MODE   = '├ ⚙️ <b>Mode</b>    ➜ {Mode}\n'

    # ──── LEECH ────────────────────────────

    L_TOTAL_FILES     = '├ 📁 <b>Total Files</b>     ➜ {Files}\n'
    L_CORRUPTED_FILES = '├ ⚠️ <b>Corrupted Files</b> ➜ {Corrupt}\n'
    L_CC              = '╰ 👤 <b>By</b> ➜ {Tag}\n\n'
    PM_BOT_MSG        = '✅ <b><i>File(s) have been sent above!</i></b>'
    L_BOT_MSG         = '📨 <b><i>File(s) have been sent to your Bot PM (Private).</i></b>'
    L_LL_MSG          = ''

    # ──── MIRROR ───────────────────────────

    M_TYPE    = '├ 🗃️ <b>Type</b>       ➜ {Mimetype}\n'
    M_SUBFOLD = '├ 📂 <b>SubFolders</b> ➜ {Folder}\n'
    TOTAL_FILES = '├ 📁 <b>Files</b>     ➜ {Files}\n'
    RCPATH    = '├ 📍 <b>Path</b>       ➜ <code>{RCpath}</code>\n'
    M_CC      = '╰ 👤 <b>By</b> ➜ {Tag}\n\n'
    M_BOT_MSG = '📨 <b><i>Link(s) have been sent to your Bot PM (Private).</i></b>'

    # ──── BUTTONS ──────────────────────────

    CLOUD_LINK     = '☁️ Cloud Vault'
    SAVE_MSG       = '📥 Save to Inbox'
    RCLONE_LINK    = '🔄 RClone Sync'
    DDL_LINK       = '🌍 {Serv} Access'
    SOURCE_URL     = '🔏 Source Gateway'
    INDEX_LINK_F   = '🗂️ File Index'
    INDEX_LINK_D   = '🧭 Directory Index'
    VIEW_LINK      = '👁️ Live Preview'
    CHECK_PM       = '🔐 Enter Private Chat'
    CHECK_LL       = '🧾 Links Archive'
    MEDIAINFO_LINK = '📊 Media Details'
    SCREENSHOTS    = '🖼️ Preview Shots'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   def get_readable_message()  ──▶  bot_utilis.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # ──── Overall Msg Header ───────────────

    STATUS_NAME = '🎯 <b><i>{Name}</i></b>'

    # ──── Progressive Status ───────────────

    BAR       = '\n│ {Bar}'
    PROCESSED = '\n├ 📦 <b>Processed</b> ➜ {Processed}'
    STATUS    = '\n├ 🔄 <b>Status</b>    ➜ <a href="{Url}">{Status}</a>'
    ETA       =                       ' | ⏳ <b>ETA</b> ➜ {Eta}'
    SPEED     = '\n├ ⚡ <b>Speed</b>    ➜ {Speed}'
    ELAPSED   =                  ' | ⏱️ <b>Elapsed</b> ➜ {Elapsed}'
    ENGINE    = '\n├ 🔧 <b>Engine</b>   ➜ {Engine}'
    STA_MODE  = '\n├ ⚙️ <b>Mode</b>     ➜ {Mode}'
    SEEDERS   = '\n├ 🌱 <b>Seeders</b>  ➜ {Seeders} | '
    LEECHERS  =          '🔻 <b>Leechers</b> ➜ {Leechers}'

    # ──── Seeding ─────────────────────────

    SEED_SIZE   = '\n├ 📦 <b>Size</b>     ➜ {Size}'
    SEED_SPEED  = '\n├ ⚡ <b>Speed</b>    ➜ {Speed} | '
    UPLOADED    =        '⬆️ <b>Uploaded</b> ➜ {Upload}'
    RATIO       = '\n├ 📊 <b>Ratio</b>    ➜ {Ratio} | '
    TIME        =        '⏱️ <b>Time</b>    ➜ {Time}'
    SEED_ENGINE = '\n├ 🔧 <b>Engine</b>   ➜ {Engine}'

    # ──── Non-Progressive / Non-Seeding ───

    STATUS_SIZE = '\n├ 📦 <b>Size</b>   ➜ {Size}'
    NON_ENGINE  = '\n├ 🔧 <b>Engine</b> ➜ {Engine}'

    # ──── Overall Msg Footer ──────────────

    USER   = '\n├ 👤 <b>User</b> ➜ <code>{User}</code> | '
    ID     =                  '🆔 <b>ID</b> ➜ <code>{Id}</code>'
    BTSEL  = '\n├ 🎛️ <b>Select</b> ➜ {Btsel}'
    CANCEL = '\n╰ {Cancel}\n\n'

    # ──── Status Footer ───────────────────

    FOOTER    = '📊 <b><i>Bot Stats</i></b>\n'
    TASKS     = '├ 📋 <b>Tasks</b>  ➜ {Tasks}\n'
    BOT_TASKS = '├ 📋 <b>Tasks</b>  ➜ {Tasks}/{Ttask} | 🟢 <b>AVL</b> ➜ {Free}\n'
    Cpu       = '├ 🖥️ <b>CPU</b>    ➜ {cpu}% | '
    FREE      =         '💾 <b>Free</b>   ➜ {free} [{free_p}%]'
    Ram       = '\n├ 🧠 <b>RAM</b>    ➜ {ram}% | '
    uptime    =         '⏱️ <b>Uptime</b> ➜ {uptime}'
    DL        = '\n╰ ⬇️ <b>DL</b>     ➜ {DL}/s | '
    UL        =         '⬆️ <b>UL</b>     ➜ {UL}/s'

    # ──── Navigation Buttons ──────────────

    PREVIOUS = '«'
    REFRESH  = '📄 Pages\n{Page}'
    NEXT     = '»'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   STOP_DUPLICATE_MSG  ──▶  clone.py / aria2_listener.py / task_manager.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    STOP_DUPLICATE = '⚠️ <b>Duplicate Found!</b>\n\n<i>This file/folder is already available in Drive.\nHere are <b>{content}</b> matching result(s):</i>'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def countNode(_, message)  ──▶  gd_count.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    COUNT_MSG  = '🔍 <b>Counting</b> ➜ <code>{LINK}</code>'
    COUNT_NAME = '📁 <b><i>{COUNT_NAME}</i></b>\n│\n'
    COUNT_SIZE = '├ 📦 <b>Size</b>       ➜ {COUNT_SIZE}\n'
    COUNT_TYPE = '├ 🗃️ <b>Type</b>       ➜ {COUNT_TYPE}\n'
    COUNT_SUB  = '├ 📂 <b>SubFolders</b> ➜ {COUNT_SUB}\n'
    COUNT_FILE = '├ 📄 <b>Files</b>      ➜ {COUNT_FILE}\n'
    COUNT_CC   = '╰ 👤 <b>By</b>         ➜ {COUNT_CC}\n'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   LIST  ──▶  gd_list.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    LIST_SEARCHING = '🔍 <b>Searching for</b> <i>{NAME}</i><b>...</b>'
    LIST_FOUND     = '✅ <b>Found {NO} result(s) for</b> <i>{NAME}</i>'
    LIST_NOT_FOUND = '❌ <b>No results found for</b> <i>{NAME}</i>'

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   async def mirror_status(_, message)  ──▶  status.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    NO_ACTIVE_DL = '''😴 <i>No Active Downloads at the moment!</i>

📊 <b>Bot Stats</b>
├ 🖥️ CPU    ➜ {cpu}%  |  💾 Free   ➜ {free} [{free_p}%]
╰ 🧠 RAM    ➜ {ram}   |  ⏱️ Uptime ➜ {uptime}'''

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   USER Settings  ──▶  user_setting.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    USER_SETTING = '''⚙️ <b><u>User Settings</u></b>

👤 <b>Name</b> ➜ {NAME}  🆔 <code>{ID}</code>
├ 🔖 Username    ➜ {USERNAME}
├ 📡 Telegram DC ➜ {DC}
╰ 🌐 Language    ➜ {LANG}

💡 <u><b>Available Args:</b></u>
• <b>-s</b> or <b>-set</b> — Set settings directly via argument'''

    UNIVERSAL = '''🌐 <b><u>Universal Settings : {NAME}</u></b>

├ ▶️ YT-DLP Options ➜ <b><code>{YT}</code></b>
├ 📅 Daily Tasks    ➜ <code>{DT}</code> per day
├ 🕐 Last Bot Used  ➜ <code>{LAST_USED}</code>
├ 🔑 User Session   ➜ <code>{USESS}</code>
├ 🎥 MediaInfo Mode ➜ <code>{MEDIAINFO}</code>
├ 💾 Save Mode      ➜ <code>{SAVE_MODE}</code>
╰ 📨 User Bot PM    ➜ <code>{BOT_PM}</code>'''

    MIRROR = '''🪞 <b><u>Mirror / Clone Settings : {NAME}</u></b>

├ ⚙️ RClone Config    ➜ <i>{RCLONE}</i>
├ 🏷️ Mirror Prefix    ➜ <code>{MPREFIX}</code>
├ 🔚 Mirror Suffix    ➜ <code>{MSUFFIX}</code>
├ ✏️ Mirror Rename    ➜ <code>{MREMNAME}</code>
├ 🌍 DDL Server(s)    ➜ <i>{DDL_SERVER}</i>
├ 📁 User TD Mode     ➜ <i>{TMODE}</i>
├ 🔢 Total User TD(s) ➜ <i>{USERTD}</i>
╰ 📅 Daily Mirror     ➜ <code>{DM}</code> per day'''

    LEECH = '''📥 <b><u>Leech Settings : {NAME}</u></b>

👤 <b>Name</b> ➜ {NAME}  🆔 <code>{ID}</code>
├ 📦 Daily Leech   ➜ <code>{DL}</code>
├ 🎬 Leech Type    ➜ <i>{LTYPE}</i>
├ 🖼️ Thumbnail     ➜ <i>{THUMB}</i>
├ ✂️ Split Size    ➜ <code>{SPLIT_SIZE}</code>
├ ⚖️ Equal Splits  ➜ <i>{EQUAL_SPLIT}</i>
├ 👥 Media Group   ➜ <i>{MEDIA_GROUP}</i>
├ 📝 Caption       ➜ <code>{LCAPTION}</code>
├ 🌸 Prefix        ➜ <code>{LPREFIX}</code>
├ 💫 Suffix        ➜ <code>{LSUFFIX}</code>
├ 🪄 Auto Rename   ➜ <code>{LREMNAME}</code>
├ 📂 Dumps         ➜ <code>{LDUMP}</code>
├ 📎 Attachment    ➜ <code>{ATTACHMENT}</code>
╰ 🧬 Metadata      ➜ <code>{METADATA}</code>'''

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #   AI Caption Settings  ──▶  bot_settings.py
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    AI_CAPTION_HEADER = '''🤖 <b><u>AI Caption Settings</u></b>

├ 🔮 AI Caption       ➜ <i>{AI_CAPTION}</i>
├ 🌟 IMDB Lookup      ➜ <i>{AI_CAPTION_IMDB}</i>
╰ 📝 Custom Template  ➜ <code>{AI_CAPTION_TEMPLATE}</code>

📌 <i>When enabled, leech uploads get auto-styled captions with title, IMDB rating, quality, audio & size.</i>'''

    AI_CAPTION_ENABLED_MSG  = '✅ <b>AI Caption Enabled!</b>\n\n<i>Stylish captions will be auto-generated for all leech uploads.</i>'
    AI_CAPTION_DISABLED_MSG = '❌ <b>AI Caption Disabled!</b>\n\n<i>Standard filename captions will be used instead.</i>'
    AI_CAPTION_IMDB_ON      = '✅ <b>IMDB Lookup Enabled!</b>\n\n<i>Ratings & genres will be automatically fetched from IMDB.</i>'
    AI_CAPTION_IMDB_OFF     = '❌ <b>IMDB Lookup Disabled!</b>\n\n<i>Only filename metadata will be used.</i>'
    AI_CAPTION_TEMPLATE_SET   = '✅ <b>AI Caption Template Updated!</b>\n\n<code>{template}</code>'
    AI_CAPTION_TEMPLATE_RESET = '🔄 <b>AI Caption Template Reset</b> to default.'

    AI_CAPTION_TEMPLATE_HELP = '''🤖 <b>AI Caption Template — Help Guide</b>

<i>Customize your caption using these variables:</i>

├ <code>{title}</code>           ➜ Movie / Series title
├ <code>{year_str}</code>        ➜ Year like "(2025)" or empty
├ <code>{imdb_line}</code>       ➜ "🌟 IMDB: 8.2\\n" or empty
├ <code>{imdb_rating}</code>     ➜ IMDB rating or "N/A"
├ <code>{quality}</code>         ➜ e.g. "1080p WEB-DL"
├ <code>{languages}</code>       ➜ e.g. "Hindi + English"
├ <code>{audio}</code>           ➜ e.g. "DD+5.1"
├ <code>{file_size}</code>       ➜ e.g. "2.4 GB"
├ <code>{season_ep_line}</code>  ➜ "📺 Episode: S01E05" or empty
├ <code>{genre_line}</code>      ➜ "🎭 Genre: Action, Drama" or empty
╰ <code>{filename}</code>        ➜ Raw filename (no extension)

📋 <b>Example Template:</b>
<code>🎬 {title}{year_str}

{imdb_line}🎞️ Quality: {quality}
🔊 Audio: {languages}
📦 Size: {file_size}{season_ep_line}{genre_line}</code>

💡 <i>Send</i> <code>reset</code> <i>to restore the default template.</i>'''

    AI_CAPTION_BT        = '🤖 AI Caption'
    AI_CAPTION_TOGGLE_BT = '🤖 AI Caption: {status}'
    AI_CAPTION_IMDB_BT   = '🌟 IMDB Lookup: {status}'
    AI_CAPTION_TPL_BT    = '📝 Custom Template'
