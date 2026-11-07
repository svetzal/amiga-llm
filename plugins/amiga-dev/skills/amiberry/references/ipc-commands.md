# Amiberry control socket commands

The reply to `HELP` from Amiberry 8.5.0 (2026.10.27) on macOS, one entry per line
as Amiberry printed it. The socket sends fields separated by tabs; they are
shown here as lines. "Verified" in SKILL.md marks the commands actually tried.

```text
QUIT, PAUSE, RESUME, RESET [HARD|SOFT]
SCREENSHOT <path>, SAVESTATE <state> <cfg>, LOADSTATE <state>
QUICKSAVE [slot], QUICKLOAD [slot] (slots 0-9)
INSERTFLOPPY <path> <drive>, EJECT_FLOPPY <drive>, LIST_FLOPPIES
SET_FLOPPY_SPEED <speed>, GET_FLOPPY_SPEED
DISK_WRITE_PROTECT <drive> <0|1>, GET_DISK_WRITE_PROTECT <drive>
INSERTCD <path>, EJECT_CD
LIST_HARDDRIVES
DISKSWAP <disknum> <drive>, QUERYDISKSWAP <drive>
GET_STATUS, GET_CONFIG <opt>, SET_CONFIG <opt> <val>
LOAD_CONFIG <path>, SAVE_CONFIG <path>, LIST_CONFIGS
HOST_SETTINGS_LIST, HOST_SETTINGS_GET <id>, HOST_SETTINGS_SET <id> <value>, HOST_SETTINGS_SAVE
LIST_MEDIA <list>, GET_FOLDER <folder>, SET_FOLDER <folder> <path>
SET_VOLUME <0-100>, GET_VOLUME, MUTE, UNMUTE
SET_WARP <0|1>, GET_WARP, TOGGLE_FULLSCREEN, OPEN_SETTINGS
CHOOSE_MEDIA <DF0-DF3|LOADSTATE|SAVESTATE|CD> (a system file dialog holds IPC until answered)
SET_DISPLAY_MODE <0-2>, GET_DISPLAY_MODE, TOGGLE_RTG
SET_NTSC <0|1>, GET_NTSC, TOGGLE_STATUS_LINE
SET_SOUND_MODE <0-3>, GET_SOUND_MODE
SET_CHIPSET <OCS|ECS|AGA>, GET_CHIPSET
SET_CPU_SPEED <speed>, GET_CPU_SPEED
GET_CPU_MODEL, SET_CPU_MODEL <68000-68060>
GET_MEMORY_CONFIG, GET_FPS
SET_CHIP_MEM <kb>, SET_FAST_MEM <kb>, SET_SLOW_MEM <kb>, SET_Z3_MEM <mb>
SET_WINDOW_SIZE <w> <h>, GET_WINDOW_SIZE
SET_SCALING <-1..2>, GET_SCALING
SET_LINE_MODE <0-2>, GET_LINE_MODE
SET_RESOLUTION <0-2>, GET_RESOLUTION
GET_JOYPORT_MODE <port>, SET_JOYPORT_MODE <port> <mode>
GET_AUTOFIRE <port>, SET_AUTOFIRE <port> <mode>
GET_LED_STATUS
FRAME_ADVANCE [n], SET_MOUSE_SPEED <10-200>, GET_MOUSE_SPEED
TOGGLE_MOUSE_GRAB
SEND_KEY <code> <state>, SEND_MOUSE <dx> <dy> <buttons>
SEND_MOUSE_ABS <x> <y> <buttons> (requires tablet_mode mousehack or real)
--- GUI automation controller commands (prefer MCP/HTTP) ---
SCREENSHOT <path> ACTIONABLE (SDL/OpenGL; unavailable on Vulkan)
GET_GUI_AUTOMATION_STATE
SET_GUI_AUTOMATION_CONFIG <expected_tablet_mode> <expected_mouse_untrap> <expected_input_config_revision> <tablet_mode> <mouse_untrap>
SEND_MOUSE_ABS_GUARDED <x> <y> <button_mask> <runtime_id> <geometry_revision> <monitor_id> <input_config_revision>
RELEASE_MOUSE_BUTTONS
READ_MEM <addr> <width>, WRITE_MEM <addr> <width> <val>
SET_AUTOCROP <0|1>, GET_AUTOCROP
INSERT_WHDLOAD <path>, EJECT_WHDLOAD, GET_WHDLOAD
--- Debugging Commands ---
DEBUG_ACTIVATE, DEBUG_DEACTIVATE, DEBUG_STATUS
DEBUG_STEP [count], DEBUG_STEP_OVER, DEBUG_CONTINUE
MONITOR <text> - GDB monitor command; lines returned as fields
GET_CPU_REGS, GET_CUSTOM_REGS
DISASSEMBLE <addr> [count] - disassemble instructions
SET_BREAKPOINT <addr>, CLEAR_BREAKPOINT <addr|ALL>, LIST_BREAKPOINTS
GET_COPPER_STATE, GET_BLITTER_STATE
GET_DRIVE_STATE [drive], GET_AUDIO_STATE, GET_DMA_STATE
GET_VERSION, PING, HELP
SETTINGS_GET <id>
SETTINGS_SET <id> <value>
SETTINGS_VALIDATE
SETTINGS_COMMIT
SETTINGS_RESET_SESSION
SETTINGS_GET_ACTIVE <id>
SETTINGS_LIST
SETTINGS_DESCRIBE <id>
SETTINGS_APPLY <live|reset|restart>
SETTINGS_MOUNTS
SETTINGS_MOUNT_ADD <uaehf value>
SETTINGS_MOUNT_REPLACE <index> <uaehf value>
SETTINGS_MOUNT_REMOVE <index>
SETTINGS_BOARDS
SETTINGS_BOARD_DESCRIBE <type> [field]
SETTINGS_BOARD_GET <type> <unit> <field>
SETTINGS_BOARD_SET <type> <unit> <field> <value>
SETTINGS_CUSTOM_CONTROLS
SETTINGS_INPUT_EVENTS
SETTINGS_CUSTOM_CONTROL_GET <port> <none|hotkey> <control>
SETTINGS_CUSTOM_CONTROL_SET <port> <none|hotkey> <control> <event>
```
