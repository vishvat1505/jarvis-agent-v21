"""
intent.py — Instant local intent matching. Zero LLM roundtrip for common commands.
Covers: workspace, window, audio, brightness, screenshots, presets, config, scripts.
"""
import re
from . import tools

RULES = [

    # Greetings
    (r"^(?:hi+|hello|hey|howdy|sup|what'?s up|greetings|good (?:morning|afternoon|evening|night))[!.,]?(?:\s+(?:jarvis|bro|there|man|buddy))?[!.,]?$",
     lambda m,_: ("Hey! I'm JARVIS, your Hyprland desktop assistant. I can open apps/files, "
                  "manage windows/workspaces, control audio/brightness, change wallpapers, "
                  "manage packages, control services, and much more. What do you need?"), False),

    # Web search — "search google for X", "search for X on google"
    (r"^search (?:on |in )?(?:google|youtube|bing|ddg|duckduckgo) for (.+)",
     lambda m,t=None: tools.open_app({"app": "https://google.com/search?q=" + __import__("urllib.parse",fromlist=["quote"]).quote(m.group(1).strip())}), False),
    (r"^search(?: for| about)? (.+?) (?:on|in|using) (google|youtube|bing|ddg|duckduckgo)",
     lambda m,_: tools.open_app({"app": f"https://{'youtube.com/results?search_query=' if 'youtube' in m.group(2) else 'google.com/search?q='}" + __import__("urllib.parse",fromlist=["quote"]).quote(m.group(1).strip())}), False),
    (r"^(?:google|search) (.+)",
     lambda m,_: tools.open_app({"app": "https://google.com/search?q=" + __import__("urllib.parse",fromlist=["quote"]).quote(m.group(1).strip())}), False),
    # ── Workspace ─────────────────────────────────────────────────────────────
    (r"(?:go|switch|move me?|take me) to workspace\s*(\d+)",
     lambda m,_: tools.workspace_go({"number":int(m.group(1))}), False),
    (r"(?:move|send) (?:this |active |current )?window to workspace\s*(\d+)",
     lambda m,_: tools.workspace_move_window({"number":int(m.group(1))}), False),
    # "move all windows"/"move all browsers"/"open all firefox windows" to a
    # workspace — must come before the single-app move pattern below, or "all
    # firefox windows" would get treated as a literal (nonexistent) app name.
    (r"(?:move|send)\s+all\s+windows?\s+to\s+workspace\s*(\d+)",
     lambda m,_: tools.workspace_move_all({"number": int(m.group(1))}), False),
    (r"(?:move|send|open)\s+all\s+(.+?)\s+to\s+workspace\s*(\d+)",
     lambda m,_: tools.workspace_move_matching({"query": m.group(1).strip(), "number": int(m.group(2))}), False),
    (r"(?:move|send)\s+(?:this\s+|the\s+|active\s+|current\s+)?(?!window\b)([a-zA-Z0-9_.\- ]+?)\s+to\s+workspace\s*(\d+)",
     lambda m,_: tools.workspace_move_window({"class":m.group(1).strip(),"number":int(m.group(2))}), False),
    # "close/kill X in workspace N" — must also come before the bare pattern
    # below for the same reason: it has no anchoring and would otherwise
    # hijack this into just switching workspaces instead of closing anything.
    (r"(?:close|kill|quit|exit)\s+(?:this\s+|that\s+|the\s+)?(.+?)\s+(?:in|on)\s+workspace\s*(\d+)",
     lambda m,_: tools.close_window({"class": m.group(1).strip()}), False),
    # This bare pattern has no anchoring, so it must come AFTER the more
    # specific move/send patterns above — otherwise it hijacks any sentence
    # that merely mentions "workspace N" (e.g. "move firefox to workspace 10"
    # would just switch workspaces instead of moving the window).
    (r"workspace\s*(\d+)",
     lambda m,_: tools.workspace_go({"number":int(m.group(1))}), False),
    (r"list workspaces?",
     lambda m,_: tools.workspace_list(), False),

    # ── Window ────────────────────────────────────────────────────────────────
    (r"(?:toggle |make |set )?(?:float|floating)(?: this| window)?",
     lambda m,_: tools.window_float({}), False),
    (r"(?:toggle |make |set )?(?:fullscreen|full screen)(?: this| window)?",
     lambda m,_: tools.window_fullscreen({"mode":0}), False),
    (r"(?:maximize|max)(?: this| window)?",
     lambda m,_: tools.window_fullscreen({"mode":1}), False),
    (r"(?:kill|close)(?: active| current| this)? window",
     lambda m,_: tools.window_kill_active(), False),
    (r"center(?: this| window)?",
     lambda m,_: tools.window_center(), False),
    (r"pin(?: this| window)?",
     lambda m,_: tools.window_pin(), False),
    (r"(?:list|show)(?: open| all)? windows?",
     lambda m,_: tools.get_open_windows(), False),
    (r"^(?:kill|close) (?!(?:file|app|folder)\b)(.+)",
     lambda m,_: tools.close_window({"class":m.group(1).strip()}), False),

    # ── Open app / website / file ────────────────────────────────────────────
    (r"open (.+?) (?:in|on) workspace\s*(\d+)",
     lambda m,_: tools.open_app({"app":m.group(1).strip(),"workspace":int(m.group(2))}), False),
    # Explicit "open file X" / "open the file X" — always resolve a real path
    # first instead of blindly running xdg-open on whatever text follows.
    (r"(?:open|launch|show)\s+(?:a\s+|the\s+|my\s+)?file\s+(?:named\s+|called\s+)?(.+)",
     lambda m,_: tools.open_file({"path":m.group(1).strip()}), False),
    (r"(?:open|launch|show)\s+(?:a\s+|the\s+|my\s+)?folder\s+(?:named\s+|called\s+)?(.+)",
     lambda m,_: tools.open_folder({"path":m.group(1).strip()}), False),
    # "open <file/it> in/on/with <app>" — explicit app override, must come
    # before the plain catch-all so e.g. "open resume.pdf in vscode" and
    # "open it in visualstudiocode" resolve correctly instead of falling
    # through to smart_open/open_app with the whole phrase as one blob.

    # Website / URL phrasing — must come before the generic "open X in app"
    # pattern because that pattern captures "a website named google" as a
    # literal file path and then fails to find it on disk.
    (r"^open(?:ing)? (?:a )?(?:new )?tab(?: in| on| with)? (.+)",
     lambda m,_: tools.open_app({"app": m.group(1).strip()}), False),
    (r"^(?:open|launch|go to|visit|browse to|navigate to) (?:the )?(?:website|site|url|webpage|web page|page)\s+(?:named |called |at |of )?(.+?)(?:\s+in\s+(.+))?$",
     lambda m,_: (tools.open_in_app({"target": m.group(1).strip(), "app": m.group(2).strip()})
                  if m.group(2) else tools.open_app({"app": m.group(1).strip()})), False),
    (r"^(?:open|launch) (?:the )?(.+?)(?:\s+website|\s+site|\s+page|\s+url)(?:\s+in\s+(.+))?$",
     lambda m,_: (tools.open_in_app({"target": m.group(1).strip(), "app": m.group(2).strip()})
                  if m.group(2) else tools.open_app({"app": m.group(1).strip()})), False),
    (r"(?:open|launch|show)\s+(.+?)\s+(?:in|on|with)\s+(.+)",
     lambda m,_: tools.open_in_app({"target":m.group(1).strip(),"app":m.group(2).strip()}), False),
    # Picking from an ambiguous "which one?" listing — must come before the
    # generic "open X" catch-all below, or "open the second one" would be
    # treated as a brand-new open command instead of a selection.
    (r"(?:open|select|use|pick|choose)\s+(?:the\s+)?(?:number\s+)?#?(\d+)(?:st|nd|rd|th)?\s*(?:one)?\s*$",
     lambda m,_: tools.select_pending({"index": m.group(1)}), False),
    (r"(?:open|select|use|pick|choose)\s+the\s+(first|second|third|fourth|fifth|sixth|seventh|eighth|1st|2nd|3rd|4th|5th|6th|7th|8th)\s*(?:one)?\s*$",
     lambda m,_: tools.select_pending({"index": tools._ORDINAL_WORDS.get(m.group(1).lower())}), False),
    # "make youtube open (in a tab)" / "make it open in the browser" — a
    # common way people phrase "also open this site/app", easy to misparse
    # since it contains the word "open" mid-sentence. Must come before the
    # generic "open X" catch-all below, since that pattern's .search()
    # fallback would otherwise match "open in a tab" as its own bogus target.
    (r"make\s+(.+?)\s+open(?:\s+in\s+.+)?\s*$",
     lambda m,_: tools.smart_open({"target": m.group(1).strip()}), False),
    # Messier vague file requests in any word order — "open any one of the
    # image from sri folder", "from sri folder open a image" — as long as
    # both an open-verb and the literal word "folder" appear somewhere.
    # Must come BEFORE the simpler type-only patterns below: those match via
    # unanchored .search, so "from sri folder open a image" would otherwise
    # match "open a image" as a substring and silently discard the folder
    # context entirely.
    (r"(?=.*\b(?:open|show)\b)(?=.*\bfolder\b).+$",
     lambda m,_: tools.smart_open_vague({"text": m.group(0).strip()}), False),
    # Vague "open a png file"/"open the pdf" — no specific name given, just a
    # type. Must come before the generic catch-all, which would otherwise
    # xdg-open the literal words "a png file".
    (r"open\s+(?:a|an|the|my)\s+([a-zA-Z0-9]{2,5})\s+(?:file|image|photo|picture|document|video)s?\s*$",
     lambda m,_: tools.open_file_by_type({"ext": m.group(1).strip()}), False),
    (r"open\s+(?:a|an|any|some)\s+(image|images|photo|photos|picture|pictures|document|documents|video|videos)\s*$",
     lambda m,_: tools.open_file_by_type({"ext": m.group(1).strip()}), False),
    # Generic "open X" — smart_open decides app/website vs. an on-disk file
    # (e.g. "open firefox"/"open youtube" -> open_app, "open report.pdf" -> open_file).
    (r"^(?:open|launch|start) (.+)",
     lambda m,_: tools.smart_open({"target":m.group(1).strip()}), False),
    (r"(?:close|quit|exit)\s+(?:the\s+)?app\s+(.+)",
     lambda m,_: tools.close_app({"app":m.group(1).strip()}), False),
    (r"(?:close|quit|exit)\s+(?:the\s+)?file\s+(.+)",
     lambda m,_: tools.close_file({"path":m.group(1).strip()}), False),
    (r"(?:delete|remove|trash)\s+(?:the\s+)?file\s+(.+)",
     lambda m,cf: tools.delete_file({"path":m.group(1).strip()}, cf), True),
    (r"(?:edit|modify)\s+(?:the\s+)?file\s+(.+)",
     lambda m,_: tools.edit_file({"path":m.group(1).strip()}), False),
    (r"(?:make|chmod)\s+(?:the\s+)?(.+?)\s+executable$",
     lambda m,_: tools.make_executable({"path": m.group(1).strip()}), False),
    (r"chmod\s+\+x\s+(.+)",
     lambda m,_: tools.make_executable({"path": m.group(1).strip()}), False),
    (r"copy\s+(?:the\s+)?file\s+(.+?)\s+to\s+(.+)",
     lambda m,_: tools.copy_file({"path": m.group(1).strip(), "destination": m.group(2).strip()}), False),
    (r"move\s+(?:the\s+)?file\s+(.+?)\s+to\s+(.+)",
     lambda m,_: tools.move_file({"path": m.group(1).strip(), "destination": m.group(2).strip()}), False),
    (r"rename\s+(?:the\s+)?file\s+(.+?)\s+to\s+(.+)",
     lambda m,_: tools.rename_file({"path": m.group(1).strip(), "new_name": m.group(2).strip()}), False),
    # ── Create folder / file ──────────────────────────────────────────────────
    # Most specific first: "create a folder in X name/call it Y"
    (r"(?:create|make|mkdir)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:in|at|under)\s+(?:my\s+)?(\w+)\s+(?:and\s+)?(?:name|call|title)\s+(?:it|that|this)\s+(?:as\s+)?(.+)",
     lambda m,_: tools.create_folder({"location": m.group(1).strip(), "name": m.group(2).strip()}), False),
    # "create a folder named X in Y" / "create a folder X in Y"
    (r"(?:create|make|mkdir)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:named|called)\s+(.+?)\s+(?:in|at|under|inside)\s+(?:my\s+)?(\w+)",
     lambda m,_: tools.create_folder({"name": m.group(1).strip(), "location": m.group(2).strip()}), False),
    (r"(?:create|make|mkdir)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(.+?)\s+(?:in|at|under|inside)\s+(?:my\s+)?(\w+)",
     lambda m,_: tools.create_folder({"name": m.group(1).strip(), "location": m.group(2).strip()}), False),
    # "create a folder named X" / "create a folder and name it X"
    (r"(?:create|make|mkdir)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:named|called)\s+(.+)",
     lambda m,_: tools.create_folder({"name": m.group(1).strip()}), False),
    (r"(?:create|make|mkdir)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:and\s+)?(?:name|call|title)\s+(?:it|that|this)\s+(?:as\s+)?(.+?)\s+(?:in|at|under)\s+(?:my\s+)?(\w+)",
     lambda m,_: tools.create_folder({"name": m.group(1).strip(), "location": m.group(2).strip()}), False),
    (r"(?:create|make|mkdir)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:and\s+)?(?:name|call|title)\s+(?:it|that|this)\s+(?:as\s+)?(.+)",
     lambda m,_: tools.create_folder({"name": m.group(1).strip()}), False),
    (r"(?:create|make|mkdir)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(.+)",
     lambda m,_: tools.create_folder({"name": m.group(1).strip()}), False),
    (r"(?:create|make|touch)\s+(?:a\s+)?(?:new\s+)?file\s+(?:named|called)\s+(.+?)\s+(?:in|at|under)\s+(?:my\s+)?(\w+)",
     lambda m,_: tools.create_file({"name": m.group(1).strip(), "location": m.group(2).strip()}), False),
    (r"(?:create|make|touch)\s+(?:a\s+)?(?:new\s+)?file\s+(?:named|called)?\s*(.+)",
     lambda m,_: tools.create_file({"name": m.group(1).strip()}), False),
    # ── List / explore ────────────────────────────────────────────────────────
    (r"(?:list|show|ls)\s+(?:files?\s+)?(?:in|of|under|inside)\s+(?:my\s+)?(.+)",
     lambda m,_: tools.list_folder({"path": m.group(1).strip()}), False),
    (r"(?:list|show|ls)\s+(?:my\s+)?(.+?)(?:\s+folder|\s+directory|\s+dir)?\s*$",
     lambda m,_: tools.list_folder({"path": m.group(1).strip()}), False),
    (r"(?:what(?:'?s| is)\s+)?(?:in|inside)\s+(?:my\s+)?(\w+)(?:\s+folder)?",
     lambda m,_: tools.list_folder({"path": m.group(1).strip()}), False),
    (r"(?:disk|storage)\s+(?:usage|space|info)",
     lambda m,_: tools.disk_usage({}), False),
    (r"how much (?:disk |storage )?space",
     lambda m,_: tools.disk_usage({}), False),
    (r"find\s+(?:files?\s+)?(?:named\s+|matching\s+)?(.+?)\s+(?:in|under|inside)\s+(?:my\s+)?(.+)",
     lambda m,_: tools.find_files({"pattern": m.group(1).strip(), "location": m.group(2).strip()}), False),
    (r"find\s+(?:files?\s+)?(?:named\s+|matching\s+)?(.+)",
     lambda m,_: tools.find_files({"pattern": m.group(1).strip()}), False),
    (r"(?:file\s+)?(?:info|details|properties|size)\s+(?:of\s+)?(?:the\s+)?(?:file\s+)?(.+)",
     lambda m,_: tools.show_file_info({"path": m.group(1).strip()}), False),



    # ── Audio ─────────────────────────────────────────────────────────────────
    (r"(?:set |change )?volume(?: to)? (\d+)%?",
     lambda m,_: tools.audio_volume({"value":m.group(1)+"%"}), False),
    (r"volume (?:up|\+)(?: (\d+)%?)?",
     lambda m,_: tools.audio_volume({"value":f"+{m.group(1) or 10}%"}), False),
    (r"volume (?:down|-)(?:  (\d+)%?)?",
     lambda m,_: tools.audio_volume({"value":f"-{m.group(1) or 10}%"}), False),
    (r"(?:mute|unmute|toggle mute)(?: audio| sound| volume)?",
     lambda m,_: tools.audio_mute(), False),
    (r"(?:mute|unmute) mic(?:rophone)?",
     lambda m,_: tools.audio_mic_mute(), False),
    (r"(?:what(?:'s| is)(?: the)? volume|get volume|volume status)",
     lambda m,_: tools.audio_get_volume(), False),
    (r"(?:play|pause)(?: music| media)?$",
     lambda m,_: tools.audio_player({"action":"play-pause"}), False),
    (r"(?:next|skip)(?: song| track| media)?",
     lambda m,_: tools.audio_player({"action":"next"}), False),
    (r"(?:previous|prev|back)(?: song| track| media)?",
     lambda m,_: tools.audio_player({"action":"previous"}), False),
    (r"(?:stop)(?: music| media| player)?",
     lambda m,_: tools.audio_player({"action":"stop"}), False),
    (r"(?:what(?:'s| is) playing|audio status|media status)",
     lambda m,_: tools.audio_status(), False),

    # ── Brightness ────────────────────────────────────────────────────────────
    (r"(?:set |change )?brightness(?: to)? (\d+)%?",
     lambda m,_: tools.brightness_set({"value":m.group(1)+"%"}), False),
    (r"brightness (?:up|\+)(?: (\d+)%?)?",
     lambda m,_: tools.brightness_set({"value":f"+{m.group(1) or 10}%"}), False),
    (r"brightness (?:down|-)(?: (\d+)%?)?",
     lambda m,_: tools.brightness_set({"value":f"-{m.group(1) or 10}%"}), False),

    # ── Screenshot ────────────────────────────────────────────────────────────
    (r"(?:take(?: a)?|capture) (?:full )?screenshot",
     lambda m,_: tools.screenshot({"mode":"full"}), False),
    (r"(?:take(?: a)?|capture) (?:region|area|selection) screenshot",
     lambda m,_: tools.screenshot({"mode":"region"}), False),
    (r"screenshot",
     lambda m,_: tools.screenshot({"mode":"full"}), False),

    # ── System ────────────────────────────────────────────────────────────────
    (r"(?:system|resource|hardware) (?:info|status|usage|stats?)",
     lambda m,_: tools.system_info(), False),
    (r"(?:what(?:'s| is)(?: my)? (?:cpu|ram|memory|disk|temperature|temp|network|wifi))",
     lambda m,_: tools.system_info(), False),
    (r"(?:list|show)(?: running)? processes?",
     lambda m,_: tools.process_list(), False),
    (r"(?:list|show) processes? (?:for|matching|with) (.+)",
     lambda m,_: tools.process_list({"filter":m.group(1).strip()}), False),
    (r"(?:kill|end)(?: process)? (.+)",
     lambda m,_: tools.process_kill({"name":m.group(1).strip()}), False),
    (r"network (?:info|status|ip)",
     lambda m,_: tools.network_info(), False),

    # ── Wallpaper ─────────────────────────────────────────────────────────────
    (r"(?:set |change )?(?:my )?wallpaper(?: to)? (.+\.(?:png|jpg|jpeg|webp|gif))",
     lambda m,_: tools.wallpaper_set({"path":m.group(1).strip()}), False),
    (r"(?:set |change |update )(?:my )?wallpaper(?: to)? (.+)",
     lambda m,_: tools.wallpaper_set({"path":m.group(1).strip()}), False),
    (r"(?:can\s+(?:u|you)\s+)?(?:random|shuffle|change)\s+(?:my\s+)?wallpaper",
     lambda m,_: tools.wallpaper_random(), False),
    (r"(?:can\s+(?:u|you)\s+)?(?:set|change|update)\s+(?:my\s+)?wallpaper",
     lambda m,_: tools.wallpaper_select(), False),
    (r"(?:pick|choose|select)\s+(?:a\s+)?(?:new\s+)?wallpaper",
     lambda m,_: tools.wallpaper_select(), False),

    # ── Session / display ─────────────────────────────────────────────────────
    (r"(?:enable|turn on|activate) night(?: mode| light)?",
     lambda m,_: tools.night_mode({"action":"on"}), False),
    (r"(?:disable|turn off) night(?: mode| light)?",
     lambda m,_: tools.night_mode({"action":"off"}), False),
    (r"(?:toggle) night(?: mode| light)?",
     lambda m,_: tools.night_mode({"action":"toggle"}), False),
    (r"(?:lock|lock screen|lock the screen)",
     lambda m,_: tools.lock_screen(), False),
    (r"(?:logout|log out|logoff|wlogout)",
     lambda m,_: tools.logout(), False),

    # ── Power ─────────────────────────────────────────────────────────────────
    (r"(?:shut ?down|power off|turn off)(?: the)?(?: computer| system| pc| laptop)?",
     lambda m,cf: tools.power_shutdown(None, cf), True),
    (r"(?:reboot|restart)(?: the)?(?: computer| system| pc| laptop)?",
     lambda m,cf: tools.power_reboot(None, cf), True),
    (r"(?:suspend|sleep)(?: the)?(?: computer| system| pc| laptop)?",
     lambda m,_: tools.power_suspend(), False),
    (r"hibernate(?: the)?(?: computer| system| pc| laptop)?",
     lambda m,cf: tools.power_hibernate(None, cf), True),
    (r"(?:battery|battery status|battery level|how much battery)",
     lambda m,_: tools.battery_status(), False),

    # ── Bluetooth ─────────────────────────────────────────────────────────────
    (r"(?:turn on|enable) bluetooth",
     lambda m,_: tools.bluetooth_toggle({"on": True}), False),
    (r"(?:turn off|disable) bluetooth",
     lambda m,_: tools.bluetooth_toggle({"on": False}), False),
    (r"(?:toggle) bluetooth",
     lambda m,_: tools.bluetooth_toggle({}), False),
    (r"(?:list|show) bluetooth devices",
     lambda m,_: tools.bluetooth_list(), False),
    (r"connect(?: to)? bluetooth (?:device )?(.+)",
     lambda m,_: tools.bluetooth_connect({"device": m.group(1).strip()}), False),
    (r"disconnect(?: bluetooth)?(?: device)? ?(.*)",
     lambda m,_: tools.bluetooth_disconnect({"device": m.group(1).strip()}), False),

    # ── WiFi ──────────────────────────────────────────────────────────────────
    (r"(?:turn on|enable) wifi",
     lambda m,_: tools.wifi_toggle({"on": True}), False),
    (r"(?:turn off|disable) wifi",
     lambda m,_: tools.wifi_toggle({"on": False}), False),
    (r"(?:toggle) wifi",
     lambda m,_: tools.wifi_toggle({}), False),
    (r"(?:list|show|scan for) wifi(?: networks)?",
     lambda m,_: tools.wifi_list(), False),
    (r"connect(?: to)? wifi (.+)",
     lambda m,_: tools.wifi_connect({"ssid": m.group(1).strip()}), False),

    # ── Clipboard ─────────────────────────────────────────────────────────────
    (r"copy (?:this |the following )?(?:to (?:the )?clipboard:?\s*)?(.+)",
     lambda m,_: tools.clipboard_set({"text": m.group(1).strip()}), False),
    (r"(?:what'?s|show|read|paste)(?: is)?(?: in)?(?: the)? clipboard",
     lambda m,_: tools.clipboard_get(), False),
    (r"clipboard history",
     lambda m,_: tools.clipboard_history(), False),

    # ── Notifications ─────────────────────────────────────────────────────────
    (r"(?:clear|dismiss|close)(?: all)? notifications?",
     lambda m,_: tools.notify_clear(), False),

    # ── Screen recording ──────────────────────────────────────────────────────
    (r"(?:start|begin) (?:screen )?record(?:ing)?",
     lambda m,_: tools.screen_record_start({}), False),
    (r"(?:stop|end) (?:screen )?record(?:ing)?",
     lambda m,_: tools.screen_record_stop(), False),


    # -- User preferences / memory ------------------------------------------------
    (r"(?:my name is|call me|i am|i\'m)\s+(.+)",
     lambda m,_: tools.prefs_set_name({"name": m.group(1).strip()}), False),
    (r"remember (?:that )?(.+)",
     lambda m,_: tools.prefs_note({"note": m.group(1).strip()}), False),
    (r"(?:what do you|what have you) remember",
     lambda m,_: tools.prefs_list_notes(), False),
    (r"(?:my|set my) (?:preferred )?browser (?:is |to )?(.+)",
     lambda m,_: tools.prefs_set({"key":"preferred_browser","value":m.group(1).strip()}), False),
    (r"(?:my|set my) (?:preferred )?editor (?:is |to )?(.+)",
     lambda m,_: tools.prefs_set({"key":"preferred_editor","value":m.group(1).strip()}), False),
    (r"(?:my|set my) (?:preferred )?terminal (?:is |to )?(.+)",
     lambda m,_: tools.prefs_set({"key":"preferred_terminal","value":m.group(1).strip()}), False),


    # "go to <site/app>" — common in compound sentences like
    # "launch firefox and go to youtube"
    (r"^go to (?:the )?(?:website )?(.+)",
     lambda m,_: tools.smart_open({"target": m.group(1).strip()}), False),
    (r"^navigate to (?:the )?(.+)",
     lambda m,_: tools.smart_open({"target": m.group(1).strip()}), False),
    (r"^visit (?:the )?(.+)",
     lambda m,_: tools.smart_open({"target": m.group(1).strip()}), False),

    # -- System status ------------------------------------------------------------
    (r"(?:system status|system info(?:rmation)?|how(?:\'?s| is) (?:my )?system|machine status|what\'?s? running)",
     lambda m,_: tools.system_status(), False),
    (r"(?:quick )?(?:resource|cpu|ram|memory) (?:usage|info|status)",
     lambda m,_: tools.system_info_brief(), False),
    (r"what(?:\'?s| is) (?:my )?(?:cpu|ram|memory|load|temperature)(?: usage| level)?",
     lambda m,_: tools.system_info_brief(), False),
    (r"(?:list|show) (?:running |failed |all )?(?:services?|systemd units?)",
     lambda m,_: tools.service_list({"filter":"running" if "running" in m.group(0) else "failed"}), False),

    # -- Package management -------------------------------------------------------
    (r"(?:install|add) (?:the )?package\s+(.+)",
     lambda m,_: tools.pkg_install({"package": m.group(1).strip()}), False),
    (r"(?:uninstall|remove) (?:the )?package\s+(.+)",
     lambda m,cf: tools.pkg_remove({"package": m.group(1).strip()}, cf), True),
    (r"(?:search|find) (?:for )?package\s+(.+)",
     lambda m,_: tools.pkg_search({"query": m.group(1).strip()}), False),
    (r"(?:update|upgrade) (?:system|all packages?|packages?)(?: now)?",
     lambda m,cf: tools.pkg_update(None, cf), True),
    (r"what packages? (?:do I |are )?installed(?:\s+matching)?\s*(.*)",
     lambda m,_: tools.pkg_list_installed({"query": m.group(1).strip()}), False),

    # -- Systemd services ---------------------------------------------------------
    (r"(?:service|systemctl) status\s+(.+)",
     lambda m,_: tools.service_status({"service": m.group(1).strip()}), False),
    (r"start (?:the )?service\s+(.+)",
     lambda m,_: tools.service_start({"service": m.group(1).strip()}), False),
    (r"stop (?:the )?service\s+(.+)",
     lambda m,cf: tools.service_stop({"service": m.group(1).strip()}, cf), True),
    (r"restart (?:the )?service\s+(.+)",
     lambda m,_: tools.service_restart({"service": m.group(1).strip()}), False),
    (r"enable (?:the )?service\s+(.+)",
     lambda m,_: tools.service_enable({"service": m.group(1).strip()}), False),
    (r"disable (?:the )?service\s+(.+)",
     lambda m,cf: tools.service_disable({"service": m.group(1).strip()}, cf), True),

    # ── Presets ───────────────────────────────────────────────────────────────
    (r"(?:make|set|apply|switch to)(?: my)?(?: desktop| setup| theme)? minimal",
     lambda m,_: tools.apply_preset({"preset":"minimal"}), False),
    (r"(?:gaming(?: mode| setup)?|game mode)",
     lambda m,_: tools.apply_preset({"preset":"gaming"}), False),
    (r"(?:make|set|apply).+(?:mac ?os|apple|macos)",
     lambda m,_: tools.apply_preset({"preset":"macos"}), False),
    (r"(?:futuristic|cyber|sci.?fi)(?: mode| theme| setup)?",
     lambda m,_: tools.apply_preset({"preset":"futuristic"}), False),
    (r"(?:focus(?: mode)?|productivity mode|work mode)",
     lambda m,_: tools.apply_preset({"preset":"focus"}), False),
    (r"(?:battery|power saving|power saver)(?: mode)?",
     lambda m,_: tools.apply_preset({"preset":"battery"}), False),
    (r"(?:programming|coding|developer)(?: mode| setup)?",
     lambda m,_: tools.apply_preset({"preset":"programming"}), False),

    # ── Hyprland config ───────────────────────────────────────────────────────
    (r"(?:set |change )?rounding(?: to)? (\d+)",
     lambda m,_: tools.hypr_set_value({"section":"decoration","key":"rounding","value":m.group(1)}), False),
    (r"(?:set )?gaps?[_ ]in(?: to)? (\d+)",
     lambda m,_: tools.hypr_set_value({"section":"general","key":"gaps_in","value":m.group(1),"file":"decorations"}), False),
    (r"(?:set )?gaps?[_ ]out(?: to)? (\d+)",
     lambda m,_: tools.hypr_set_value({"section":"general","key":"gaps_out","value":m.group(1),"file":"decorations"}), False),
    (r"(?:set )?border(?: size)?(?: to)? (\d+)",
     lambda m,_: tools.hypr_set_value({"section":"general","key":"border_size","value":m.group(1),"file":"decorations"}), False),
    (r"(?:set )?(?:active )?opacity(?: to)? ([0-9.]+)",
     lambda m,_: tools.hypr_set_value({"section":"decoration","key":"active_opacity","value":m.group(1),"file":"decorations"}), False),
    (r"(?:set )?inactive opacity(?: to)? ([0-9.]+)",
     lambda m,_: tools.hypr_set_value({"section":"decoration","key":"inactive_opacity","value":m.group(1),"file":"decorations"}), False),
    (r"(?:enable|turn on) blur",
     lambda m,_: tools.hypr_set_blur({"enabled":True}), False),
    (r"(?:disable|turn off) blur",
     lambda m,_: tools.hypr_set_blur({"enabled":False}), False),
    (r"(?:set )?blur[_ ]size(?: to)? (\d+)",
     lambda m,_: tools.hypr_set_blur({"size":int(m.group(1))}), False),
    (r"(?:set )?blur[_ ]passes?(?: to)? (\d+)",
     lambda m,_: tools.hypr_set_blur({"passes":int(m.group(1))}), False),
    (r"(?:enable|turn on) shadow",
     lambda m,_: tools.hypr_set_shadow({"enabled":True}), False),
    (r"(?:disable|turn off) shadow",
     lambda m,_: tools.hypr_set_shadow({"enabled":False}), False),
    (r"(?:set )?shadow[_ ]range(?: to)? (\d+)",
     lambda m,_: tools.hypr_set_shadow({"range":int(m.group(1))}), False),
    (r"(?:enable|turn on) dim",
     lambda m,_: tools.hypr_set_value({"section":"decoration","key":"dim_inactive","value":"true","file":"decorations"}), False),
    (r"(?:disable|turn off) dim",
     lambda m,_: tools.hypr_set_value({"section":"decoration","key":"dim_inactive","value":"false","file":"decorations"}), False),
    (r"(?:set )?dim[_ ]strength(?: to)? ([0-9.]+)",
     lambda m,_: tools.hypr_set_value({"section":"decoration","key":"dim_strength","value":m.group(1),"file":"decorations"}), False),
    (r"(?:switch|set|change)(?: layout)? to dwindle",
     lambda m,_: tools.hypr_set_value({"section":"general","key":"layout","value":"dwindle","file":"system"}), False),
    (r"(?:switch|set|change)(?: layout)? to master",
     lambda m,_: tools.hypr_set_value({"section":"general","key":"layout","value":"master","file":"system"}), False),
    (r"(?:disable|turn off) animations?",
     lambda m,_: tools.hypr_set_value({"section":"animations","key":"enabled","value":"no","file":"animations"}), False),
    (r"(?:enable|turn on) animations?",
     lambda m,_: tools.hypr_set_value({"section":"animations","key":"enabled","value":"yes","file":"animations"}), False),
    (r"(?:toggle|change) blur",
     lambda m,_: tools.hypr_run_script({"name":"ChangeBlur"}), False),
    (r"(?:toggle|change) layout",
     lambda m,_: tools.hypr_run_script({"name":"ChangeLayout"}), False),
    (r"(?:toggle|enable|disable) game ?mode",
     lambda m,_: tools.hypr_run_script({"name":"GameMode"}), False),
    (r"(?:show|list)(?: all)? keybinds?",
     lambda m,_: tools.hypr_list_keybinds(), False),
    (r"(?:list|show) (?:animation )?presets?",
     lambda m,_: tools.hypr_list_animations(), False),
    (r"(?:switch|change|use) animation(?: preset)? (?:to )?(.+)",
     lambda m,_: tools.hypr_switch_animation({"preset":m.group(1).strip()}), False),
    (r"(?:run|launch) script (.+)",
     lambda m,_: tools.hypr_run_script({"name":m.group(1).strip()}), False),
    (r"list scripts",
     lambda m,_: tools.hypr_list_scripts(), False),
    (r"(?:show|read|what(?:'s| is)(?: my)?) (decorations?|animations?|keybinds?|settings?|system|env|rules?|startup|monitors?|defaults?|workspaces?)(?: config)?",
     lambda m,_: tools.hypr_read_config({"what":m.group(1).rstrip("s")}), False),
    (r"(?:show|get) live (?:values?|settings?)",
     lambda m,_: tools.hypr_live_values(), False),
    (r"reload(?: hyprland| config)?",
     lambda m,_: tools.hypr_reload(), False),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), h, nc) for p, h, nc in RULES]

# Verbs that mark the start of a new sub-command when splitting a compound
# sentence like "open firefox and open youtube in it". Only clauses that
# start with (or inherit) one of these get treated as separate commands —
# anything else is left alone and falls through to the LLM as before.
_ACTION_VERBS = (
    "open", "close", "launch", "start", "kill", "delete", "remove", "trash", "go",
    "edit", "modify", "mute", "unmute", "play", "pause", "stop", "lock",
    "screenshot", "take", "quit", "exit", "make", "chmod", "select", "pick",
    "use", "choose",
)
_CONNECTOR_RE = re.compile(r"\s+and then\s+|\s+then\s+|\s+and\s+", re.IGNORECASE)


def _split_compound(t):
    """
    Split "open firefox and open youtube in it" into ["open firefox",
    "open youtube in it"]. Returns None (don't split) unless every resulting
    clause clearly starts with — or can inherit — a recognized action verb,
    so ambiguous sentences ("cats and dogs") are left untouched.
    """
    parts = [p.strip() for p in _CONNECTOR_RE.split(t) if p.strip()]
    if len(parts) <= 1:
        return None
    out, last_verb = [], None
    for p in parts:
        words = p.split()
        first = words[0].lower() if words else ""
        if first in _ACTION_VERBS:
            last_verb = first
            out.append(p)
        elif last_verb:
            out.append(f"{last_verb} {p}")
        else:
            return None
    return out


def _match_single(t, confirm_fn):
    for pattern, handler, needs_confirm in _COMPILED:
        m = pattern.fullmatch(t) or pattern.search(t)
        if m:
            try:
                return handler(m, confirm_fn if needs_confirm else None), True
            except Exception as e:
                return f"Error: {e}", True
    return "", False


_CASUAL_PREFIX_RE = re.compile(
    r"^(?:hey\s+)?jarvis[,\s]+|"
    r"^(?:can|could|would)\s+(?:you|u)\s+(?:please\s+)?|"
    r"^(?:please|pls)\s+|"
    r"^(?:i\s+want\s+you\s+to|i\s+need\s+you\s+to)\s+",
    re.IGNORECASE,
)

def match(text, confirm_fn):
    t = text.strip()
    prev = None
    while prev != t:
        prev = t
        t = _CASUAL_PREFIX_RE.sub("", t).strip()

    clauses = _split_compound(t)
    if clauses:
        replies, any_matched = [], False
        for clause in clauses:
            r, matched = _match_single(clause, confirm_fn)
            if matched:
                any_matched = True
                replies.append(r or "Done.")
        if any_matched:
            return " | ".join(replies), True
        # nothing in the split actually matched anything real -> treat as a
        # single string instead and let it fall through to the LLM normally

    return _match_single(t, confirm_fn)
