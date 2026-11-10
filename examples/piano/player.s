; player.s: EXP-004's piano player for the baseline A500.
;
; A 68000 on Kickstart 1.2 with OCS: plays recorded piano performances
; (score byte streams) through Paula's four voices with 8-bit samples,
; exactly as the host model in tools/amiga_env/piano/player.py does, so
; that the two voice logs can be compared byte for byte.
;
; Build it with `amiga-env piano-disk examples/piano/piano.toml`, which
; makes the data in runs/exp004/m68k/ (the tables, screen.i and keys.i)
; and assembles this file with that folder on the include path. `-DLOG=1`
; makes the test build, which also writes the voice log (see m68k.py).
;
; The program holds the samples (in chip RAM) and the tables. The rest are
; files on the disk, read with dos.library from the current directory,
; which is the disk's root when it boots: title.ilbm (the screen),
; scores/index (one line a piece, in list order: the score's file name, a
; space and its title) and the scores, each loaded when it is chosen.
;
; Usage from a CLI or the startup-sequence:
;   piano            the screen: a 320x200 16-colour NTSC screen showing the
;                    title picture with the song list drawn in (screen.py).
;                    A click on a piece's line, or its key (1 to 9, then
;                    A to Z without F and Q), plays it, or switches to it
;                    while another plays. Left alone, it plays the pieces
;                    in turn (choose, below). Space stops; F switches the
;                    audio filter (and the power LED, and the screen's
;                    filter light), which is off at the start; Esc or Q
;                    quits, putting the filter back as it was.
;   piano 3 1        plays pieces 3 and 1 (their keys), then ends; no screen
;
; The screen is an Intuition custom screen with a borderless backdrop
; window over it for the mouse and the keys (IDCMP MOUSEBUTTONS and
; RAWKEY). The picture is an uncompressed IFF ILBM, copied into the
; screen's planes. The playing piece's line turns gold: a user copper list
; on the screen's viewport changes colour 13 on that line's rows. Five
; scopes in the floor band show the voices and their mix; the task draws
; them after each vertical blank from the player's own state, since Paula's
; registers cannot be read.
;
; How a piece plays. The program takes CIA-B timer A through ciab.resource
; as a 1 kHz interrupt and the four audio interrupt vectors with
; SetIntVector, and drives Paula directly. Every millisecond the CIA
; interrupt steps the fades, reads the score's events for that millisecond,
; and on a frame tick (tick k at k * 1000 // 60 ms) decays every voice. Each
; note starts Paula on the whole sample; the channel's audio interrupt,
; which Paula raises once it has taken the start and length, writes the
; loop's start and length so that Paula goes round the loop when the sample
; ends. Nothing the task does changes what the interrupts write.
;
; Status for the host, at the unused 68000 vectors from $100 (see STATUS).

        ifnd    LOG
LOG     equ     0
        endif

; exec.library (V33), from the NDK's exec_lib.fd
_LVOForbid          equ -132
_LVOPermit          equ -138
_LVOFreeMem         equ -210
_LVOAvailMem        equ -216
_LVOSetSignal       equ -306
_LVOSetIntVector    equ -162
_LVOAddIntServer    equ -168
_LVORemIntServer    equ -174
_LVOFindTask        equ -294
_LVOSignal          equ -324
_LVOAllocSignal     equ -330
_LVOFreeSignal      equ -336
_LVOAllocMem        equ -198
_LVOWait            equ -318
_LVOGetMsg          equ -372
_LVOReplyMsg        equ -378
_LVOCloseLibrary    equ -414
_LVOOpenResource    equ -498
_LVORawDoFmt        equ -522
_LVOTypeOfMem       equ -534
_LVOOpenLibrary     equ -552
; dos.library (V33), from dos_lib.fd
_LVOOpen            equ -30
_LVOClose           equ -36
_LVORead            equ -42
_LVOWrite           equ -48
_LVOOutput          equ -60
_LVOSeek            equ -66
_LVOLock            equ -84
_LVOUnLock          equ -90
_LVOExamine         equ -102
_LVODelay           equ -198
; graphics.library (V33), from graphics_lib.sfd
_LVOLoadRGB4        equ -192
_LVOWaitTOF         equ -270
_LVOCBump           equ -366
_LVOCMove           equ -372
_LVOCWait           equ -378
_LVOFreeCopList     equ -546
_LVOUCopperListInit equ -594
; intuition.library (V33), from intuition_lib.sfd
_LVOCloseScreen     equ -66
_LVOCloseWindow     equ -72
_LVOOpenScreen      equ -198
_LVOOpenWindow      equ -204
_LVOShowTitle       equ -288
_LVOMakeScreen      equ -384
_LVORethinkDisplay  equ -396
; ciab.resource (cia_lib.fd)
_LVOAddICRVector    equ -6
_LVORemICRVector    equ -12
_LVOAbleICR         equ -18

ExecBase        equ 4
VBlankFrequency equ 530         ; in ExecBase: 60 on NTSC, 50 on PAL
MEMF_PUBLIC     equ 1
MEMF_CHIP       equ 2
MEMF_CLEAR      equ $10000
NT_INTERRUPT    equ 2
INTB_VERTB      equ 5
INTB_AUD0       equ 7
CIAICRB_TA      equ 0
SIGBREAKF_CTRL_C equ $1000

MODE_OLDFILE    equ 1005
ACCESS_READ     equ -2
fib_Size        equ 124
OFFSET_BEGINNING equ -1
OFFSET_END      equ 1

; Intuition and graphics structures (offsets checked against the NDK 3.2
; includes with vasm; they are the same in V33)
sc_ViewPort     equ 44
sc_BitMap       equ 184
bm_BytesPerRow  equ 0
bm_Planes       equ 8
vp_UCopIns      equ 20
vp_DyOffset     equ 30
gb_ActiView     equ 34
v_DyOffset      equ 12
ucl_FirstCopList equ 4
ucl_SIZEOF      equ 12
wd_MouseY       equ 12
wd_MouseX       equ 14
wd_UserPort     equ 86
mp_SigBit       equ 15
im_Class        equ 20
im_Code         equ 24
im_MouseX       equ 32
im_MouseY       equ 34
CUSTOMSCREEN    equ $000f
SCREENQUIET     equ $0100
MOUSEBUTTONS    equ $00000008
RAWKEY          equ $00000400
SIMPLE_REFRESH  equ $00000040
BACKDROP        equ $00000100
BORDERLESS      equ $00000800
ACTIVATE        equ $00001000
RMBTRAP         equ $00010000
NOCAREREFRESH   equ $00020000
SELECTDOWN      equ $68
KEY_UP          equ $80             ; in a RAWKEY code
KEY_ESC         equ $45
KEY_Q           equ $10
KEY_SPACE       equ $40
KEY_F           equ $23

custom          equ $dff000
DMACON          equ $096
INTENA          equ $09a
INTREQ          equ $09c
AUD0LC          equ $0a0        ; then LEN +4, PER +6, VOL +8; channels $10 apart
COLOR13         equ custom+$19a
COLOR14         equ custom+$19c

ciaapra         equ $bfe001         ; bit 1: the power LED and the audio filter, 0 = on
LED_BIT         equ 1
ciabtalo        equ $bfd400
ciabtahi        equ $bfd500
ciabcra         equ $bfde00

; 716 E-clock ticks (715,909 Hz on NTSC) between interrupts: 1.000127 ms,
; which is exactly 3,580 cycles of Paula's 3,579,545 Hz clock.
TIMER_LATCH     equ 715
TIMER_PERIOD    equ TIMER_LATCH+1
PAULA_PER_MS    equ TIMER_PERIOD*5
VOICES          equ 4
FADE_MS         equ 5           ; as player.FADE_MS
LOG_BYTES       equ 362400      ; 15,100 ticks, 251 s: room for the scores beside it
MAX_PIECES      equ 33          ; 1-9 and A-Z without F and Q

; The screen and the scopes; screen.i (made with the picture) has the rows.
SCREEN_WIDTH    equ 320
SCREEN_HEIGHT   equ 200
DEPTH           equ 4
ROW_BYTES       equ SCREEN_WIDTH/8
PICTURE_BYTES   equ ROW_BYTES*SCREEN_HEIGHT*DEPTH
SCOPE_STEP      equ 960         ; Paula clocks a scope column: 3 samples at period 320
SCOPE_SHIFT     equ 7           ; a voice's trace: sample * volume >> 7,
VOICE_HALF      equ 16          ; at most this from the centre
MIX_HALF        equ 21          ; the mixed trace: half the voices' sum, at most this
BEAM_GUARD      equ 64          ; lines above the band a unit may not start on

        include "screen.i"      ; LIST_*, LINE_*, colours, SCOPE_*, line_tops
        include "light.i"       ; FILTER_LIGHT_*: the filter light's rows and colours
BAND_BYTES      equ ROW_BYTES*SCOPE_ROWS
; The light is in the voice traces' register; the copper list changes it on
; the light's rows only, so no voice trace may reach them.
        if      SCOPE_CENTRE+VOICE_HALF>=FILTER_LIGHT_TOP
        fail    "the voice traces would reach the filter light's rows"
        endif
; The mixed scope is drawn in two units split at a byte, so no two units
; share a byte of the screen (screen.py checks the voice scopes).
MIX_SPLIT       equ ((((MIX_SCOPE_LEFT+64)/8)*8)-MIX_SCOPE_LEFT)

; Status block, read by the host through the emulator's memory.
STATUS          equ $100
ST_MAGIC        equ 0           ; 'PIAN'
ST_STATE        equ 4           ; 0 starting, 1 playing, 2 ended, 3 waiting for a choice, -1 failed
ST_LOGBASE      equ 8
ST_LOGBYTES     equ 12
ST_SAMPLES      equ 16          ; where the samples are in chip RAM
ST_COPIED       equ 20          ; 0: LoadSeg put the chip hunk in chip RAM; 1: copied
ST_TOTAL_E      equ 24          ; E-clock ticks spent in the player's interrupts
ST_MS           equ 28          ; milliseconds played
ST_MAX_FRAME_E  equ 32          ; most E-clock ticks in one frame (16 or 17 ms)
ST_FRAMES       equ 36
ST_MAX_MS_E     equ 40          ; most in one millisecond's interrupt
ST_PIECE        equ 44          ; the piece playing or last played, from 0 in list order
ST_ENTRY_E      equ 48          ; E-clock ticks from the timer running out to the handler
ST_PLAYED       equ 52          ; pieces played to their end or stopped
ST_STOPPED      equ 56          ; 1 when the last piece was stopped (a choice or a quit)
ST_PIECES       equ 60          ; pieces in the index
ST_SCORE        equ 64          ; where the score is
ST_SCORE_BYTES  equ 68
ST_CHIP_FREE    equ 72          ; AvailMem while the score is loaded: chip RAM
ST_OTHER_FREE   equ 76          ; and all other memory
ST_KEY          equ 80          ; the last RAWKEY code
ST_KEYS         equ 84          ; RAWKEY messages
ST_WINDOW       equ 88          ; the backdrop window, 0 without the screen
ST_CLICKS       equ 92          ; left button presses
ST_CLICK_XY     equ 96          ; the last one: x in the high word, y in the low
ST_SCOPE_FRAMES equ 100         ; scope frames drawn in this piece
ST_SCOPE_E      equ 104         ; E-clock ticks drawing them, less the interrupts' time
ST_SCOPE_MAX_E  equ 108         ; the most for one scope frame
ST_HIGHLIGHT    equ 112         ; the line in gold, -1 for none
ST_SCREEN_CHIP  equ 116         ; chip RAM free with the screen open, before a piece
ST_DRAW_E       equ 120         ; E-clock ticks taking back and plotting points (after ST_SCOPE_E's)
ST_DRAW_MAX_E   equ 124         ; the most for one frame
; Times are vertical blanks counted from the start of the program (ST_VBLANKS).
ST_VBLANKS      equ 128         ; vertical blanks since the program started
ST_VBLANK_HZ    equ 132         ; their rate
ST_SCREEN_AT    equ 136         ; when the screen was up and taking choices
ST_CHOSEN_AT    equ 140         ; when the task took the last choice
ST_ENDED_AT     equ 144         ; when the last piece was ended and given back
ST_LOADED_AT    equ 148         ; when the chosen piece's score was ready
ST_GOLD_AT      equ 152         ; when its line was gold
ST_PLAYING_AT   equ 156         ; when its timer started: its millisecond 0
ST_FIRST_NOTE_AT equ 160        ; when its first note started
ST_FIRST_NOTE_MS equ 164        ; and the piece's millisecond for that note
ST_STARTS       equ 168         ; pieces started
ST_ROTATED      equ 172         ; of those, started by the rotation
ST_NEXT         equ 176         ; the piece the rotation plays next, from 0
ST_ROTATE_AT    equ 180         ; when it will, -1 when it waits for a choice
ST_PRELOAD_FRAMES equ 184       ; vertical blanks loading every score at the start
ST_SCORES_BYTES equ 188         ; their bytes
ST_FILTER_KEYS  equ 192         ; presses of F, each switching the audio filter
ST_END          equ 196
ST_PER_PIECE    equ ST_TOTAL_E  ; cleared before each piece, to ST_PLAYED

; A voice
V_KEY           equ 0           ; 0-87, -1 when silent
V_SAMPLE        equ 2           ; -1 when silent
V_PERIOD        equ 4
V_VOLUME        equ 6           ; 8.8
V_SERIAL        equ 8           ; the note's number among the note ons, from 1
V_KEYDN         equ 10
V_TICKS         equ 12          ; ticks since the note started
V_OUT           equ 14          ; Paula volume register
V_FADE          equ 16          ; ms until the waiting note starts, 0 when none waits
V_FROM          equ 18          ; Paula volume when the fade began
V_PSAMPLE       equ 20          ; what Paula plays, for the scopes: sample, -1 for none
V_PPERIOD       equ 22          ; its period
V_PSTART        equ 24          ; the millisecond it started
V_SIZE          equ 28

; Key table (keys.bin), 12 bytes a key
K_SAMPLE        equ 0
K_PERIOD        equ 2
K_LEVEL         equ 4
K_HELD          equ 6
K_RELEASE       equ 8
K_ATTACK        equ 10
K_SIZE          equ 12

; Sample table (samples.tab), 12 bytes a sample
S_OFFSET        equ 0
S_WORDS         equ 4
S_LOOP          equ 6
S_LOOPWORDS     equ 10
S_SIZE          equ 12

; A voice as the scopes take it, copied with interrupts off
C_SAMPLE        equ 0
C_PERIOD        equ 2
C_OUT           equ 4
C_ELAPSED       equ 6           ; ms since it started, at most 65,535
C_SIZE          equ 8

; Interrupt structure
IS_SIZE         equ 22

CALLGFX macro
        move.l  gfxbase,a6
        jsr     _LVO\1(a6)
        move.l  ExecBase.w,a6
        endm

CALLINT macro
        move.l  intbase,a6
        jsr     _LVO\1(a6)
        move.l  ExecBase.w,a6
        endm

        section code,code

start:
        lea     bss_start,a1            ; every variable starts at 0
        move.w  #(bss_end-bss_start)/2-1,d1
.zero:  clr.w   (a1)+
        dbf     d1,.zero
        move.l  a0,args
        move.l  d0,args_len
        move.l  ExecBase.w,a6
        lea     STATUS+ST_STATE.w,a0
        moveq   #(ST_END-ST_STATE)/4-1,d0
.clear: clr.l   (a0)+
        dbf     d0,.clear
        move.l  #-1,STATUS+ST_HIGHLIGHT.w
        move.l  #'PIAN',STATUS+ST_MAGIC.w
        move.b  ciaapra,d0              ; the filter as it was, for the end
        and.b   #1<<LED_BIT,d0
        move.b  d0,led_start
        bset    #LED_BIT,ciaapra        ; then off: the piano starts unfiltered

        lea     dosname(pc),a1
        moveq   #0,d0
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,dosbase
        beq     failed
        bsr     start_clock
        tst.l   d0
        beq     failed

        bsr     samples_to_chip
        tst.l   d0
        beq     no_memory
        if      LOG
        move.l  #LOG_BYTES,d0
        moveq   #MEMF_PUBLIC,d1
        jsr     _LVOAllocMem(a6)
        tst.l   d0
        beq     no_memory
        move.l  d0,STATUS+ST_LOGBASE.w
        endif
        bsr     read_index
        tst.l   d0
        beq     failed
        bsr     load_scores

        lea     banner(pc),a0
        lea     fmt_args,a1
        move.l  pieces,(a1)
        move.l  #samples_end-samples,4(a1)
        move.l  samples_base,8(a1)
        lea     loaded(pc),a2
        tst.l   STATUS+ST_COPIED.w
        beq.s   .how
        lea     copied(pc),a2
.how:   move.l  a2,12(a1)
        bsr     print

        bsr     next_argument
        bmi.s   .screen
        bsr     play_arguments
        bra.s   .ended
.screen:
        bsr     open_display
        tst.l   d0
        beq.s   failed
        bsr     choose
        bsr     close_display
.ended: move.l  #2,STATUS+ST_STATE.w
        bra.s   close

no_memory:
        lea     memory_text(pc),a0
        bsr     print
failed: move.l  #-1,STATUS+ST_STATE.w
        bsr     close_display
close:  bsr     restore_filter
        bsr     free_scores
        move.l  index_mem,d0
        beq.s   .log
        move.l  d0,a1
        move.l  index_bytes,d0
        addq.l  #1,d0
        jsr     _LVOFreeMem(a6)
.log:
        if      LOG
        move.l  STATUS+ST_LOGBASE.w,d0
        beq.s   .dos
        move.l  d0,a1
        move.l  #LOG_BYTES,d0
        jsr     _LVOFreeMem(a6)
.dos:
        endif
        bsr     stop_clock
        move.l  dosbase,d0
        beq.s   .out
        move.l  d0,a1
        jsr     _LVOCloseLibrary(a6)
.out:   moveq   #0,d0
        rts

; Put the filter back as it was when the program started.
restore_filter:
        move.b  ciaapra,d0
        move.b  led_start,d1
        eor.b   d1,d0
        btst    #LED_BIT,d0
        beq.s   .same
        bchg    #LED_BIT,ciaapra
.same:  rts

; The vertical blank count (ST_VBLANKS) and the alarm: a signal the
; vertical blank server sends the task when the count reaches alarm_at
; while alarm_on is set. d0: 0 when there is no signal for it.
start_clock:
        move.b  VBlankFrequency(a6),d0
        and.l   #$ff,d0
        move.l  d0,STATUS+ST_VBLANK_HZ.w
        sub.l   a1,a1
        jsr     _LVOFindTask(a6)
        move.l  d0,task
        moveq   #-1,d0
        jsr     _LVOAllocSignal(a6)
        move.b  d0,alarm_bit
        bmi.s   .none
        moveq   #0,d1
        bset    d0,d1
        move.l  d1,alarm_mask
        moveq   #INTB_VERTB,d0
        lea     vbint,a1
        jsr     _LVOAddIntServer(a6)
        move.w  #1,clock_on
        moveq   #1,d0
        rts
.none:  moveq   #0,d0
        rts

stop_clock:
        tst.w   clock_on
        beq.s   .signal
        moveq   #INTB_VERTB,d0
        lea     vbint,a1
        jsr     _LVORemIntServer(a6)
        clr.w   clock_on
.signal:
        move.b  alarm_bit,d0
        ble.s   .out                    ; none (or 0, which AllocSignal(-1) never gives)
        ext.w   d0
        ext.l   d0
        jsr     _LVOFreeSignal(a6)
        clr.b   alarm_bit
.out:   rts

; The vertical blank server: count, and signal the task at its alarm.
vb_handler:
        addq.l  #1,STATUS+ST_VBLANKS.w
        tst.w   alarm_on
        beq.s   .out
        move.l  STATUS+ST_VBLANKS.w,d0
        sub.l   alarm_at,d0
        bmi.s   .out
        clr.w   alarm_on
        move.l  task,a1
        move.l  alarm_mask,d0
        move.l  ExecBase.w,a6
        jsr     _LVOSignal(a6)
.out:   moveq   #0,d0                   ; the rest of the chain runs too
        rts

; ---------------------------------------------------------------------------
; The pieces: the index and the arguments.
; ---------------------------------------------------------------------------

; Load scores/index and split it into pieces: d0 is 0 when it cannot.
; Each line is a file name, a space and a title; the names and titles are
; ended with 0 in place, and their addresses go to files and titles.
read_index:
        lea     index_name(pc),a0
        bsr     load_file
        tst.l   d0
        bne.s   .parse
        lea     no_index_text(pc),a0
        bsr     print
        moveq   #0,d0
        rts
.parse: move.l  d0,index_mem
        move.l  d1,index_bytes
        move.l  d0,a0
        lea     files,a1
        lea     titles,a2
        moveq   #0,d1                   ; pieces
.line:  tst.b   (a0)
        beq.s   .done
        cmp.b   #10,(a0)
        bne.s   .entry
        addq.l  #1,a0                   ; an empty line
        bra.s   .line
.entry: cmp.w   #MAX_PIECES,d1
        beq.s   .done
        move.l  a0,(a1)+                ; the file
.name:  move.b  (a0)+,d0
        beq.s   .short
        cmp.b   #10,d0
        beq.s   .short
        cmp.b   #' ',d0
        bne.s   .name
        clr.b   -1(a0)
        move.l  a0,(a2)+                ; the title
.title: move.b  (a0)+,d0
        beq.s   .last
        cmp.b   #10,d0
        bne.s   .title
        clr.b   -1(a0)
        addq.w  #1,d1
        bra.s   .line
.last:  subq.l  #1,a0
        addq.w  #1,d1
        bra.s   .done
.short: subq.l  #4,a1                   ; a line with no title is left out
        tst.b   -1(a0)
        bne.s   .line
        subq.l  #1,a0
.done:  move.l  d1,pieces
        move.l  d1,STATUS+ST_PIECES.w
        moveq   #1,d0
        rts

; Load every piece's score now, so that a choice never waits for the
; floppy: score_table gets each one's memory and size (0 for a score that
; cannot be loaded; choosing it says so). AllocMem takes memory other than
; chip RAM first when the machine has some.
load_scores:
        movem.l d2-d3/a2,-(sp)
        move.l  STATUS+ST_VBLANKS.w,d3
        lea     score_table,a2
        moveq   #0,d2
.next:  cmp.l   pieces,d2
        beq.s   .done
        lea     files,a0
        move.l  d2,d0
        lsl.l   #2,d0
        move.l  0(a0,d0.l),a0
        bsr     load_file
        move.l  d0,(a2)+
        move.l  d1,(a2)+
        add.l   d1,STATUS+ST_SCORES_BYTES.w
        addq.l  #1,d2
        bra.s   .next
.done:  move.l  STATUS+ST_VBLANKS.w,d0
        sub.l   d3,d0
        move.l  d0,STATUS+ST_PRELOAD_FRAMES.w
        lea     fmt_args,a1
        move.l  STATUS+ST_SCORES_BYTES.w,(a1)
        move.l  d0,4(a1)
        lea     scores_text(pc),a0
        bsr     print
        movem.l (sp)+,d2-d3/a2
        rts

free_scores:
        movem.l d2/a2,-(sp)
        lea     score_table,a2
        moveq   #MAX_PIECES-1,d2
.next:  move.l  (a2),d0
        beq.s   .skip
        move.l  d0,a1
        move.l  4(a2),d0
        addq.l  #1,d0
        jsr     _LVOFreeMem(a6)
        clr.l   (a2)
.skip:  addq.l  #8,a2
        dbf     d2,.next
        movem.l (sp)+,d2/a2
        rts

; d0: the piece for the key character in d0 (from 0), negative for none.
piece_for_key:
        lea     menu_keys(pc),a0
        moveq   #0,d1
.find:  cmp.l   pieces,d1
        beq.s   .none
        cmp.b   (a0)+,d0
        beq.s   .found
        addq.l  #1,d1
        bra.s   .find
.found: move.l  d1,d0
        rts
.none:  moveq   #-1,d0
        rts

; The pieces named in the arguments, one key each, in order; d0 is the
; first key. No screen: the task waits with Delay.
play_arguments:
.piece: bsr     piece_for_key
        bmi.s   .next                   ; not a piece's key
        bsr     start_piece
        tst.l   d0
        bne.s   .next
.wait:  tst.w   finished
        bne.s   .end
        moveq   #0,d0
        moveq   #0,d1
        jsr     _LVOSetSignal(a6)
        and.l   #SIGBREAKF_CTRL_C,d0
        bne.s   .stop
        move.l  dosbase,a6
        moveq   #1,d1                   ; 1/50 s
        jsr     _LVODelay(a6)
        move.l  ExecBase.w,a6
        bra.s   .wait
.stop:  move.l  #1,STATUS+ST_STOPPED.w
.end:   moveq   #-1,d0
        bsr     end_piece
        bsr     flush_results
.next:  bsr     next_argument
        bpl.s   .piece
        rts

; d0: the next non-space character of the argument line, upper case for
; letters, negative at its end.
next_argument:
        move.l  args,a0
.skip:  subq.l  #1,args_len
        bmi.s   .end
        move.b  (a0)+,d0
        cmp.b   #' ',d0
        bls.s   .skip                   ; spaces, tabs and the line end
        move.l  a0,args
        and.l   #$ff,d0
        cmp.b   #'a',d0
        bcs.s   .out
        cmp.b   #'z',d0
        bhi.s   .out
        sub.b   #'a'-'A',d0
.out:   tst.l   d0
        rts
.end:   move.l  a0,args
        moveq   #-1,d0
        rts

; ---------------------------------------------------------------------------
; The screen: open it, show the picture, take choices, close it.
; ---------------------------------------------------------------------------

; Open graphics and Intuition, the screen and its window, and show the
; picture. d0: 0 when something is missing (and it has said what).
open_display:
        movem.l d2-d7/a2-a5,-(sp)
        lea     gfxname(pc),a1
        moveq   #0,d0
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,gfxbase
        beq     .fail
        lea     intname_lib(pc),a1
        moveq   #0,d0
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,intbase
        beq     .fail

        lea     picture_name(pc),a0     ; the picture, read before the screen opens
        bsr     load_file
        move.l  d0,picture_mem
        move.l  d1,picture_bytes
        bne.s   .parse
        lea     no_picture_text(pc),a0
        bra     .say
.parse: bsr     parse_ilbm
        tst.l   d0
        bne.s   .tables
        lea     bad_picture_text(pc),a0
        bra     .say

.tables:
        move.l  #BAND_BYTES*DEPTH,d0    ; the floor band's copy
        moveq   #MEMF_PUBLIC,d1
        jsr     _LVOAllocMem(a6)
        move.l  d0,band_copy
        beq     .memory
        move.l  #65*256,d0              ; a trace's row for each volume and sample
        moveq   #MEMF_PUBLIC,d1
        jsr     _LVOAllocMem(a6)
        move.l  d0,trace_table
        beq     .memory
        bsr     make_tables
        move.l  #trace_sets,front
        move.l  #trace_sets+MIX_SCOPE_WIDTH*(VOICES+1),back

        lea     newscreen,a0
        CALLINT OpenScreen
        move.l  d0,screen
        beq     .noscreen
        lea     newwindow,a0
        move.l  d0,30(a0)               ; nw_Screen
        CALLINT OpenWindow
        move.l  d0,window
        beq     .noscreen
        move.l  d0,STATUS+ST_WINDOW.w
        move.l  screen,a0
        moveq   #0,d0
        CALLINT ShowTitle               ; the backdrop window covers the title bar

        move.l  screen,a0               ; the planes, the colours
        lea     sc_BitMap(a0),a0
        lea     planes,a1
        moveq   #DEPTH-1,d0
.planes:
        move.l  bm_Planes(a0),(a1)+
        addq.l  #4,a0
        dbf     d0,.planes
        bsr     show_picture
        move.l  gfxbase,a0              ; the band's lines on the display
        move.l  gb_ActiView(a0),a0
        move.w  v_DyOffset(a0),d0
        move.l  screen,a0
        add.w   sc_ViewPort+vp_DyOffset(a0),d0
        add.w   #SCOPE_TOP,d0
        move.w  d0,d1
        sub.w   #BEAM_GUARD,d0
        move.w  d0,band_first
        add.w   #SCOPE_ROWS-1,d1
        move.w  d1,band_last
        move.l  screen,a0
        lea     sc_ViewPort(a0),a0
        lea     palette,a1
        moveq   #16,d0
        CALLGFX LoadRGB4
        bsr     show_filter             ; the light, by the user copper list
        bsr     copy_band

        move.l  picture_mem,a1          ; the file is not needed any more
        move.l  picture_bytes,d0
        addq.l  #1,d0
        jsr     _LVOFreeMem(a6)
        clr.l   picture_mem
        moveq   #MEMF_CHIP,d1
        jsr     _LVOAvailMem(a6)
        move.l  d0,STATUS+ST_SCREEN_CHIP.w
        moveq   #1,d0
        bra.s   .out
.memory:
        lea     memory_text(pc),a0
        bra.s   .say
.noscreen:
        lea     no_screen_text(pc),a0
.say:   bsr     print
.fail:  moveq   #0,d0
.out:   movem.l (sp)+,d2-d7/a2-a5
        rts

; Close whatever open_display opened; safe to call twice.
close_display:
        moveq   #-1,d0
        moveq   #0,d1
        bsr     make_copper             ; no user copper list left on the viewport
        move.l  window,d0
        beq.s   .screen
        move.l  d0,a0
        bsr     drain_messages
        move.l  window,a0
        CALLINT CloseWindow
        clr.l   window
        clr.l   STATUS+ST_WINDOW.w
.screen:
        move.l  screen,d0
        beq.s   .mem
        move.l  d0,a0
        CALLINT CloseScreen
        clr.l   screen
.mem:   move.l  picture_mem,d0
        beq.s   .copy
        move.l  d0,a1
        move.l  picture_bytes,d0
        addq.l  #1,d0
        jsr     _LVOFreeMem(a6)
        clr.l   picture_mem
.copy:  move.l  band_copy,d0
        beq.s   .table
        move.l  d0,a1
        move.l  #BAND_BYTES*DEPTH,d0
        jsr     _LVOFreeMem(a6)
        clr.l   band_copy
.table: move.l  trace_table,d0
        beq.s   .libs
        move.l  d0,a1
        move.l  #65*256,d0
        jsr     _LVOFreeMem(a6)
        clr.l   trace_table
.libs:  move.l  intbase,d0
        beq.s   .gfx
        move.l  d0,a1
        jsr     _LVOCloseLibrary(a6)
        clr.l   intbase
.gfx:   move.l  gfxbase,d0
        beq.s   .out
        move.l  d0,a1
        jsr     _LVOCloseLibrary(a6)
        clr.l   gfxbase
.out:   rts

; Reply to every message waiting at window a0's port.
drain_messages:
        move.l  a2,-(sp)
        move.l  wd_UserPort(a0),a2
.next:  move.l  a2,a0
        jsr     _LVOGetMsg(a6)
        tst.l   d0
        beq.s   .out
        move.l  d0,a1
        jsr     _LVOReplyMsg(a6)
        bra.s   .next
.out:   move.l  (sp)+,a2
        rts

; Find the ILBM's header, colours and body in picture_mem. d0: 0 unless it
; is 320x200, 4 planes and uncompressed. Sets palette and body.
parse_ilbm:
        move.l  picture_mem,a0
        cmp.l   #'FORM',(a0)
        bne     .bad
        cmp.l   #'ILBM',8(a0)
        bne     .bad
        move.l  a0,a1
        add.l   picture_bytes,a1        ; the end
        lea     12(a0),a0
        clr.l   body
        moveq   #0,d2                   ; 1 when BMHD was right
.chunk: lea     8(a0),a2                ; the chunk's data
        cmp.l   a1,a2
        bhi     .done
        move.l  4(a0),d1                ; its size
        cmp.l   #'BMHD',(a0)
        bne     .cmap
        cmp.w   #SCREEN_WIDTH,(a2)
        bne     .bad
        cmp.w   #SCREEN_HEIGHT,2(a2)
        bne     .bad
        cmp.b   #DEPTH,8(a2)
        bne     .bad
        tst.b   10(a2)                  ; compression
        bne     .bad
        moveq   #1,d2
        bra     .skip
.cmap:  cmp.l   #'CMAP',(a0)
        bne     .body
        lea     palette,a3              ; 8-bit RGB to $0RGB
        move.l  d1,d3
        divu    #3,d3
        cmp.w   #16,d3
        bls     .count
        moveq   #16,d3
.count: move.l  a2,a4
        bra     .cnext
.colour:
        moveq   #0,d0
        move.b  (a4)+,d0
        lsr.w   #4,d0
        lsl.w   #4,d0
        move.b  (a4)+,d4
        lsr.b   #4,d4
        or.b    d4,d0
        lsl.w   #4,d0
        move.b  (a4)+,d4
        lsr.b   #4,d4
        or.b    d4,d0
        move.w  d0,(a3)+
.cnext: dbf     d3,.colour
        bra     .skip
.body:  cmp.l   #'BODY',(a0)
        bne     .skip
        cmp.l   #PICTURE_BYTES,d1
        bcs     .bad
        move.l  a2,body
.skip:  addq.l  #1,d1                   ; chunks are padded to even sizes
        and.w   #$fffe,d1
        lea     0(a2,d1.l),a0
        bra     .chunk
.done:  tst.l   d2
        beq     .bad
        tst.l   body
        beq     .bad
        moveq   #1,d0
        rts
.bad:   moveq   #0,d0
        rts

; Copy the ILBM's interleaved rows into the screen's four planes.
show_picture:
        movem.l d2-d3/a2-a3,-(sp)
        move.l  body,a0
        moveq   #0,d2                   ; the row's offset in a plane
        move.w  #SCREEN_HEIGHT-1,d3
.row:   lea     planes,a2
        moveq   #DEPTH-1,d1
.plane: move.l  (a2)+,a1
        add.l   d2,a1
        moveq   #ROW_BYTES/2-1,d0
.word:  move.w  (a0)+,(a1)+
        dbf     d0,.word
        dbf     d1,.plane
        add.l   #ROW_BYTES,d2
        dbf     d3,.row
        movem.l (sp)+,d2-d3/a2-a3
        rts

; Keep a copy of the scope band, all four planes, for restoring it.
copy_band:
        move.l  band_copy,a1
        lea     planes,a2
        moveq   #DEPTH-1,d1
.plane: move.l  (a2)+,a0
        add.l   #SCOPE_TOP*ROW_BYTES,a0
        move.w  #BAND_BYTES/2-1,d0
.word:  move.w  (a0)+,(a1)+
        dbf     d0,.word
        dbf     d1,.plane
        rts

; Rows' offsets in a plane (row_offsets), and the trace table: for each
; Paula volume 0 to 64 and each sample byte, the trace's row from the
; centre, sample * volume >> SCOPE_SHIFT, clamped to VOICE_HALF.
make_tables:
        lea     row_offsets,a0
        moveq   #0,d0
        move.w  #SCREEN_HEIGHT-1,d1
.row:   move.w  d0,(a0)+
        add.w   #ROW_BYTES,d0
        dbf     d1,.row
        move.l  trace_table,a0
        moveq   #0,d2                   ; volume
.vol:   moveq   #0,d1                   ; sample byte
.byte:  move.b  d1,d0
        ext.w   d0
        muls    d2,d0
        asr.l   #SCOPE_SHIFT,d0
        cmp.w   #VOICE_HALF,d0
        ble.s   .low
        moveq   #VOICE_HALF,d0
.low:   cmp.w   #-VOICE_HALF,d0
        bge.s   .high
        moveq   #-VOICE_HALF,d0
.high:  move.b  d0,(a0)+
        addq.w  #1,d1
        cmp.w   #256,d1
        bne.s   .byte
        addq.w  #1,d2
        cmp.w   #65,d2
        bne.s   .vol
        rts

; Take choices until Esc or Q: a click on a piece's line or its key plays
; it, switching from the piece playing. While a piece plays, the scopes
; are drawn after every vertical blank.
;
; The rotation: ROTATE_S seconds after the screen appears with no input,
; and that long after each piece ends, the next piece plays by itself (the
; first after the last). A choice plays that piece now and the rotation goes
; on from it. Space stops the piece playing and holds the rotation until the
; next choice. Waiting is Wait on the window's port and the alarm, which the
; vertical blank server signals.
choose:
        move.l  #3,STATUS+ST_STATE.w
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_SCREEN_AT.w
        move.l  #ROTATE_S,d0
        mulu    STATUS+ST_VBLANK_HZ+2.w,d0
        move.l  d0,rotate_frames
        clr.l   STATUS+ST_NEXT.w
        bsr     arm_rotation
.loop:  bsr     flush_results
        tst.w   playing
        beq.s   .idle
        tst.w   finished
        beq.s   .draw
        moveq   #-1,d0
        bsr     end_piece               ; it played to its end
        bsr     arm_rotation            ; the next, after the gap
        bra.s   .loop
.draw:  bsr     scope_frame
        bra.s   .messages
.idle:  bsr     rotation_due
        bne     .rotate
        move.l  window,a0
        move.l  wd_UserPort(a0),a0
        moveq   #0,d1
        move.b  mp_SigBit(a0),d1
        moveq   #0,d0
        bset    d1,d0
        or.l    alarm_mask,d0
        jsr     _LVOWait(a6)
.messages:
        bsr     next_choice
        tst.l   d0
        bne.s   .act
        tst.l   d1                      ; input that chose nothing: while the
        beq.s   .loop                   ; rotation counts, the quiet starts again
        cmp.l   #-1,STATUS+ST_ROTATE_AT.w
        beq.s   .loop
        bsr     arm_rotation
        bra.s   .loop
.act:   cmp.l   #-1,d0
        beq.s   .quit
        cmp.l   #-2,d0
        beq.s   .hold
        subq.l  #1,d0                   ; the piece, from 0
.play:  move.l  d0,-(sp)
        addq.l  #1,d0                   ; the rotation goes on from it
        cmp.l   pieces,d0
        bcs.s   .next
        moveq   #0,d0
.next:  move.l  d0,STATUS+ST_NEXT.w
        bsr     hold_rotation           ; until it ends
        tst.w   playing
        beq.s   .start
        move.l  #1,STATUS+ST_STOPPED.w
        move.l  (sp),d0
        bsr     end_piece               ; and its line gold at once
.start: move.l  (sp)+,d0
        bsr     start_piece
        tst.l   d0
        beq     .loop
        bsr     arm_rotation            ; it could not play: on to the next
        bra     .loop
.rotate:
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_CHOSEN_AT.w
        addq.l  #1,STATUS+ST_ROTATED.w
        move.l  STATUS+ST_NEXT.w,d0
        bra.s   .play
.hold:  bsr     hold_rotation
        tst.w   playing
        beq     .loop
        move.l  #1,STATUS+ST_STOPPED.w
        moveq   #-1,d0
        bsr     end_piece
        bra     .loop
.quit:  bsr     hold_rotation
        tst.w   playing
        beq.s   .out
        move.l  #1,STATUS+ST_STOPPED.w
        moveq   #-1,d0
        bsr     end_piece
.out:   bra     flush_results

; Play the next piece rotate_frames from now: the alarm wakes the task then.
arm_rotation:
        tst.l   pieces
        beq.s   hold_rotation
        move.l  STATUS+ST_VBLANKS.w,d0
        add.l   rotate_frames,d0
        clr.w   alarm_on                ; the server must not see half of it
        move.l  d0,alarm_at
        move.l  d0,STATUS+ST_ROTATE_AT.w
        move.w  #1,alarm_on
        rts

; No rotation until the next choice.
hold_rotation:
        clr.w   alarm_on
        move.l  #-1,STATUS+ST_ROTATE_AT.w
        rts

; Z clear when the rotation's time has come.
rotation_due:
        move.l  STATUS+ST_ROTATE_AT.w,d0
        cmp.l   #-1,d0
        beq.s   .no
        sub.l   STATUS+ST_VBLANKS.w,d0
        bgt.s   .no
        moveq   #1,d0
        rts
.no:    moveq   #0,d0
        rts

; Read the window's messages. d0: -1 to quit, -2 to stop and hold the
; rotation (Space), n + 1 for piece n, 0 for nothing; d1: how many key
; presses and clicks there were. The last choice among the waiting messages
; wins, but a quit always does.
next_choice:
        movem.l d2-d5/a2,-(sp)
        moveq   #0,d4                   ; the choice
        moveq   #0,d5                   ; the input
.next:  move.l  window,a0
        move.l  wd_UserPort(a0),a0
        jsr     _LVOGetMsg(a6)
        tst.l   d0
        beq     .out
        move.l  d0,a1
        move.l  im_Class(a1),d2
        move.w  im_Code(a1),d3
        move.w  im_MouseX(a1),d0
        swap    d0
        move.w  im_MouseY(a1),d0
        move.l  d0,a2                   ; x and y
        jsr     _LVOReplyMsg(a6)
        cmp.l   #RAWKEY,d2
        bne.s   .mouse
        addq.l  #1,STATUS+ST_KEYS.w
        and.l   #$ffff,d3
        move.l  d3,STATUS+ST_KEY.w
        btst    #7,d3                   ; a key going up
        bne     .next
        addq.l  #1,d5
        cmp.b   #KEY_ESC,d3
        beq     .quit
        cmp.b   #KEY_Q,d3
        beq     .quit
        cmp.b   #KEY_SPACE,d3
        beq     .hold
        cmp.b   #KEY_F,d3
        beq     .filter
        lea     piece_keys,a0
        moveq   #0,d0
.key:   cmp.l   pieces,d0
        beq     .next
        cmp.b   (a0)+,d3
        beq.s   .chosen
        addq.l  #1,d0
        bra.s   .key
.mouse: cmp.l   #MOUSEBUTTONS,d2
        bne     .next
        cmp.w   #SELECTDOWN,d3
        bne     .next
        addq.l  #1,d5
        addq.l  #1,STATUS+ST_CLICKS.w
        move.l  a2,STATUS+ST_CLICK_XY.w
        move.l  a2,d1
        swap    d1
        cmp.w   #LIST_LEFT-4,d1         ; left of the list: not a choice
        blt     .next
        swap    d1                      ; y
        lea     line_tops(pc),a0
        moveq   #0,d0
.line:  cmp.l   pieces,d0
        beq     .next
        cmp.w   #LIST_LINES,d0
        beq     .next
        move.w  (a0)+,d2
        cmp.w   d2,d1
        blt.s   .below
        add.w   #LINE_PITCH,d2
        cmp.w   d2,d1
        blt.s   .chosen
.below: addq.l  #1,d0
        bra.s   .line
.chosen:
        addq.l  #1,d0
        cmp.l   #-1,d4
        beq     .next                   ; a quit stands
        move.l  d0,d4
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_CHOSEN_AT.w
        bra     .next
.hold:  cmp.l   #-1,d4
        beq     .next
        moveq   #-2,d4
        bra     .next
.filter:                                ; the A500's audio filter, and the power
        bchg    #LED_BIT,ciaapra        ; LED with it: only that bit, by the task
        addq.l  #1,STATUS+ST_FILTER_KEYS.w
        bsr     show_filter
        bra     .next
.quit:  moveq   #-1,d4
        bra     .next
.out:   move.l  d4,d0
        move.l  d5,d1
        movem.l (sp)+,d2-d5/a2
        rts

; Put line d0 in gold (-1 for none): the user copper list remade with it.
highlight:
        move.l  screen,d1
        beq.s   .out
        cmp.l   STATUS+ST_HIGHLIGHT.w,d0
        beq.s   .already
        moveq   #1,d1
        bra     make_copper
.out:   rts
.already:                               ; that line is gold already: since
        tst.l   d0                      ; this choice, unless it is the piece
        bmi.s   .out                    ; that was playing, chosen again
        move.l  STATUS+ST_GOLD_AT.w,d1
        cmp.l   STATUS+ST_CHOSEN_AT.w,d1
        bcc.s   .out
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_GOLD_AT.w
        rts

; show_filter: the user copper list remade for the filter as it is now.
show_filter:
        move.l  STATUS+ST_HIGHLIGHT.w,d0
        moveq   #1,d1
        bra     make_copper

; make_copper: a user copper list on the screen's viewport. Line d0 (-1 for
; none) in gold: colour 13 is HIGHLIGHT_COLOUR on its rows and TEXT_COLOUR
; again after them. With d1 not 0, the filter light: colour 14 (the voice
; traces') is FILTER_LIGHT_ON while the filter is on (CIA-A bit clear) or
; FILTER_LIGHT_OFF on the light's rows, and FILTER_LIGHT_BACK after them.
; With d1 = 0 there is no list at all. The old list is freed once the
; display has been remade without it. With no memory nothing changes.
make_copper:
        movem.l d2-d4/a2-a3,-(sp)
        move.l  screen,d2
        beq     .out
        move.l  d0,d2
        move.l  d1,d4
        sub.l   a2,a2                   ; the new list, none for d1 = 0
        tst.l   d4
        beq     .set
        moveq   #ucl_SIZEOF,d0
        move.l  #MEMF_PUBLIC|MEMF_CLEAR,d1
        jsr     _LVOAllocMem(a6)
        tst.l   d0
        beq     .out                    ; no memory: as it was
        move.l  d0,a2
        move.l  a2,a0
        moveq   #9,d0
        CALLGFX UCopperListInit
        tst.l   d2
        bmi     .light
        lea     line_tops(pc),a0
        move.w  d2,d0
        add.w   d0,d0
        move.w  0(a0,d0.w),d3           ; the line's first row
        move.w  d3,d0
        move.l  #COLOR13,d1
        move.w  #HIGHLIGHT_COLOUR,d4
        bsr     .change
        move.w  d3,d0
        add.w   #LINE_ROWS,d0
        move.w  #TEXT_COLOUR,d4
        bsr     .change
.light: move.w  #FILTER_LIGHT_OFF,d4
        btst    #LED_BIT,ciaapra
        bne.s   .dark
        move.w  #FILTER_LIGHT_ON,d4
.dark:  move.w  #FILTER_LIGHT_TOP,d0
        move.l  #COLOR14,d1
        bsr     .change
        move.w  #FILTER_LIGHT_END,d0
        move.w  #FILTER_LIGHT_BACK,d4
        bsr     .change
        move.l  a2,a1                   ; CEND
        move.w  #10000,d0
        move.w  #255,d1
        CALLGFX CWait
        move.l  a2,a1
        CALLGFX CBump
.set:   jsr     _LVOForbid(a6)
        move.l  screen,a0
        move.l  sc_ViewPort+vp_UCopIns(a0),a3   ; the old list
        move.l  a2,sc_ViewPort+vp_UCopIns(a0)
        jsr     _LVOPermit(a6)
        move.l  screen,a0
        CALLINT MakeScreen
        CALLINT RethinkDisplay
        cmp.l   STATUS+ST_HIGHLIGHT.w,d2
        beq.s   .same                   ; the line was gold already
        move.l  d2,STATUS+ST_HIGHLIGHT.w
        bmi.s   .same
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_GOLD_AT.w
.same:  move.l  a3,d0
        beq.s   .out
        CALLGFX WaitTOF                 ; the copper has the new list now
        move.l  ucl_FirstCopList(a3),a0
        CALLGFX FreeCopList
        move.l  a3,a1
        moveq   #ucl_SIZEOF,d0
        jsr     _LVOFreeMem(a6)
.out:   movem.l (sp)+,d2-d4/a2-a3
        rts
; .change: wait for row d0, then register d1 (an address) to colour d4.
.change:
        move.l  d1,-(sp)
        move.l  a2,a1
        moveq   #0,d1
        CALLGFX CWait
        move.l  a2,a1
        CALLGFX CBump
        move.l  a2,a1
        move.l  (sp)+,d0
        move.w  d4,d1
        CALLGFX CMove
        move.l  a2,a1
        CALLGFX CBump
        rts

; ---------------------------------------------------------------------------
; One piece: load its score, start it, end it.
; ---------------------------------------------------------------------------

; Start piece d0 (from 0): its line gold first, so the choice shows at
; once, then its score (in memory since the start) and its timer.
; d0: 0 when it plays.
start_piece:
        movem.l d2-d7/a2-a5,-(sp)
        clr.l   STATUS+ST_LOADED_AT.w   ; this piece's times, to come (a
        clr.l   STATUS+ST_PLAYING_AT.w  ; switch has put the line in gold)
        clr.l   STATUS+ST_FIRST_NOTE_AT.w
        clr.l   STATUS+ST_FIRST_NOTE_MS.w
        move.l  d0,d6
        lsl.l   #3,d0
        lea     score_table,a0
        move.l  0(a0,d0.l),score_mem
        move.l  4(a0,d0.l),score_bytes
        tst.l   score_mem
        bne.s   .loaded
        lea     no_score_text(pc),a0
        bsr     print
        moveq   #1,d0
        bra     .out
.loaded:
        move.l  d6,d0
        bsr     highlight               ; a switch has done it already
        bsr     reset_piece
        move.l  d6,STATUS+ST_PIECE.w
        move.l  score_mem,score_ptr
        move.l  score_mem,STATUS+ST_SCORE.w
        move.l  score_bytes,STATUS+ST_SCORE_BYTES.w
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_LOADED_AT.w
        bsr     take_audio
        bsr     take_timer
        tst.l   d0
        beq.s   .play
        bsr     give_audio              ; the timer is someone else's
        clr.l   score_mem
        lea     busy_text(pc),a0
        bsr     print
        moveq   #-1,d0
        bsr     highlight
        moveq   #1,d0
        bra.s   .out
.play:  move.w  #1,playing
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_PLAYING_AT.w
        addq.l  #1,STATUS+ST_STARTS.w
        move.l  #1,STATUS+ST_STATE.w
        bsr     flush_results           ; the piece before's, now this one plays
        moveq   #MEMF_CHIP,d1           ; then what it found, while it plays
        jsr     _LVOAvailMem(a6)
        move.l  d0,STATUS+ST_CHIP_FREE.w
        moveq   #0,d1
        jsr     _LVOAvailMem(a6)
        sub.l   STATUS+ST_CHIP_FREE.w,d0
        move.l  d0,STATUS+ST_OTHER_FREE.w
        lea     fmt_args,a1
        lea     titles,a0
        move.l  d6,d0
        lsl.l   #2,d0
        move.l  0(a0,d0.l),(a1)
        lea     loading_text(pc),a0
        bsr     print
        lea     fmt_args,a1
        move.l  score_bytes,(a1)
        move.l  score_mem,4(a1)
        move.l  STATUS+ST_CHIP_FREE.w,8(a1)
        move.l  STATUS+ST_OTHER_FREE.w,12(a1)
        lea     playing_text(pc),a0
        bsr     print
        moveq   #0,d0
.out:   movem.l (sp)+,d2-d7/a2-a5
        rts

; Stop the piece playing (or finished), give everything back, put line d0
; in gold (-1 for none: a switch passes the next piece's), and say what it
; measured. Its score stays in memory.
end_piece:
        movem.l d2-d7/a2-a5,-(sp)
        move.l  d0,d6                   ; (give_audio uses d2)
        bsr     give_timer
        bsr     give_audio
        clr.w   playing
        clr.l   score_mem
        addq.l  #1,STATUS+ST_PLAYED.w
        move.l  d6,d0
        bsr     highlight
        tst.l   screen
        beq.s   .print
        bsr     restore_band            ; the traces go
.print: bsr     print_results
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_ENDED_AT.w
        move.l  #3,STATUS+ST_STATE.w
        movem.l (sp)+,d2-d7/a2-a5
        rts

; ---------------------------------------------------------------------------
; The scopes: four voices and their mix, in the floor band.
; ---------------------------------------------------------------------------

; One scope frame. After the vertical blank, draw the traces made last
; time, scope by scope: each scope's old points are copied back from
; band_copy and its new ones plotted, and no scope is started while the
; beam is on the band or about to reach it (beam_clear), so the beam
; always shows a scope whole, old or new. The next traces are made into
; the other buffer while the beam holds the drawing up, or after it. The
; traces are a frame late. Counts the E-clock ticks of both kinds of work,
; less the player's interrupts' share; waiting for the beam is not counted.
scope_frame:
        movem.l d2-d7/a2-a5,-(sp)
        CALLGFX WaitTOF
        clr.w   made
        clr.l   draw_sum
        clr.l   make_sum
        bsr     draw_units
        bsr     make_traces             ; if the beam did not leave time for it
        move.l  front,d0                ; show what was just made, next time
        move.l  back,front
        move.l  d0,back
        move.l  draw_sum,d0
        add.l   d0,STATUS+ST_DRAW_E.w
        cmp.l   STATUS+ST_DRAW_MAX_E.w,d0
        bls.s   .most
        move.l  d0,STATUS+ST_DRAW_MAX_E.w
.most:  move.l  make_sum,d0
        add.l   d0,STATUS+ST_SCOPE_E.w
        addq.l  #1,STATUS+ST_SCOPE_FRAMES.w
        cmp.l   STATUS+ST_SCOPE_MAX_E.w,d0
        bls.s   .out
        move.l  d0,STATUS+ST_SCOPE_MAX_E.w
.out:   movem.l (sp)+,d2-d7/a2-a5
        rts

; Make the next traces into the back buffer, once a frame.
make_traces:
        tst.w   made
        bne.s   .out
        movem.l d2-d7/a2-a5,-(sp)
        bsr     stopwatch_start
        bsr     take_voices
        bsr     trace_voices
        bsr     stopwatch_stop
        add.l   d0,make_sum
        move.w  #1,made
        movem.l (sp)+,d2-d7/a2-a5
.out:   rts

stopwatch_start:
        bsr     clock
        move.l  d0,watch_ms
        move.w  d1,watch_count
        move.l  isr_e,watch_isr
        rts

; d0: the E-clock ticks since stopwatch_start, less the interrupts'.
stopwatch_stop:
        bsr     clock
        sub.l   watch_ms,d0             ; ms between
        mulu    #TIMER_PERIOD,d0
        move.w  watch_count,d2
        sub.w   d1,d2                   ; the timer counts down
        ext.l   d2
        add.l   d2,d0                   ; E-clock ticks between
        move.l  isr_e,d1
        sub.l   watch_isr,d1
        sub.l   d1,d0                   ; less the interrupts' own
        bpl.s   .pos
        moveq   #0,d0
.pos:   rts

; d0: the player's millisecond, d1: CIA-B timer A's count within it.
clock:
.again: move.l  now,d2
        bsr     read_timer
        move.l  d0,d1
        move.l  d2,d0
        cmp.l   now,d2
        bne.s   .again
        rts

; Copy what Paula plays on each voice into taken. Interrupts stay on, so
; that the player's are never late for the scopes: a note that starts
; while this copies shows wrongly for one scope frame at most.
take_voices:
        move.l  now,d2
        lea     voices,a0
        lea     taken,a1
        moveq   #VOICES-1,d1
.voice: move.w  V_PSAMPLE(a0),C_SAMPLE(a1)
        move.w  V_PPERIOD(a0),C_PERIOD(a1)
        move.w  V_OUT(a0),C_OUT(a1)
        move.l  d2,d0
        sub.l   V_PSTART(a0),d0
        cmp.l   #$ffff,d0
        bls.s   .short
        move.l  #$ffff,d0
.short: move.w  d0,C_ELAPSED(a1)
        lea     V_SIZE(a0),a0
        lea     C_SIZE(a1),a1
        dbf     d1,.voice
        rts

; Each voice's trace for MIX_SCOPE_WIDTH columns into the back buffer, and
; the mix after them: where Paula
; is in the sample now, the classic tracker way (the samples played since
; the start, through the loop), then a column every SCOPE_STEP clocks.
trace_voices:
        lea     taken,a3
        move.l  back,a2
        moveq   #VOICES-1,d7
.voice: move.w  d7,-(sp)
        move.w  C_SAMPLE(a3),d0
        bmi.s   .flat
        tst.w   C_OUT(a3)
        bne.s   .sound
.flat:  move.w  #MIX_SCOPE_WIDTH-1,d0   ; silent: the centre line
.zero:  clr.b   (a2)+
        dbf     d0,.zero
        bra     .next
.sound: mulu    #S_SIZE,d0
        lea     sampletab,a4
        add.l   d0,a4
        move.l  samples_base,a0
        add.l   S_OFFSET(a4),a0         ; the sample
        move.w  S_WORDS(a4),d4
        add.w   d4,d4                   ; its length in bytes
        move.w  S_LOOPWORDS(a4),d5
        add.w   d5,d5                   ; the loop's
        move.w  C_ELAPSED(a3),d0
        mulu    #PAULA_PER_MS,d0        ; Paula clocks since it started
        move.w  C_PERIOD(a3),d1
        bsr     divide_long             ; samples since it started
        moveq   #0,d3
        move.w  d4,d3
        cmp.l   d3,d0
        bcs.s   .first                  ; still in the first pass
        sub.l   d3,d0                   ; then round the loop
        divu    d5,d0
        swap    d0
        add.w   d4,d0
        sub.w   d5,d0                   ; the loop ends where the sample does
.first: move.w  d0,d3                   ; the byte now
        move.l  #SCOPE_STEP*256,d0      ; bytes a column, 8.8
        divu    C_PERIOD(a3),d0
        moveq   #0,d6
        move.b  d0,d6                   ; fraction
        lsr.w   #8,d0                   ; whole bytes
        move.l  trace_table,a1
        move.w  C_OUT(a3),d1
        lsl.w   #8,d1
        add.w   d1,a1                   ; the row for its volume
        moveq   #0,d2                   ; the fraction so far
        move.w  #MIX_SCOPE_WIDTH-1,d7
        moveq   #0,d1
.col:   move.b  0(a0,d3.w),d1
        move.b  0(a1,d1.w),(a2)+
        add.b   d6,d2
        addx.w  d0,d3
        cmp.w   d4,d3
        bcs.s   .in
        sub.w   d5,d3
.in:    dbf     d7,.col
.next:  lea     C_SIZE(a3),a3
        move.w  (sp)+,d7
        dbf     d7,.voice
        move.l  back,a0                 ; the mix: half the voices' sum, clamped
        lea     MIX_SCOPE_WIDTH*VOICES(a0),a1
        move.w  #MIX_SCOPE_WIDTH-1,d7
.mix:   move.b  (a0),d0
        ext.w   d0
        move.b  MIX_SCOPE_WIDTH(a0),d1
        ext.w   d1
        add.w   d1,d0
        move.b  MIX_SCOPE_WIDTH*2(a0),d1
        ext.w   d1
        add.w   d1,d0
        move.b  MIX_SCOPE_WIDTH*3(a0),d1
        ext.w   d1
        add.w   d1,d0
        addq.l  #1,a0
        asr.w   #1,d0
        cmp.w   #MIX_HALF,d0
        ble.s   .low
        moveq   #MIX_HALF,d0
.low:   cmp.w   #-MIX_HALF,d0
        bge.s   .high
        moveq   #-MIX_HALF,d0
.high:  move.b  d0,(a1)+
        dbf     d7,.mix
        rts

; d0.l / d1.w: d0.l the quotient. Uses d2.
divide_long:
        move.l  d0,d2
        clr.w   d2
        swap    d2
        divu    d1,d2                   ; the high word: remainder and quotient
        move.l  d2,-(sp)
        move.w  d0,d2
        divu    d1,d2                   ; the low word, after that remainder
        move.l  (sp)+,d0
        swap    d0
        move.w  d2,d0
        rts

; Copy the whole band back from band_copy with the CPU, a row at a time
; (40 bytes in two MOVEMs), when a piece ends. While a piece plays, each
; scope takes back only its own points (draw_unit).
restore_band:
        movem.l d2-d7/a2-a4,-(sp)
        move.l  band_copy,a0
        lea     planes,a4
        moveq   #DEPTH-1,d0
.plane: move.l  (a4)+,a3
        add.l   #SCOPE_TOP*ROW_BYTES,a3
        move.w  #SCOPE_ROWS-1,d1
.row:   movem.l (a0)+,d2-d7/a1-a2
        movem.l d2-d7/a1-a2,(a3)
        movem.l (a0)+,d2-d3
        movem.l d2-d3,32(a3)
        lea     ROW_BYTES(a3),a3
        dbf     d1,.row
        dbf     d0,.plane
        clr.w   drawn                   ; no points to take back
        movem.l (sp)+,d2-d7/a2-a4
        rts

; Draw the six units: the four voice scopes (colour 14) and the mixed
; scope in two halves (colour 15), each when the beam allows.
draw_units:
        move.l  front,a0
        lea     voice_scope_left(pc),a1
        lea     old_points,a2
        moveq   #VOICES-1,d7
.voice: movem.l a0-a2,-(sp)
        bsr     make_if_held
        move.w  (a1),d4                 ; the left column
        moveq   #VOICE_SCOPE_WIDTH,d6
        moveq   #0,d3                   ; colour 14
        bsr     draw_unit
        movem.l (sp)+,a0-a2
        lea     MIX_SCOPE_WIDTH(a0),a0
        addq.l  #2,a1
        lea     VOICE_SCOPE_WIDTH*2(a2),a2
        dbf     d7,.voice
        move.l  a2,-(sp)
        bsr     make_if_held
        move.l  front,a0
        lea     MIX_SCOPE_WIDTH*VOICES(a0),a0
        move.w  #MIX_SCOPE_LEFT,d4
        moveq   #MIX_SPLIT,d6
        moveq   #1,d3                   ; colour 15
        bsr     draw_unit
        move.l  (sp),a2
        bsr     make_if_held
        move.l  (sp)+,a2
        move.l  front,a0
        lea     MIX_SCOPE_WIDTH*VOICES+MIX_SPLIT(a0),a0
        lea     MIX_SPLIT*2(a2),a2
        move.w  #MIX_SCOPE_LEFT+MIX_SPLIT,d4
        moveq   #MIX_SCOPE_WIDTH-MIX_SPLIT,d6
        moveq   #1,d3
        bsr     draw_unit
        move.w  #1,drawn
        rts

; Make the next traces now if the beam holds the drawing up. Keeps a0-a2.
make_if_held:
        tst.w   made
        bne.s   .out
        bsr     beam_held
        beq.s   .out
        movem.l a0-a2,-(sp)
        bsr     make_traces
        movem.l (sp)+,a0-a2
.out:   rts

; One unit: d6 points from the trace a0, from column d4; d3 0 for colour
; 14, 1 for colour 15; a2 holds the unit's points from last time (their
; offsets in a plane), which are taken back first and then replaced.
draw_unit:
        movem.l d7/a6,-(sp)
        move.l  a0,unit_trace
        bsr     beam_clear
        bsr     stopwatch_start
        movem.l planes,a3-a6            ; planes 0 to 3, a3 is plane 0
        tst.w   drawn
        beq.s   .plot
        move.l  a2,a1                   ; take back last time's points
        move.l  band_copy,a0
        sub.l   #SCOPE_TOP*ROW_BYTES,a0 ; so a plane offset indexes the copy
        move.w  d6,d7
        subq.w  #1,d7
.back:  move.w  (a1)+,d0
        move.b  0(a0,d0.w),0(a3,d0.w)
        dbf     d7,.back
        lea     BAND_BYTES(a0),a0
        move.l  a2,a1
        move.w  d6,d7
        subq.w  #1,d7
.back1: move.w  (a1)+,d0
        move.b  0(a0,d0.w),0(a4,d0.w)
        dbf     d7,.back1
        lea     BAND_BYTES(a0),a0
        move.l  a2,a1
        move.w  d6,d7
        subq.w  #1,d7
.back2: move.w  (a1)+,d0
        move.b  0(a0,d0.w),0(a5,d0.w)
        dbf     d7,.back2
        lea     BAND_BYTES(a0),a0
        move.l  a2,a1
        move.w  d6,d7
        subq.w  #1,d7
.back3: move.w  (a1)+,d0
        move.b  0(a0,d0.w),0(a6,d0.w)
        dbf     d7,.back3
.plot:  move.l  unit_trace,a0
        lea     row_offsets+SCOPE_CENTRE*2,a1
        move.w  d4,d5
        lsr.w   #3,d4                   ; the column's byte
        not.w   d5
        and.w   #7,d5                   ; and bit
        move.w  d6,d7
        subq.w  #1,d7
.point: move.b  (a0)+,d0
        ext.w   d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d2
        add.w   d4,d2
        move.w  d2,(a2)+                ; for next time
        tst.w   d3
        bne.s   .fifteen
        bclr    d5,0(a3,d2.w)
        bra.s   .upper
.fifteen:
        bset    d5,0(a3,d2.w)
.upper: bset    d5,0(a4,d2.w)
        bset    d5,0(a5,d2.w)
        bset    d5,0(a6,d2.w)
        subq.w  #1,d5
        bpl.s   .same
        moveq   #7,d5
        addq.w  #1,d4
.same:  dbf     d7,.point
        bsr     stopwatch_stop
        add.l   d0,draw_sum
        movem.l (sp)+,d7/a6
        rts

; Wait until the beam is clear of the band: not on it, and not within
; BEAM_GUARD lines above it, which is longer than a unit takes.
beam_clear:
.wait:  bsr.s   beam_held
        bne.s   .wait
        rts

; Z clear when the beam is in the guard lines or on the band. Uses d0.
beam_held:
        move.l  custom+4,d0             ; VPOSR and VHPOSR
        lsr.l   #8,d0
        and.w   #$1ff,d0                ; the beam's line
        cmp.w   band_first,d0
        bcs.s   .clear                  ; above the guard
        cmp.w   band_last,d0
        bhi.s   .clear                  ; below the band
        moveq   #1,d0
        rts
.clear: moveq   #0,d0
        rts


; Everything a piece starts from: silent voices, time 0, the score's start,
; the log's start, and the status's measurements cleared.
reset_piece:
        lea     piece_state,a0
        move.w  #(piece_state_end-piece_state)/2-1,d0
.clear: clr.w   (a0)+
        dbf     d0,.clear
        lea     STATUS+ST_PER_PIECE.w,a0
        moveq   #(ST_PLAYED-ST_PER_PIECE)/4-1,d0
.stat:  clr.l   (a0)+
        dbf     d0,.stat
        clr.l   STATUS+ST_STOPPED.w
        clr.l   STATUS+ST_LOGBYTES.w
        clr.l   STATUS+ST_SCOPE_FRAMES.w
        clr.l   STATUS+ST_SCOPE_E.w
        clr.l   STATUS+ST_SCOPE_MAX_E.w
        clr.l   STATUS+ST_DRAW_E.w
        clr.l   STATUS+ST_DRAW_MAX_E.w
        if      LOG
        move.l  STATUS+ST_LOGBASE.w,d0
        move.l  d0,log_ptr
        add.l   #LOG_BYTES,d0
        move.l  d0,log_end
        endif
        bra     voices_silent

print_results:
        lea     STATUS.w,a0
        lea     fmt_args,a1
        move.l  ST_FRAMES(a0),d1
        move.l  d1,(a1)
        move.l  ST_TOTAL_E(a0),d0
        tst.l   d1
        beq.s   .none
        divu    d1,d0                   ; average per frame (fits a word)
.none:  and.l   #$ffff,d0
        move.l  d0,4(a1)
        move.l  ST_MAX_FRAME_E(a0),8(a1)
        move.l  ST_MAX_MS_E(a0),12(a1)
        lea     results(pc),a0
        tst.l   STATUS+ST_STOPPED.w
        beq.s   .print
        lea     stopped(pc),a0
.print: move.l  a3,-(sp)                ; formatted now, written by flush_results
        lea     results_buf,a3
        bsr     format
        if      LOG
.end:   tst.b   (a3)+
        bne.s   .end
        subq.l  #1,a3
        lea     log_text(pc),a0
        lea     fmt_args,a1
        move.l  STATUS+ST_LOGBYTES.w,(a1)
        move.l  STATUS+ST_LOGBASE.w,4(a1)
        bsr     format
        endif
        move.l  (sp)+,a3
        move.w  #1,results_pending
        rts

; Load the file named a0 (a C string) into new public memory, with a 0
; after it. d0: the memory, or 0 when the file or the memory is missing;
; d1: the file's size. Free it with FreeMem(d0, d1 + 1). The size comes
; from Examine, which reads only the file's header block.
load_file:
        movem.l d2-d5/a2,-(sp)
        move.l  dosbase,a6
        move.l  a0,-(sp)                ; the name, for Open
        move.l  a0,d1
        moveq   #ACCESS_READ,d2
        jsr     _LVOLock(a6)
        move.l  d0,d4
        beq     .nolock
        move.l  d4,d1
        move.l  #fib,d2
        jsr     _LVOExamine(a6)
        move.l  d0,d3
        move.l  d4,d1
        jsr     _LVOUnLock(a6)
        tst.l   d3
        beq    .nolock
        move.l  fib+fib_Size,d5
        move.l  (sp)+,d1
        move.l  #MODE_OLDFILE,d2
        jsr     _LVOOpen(a6)
        move.l  d0,d4
        beq.s   .fail
        tst.l   d5
        ble.s   .close
        move.l  ExecBase.w,a6
        move.l  d5,d0
        addq.l  #1,d0
        move.l  #MEMF_PUBLIC|MEMF_CLEAR,d1  ; cleared, so the 0 after it is there
        jsr     _LVOAllocMem(a6)
        move.l  dosbase,a6
        move.l  d0,a2
        tst.l   d0
        beq.s   .close
        move.l  d4,d1
        move.l  a2,d2
        move.l  d5,d3
        jsr     _LVORead(a6)
        cmp.l   d5,d0
        beq.s   .read
        move.l  ExecBase.w,a6           ; a short read: give the memory back
        move.l  a2,a1
        move.l  d5,d0
        addq.l  #1,d0
        jsr     _LVOFreeMem(a6)
        move.l  dosbase,a6
        bra.s   .close
.read:  move.l  d4,d1
        jsr     _LVOClose(a6)
        move.l  a2,d0
        move.l  d5,d1
        bra.s   .out
.nolock:
        addq.l  #4,sp
        bra.s   .fail
.close: move.l  d4,d1
        jsr     _LVOClose(a6)
.fail:  moveq   #0,d0
        moveq   #0,d1
.out:   move.l  ExecBase.w,a6
        movem.l (sp)+,d2-d5/a2
        rts

; ---------------------------------------------------------------------------
; Samples, Paula, the timer, the CLI.
; ---------------------------------------------------------------------------

; Find the samples in chip RAM. LoadSeg was asked for chip memory for their
; hunk; if it put them elsewhere, copy them into chip RAM from AllocMem.
; d0: 0 when there is no chip memory for them.
samples_to_chip:
        lea     samples,a1
        move.l  a1,samples_base
        move.l  a1,STATUS+ST_SAMPLES.w
        jsr     _LVOTypeOfMem(a6)
        btst    #1,d0                   ; MEMF_CHIP
        bne.s   .ok
        move.l  #samples_end-samples,d0
        moveq   #MEMF_CHIP,d1
        jsr     _LVOAllocMem(a6)
        tst.l   d0
        beq.s   .out
        move.l  d0,samples_base
        move.l  d0,STATUS+ST_SAMPLES.w
        move.l  #1,STATUS+ST_COPIED.w
        move.l  d0,a1
        lea     samples,a0
        move.l  #(samples_end-samples)/2,d1
.copy:  move.w  (a0)+,(a1)+
        subq.l  #1,d1
        bne.s   .copy
.ok:    moveq   #1,d0
.out:   rts

voices_silent:
        lea     voices,a0
        moveq   #VOICES-1,d0
.loop:  move.w  #-1,V_KEY(a0)
        move.w  #-1,V_SAMPLE(a0)
        move.w  #-1,V_PSAMPLE(a0)
        lea     V_SIZE(a0),a0
        dbf     d0,.loop
        rts

take_audio:
        lea     custom,a5
        move.w  #$000f,DMACON(a5)       ; audio DMA off
        move.w  #$0780,INTENA(a5)       ; audio interrupts off
        move.w  #$0780,INTREQ(a5)
        moveq   #VOICES-1,d2
        lea     AUD0LC(a5),a0
.vol:   move.w  #0,8(a0)
        lea     $10(a0),a0
        dbf     d2,.vol
        moveq   #0,d2
        lea     audints,a2
        lea     old_audio,a3
.vec:   moveq   #INTB_AUD0,d0
        add.l   d2,d0
        move.l  a2,a1
        jsr     _LVOSetIntVector(a6)
        move.l  d0,(a3)+
        lea     IS_SIZE(a2),a2
        addq.l  #1,d2
        cmp.l   #VOICES,d2
        bne.s   .vec
        rts

give_audio:
        lea     custom,a5
        move.w  #$000f,DMACON(a5)
        move.w  #$0780,INTENA(a5)
        move.w  #$0780,INTREQ(a5)
        lea     AUD0LC(a5),a0
        moveq   #VOICES-1,d2
.vol:   move.w  #0,8(a0)
        lea     $10(a0),a0
        dbf     d2,.vol
        moveq   #0,d2
        lea     old_audio,a3
.vec:   moveq   #INTB_AUD0,d0
        add.l   d2,d0
        move.l  (a3)+,a1
        jsr     _LVOSetIntVector(a6)
        addq.l  #1,d2
        cmp.l   #VOICES,d2
        bne.s   .vec
        rts

; Take CIA-B timer A and start it as a 1 kHz interrupt. d0: 0 on success.
take_timer:
        clr.w   timer_busy
        lea     ciabname(pc),a1
        jsr     _LVOOpenResource(a6)
        move.l  d0,ciabbase
        beq.s   .busy
        move.l  d0,a6
        moveq   #CIAICRB_TA,d0
        lea     ciaint,a1
        jsr     _LVOAddICRVector(a6)
        tst.l   d0
        bne.s   .taken
        move.b  ciabcra,d0
        and.b   #$c0,d0                 ; stopped, continuous; keep bits 6 and 7
        move.b  d0,ciabcra
        move.b  #TIMER_LATCH&$ff,ciabtalo
        move.b  #TIMER_LATCH>>8,ciabtahi
        or.b    #$11,d0                 ; load the latch and start
        move.b  d0,ciabcra
        move.w  #$81,d0                 ; enable the timer A interrupt
        jsr     _LVOAbleICR(a6)
        move.l  ExecBase.w,a6
        moveq   #0,d0
        rts
.taken: move.l  ExecBase.w,a6
.busy:  move.w  #1,timer_busy
        moveq   #1,d0
        rts

give_timer:
        move.b  ciabcra,d0
        and.b   #$c0,d0
        move.b  d0,ciabcra              ; stop it
        move.l  ciabbase,a6
        moveq   #CIAICRB_TA,d0
        lea     ciaint,a1
        jsr     _LVORemICRVector(a6)
        move.l  ExecBase.w,a6
        rts

; Print the RawDoFmt format a0 with the arguments a1 to the CLI.
print:
        move.l  a3,-(sp)
        lea     textbuf,a3
        bsr     format
        lea     textbuf,a0
        bsr     write_text
        move.l  (sp)+,a3
        rts

; Format a0 with the arguments a1 into the buffer at a3 (RawDoFmt).
format:
        movem.l a2-a3/a6,-(sp)
        move.l  ExecBase.w,a6
        lea     putchar(pc),a2
        jsr     _LVORawDoFmt(a6)
        movem.l (sp)+,a2-a3/a6
        rts

; Write the C string a0 to the CLI.
write_text:
        movem.l d2-d3/a6,-(sp)
        move.l  a0,d2
        moveq   #-1,d3
.len:   addq.l  #1,d3
        tst.b   (a0)+
        bne.s   .len
        tst.l   d3
        beq.s   .out
        move.l  dosbase,a6
        jsr     _LVOOutput(a6)
        move.l  d0,d1
        beq.s   .out
        jsr     _LVOWrite(a6)
.out:   movem.l (sp)+,d2-d3/a6
        rts

; Write the last piece's results, if they wait. Writing to the CLI takes
; several frames, so a switch starts the next piece first.
flush_results:
        tst.w   results_pending
        beq.s   .out
        clr.w   results_pending
        lea     results_buf,a0
        bsr     write_text
.out:   rts

putchar:
        move.b  d0,(a3)+
        rts

; ---------------------------------------------------------------------------
; The 1 kHz interrupt: one millisecond of the player.
; ---------------------------------------------------------------------------

cia_handler:
        bsr     read_timer              ; how late exec called us
        move.l  #TIMER_LATCH,d1
        sub.l   d0,d1
        add.l   d1,STATUS+ST_ENTRY_E.w
        move.l  now,d0                  ; most milliseconds have nothing to do
        tst.w   fading
        bne.s   .work
        tst.w   score_done
        bne.s   .work
        cmp.l   score_time,d0
        bcc.s   .work                   ; an event is due
        cmp.l   next_tick,d0
        beq.s   .work
        addq.l  #1,now
        bra.s   .out
.work:  movem.l d2-d7/a2-a4,-(sp)
        lea     custom,a5
        bsr.s   millisecond
        movem.l (sp)+,d2-d7/a2-a4
.out:   bsr     read_timer
        move.l  #TIMER_LATCH,d1
        sub.l   d0,d1                   ; E-clock ticks since the timer ran out
        bpl.s   .pos
        moveq   #0,d1
.pos:   add.l   d1,frame_e
        add.l   d1,isr_e
        cmp.l   STATUS+ST_MAX_MS_E.w,d1
        bls.s   .done
        move.l  d1,STATUS+ST_MAX_MS_E.w
.done:  move.l  now,STATUS+ST_MS.w
        rts

millisecond:
        tst.w   finished
        bne.s   .out
        tst.w   score_done
        beq.s   .run
        bsr     any_active
        bne.s   .run
        move.w  #1,finished
        bra.s   .out
.run:   bsr     step_fades
        tst.w   score_done
        bne.s   .tick
        bsr     read_events
.tick:  move.l  now,d0
        cmp.l   next_tick,d0
        bne.s   .next
        bsr     tick
.next:  addq.l  #1,now
.out:   rts

; d0: the count of CIA-B timer A. Uses d1.
read_timer:
        moveq   #0,d0
        move.b  ciabtahi,d0
        move.b  ciabtalo,d1
        cmp.b   ciabtahi,d0
        beq.s   .same
        move.b  ciabtahi,d0             ; the low byte wrapped between the reads
        move.b  ciabtalo,d1
.same:  lsl.w   #8,d0
        move.b  d1,d0
        rts

; Z clear when some voice is sounding or waiting.
any_active:
        lea     voices,a0
        moveq   #VOICES-1,d0
.loop:  tst.w   V_KEY(a0)
        bpl.s   .yes
        lea     V_SIZE(a0),a0
        dbf     d0,.loop
        moveq   #0,d0
        rts
.yes:   moveq   #1,d0
        rts

; Step every fading voice: 3/4, 2/4, 1/4 of its volume, then stop, then
; start the waiting note.
step_fades:
        lea     voices,a3
        moveq   #0,d7
.loop:  tst.w   V_FADE(a3)
        beq.s   .next
        subq.w  #1,V_FADE(a3)
        move.w  V_FADE(a3),d0
        bne.s   .fade
        subq.w  #1,fading               ; this one starts now
.fade:
        cmp.w   #2,d0
        bcs.s   .low
        subq.w  #1,d0
        mulu    V_FROM(a3),d0
        lsr.w   #2,d0
        move.w  d0,V_OUT(a3)
        bsr     set_volume
        bra.s   .next
.low:   tst.w   d0
        beq.s   .start
        clr.w   V_OUT(a3)
        bsr     stop_voice
        bra.s   .next
.start: bsr     start_voice
.next:  lea     V_SIZE(a3),a3
        addq.w  #1,d7
        cmp.w   #VOICES,d7
        bne.s   .loop
        rts

; Paula volume d0 for voice d7. Uses d1, a0.
set_volume:
        move.w  d7,d1
        lsl.w   #4,d1
        lea     AUD0LC(a5),a0
        move.w  d0,8(a0,d1.w)
        rts

; Start voice a3 (number d7) on Paula: the whole sample, then its loop from
; the audio interrupt. Uses d0-d1, a0-a1.
start_voice:
        move.w  V_VOLUME(a3),d0
        lsr.w   #8,d0
        move.w  d0,V_OUT(a3)
        move.w  V_SAMPLE(a3),d1
        mulu    #S_SIZE,d1
        lea     sampletab,a0
        add.l   d1,a0
        move.w  d7,d1
        lsl.w   #4,d1
        lea     AUD0LC(a5),a1
        add.w   d1,a1
        move.l  samples_base,d1
        add.l   S_OFFSET(a0),d1
        move.l  d1,(a1)                 ; AUDxLC
        move.w  S_WORDS(a0),4(a1)       ; AUDxLEN
        move.w  V_PERIOD(a3),6(a1)      ; AUDxPER
        move.w  d0,8(a1)                ; AUDxVOL
        move.w  d7,d1
        lsl.w   #3,d1
        lea     loops,a1
        add.w   d1,a1
        move.l  samples_base,d1
        add.l   S_LOOP(a0),d1
        move.l  d1,(a1)+
        move.w  S_LOOPWORDS(a0),(a1)
        move.w  V_SAMPLE(a3),V_PSAMPLE(a3)  ; for the scopes
        move.w  V_PERIOD(a3),V_PPERIOD(a3)
        move.l  now,V_PSTART(a3)
        move.w  #$0080,d0
        lsl.w   d7,d0
        move.w  d0,INTREQ(a5)           ; nothing stale
        or.w    #$8000,d0
        move.w  d0,INTENA(a5)
        moveq   #1,d0
        lsl.w   d7,d0
        or.w    #$8200,d0
        move.w  d0,DMACON(a5)
        rts

; Stop voice a3 (number d7) on Paula. Uses d0, a0.
stop_voice:
        move.w  #-1,V_PSAMPLE(a3)
        moveq   #1,d0
        lsl.w   d7,d0
        move.w  d0,DMACON(a5)
        move.w  #$0080,d0
        lsl.w   d7,d0
        move.w  d0,INTENA(a5)
        move.w  d7,d0
        lsl.w   #4,d0
        lea     AUD0LC(a5),a0
        move.w  #0,8(a0,d0.w)
        rts

; Read the score's events up to this millisecond. Keeps a2 and d6.
read_events:
        move.l  score_ptr,a2
        move.l  now,d6
.next:  cmp.l   score_time,d6
        bcs     .done                   ; the next event is later
        moveq   #0,d0
        move.b  (a2)+,d0
        cmp.b   #$58,d0
        bcs.s   .on
        cmp.b   #$80,d0
        bcs.s   .short
        cmp.b   #$d8,d0
        bcs.s   .off
        cmp.b   #$e0,d0
        beq.s   .wait8
        cmp.b   #$e1,d0
        beq.s   .wait16
        cmp.b   #$f0,d0
        beq.s   .down
        cmp.b   #$f1,d0
        beq.s   .up
        move.w  #1,score_done           ; $ff, the end
        bra.s   .done
.on:    moveq   #0,d1
        move.b  (a2)+,d1
        bsr     note_on
        bra     .next
.short: sub.w   #$57,d0
        add.l   d0,score_time
        bra     .next
.wait8: move.b  (a2)+,d0
        add.l   d0,score_time
        bra     .next
.wait16:
        move.b  (a2)+,d0
        lsl.w   #8,d0
        move.b  (a2)+,d0
        add.l   d0,score_time
        bra     .next
.off:   sub.b   #$80,d0
        lea     voices,a0
        moveq   #VOICES-1,d1
.offv:  cmp.w   V_KEY(a0),d0
        bne.s   .offn
        clr.w   V_KEYDN(a0)
.offn:  lea     V_SIZE(a0),a0
        dbf     d1,.offv
        bra     .next
.down:  move.w  #1,pedal
        bra     .next
.up:    clr.w   pedal
        bra     .next
.done:  move.l  a2,score_ptr
        rts

; Note on: key d0, velocity d1. Keeps a2 and d6.
note_on:
        addq.w  #1,serial
        cmp.w   #1,serial
        bne.s   .later
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_FIRST_NOTE_AT.w  ; for the host
        move.l  now,STATUS+ST_FIRST_NOTE_MS.w
.later:
        move.w  d0,d2                   ; key
        mulu    #K_SIZE,d0
        lea     keys,a4
        add.l   d0,a4                   ; a4: the key's sound
        bsr     choose_voice            ; a3, d7
        lea     velocity,a0
        add.w   d1,d1
        move.w  0(a0,d1.w),d3
        mulu    K_LEVEL(a4),d3
        lsr.l   #8,d3
        cmp.l   #256,d3
        bcc.s   .loud
        move.l  #256,d3
.loud:  tst.w   V_FADE(a3)
        bne.s   .set                    ; replaces the waiting note
        tst.w   V_KEY(a3)
        bmi.s   .set                    ; a free voice
        move.w  #FADE_MS,V_FADE(a3)     ; cut a sounding note
        addq.w  #1,fading
        move.w  V_OUT(a3),V_FROM(a3)
.set:   move.w  d2,V_KEY(a3)
        move.w  K_SAMPLE(a4),V_SAMPLE(a3)
        move.w  K_PERIOD(a4),V_PERIOD(a3)
        move.w  d3,V_VOLUME(a3)
        move.w  serial,V_SERIAL(a3)
        move.w  #1,V_KEYDN(a3)
        clr.w   V_TICKS(a3)
        tst.w   V_FADE(a3)
        bne.s   .out
        bsr     start_voice
.out:   rts

; The voice for key d2: the one sounding it, else the lowest free one, else
; the quietest whose key is up, else the quietest; the oldest on a tie.
; a3: the voice, d7: its number. Uses d0, d3, a1.
choose_voice:
        lea     voices,a3
        moveq   #0,d7
.same:  cmp.w   V_KEY(a3),d2
        beq.s   .found
        lea     V_SIZE(a3),a3
        addq.w  #1,d7
        cmp.w   #VOICES,d7
        bne.s   .same
        lea     voices,a3
        moveq   #0,d7
.free:  tst.w   V_KEY(a3)
        bmi.s   .found
        lea     V_SIZE(a3),a3
        addq.w  #1,d7
        cmp.w   #VOICES,d7
        bne.s   .free
        lea     voices,a3
        moveq   #0,d7
        lea     V_SIZE(a3),a1
        moveq   #1,d3
.steal: move.w  V_KEYDN(a1),d0
        cmp.w   V_KEYDN(a3),d0
        bcs.s   .better
        bne.s   .worse
        move.w  V_VOLUME(a1),d0
        cmp.w   V_VOLUME(a3),d0
        bcs.s   .better
        bne.s   .worse
        move.w  V_SERIAL(a1),d0
        cmp.w   V_SERIAL(a3),d0
        bcc.s   .worse
.better:
        move.l  a1,a3
        move.w  d3,d7
.worse: lea     V_SIZE(a1),a1
        addq.w  #1,d3
        cmp.w   #VOICES,d3
        bne.s   .steal
.found: rts

; A frame tick: decay every sounding voice, log, count the frame.
tick:
        lea     voices,a3
        moveq   #0,d7
.loop:  tst.w   V_KEY(a3)
        bmi.s   .log
        tst.w   V_FADE(a3)
        bne.s   .log
        bsr     decay
.log:
        if      LOG
        bsr     log_voice
        endif
        lea     V_SIZE(a3),a3
        addq.w  #1,d7
        cmp.w   #VOICES,d7
        bne.s   .loop
        move.l  frame_e,d0
        add.l   d0,STATUS+ST_TOTAL_E.w
        cmp.l   STATUS+ST_MAX_FRAME_E.w,d0
        bls.s   .max
        move.l  d0,STATUS+ST_MAX_FRAME_E.w
.max:   clr.l   frame_e
        addq.l  #1,STATUS+ST_FRAMES.w
        add.l   #16,next_tick           ; 1000 / 60 = 16 rem 40
        add.w   #40,tick_rem
        cmp.w   #60,tick_rem
        bcs.s   .out
        sub.w   #60,tick_rem
        addq.l  #1,next_tick
.out:   rts

; Decay voice a3 (number d7) by one tick. Uses d0-d1, a0.
decay:
        move.w  V_KEY(a3),d0
        mulu    #K_SIZE,d0
        lea     keys,a0
        add.l   d0,a0
        move.w  V_KEYDN(a3),d1
        or.w    pedal,d1
        addq.w  #1,V_TICKS(a3)
        tst.w   d1
        beq.s   .rel
        move.w  V_TICKS(a3),d0
        cmp.w   K_ATTACK(a0),d0
        bls.s   .out                    ; the recorded attack still fades by itself
        move.w  K_HELD(a0),d0
        bra.s   .apply
.rel:   move.w  K_RELEASE(a0),d0
.apply: mulu    V_VOLUME(a3),d0
        swap    d0
        move.w  d0,V_VOLUME(a3)
        lsr.w   #8,d0
        bne.s   .sound
        move.w  #-1,V_KEY(a3)
        move.w  #-1,V_SAMPLE(a3)
        clr.w   V_PERIOD(a3)
        clr.w   V_VOLUME(a3)
        clr.w   V_KEYDN(a3)
        clr.w   V_OUT(a3)
        bra     stop_voice
.sound: cmp.w   V_OUT(a3),d0
        beq.s   .out
        move.w  d0,V_OUT(a3)
        bra     set_volume
.out:   rts

        if      LOG
; One voice's log record: key, sample, period, volume, Paula volume.
log_voice:
        move.l  log_ptr,a0
        cmp.l   log_end,a0
        bcc.s   .full
        move.b  V_KEY+1(a3),(a0)+
        move.b  V_SAMPLE+1(a3),(a0)+
        move.w  V_PERIOD(a3),(a0)+
        move.b  V_VOLUME(a3),(a0)+
        move.b  V_OUT+1(a3),(a0)+
        move.l  a0,log_ptr
        sub.l   STATUS+ST_LOGBASE.w,a0
        move.l  a0,STATUS+ST_LOGBYTES.w
.full:  rts
        endif

; Audio interrupt for channel is_Data (a1): Paula has taken the start and
; length of the whole sample, so give it the loop's for when the sample
; ends, and turn this channel's interrupt off until its next note.
; Called with a0 = custom chips; d0-d1/a0-a1/a5 are free.
aud_handler:
        move.l  a1,-(sp)
        bsr     read_timer
        move.l  (sp)+,a1
        move.w  d0,-(sp)                ; the count on entry
        move.l  a1,d1                   ; the channel
        move.w  d1,d0
        lsl.w   #3,d0
        lea     loops,a1
        add.w   d0,a1
        move.w  d1,d0
        lsl.w   #4,d0
        lea     AUD0LC(a0),a5
        add.w   d0,a5
        move.l  (a1)+,(a5)              ; AUDxLC: the loop
        move.w  (a1),4(a5)              ; AUDxLEN
        move.w  #$0080,d0
        lsl.w   d1,d0
        move.w  d0,INTENA(a0)
        move.w  d0,INTREQ(a0)
        bsr     read_timer
        move.w  (sp)+,d1
        sub.w   d0,d1                   ; ticks spent (the timer counts down)
        bpl.s   .pos
        add.w   #TIMER_PERIOD,d1
.pos:   ext.l   d1
        add.l   d1,frame_e
        add.l   d1,isr_e
        rts



        SCREEN_TABLES                   ; line_tops, voice_scope_left (screen.i)

dosname:        dc.b "dos.library",0
gfxname:        dc.b "graphics.library",0
intname_lib:    dc.b "intuition.library",0
ciabname:       dc.b "ciab.resource",0
index_name:     dc.b "scores/index",0
picture_name:   dc.b "title.ilbm",0
menu_keys:      dc.b "123456789ABCDEGHIJKLMNOPRSTUVWXYZ"
banner:         dc.b "EXP-004, the expressive piano: %ld pieces.",10
                dc.b "Samples: %ld bytes at $%lx in chip RAM,",10
                dc.b "%s.",10,0
loaded:         dc.b "where LoadSeg put them",0
copied:         dc.b "copied there from elsewhere",0
loading_text:   dc.b 10,"%s",10,0
scores_text:    dc.b "Scores: %ld bytes, loaded in %ld vertical blanks.",10,0
playing_text:   dc.b "Score: %ld bytes at $%lx.",10
                dc.b "Free memory: %ld bytes chip, %ld other.",10,0
results:        dc.b "Done: %ld frames (1/60 s). Player time a frame",10
                dc.b "in E-clock ticks (11932 a frame): average %ld,",10
                dc.b "worst %ld. Worst millisecond: %ld ticks of 716.",10,0
stopped:        dc.b "Stopped after %ld frames. Player time a frame",10
                dc.b "in E-clock ticks (11932 a frame): average %ld,",10
                dc.b "worst %ld. Worst millisecond: %ld ticks of 716.",10,0
busy_text:      dc.b "CIA-B timer A is in use; nothing played.",10,0
memory_text:    dc.b "Not enough memory.",10,0
no_index_text:  dc.b "Cannot read scores/index: run piano from the disk's root.",10,0
no_score_text:  dc.b "Cannot load that score.",10,0
no_picture_text: dc.b "Cannot read title.ilbm: run piano from the disk's root.",10,0
bad_picture_text: dc.b "title.ilbm is not a 320x200 4-plane uncompressed ILBM.",10,0
no_screen_text: dc.b "Cannot open the screen.",10,0
        if      LOG
log_text:       dc.b "Voice log: %ld bytes at $%lx.",10,0
        endif
intname:        dc.b "EXP-004 piano",0
        even

        section tables,data

newscreen:      dc.w 0,0,SCREEN_WIDTH,SCREEN_HEIGHT,DEPTH     ; left, top, size, depth
                dc.b 0,1                                      ; detail and block pens
                dc.w 0                                        ; lowres
                dc.w CUSTOMSCREEN|SCREENQUIET                 ; no title bar drawn
                dc.l 0,0,0,0                                  ; font, title, gadgets, bitmap
newwindow:      dc.w 0,0,SCREEN_WIDTH,SCREEN_HEIGHT
                dc.b 0,1
                dc.l MOUSEBUTTONS|RAWKEY
                dc.l BACKDROP|BORDERLESS|ACTIVATE|RMBTRAP|SIMPLE_REFRESH|NOCAREREFRESH
                dc.l 0,0,0                                    ; gadgets, checkmark, title
                dc.l 0                                        ; the screen (nw_Screen, 30)
                dc.l 0                                        ; bitmap
                dc.w 0,0,0,0                                  ; size limits
                dc.w CUSTOMSCREEN
ciaint:         dc.l 0,0
                dc.b NT_INTERRUPT,0
                dc.l intname,0,cia_handler
vbint:          dc.l 0,0
                dc.b NT_INTERRUPT,0
                dc.l intname,0,vb_handler
audints:
        rept    VOICES
                dc.l 0,0
                dc.b NT_INTERRUPT,0
                dc.l intname,REPTN,aud_handler
        endr
        include "menu.i"                ; ROTATE_S, and piece_keys: each piece's raw key code
        even
keys:           incbin "keys.bin"
sampletab:      incbin "samples.tab"
velocity:       incbin "velocity.bin"
        even

        section samples,data_c

samples:        incbin "samples.bin"
samples_end:

        section state,bss

bss_start:
piece_state:                            ; cleared before each piece
voices:         ds.b V_SIZE*VOICES
loops:          ds.b 8*VOICES           ; loop start (long) and length (word) per channel
now:            ds.l 1
next_tick:      ds.l 1
score_time:     ds.l 1
frame_e:        ds.l 1
tick_rem:       ds.w 1
serial:         ds.w 1
pedal:          ds.w 1
score_done:     ds.w 1
finished:       ds.w 1
fading:         ds.w 1                  ; voices waiting for a fade
piece_state_end:
isr_e:          ds.l 1                  ; E-clock ticks in the interrupts, never cleared
score_ptr:      ds.l 1
old_audio:      ds.l VOICES
samples_base:   ds.l 1
dosbase:        ds.l 1
gfxbase:        ds.l 1
intbase:        ds.l 1
ciabbase:       ds.l 1
args:           ds.l 1
args_len:       ds.l 1
pieces:         ds.l 1
files:          ds.l MAX_PIECES
titles:         ds.l MAX_PIECES
index_mem:      ds.l 1
index_bytes:    ds.l 1
score_mem:      ds.l 1                  ; the score playing
score_bytes:    ds.l 1
score_table:    ds.l 2*MAX_PIECES       ; each piece's score: memory and size
log_ptr:        ds.l 1
log_end:        ds.l 1
fmt_args:       ds.l 4
screen:         ds.l 1
window:         ds.l 1
planes:         ds.l DEPTH
picture_mem:    ds.l 1                  ; title.ilbm while it is read
picture_bytes:  ds.l 1
body:           ds.l 1                  ; its BODY
band_copy:      ds.l 1                  ; the scope band's four planes
trace_table:    ds.l 1                  ; 65 volumes x 256 sample bytes
taken:          ds.b C_SIZE*VOICES
palette:        ds.w 16
row_offsets:    ds.w SCREEN_HEIGHT
timer_busy:     ds.w 1
playing:        ds.w 1
drawn:          ds.w 1                  ; 1 when old_points are on the screen
band_first:     ds.w 1                  ; the first beam line no unit may start on
band_last:      ds.w 1                  ; the band's last line on the display
unit_trace:     ds.l 1
old_points:     ds.w VOICES*VOICE_SCOPE_WIDTH+MIX_SCOPE_WIDTH
front:          ds.l 1                  ; the traces being drawn: voices, then the mix
back:           ds.l 1                  ; the traces being made
draw_sum:       ds.l 1
make_sum:       ds.l 1
made:           ds.w 1
trace_sets:     ds.b 2*MIX_SCOPE_WIDTH*(VOICES+1)
watch_count:    ds.w 1
watch_ms:       ds.l 1
watch_isr:      ds.l 1
task:           ds.l 1                  ; this program's task, for the alarm
alarm_mask:     ds.l 1
alarm_at:       ds.l 1                  ; the vertical blank count it goes off at
alarm_on:       ds.w 1
rotate_frames:  ds.l 1                  ; ROTATE_S in vertical blanks
clock_on:       ds.w 1                  ; 1 while the vertical blank server is in
alarm_bit:      ds.b 1
led_start:      ds.b 1                  ; ciaapra's LED bit when the program started
                cnop 0,4
fib:            ds.b 260                ; a FileInfoBlock, longword aligned
textbuf:        ds.b 512
results_buf:    ds.b 512                ; a piece's results, until flush_results
results_pending: ds.w 1
                ds.w 1
bss_end:
