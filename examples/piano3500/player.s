; player.s: EXP-006's A3500 piano player, the 68030 counterpart of
; tools/amiga_env/piano/player3500.py.
;
; For the A3500 (68030 at 25 MHz, ECS, NTSC, Kickstart 2.04 or later) with
; about 12 MB of fast RAM free. Two ways to run it, from the folder that
; holds its files:
;
;   player           the screen: the title picture with the song list (as
;                    EXP-004's A500 disk shows it). A click on a piece's
;                    line, or its key (1 to 9, then A to Z without F and Q),
;                    plays it, or switches to it. Left alone it plays the
;                    pieces in turn: the first ROTATE_S seconds after the
;                    screen appears, and each next one ROTATE_S seconds after
;                    the last ends. Space stops and holds the rotation until
;                    the next choice; F switches the audio filter (and the
;                    power LED, and the screen's filter light); Esc or Q
;                    quits.
;   player RUN NAME  one piece, scores/NAME.score, with no screen; RUN is a
;                    number the host waits for.
;
; It loads piano.tab and samples.bin (tools/amiga_env/piano/m68k3500.py),
; and for the screen title.ilbm and scores/index (one line a piece: its
; name, a space, its title) with every score at the start. The test build
; (LOG=1) writes each piece's voice log to logs/NAME.log as it plays, and
; when a piece ends, the status block to logs/NAME.stat.
;
; The host passes the model's constants with -D (amiga-env piano3500-run):
; VOICES, BLOCK, PERIOD, FADE_STEP, STOP_VOLUME, LIMIT_BLOCKS, OUTPUT_SHIFT,
; QUEUE and LOG. They are not written here, so they cannot drift from the
; model's. screen.i and menu.i (made from EXP-004's screen by the host)
; give the list's rows, the colours and the piece keys; scopes.i (from the
; recipe's [scopes]) gives the two scopes' columns.
;
; How it plays. Paula plays blocks of BLOCK samples at period PERIOD from
; two buffers in chip RAM, four channels: left high byte (0, volume 64),
; right high (1, 64), right low bits (2, volume 1), left low bits (3, 1).
; Channel 0's audio interrupt comes when Paula takes a block; the handler
; points the channels at the other buffer and makes the next block into it,
; in player3500's order:
;
;   1. decay every voice whose note started before the block;
;   2. the score's events that fall in the block, each at its sample
;      (ms * 3,579,545 / 128,000);
;   3. mix every voice into 32-bit sums, in runs split where a queued change
;      (a cut's fade level, or a note's start) falls;
;   4. shift each sum right by OUTPUT_SHIFT, clamp it to 16 bits, split it
;      into the four channels' bytes, and add it to the block's checksum;
;   5. the test build: the block's record into the voice log;
;   6. decide whether there is another block, as the model does.
;
; Nothing the task does changes what the interrupt makes. The task draws
; the screen: the playing piece's line in gold (a user copper list), and
; two scopes in the floor band, side by side in the middle of the screen:
; the left output channel and the right, from the block Paula is playing.
; The scopes go in a cycle of five steps: make the traces, then draw each
; of four units (each scope in two halves). One step is done after a
; vertical blank, and at most one a block, so the screen adds one step's
; work to a block at most.
;
; Status block at $100 (longs), read by the host: see STATUS below.

        machine 68030

        ifnd    VOICES
        fail    "assemble with the model's constants (amiga-env piano3500-run)"
        endif

_LVOForbid          equ -132
_LVOPermit          equ -138
_LVOSetIntVector    equ -162
_LVOAddIntServer    equ -168
_LVORemIntServer    equ -174
_LVOAllocMem        equ -198
_LVOFreeMem         equ -210
_LVOAvailMem        equ -216
_LVOFindTask        equ -294
_LVOSetSignal       equ -306
_LVOWait            equ -318
_LVOSignal          equ -324
_LVOAllocSignal     equ -330
_LVOFreeSignal      equ -336
_LVOGetMsg          equ -372
_LVOReplyMsg        equ -378
_LVOCloseLibrary    equ -414
_LVOOpenDevice      equ -444
_LVOCloseDevice     equ -450
_LVOOpenLibrary     equ -552
_LVOCacheControl    equ -648
_LVOOpen            equ -30         ; dos
_LVOClose           equ -36
_LVORead            equ -42
_LVOWrite           equ -48
_LVOSeek            equ -66
_LVOReadEClock      equ -60         ; timer.device
_LVOLoadRGB4        equ -192        ; graphics
_LVOSetRGB4         equ -288        ; graphics
_LVOWaitTOF         equ -270
_LVOCBump           equ -366
_LVOCMove           equ -372
_LVOCWait           equ -378
_LVOFreeCopList     equ -546
_LVOUCopperListInit equ -594
_LVOCloseScreen     equ -66         ; intuition
_LVOCloseWindow     equ -72
_LVOOpenScreen      equ -198
_LVOOpenWindow      equ -204
_LVOShowTitle       equ -288
_LVOMakeScreen      equ -384
_LVORethinkDisplay  equ -396

ExecBase        equ 4
VBlankFrequency equ 530
MEMF_PUBLIC     equ 1
MEMF_CHIP       equ 2
MEMF_FAST       equ 4
MEMF_CLEAR      equ $10000
MEMF_LARGEST    equ $20000
MODE_OLDFILE    equ 1005
MODE_NEWFILE    equ 1006
OFFSET_BEGINNING equ -1
OFFSET_END      equ 1
CACRF_EnableD   equ $100
INTB_VERTB      equ 5
INTB_AUD0       equ 7
INTF_AUD0       equ $0080
NT_INTERRUPT    equ 2
IO_DEVICE       equ 20
IOTV_SIZE       equ 40

; Intuition and graphics structures (as in EXP-004's player)
sc_ViewPort     equ 44
sc_BitMap       equ 184
bm_Planes       equ 8
vp_UCopIns      equ 20
vp_DyOffset     equ 30
gb_ActiView     equ 34
v_DyOffset      equ 12
ucl_FirstCopList equ 4
ucl_SIZEOF      equ 12
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
KEY_ESC         equ $45
KEY_Q           equ $10
KEY_SPACE       equ $40
KEY_F           equ $23

CUSTOM          equ $dff000
VPOSR           equ $004
DMACON          equ $096
INTENA          equ $09a
INTREQ          equ $09c
AUD0LC          equ $0a0
AUDLEN          equ 4
AUDPER          equ 6
AUDVOL          equ 8
COLOR13         equ CUSTOM+$19a
ciaapra         equ $bfe001         ; bit 1: the power LED and the audio filter, 0 = on
LED_BIT         equ 1

BLOCK_E         equ BLOCK*PERIOD/5  ; E-clock ticks a block (13,107.2 rounded down)
LOG_VOICE       equ 14
LOG_BLOCK       equ 8+VOICES*LOG_VOICE
LOG_HALF_BLOCKS equ 64
LOG_HALF        equ LOG_HALF_BLOCKS*LOG_BLOCK
LOG_HEADER      equ 16
SILENT          equ $ff
MAX_PIECES      equ 33

; The screen and the scopes; screen.i (made with the picture) has the rows.
SCREEN_WIDTH    equ 320
SCREEN_HEIGHT   equ 200
DEPTH           equ 4
ROW_BYTES       equ SCREEN_WIDTH/8
PICTURE_BYTES   equ ROW_BYTES*SCREEN_HEIGHT*DEPTH
SCOPE_HALF      equ 21          ; a trace: at most this from the centre
SCOPE_SHIFT     equ 2           ; a channel's high byte >> this
SCOPE_STRIDE    equ 6           ; output samples a column
UNITS           equ 4           ; drawing units: each scope in two halves
STEPS           equ UNITS+1     ; a cycle: make the traces, then draw each unit
BEAM_GUARD      equ 64          ; lines above the band a unit may not start on

        include "screen.i"      ; LIST_*, LINE_*, colours, SCOPE_*, line_tops
        include "scopes.i"      ; STEREO_LEFT_L, STEREO_LEFT_R, STEREO_WIDTH
        include "light.i"       ; FILTER_LIGHT_REGISTER, FILTER_LIGHT_ON, FILTER_LIGHT_OFF
BAND_BYTES      equ ROW_BYTES*SCOPE_ROWS
HALF_WIDTH      equ STEREO_WIDTH/2  ; a unit: half a scope, ending on a byte boundary
        if      STEREO_WIDTH*SCOPE_STRIDE>BLOCK
        fail    "a scope's columns would read past the block"
        endif

; Status block (longs at $100).
STATUS          equ $100
ST_MAGIC        equ 0           ; 'P35P'
ST_STATE        equ 4           ; 0 loading, 1 playing, 2 done, 3 waiting for a choice, -1 failed
ST_ERROR        equ 8           ; why it failed (ERR_ below)
ST_RUN          equ 12          ; RUN from the command line
ST_BLOCKS       equ 16          ; blocks made (this piece, from here to ST_QUEUE_FULL)
ST_TOTAL_E      equ 20          ; E-clock ticks making them
ST_WORST_E      equ 24          ; the most for one block
ST_OVERRUNS     equ 28          ; blocks that took longer than a block lasts
ST_NOTES        equ 32
ST_STEALS       equ 36
ST_RESTRIKES    equ 40
ST_CLAMPED      equ 44          ; output values clamped
ST_LOG_BYTES    equ 48          ; voice log bytes written to the file
ST_LOG_OVERRUNS equ 52          ; log blocks lost: both buffers were full
ST_QUEUE_FULL   equ 56          ; changes lost: a voice's queue was full
ST_EFREQ        equ 60          ; E-clock ticks a second
ST_CACR         equ 64          ; CacheControl's bits found at the start
ST_SAMPLES      equ 68          ; where the samples are
ST_MODE         equ 72          ; 1 with the screen
ST_PIECE        equ 76          ; the piece playing or last played, from 0
ST_PIECES       equ 80          ; pieces in the index
ST_PLAYED       equ 84          ; pieces played to their end or stopped
ST_STOPPED      equ 88          ; 1 when the last piece was stopped
ST_STARTS       equ 92          ; pieces started
ST_ROTATED      equ 96          ; of those, started by the rotation
ST_NEXT         equ 100         ; the piece the rotation plays next
ST_ROTATE_AT    equ 104         ; when, -1 while it waits for a choice
ST_HIGHLIGHT    equ 108         ; the line in gold, -1 for none
ST_WINDOW       equ 112         ; the backdrop window
ST_KEY          equ 116         ; the last RAWKEY code
ST_KEYS         equ 120
ST_CLICKS       equ 124
ST_CLICK_XY     equ 128         ; x in the high word, y in the low
ST_FILTER_KEYS  equ 132         ; presses of F
; Times are vertical blanks counted from the start of the program.
ST_VBLANKS      equ 136
ST_VBLANK_HZ    equ 140
ST_LOADED_AT    equ 144         ; the samples were in memory
ST_PRELOAD_FRAMES equ 148       ; vertical blanks loading every score
ST_SCREEN_AT    equ 152         ; the screen was up and taking choices
ST_CHOSEN_AT    equ 156         ; the task took the last choice
ST_GOLD_AT      equ 160         ; its line was gold
ST_PLAYING_AT   equ 164         ; its first block was made
ST_FIRST_NOTE_AT equ 168        ; its first note was started
ST_ENDED_AT     equ 172
ST_WORST_TOTAL_E equ 176        ; the most E-clock ticks of mixing and screen work in one block's time
ST_TASK_E       equ 180         ; the screen's E-clock ticks while this piece played
ST_UNITS        equ 184         ; drawing units drawn
ST_UNIT_MAX_E   equ 188         ; the most for one
; Fast RAM free (AvailMem), in bytes: just before samples.bin's AllocMem, and
; when every allocation for the screen is done (with no screen, when the
; piece has begun).
ST_FAST_FREE_BEFORE equ 192     ; in all
ST_FAST_LARGEST_BEFORE equ 196  ; the largest block, which samples.bin must fit
ST_FAST_FREE_AFTER equ 200
ST_FAST_LARGEST_AFTER equ 204
ST_SIZE         equ 208

ERR_DOS         equ 1
ERR_ARGS        equ 2
ERR_TABLES      equ 3
ERR_SAMPLES     equ 4
ERR_SCORE       equ 5
ERR_CHIP        equ 6
ERR_TIMER       equ 7
ERR_LOG         equ 8
ERR_SCOREBYTE   equ 9
ERR_SIGNAL      equ 10
ERR_INDEX       equ 11
ERR_SCREEN      equ 12

; A sound record in piano.tab (12 bytes).
SO_SAMPLE       equ 0
SO_STEP         equ 2
SO_HELD         equ 6
SO_RELEASE      equ 8
SO_ATTACK       equ 10
; A key record (8 bytes) and a sample record (16 bytes).
KE_ROOT         equ 0
KE_LEFT         equ 2
KE_RIGHT        equ 4
SE_OFFSET       equ 0
SE_LENGTH       equ 4
SE_LOOPLEN      equ 12

; A queued change (16 bytes): at a sample, a fade level, or a new tone.
CH_AT           equ 0
CH_Q            equ 4           ; 3, 2 or 1 quarters; 0 for a new tone
CH_SAMPLE       equ 6
CH_STEP         equ 8
CH_LEFT         equ 12
CH_RIGHT        equ 14
CH_SIZE         equ 16

; A voice.
        rsreset
VO_KEY          rs.w 1          ; -1 when free
VO_KEYDOWN      rs.w 1
VO_VOLUME       rs.w 1
VO_PANL         rs.w 1
VO_PANR         rs.w 1
VO_HASTONE      rs.w 1
VO_BLOCKS       rs.l 1
VO_SOUND        rs.l 1          ; its sound record
VO_SERIAL       rs.l 1
VO_START        rs.l 1          ; output sample its note starts on
VO_TQ           rs.w 1          ; the tone: quarters, sample, multipliers
VO_TSAMPLE      rs.w 1
VO_TLEFT        rs.w 1
VO_TRIGHT       rs.w 1
VO_TPHASE       rs.l 1          ; phase, integer part
VO_TFRAC        rs.w 1          ; and fraction
VO_QHEAD        rs.w 1
VO_TSTEP        rs.l 1
VO_QCOUNT       rs.w 1
VO_PADW         rs.w 1
VO_QUEUE        rs.b QUEUE*CH_SIZE
VO_SIZE         rs.b 0

; Variables, at offsets from a5.
        rsreset
EXECBASE        rs.l 1
DOSBASE         rs.l 1
TIMERBASE       rs.l 1
TASK            rs.l 1
SIGMASK         rs.l 1
SIGBIT          rs.l 1
OLDINT          rs.l 1
INSTALLED       rs.l 1
CACR            rs.l 1
SCREEN          rs.l 1          ; 1: the screen; 0: one piece from the command line
TABLES          rs.l 1
TABLES_SIZE     rs.l 1
SAMPLES         rs.l 1
SAMPLES_SIZE    rs.l 1
SCORE           rs.l 1          ; the score playing
ONE_SCORE       rs.l 1          ; the command line's piece's score
ONE_SCORE_SIZE  rs.l 1
CHIPMEM         rs.l 1
LOGMEM          rs.l 1
LOGFILE         rs.l 1
LAYER_OF        rs.l 1
VOLUMES         rs.l 1
SAMPTAB         rs.l 1
KEYTAB          rs.l 1
SOUNDS          rs.l 1
KEY_STRIDE      rs.l 1          ; layers * 12
SCOREP          rs.l 1          ; the next byte of the score
NOW_MS          rs.l 1
NEXT_AT         rs.l 1          ; output sample of the next event
NEXT_KIND       rs.l 1          ; 1 on, 2 off, 3 pedal down, 4 pedal up
NEXT_KEY        rs.l 1
NEXT_VEL        rs.l 1
PENDING         rs.l 1          ; 1 while an event is waiting
LAST_BLOCK      rs.l 1          ; the block of the last event
BLOCKNO         rs.l 1
BEGIN           rs.l 1          ; BLOCKNO * BLOCK
PEDAL           rs.w 1
PADV            rs.w 1
SERIAL          rs.l 1
PLAYING         rs.l 1          ; the buffer being made, 0 or 1
OUTBUF          rs.l 1          ; channel 0's part of the buffer being made
FINISHED        rs.l 1          ; the piece has ended, or was stopped
PIECE_ON        rs.l 1          ; a piece is playing (the task's view)
TASK_E_PENDING  rs.l 1          ; the screen's E-clock ticks since the last block
OFFSET          rs.l 1          ; where the run being mixed starts, in samples
RUNCOUNT        rs.l 1
LOGHALF         rs.l 1          ; the log buffer the interrupt fills, 0 or 1
LOGPOS          rs.l 1          ; bytes in it
LOGFULL0        rs.l 1          ; a full buffer waiting for the task
LOGFULL1        rs.l 1
T0              rs.l 2
T1              rs.l 2
W0              rs.l 2          ; the screen's stopwatch
W1              rs.l 2
W_MIX           rs.l 1          ; ST_TOTAL_E when the stopwatch started
LOAD_FREE       rs.l 1          ; fast RAM free just before load_file's AllocMem
LOAD_LARGEST    rs.l 1          ; and its largest block
RUNNO           rs.l 1
NAMEP           rs.l 1
VOICE_ARRAY     rs.b VOICES*VO_SIZE
SUMS_L          rs.l BLOCK
SUMS_R          rs.l BLOCK
PATH            rs.b 128
VARS_SIZE       rs.b 0

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
        movem.l d2-d7/a2-a6,-(sp)
        lea     vars,a5
        move.l  a0,a2                   ; the command line
        move.l  d0,d2
        move.l  a5,a0
        move.l  #(VARS_SIZE+3)/4-1,d0
.clrv:  clr.l   (a0)+
        subq.l  #1,d0
        bpl.s   .clrv
        lea     screen_vars,a0
        move.l  #(screen_vars_end-screen_vars)/4-1,d0
.clrs:  clr.l   (a0)+
        subq.l  #1,d0
        bpl.s   .clrs
        move.l  ExecBase.w,a6
        move.l  a6,EXECBASE(a5)
        moveq   #-1,d0
        move.l  d0,SIGBIT(a5)
        lea     STATUS.w,a0
        moveq   #ST_SIZE/4-1,d0
.clrst: clr.l   (a0)+
        dbra    d0,.clrst
        move.l  #-1,STATUS+ST_HIGHLIGHT.w
        move.l  #-1,STATUS+ST_ROTATE_AT.w
        move.l  #'P35P',STATUS+ST_MAGIC.w
        move.b  ciaapra,d0              ; the filter as it was, for the end
        and.b   #1<<LED_BIT,d0
        move.b  d0,led_start
        move.w  #1,led_known
        bset    #LED_BIT,ciaapra        ; then off: the piano starts unfiltered (F
                                        ; switches it; the end puts it back)

        bsr     parse_args
        bne     failed
        move.l  RUNNO(a5),STATUS+ST_RUN.w
        move.l  SCREEN(a5),STATUS+ST_MODE.w

        lea     dosname(pc),a1
        moveq   #37,d0
        moveq   #ERR_DOS,d7
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,DOSBASE(a5)
        beq     failed

        lea     timername(pc),a0
        moveq   #0,d0
        lea     timereq,a1
        moveq   #0,d1
        jsr     _LVOOpenDevice(a6)
        moveq   #ERR_TIMER,d7
        tst.l   d0
        bne     failed
        move.l  timereq+IO_DEVICE,TIMERBASE(a5)
        bsr     start_clock             ; the vertical blank count and the alarm
        moveq   #ERR_SIGNAL,d7
        tst.l   d0
        beq     failed

        ; The data.
        lea     tabname(pc),a0
        moveq   #0,d2
        bsr     load_file
        moveq   #ERR_TABLES,d7
        tst.l   d0
        beq     failed
        move.l  d0,TABLES(a5)
        move.l  d1,TABLES_SIZE(a5)
        bsr     tables
        bne     failed
        lea     samname(pc),a0
        moveq   #0,d2
        bsr     load_file
        move.l  LOAD_FREE(a5),STATUS+ST_FAST_FREE_BEFORE.w
        move.l  LOAD_LARGEST(a5),STATUS+ST_FAST_LARGEST_BEFORE.w
        moveq   #ERR_SAMPLES,d7
        tst.l   d0
        beq     failed
        move.l  d0,SAMPLES(a5)
        move.l  d1,SAMPLES_SIZE(a5)
        move.l  d0,STATUS+ST_SAMPLES.w
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_LOADED_AT.w

        move.l  EXECBASE(a5),a6
        move.l  #8*BLOCK,d0
        move.l  #MEMF_CHIP|MEMF_CLEAR,d1
        moveq   #ERR_CHIP,d7
        jsr     _LVOAllocMem(a6)
        move.l  d0,CHIPMEM(a5)
        beq     failed
        if      LOG
        move.l  #2*LOG_HALF,d0
        move.l  #MEMF_FAST|MEMF_CLEAR,d1
        moveq   #ERR_LOG,d7
        jsr     _LVOAllocMem(a6)
        move.l  d0,LOGMEM(a5)
        beq     failed
        endif

        moveq   #ERR_SIGNAL,d7
        moveq   #-1,d0
        jsr     _LVOAllocSignal(a6)
        move.l  d0,SIGBIT(a5)
        bmi     failed
        moveq   #0,d1
        bset    d0,d1
        move.l  d1,SIGMASK(a5)
        sub.l   a1,a1
        jsr     _LVOFindTask(a6)
        move.l  d0,TASK(a5)

        moveq   #0,d0
        moveq   #0,d1
        jsr     _LVOCacheControl(a6)
        move.l  d0,CACR(a5)
        move.l  d0,STATUS+ST_CACR.w
        move.l  #CACRF_EnableD,d0       ; the data cache on while it plays
        move.l  #CACRF_EnableD,d1
        jsr     _LVOCacheControl(a6)

        move.l  TIMERBASE(a5),a6
        lea     T0(a5),a0
        jsr     _LVOReadEClock(a6)
        move.l  d0,STATUS+ST_EFREQ.w

        move.l  EXECBASE(a5),a6
        lea     intr,a1
        move.b  #NT_INTERRUPT,8(a1)
        lea     intrname(pc),a0
        move.l  a0,10(a1)
        move.l  a5,14(a1)
        lea     handler(pc),a0
        move.l  a0,18(a1)
        moveq   #INTB_AUD0,d0
        jsr     _LVOSetIntVector(a6)
        move.l  d0,OLDINT(a5)
        move.l  #1,INSTALLED(a5)

        tst.l   SCREEN(a5)
        bne.s   .screen

        ; One piece, named on the command line; no screen.
        lea     scoredir(pc),a0
        lea     scoreext(pc),a1
        bsr     make_path
        lea     PATH(a5),a0
        moveq   #0,d2
        bsr     load_file
        moveq   #ERR_SCORE,d7
        tst.l   d0
        beq     failed
        move.l  d0,ONE_SCORE(a5)
        move.l  d1,ONE_SCORE_SIZE(a5)
        move.l  d0,SCORE(a5)
        bsr     begin_piece
        bne     failed
        bsr     fast_after
.wait:  move.l  EXECBASE(a5),a6
        move.l  SIGMASK(a5),d0
        jsr     _LVOWait(a6)
        if      LOG
        bsr     write_full
        endif
        tst.l   FINISHED(a5)
        beq.s   .wait
        bsr     finish_piece
        moveq   #0,d7
        bra     cleanup

        ; The screen: every score loaded now, then choices until Esc or Q.
.screen:
        bsr     read_index
        moveq   #ERR_INDEX,d7
        tst.l   d0
        beq     failed
        bsr     load_scores
        moveq   #ERR_SCORE,d7
        tst.l   d0
        beq     failed
        bsr     open_display
        moveq   #ERR_SCREEN,d7
        tst.l   d0
        beq     failed
        bsr     choose
        bsr     close_display
        move.l  #2,STATUS+ST_STATE.w
        moveq   #0,d7
        bra.s   cleanup

failed: move.l  d7,STATUS+ST_ERROR.w
        move.l  #-1,STATUS+ST_STATE.w
        moveq   #20,d7
        bsr     write_status

; cleanup: undo whatever was done, then return d7.
cleanup:
        lea     CUSTOM,a0
        move.w  #INTF_AUD0,INTENA(a0)
        move.w  #$000f,DMACON(a0)
        move.l  EXECBASE(a5),a6
        bsr     close_display
        bsr     restore_filter
        tst.l   INSTALLED(a5)
        beq.s   .noint
        moveq   #INTB_AUD0,d0
        move.l  OLDINT(a5),a1
        jsr     _LVOSetIntVector(a6)
        move.l  CACR(a5),d0
        move.l  #CACRF_EnableD,d1
        jsr     _LVOCacheControl(a6)
.noint: move.l  SIGBIT(a5),d0
        bmi.s   .nosig
        jsr     _LVOFreeSignal(a6)
.nosig: bsr     stop_clock
        move.l  LOGFILE(a5),d1
        beq.s   .nofile
        move.l  DOSBASE(a5),a6
        jsr     _LVOClose(a6)
        clr.l   LOGFILE(a5)
        move.l  EXECBASE(a5),a6
.nofile:
        bsr     free_scores
        lea     index_mem,a0
        move.l  index_bytes,d0
        addq.l  #1,d0
        bsr     free
        lea     CHIPMEM(a5),a0
        move.l  #8*BLOCK,d0
        bsr     free
        lea     LOGMEM(a5),a0
        move.l  #2*LOG_HALF,d0
        bsr     free
        lea     TABLES(a5),a0
        move.l  TABLES_SIZE(a5),d0
        bsr     free
        lea     SAMPLES(a5),a0
        move.l  SAMPLES_SIZE(a5),d0
        bsr     free
        lea     ONE_SCORE(a5),a0
        move.l  ONE_SCORE_SIZE(a5),d0
        bsr     free
        tst.l   TIMERBASE(a5)
        beq.s   .notimer
        lea     timereq,a1
        jsr     _LVOCloseDevice(a6)
.notimer:
        move.l  DOSBASE(a5),d0
        beq.s   .out
        move.l  d0,a1
        jsr     _LVOCloseLibrary(a6)
.out:   move.l  d7,d0
        movem.l (sp)+,d2-d7/a2-a6
        rts

; ---------------------------------------------------------------------------
; One piece: begin it, finish it. The interrupt does the playing.
; ---------------------------------------------------------------------------

; begin_piece: the piece whose score is SCORE and name NAMEP, from its start.
; Z set when it plays, else d7 says why.
begin_piece:
        movem.l d2-d7/a2-a4,-(sp)
        lea     STATUS+ST_BLOCKS.w,a0   ; this piece's measurements
        moveq   #(ST_QUEUE_FULL+4-ST_BLOCKS)/4-1,d0
.st:    clr.l   (a0)+
        dbra    d0,.st
        clr.l   STATUS+ST_STOPPED.w
        clr.l   STATUS+ST_PLAYING_AT.w
        clr.l   STATUS+ST_FIRST_NOTE_AT.w
        clr.l   STATUS+ST_WORST_TOTAL_E.w
        clr.l   STATUS+ST_TASK_E.w
        clr.l   STATUS+ST_UNITS.w
        clr.l   STATUS+ST_UNIT_MAX_E.w
        lea     NOW_MS(a5),a0           ; the player's state, NOW_MS to LOGFULL1
        move.l  #(T0-NOW_MS)/4-1,d0
.pv:    clr.l   (a0)+
        dbra    d0,.pv
        bsr     reset_voices
        if      LOG
        lea     logdir(pc),a0
        lea     logext(pc),a1
        bsr     make_path
        move.l  DOSBASE(a5),a6
        lea     PATH(a5),a0
        move.l  a0,d1
        move.l  #MODE_NEWFILE,d2
        moveq   #ERR_LOG,d7
        jsr     _LVOOpen(a6)
        move.l  d0,LOGFILE(a5)
        beq.s   .bad
        bsr     write_header            ; a header with 0 blocks, until the end
        endif
        move.l  SCORE(a5),SCOREP(a5)
        bsr     next_event
        bne.s   .bad
        move.l  CHIPMEM(a5),a0
        move.w  #8*BLOCK/4-1,d0
.chip:  clr.l   (a0)+
        dbra    d0,.chip
        move.l  EXECBASE(a5),a6
        moveq   #0,d0
        move.l  SIGMASK(a5),d1
        jsr     _LVOSetSignal(a6)
        move.l  #1,PIECE_ON(a5)
        addq.l  #1,STATUS+ST_STARTS.w
        move.l  #1,STATUS+ST_STATE.w
        bsr     start_sound
        moveq   #0,d0
.out:   movem.l (sp)+,d2-d7/a2-a4
        rts
.bad:   moveq   #1,d0
        bra.s   .out

; finish_piece: stop the sound if it still plays, write the rest of the log
; and the piece's status file.
finish_piece:
        movem.l d2-d7/a2-a4,-(sp)
        lea     CUSTOM,a0
        move.w  #INTF_AUD0,INTENA(a0)
        move.w  #$000f,DMACON(a0)
        move.l  #1,FINISHED(a5)
        if      LOG
        bsr     write_full
        bsr     write_rest
        endif
        clr.l   PIECE_ON(a5)
        addq.l  #1,STATUS+ST_PLAYED.w
        move.l  #2,STATUS+ST_STATE.w
        bsr     write_status
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_ENDED_AT.w
        move.l  EXECBASE(a5),a6
        movem.l (sp)+,d2-d7/a2-a4
        rts

; write_status: the status block to logs/NAME.stat, so the host has each
; piece's figures after the next piece has started. Needs dos.library and
; the name; does nothing without them.
write_status:
        tst.l   DOSBASE(a5)
        beq.s   .none
        tst.l   NAMEP(a5)
        beq.s   .none
        lea     logdir(pc),a0
        lea     statext(pc),a1
        bsr     make_path
        move.l  DOSBASE(a5),a6
        lea     PATH(a5),a0
        move.l  a0,d1
        move.l  #MODE_NEWFILE,d2
        jsr     _LVOOpen(a6)
        move.l  d0,d4
        beq.s   .none
        move.l  d4,d1
        move.l  #STATUS,d2
        move.l  #ST_SIZE,d3
        jsr     _LVOWrite(a6)
        move.l  d4,d1
        jsr     _LVOClose(a6)
.none:  rts

; free: FreeMem the block whose address is at (a0), d0 bytes, if any.
free:   move.l  (a0),d1
        beq.s   .none
        clr.l   (a0)
        move.l  d1,a1
        move.l  EXECBASE(a5),a6
        jsr     _LVOFreeMem(a6)
.none:  rts

; parse_args: a2 the command line, d2 its length -> RUNNO, NAMEP (the name,
; ended with a zero byte in place), or SCREEN = 1 for an empty line. Z set
; when it is good, else d7 = ERR_ARGS.
parse_args:
        moveq   #ERR_ARGS,d7
        tst.l   d2
        beq.s   .screen
        clr.b   -1(a2,d2.l)             ; the line ends with a newline: end it there
        moveq   #0,d0
.space: move.b  (a2)+,d1
        beq.s   .screen                 ; nothing on the line: the screen
        cmp.b   #' ',d1
        beq.s   .space
.digit: sub.b   #'0',d1
        bcs.s   .bad
        cmp.b   #9,d1
        bhi.s   .bad
        mulu.l  #10,d0
        ext.w   d1
        ext.l   d1
        add.l   d1,d0
        move.b  (a2)+,d1
        beq.s   .bad
        cmp.b   #' ',d1
        bne.s   .digit
        move.l  d0,RUNNO(a5)
.skip:  move.b  (a2)+,d1
        beq.s   .bad
        cmp.b   #' ',d1
        beq.s   .skip
        subq.l  #1,a2
        move.l  a2,NAMEP(a5)
.end:   move.b  (a2)+,d1
        beq.s   .good
        cmp.b   #' ',d1
        bne.s   .end
        clr.b   -1(a2)
.good:  moveq   #0,d0
        rts
.screen:
        move.l  #1,SCREEN(a5)
        moveq   #0,d0
        rts
.bad:   moveq   #1,d0
        rts

; make_path: PATH = the string at a0, the name, the string at a1. Keeps a2.
make_path:
        move.l  a2,-(sp)
        lea     PATH(a5),a2
.dir:   move.b  (a0)+,(a2)+
        bne.s   .dir
        subq.l  #1,a2
        move.l  NAMEP(a5),a0
.name:  move.b  (a0)+,(a2)+
        bne.s   .name
        subq.l  #1,a2
.ext:   move.b  (a1)+,(a2)+
        bne.s   .ext
        move.l  (sp)+,a2
        rts

; load_file: the file named at a0, whole, into new fast RAM, with d2 more
; bytes after it (d2 is 0 or 1; 1 puts a 0 there). d0 = its address (0 when
; it failed), d1 = its size; free it with the size plus d2.
load_file:
        movem.l d2-d7/a6,-(sp)
        move.l  d2,d7                   ; the extra bytes
        moveq   #0,d6                   ; the memory
        moveq   #0,d5                   ; the size
        move.l  DOSBASE(a5),a6
        move.l  a0,d1
        move.l  #MODE_OLDFILE,d2
        jsr     _LVOOpen(a6)
        move.l  d0,d4
        beq.s   .out
        move.l  d4,d1
        moveq   #0,d2
        moveq   #OFFSET_END,d3
        jsr     _LVOSeek(a6)
        move.l  d4,d1
        moveq   #0,d2
        moveq   #OFFSET_BEGINNING,d3
        jsr     _LVOSeek(a6)
        move.l  d0,d5                   ; the end, from the first Seek
        ble.s   .close
        bsr     fast_free
        move.l  d0,LOAD_FREE(a5)
        move.l  d1,LOAD_LARGEST(a5)
        move.l  EXECBASE(a5),a6
        move.l  d5,d0
        add.l   d7,d0
        move.l  #MEMF_FAST,d1
        jsr     _LVOAllocMem(a6)
        move.l  d0,d6
        beq.s   .close
        move.l  DOSBASE(a5),a6
        move.l  d4,d1
        move.l  d6,d2
        move.l  d5,d3
        jsr     _LVORead(a6)
        cmp.l   d5,d0
        bne.s   .short
        tst.l   d7
        beq.s   .close
        move.l  d6,a0
        clr.b   (a0,d5.l)               ; the 0 after the text
        bra.s   .close
.short: move.l  EXECBASE(a5),a6         ; short: give the memory back
        move.l  d6,a1
        move.l  d5,d0
        add.l   d7,d0
        jsr     _LVOFreeMem(a6)
        moveq   #0,d6
.close: move.l  DOSBASE(a5),a6
        move.l  d4,d1
        jsr     _LVOClose(a6)
.out:   move.l  d6,d0
        move.l  d5,d1
        movem.l (sp)+,d2-d7/a6
        rts

; fast_free: d0 = fast RAM free in all, d1 = its largest free block.
fast_free:
        movem.l d2/a0-a1/a6,-(sp)
        move.l  ExecBase.w,a6
        move.l  #MEMF_FAST|MEMF_LARGEST,d1
        jsr     _LVOAvailMem(a6)
        move.l  d0,d2
        move.l  #MEMF_FAST,d1
        jsr     _LVOAvailMem(a6)
        move.l  d2,d1
        movem.l (sp)+,d2/a0-a1/a6
        rts

; fast_after: fast_free into the status block, once the allocations are done.
fast_after:
        movem.l d0-d1,-(sp)
        bsr     fast_free
        move.l  d0,STATUS+ST_FAST_FREE_AFTER.w
        move.l  d1,STATUS+ST_FAST_LARGEST_AFTER.w
        movem.l (sp)+,d0-d1
        rts

; tables: check piano.tab and find its sections. Z set when good.
tables:
        moveq   #ERR_TABLES,d7
        move.l  TABLES(a5),a0
        cmp.l   #'P35T',(a0)
        bne.s   .bad
        cmp.w   #1,4(a0)
        bne.s   .bad
        moveq   #0,d0
        move.w  8(a0),d0                ; layers
        mulu.w  #12,d0
        move.l  d0,KEY_STRIDE(a5)
        lea     16(a0),a1
        move.l  a1,LAYER_OF(a5)
        lea     128(a1),a1
        move.l  a1,VOLUMES(a5)
        moveq   #0,d0
        move.w  10(a0),d0               ; roots
        lsl.l   #8,d0                   ; * 128 words
        add.l   d0,a1
        move.l  a1,SAMPTAB(a5)
        moveq   #0,d0
        move.w  12(a0),d0               ; samples
        lsl.l   #4,d0
        add.l   d0,a1
        move.l  a1,KEYTAB(a5)
        moveq   #0,d0
        move.w  6(a0),d0                ; keys
        lsl.l   #3,d0
        add.l   d0,a1
        move.l  a1,SOUNDS(a5)
        moveq   #0,d0
        rts
.bad:   moveq   #1,d0
        rts

; reset_voices: every voice free.
reset_voices:
        movem.l d7/a2,-(sp)
        lea     VOICE_ARRAY(a5),a2
        moveq   #VOICES-1,d7
.v:     bsr     free_voice
        lea     VO_SIZE(a2),a2
        dbra    d7,.v
        movem.l (sp)+,d7/a2
        rts

; start_sound: silence in both buffers, the four channels pointed at
; buffer 0, the interrupt and DMA on. The first interrupt makes block 0.
start_sound:
        lea     CUSTOM,a0
        move.w  #$000f,DMACON(a0)
        move.l  CHIPMEM(a5),d0
        lea     AUD0LC(a0),a1
        lea     volumes(pc),a2
        moveq   #3,d1
.chan:  move.l  d0,(a1)
        move.w  #BLOCK/2,AUDLEN(a1)
        move.w  #PERIOD,AUDPER(a1)
        move.w  (a2)+,AUDVOL(a1)
        add.l   #BLOCK,d0
        lea     16(a1),a1
        dbra    d1,.chan
        move.w  #INTF_AUD0,INTREQ(a0)
        move.w  #$8000|INTF_AUD0,INTENA(a0)
        move.w  #$820f,DMACON(a0)
        rts

; next_event: read the score up to its next event, into NEXT_*; at the end,
; PENDING = 0 and LAST_BLOCK is the block of the last event. Z set when
; good, else d7 = ERR_SCOREBYTE.
next_event:
        move.l  SCOREP(a5),a0
        moveq   #0,d0
.byte:  move.b  (a0)+,d0
        cmp.b   #$58,d0
        bcs.s   .on
        cmp.b   #$80,d0
        bcs.s   .short
        cmp.b   #$d8,d0
        bcs.s   .off
        cmp.b   #$e0,d0
        beq.s   .wait1
        cmp.b   #$e1,d0
        beq.s   .wait2
        cmp.b   #$f0,d0
        beq.s   .down
        cmp.b   #$f1,d0
        beq.s   .up
        cmp.b   #$ff,d0
        beq.s   .end
        moveq   #ERR_SCOREBYTE,d7
        moveq   #1,d0
        rts
.short: sub.l   #$57,d0
        add.l   d0,NOW_MS(a5)
        bra.s   .byte
.wait1: move.b  (a0)+,d0
        add.l   d0,NOW_MS(a5)
        moveq   #0,d0
        bra.s   .byte
.wait2: move.b  (a0)+,d0
        lsl.w   #8,d0
        move.b  (a0)+,d0
        add.l   d0,NOW_MS(a5)
        moveq   #0,d0
        bra.s   .byte
.on:    move.l  d0,NEXT_KEY(a5)
        moveq   #0,d0
        move.b  (a0)+,d0
        move.l  d0,NEXT_VEL(a5)
        moveq   #1,d0
        bra.s   .event
.off:   sub.b   #$80,d0
        move.l  d0,NEXT_KEY(a5)
        moveq   #2,d0
        bra.s   .event
.down:  moveq   #3,d0
        bra.s   .event
.up:    moveq   #4,d0
.event: move.l  d0,NEXT_KIND(a5)
        move.l  a0,SCOREP(a5)
        move.l  NOW_MS(a5),d0
        bsr     sample_of_ms
        move.l  d0,NEXT_AT(a5)
        move.l  #1,PENDING(a5)
        moveq   #0,d0
        rts
.end:   move.l  a0,SCOREP(a5)
        clr.l   PENDING(a5)
        move.l  NOW_MS(a5),d0
        bsr     sample_of_ms
        divu.l  #BLOCK,d0
        move.l  d0,LAST_BLOCK(a5)
        moveq   #0,d0
        rts

; sample_of_ms: d0 = d0 * 3,579,545 / 128,000 (64-bit product).
sample_of_ms:
        move.l  d1,-(sp)
        mulu.l  #3579545,d1:d0
        divu.l  #128000,d1:d0
        move.l  (sp)+,d1
        rts

; The audio interrupt for channel 0 (SetIntVector): a1 = the variables.
handler:
        move.w  #INTF_AUD0,CUSTOM+INTREQ
        movem.l d2-d7/a2-a4,-(sp)
        move.l  a1,a5
        tst.l   FINISHED(a5)
        bne     .quick
        move.l  TIMERBASE(a5),a6
        lea     T0(a5),a0
        jsr     _LVOReadEClock(a6)

        move.l  PLAYING(a5),d0
        eor.l   #1,d0
        move.l  d0,PLAYING(a5)
        lsl.l   #2,d0
        mulu.w  #BLOCK,d0
        add.l   CHIPMEM(a5),d0
        move.l  d0,OUTBUF(a5)
        tst.l   BLOCKNO(a5)
        bne.s   .later
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_PLAYING_AT.w
.later: lea     CUSTOM+AUD0LC,a0
        move.l  d0,(a0)
        add.l   #BLOCK,d0
        move.l  d0,$10(a0)
        add.l   #BLOCK,d0
        move.l  d0,$20(a0)
        add.l   #BLOCK,d0
        move.l  d0,$30(a0)

        bsr     decay
        bsr     events
        bsr     mix
        bsr     out
        if      LOG
        bsr     log_block
        endif
        bsr     next_block

        move.l  TIMERBASE(a5),a6
        lea     T1(a5),a0
        jsr     _LVOReadEClock(a6)
        move.l  T1+4(a5),d0
        sub.l   T0+4(a5),d0
        add.l   d0,STATUS+ST_TOTAL_E.w
        cmp.l   STATUS+ST_WORST_E.w,d0
        bls.s   .notworst
        move.l  d0,STATUS+ST_WORST_E.w
.notworst:
        cmp.l   #BLOCK_E,d0
        bls.s   .intime
        addq.l  #1,STATUS+ST_OVERRUNS.w
.intime:
        add.l   TASK_E_PENDING(a5),d0   ; with the screen's work since the last block
        clr.l   TASK_E_PENDING(a5)
        cmp.l   STATUS+ST_WORST_TOTAL_E.w,d0
        bls.s   .total
        move.l  d0,STATUS+ST_WORST_TOTAL_E.w
.total:
        move.l  BLOCKNO(a5),STATUS+ST_BLOCKS.w
.quick: movem.l (sp)+,d2-d7/a2-a4
        rts

; 1. Decay.
decay:
        lea     VOICE_ARRAY(a5),a2
        moveq   #VOICES-1,d7
.v:     tst.w   VO_KEY(a2)
        bmi.s   .next
        move.l  VO_START(a2),d0
        cmp.l   BEGIN(a5),d0
        bge.s   .next                   ; it has not started yet
        addq.l  #1,VO_BLOCKS(a2)
        move.l  VO_SOUND(a2),a0
        move.w  VO_KEYDOWN(a2),d1
        or.w    PEDAL(a5),d1
        beq.s   .released
        moveq   #0,d0
        move.w  SO_ATTACK(a0),d0
        cmp.l   VO_BLOCKS(a2),d0
        bcc.s   .next                   ; held, and its attack still plays
        move.w  SO_HELD(a0),d0
        bra.s   .apply
.released:
        move.w  SO_RELEASE(a0),d0
.apply: mulu.w  VO_VOLUME(a2),d0
        swap    d0
        move.w  d0,VO_VOLUME(a2)
        cmp.w   #STOP_VOLUME,d0
        bcs.s   .stop
        tst.w   VO_HASTONE(a2)
        beq.s   .next
        bsr     tone_multipliers
        move.w  d0,VO_TLEFT(a2)
        move.w  d1,VO_TRIGHT(a2)
        bra.s   .next
.stop:  bsr     free_voice
.next:  lea     VO_SIZE(a2),a2
        dbra    d7,.v
        rts

; tone_multipliers: the voice at a2's volume times its pan gains, >> 16:
; d0 = left, d1 = right.
tone_multipliers:
        move.w  VO_VOLUME(a2),d0
        move.w  d0,d1
        mulu.w  VO_PANL(a2),d0
        swap    d0
        mulu.w  VO_PANR(a2),d1
        swap    d1
        rts

; free_voice: the voice at a2 free.
free_voice:
        move.w  #-1,VO_KEY(a2)
        clr.w   VO_KEYDOWN(a2)
        clr.w   VO_VOLUME(a2)
        clr.w   VO_HASTONE(a2)
        clr.w   VO_QHEAD(a2)
        clr.w   VO_QCOUNT(a2)
        rts

; 2. The score's events that fall in this block.
events:
.loop:  tst.l   PENDING(a5)
        beq.s   .done
        move.l  BEGIN(a5),d0
        add.l   #BLOCK,d0
        cmp.l   NEXT_AT(a5),d0
        ble.s   .done                   ; the next event is in a later block
        move.l  NEXT_KIND(a5),d0
        cmp.w   #1,d0
        beq.s   .on
        cmp.w   #2,d0
        beq.s   .off
        cmp.w   #3,d0
        seq     d0
        and.w   #1,d0
        move.w  d0,PEDAL(a5)
        bra.s   .read
.off:   move.l  NEXT_KEY(a5),d0
        lea     VOICE_ARRAY(a5),a2
        moveq   #VOICES-1,d1
.offv:  cmp.w   VO_KEY(a2),d0
        bne.s   .offn
        clr.w   VO_KEYDOWN(a2)
.offn:  lea     VO_SIZE(a2),a2
        dbra    d1,.offv
        bra.s   .read
.on:    bsr     note_on
.read:  bsr     next_event
        beq.s   .loop
        move.l  d7,STATUS+ST_ERROR.w    ; a bad byte: end the piece here
        clr.l   PENDING(a5)
.done:  rts

; note_on: NEXT_KEY at NEXT_VEL, at sample NEXT_AT.
note_on:
        addq.l  #1,SERIAL(a5)
        addq.l  #1,STATUS+ST_NOTES.w
        tst.l   STATUS+ST_FIRST_NOTE_AT.w
        bne.s   .stamped
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_FIRST_NOTE_AT.w
.stamped:
        move.l  NEXT_KEY(a5),d5
        move.l  NEXT_AT(a5),d4
        bsr     choose_voice            ; a2 = the voice
        ; waiting: active, and its note starts after this one's sample.
        moveq   #0,d6                   ; 0 free, 1 sounding, 2 waiting
        tst.w   VO_KEY(a2)
        bmi.s   .free
        moveq   #1,d6
        cmp.l   VO_START(a2),d4
        bge.s   .free
        moveq   #2,d6
.free:  ; its sound, volume and pan
        move.l  NEXT_VEL(a5),d0
        move.l  LAYER_OF(a5),a0
        moveq   #0,d1
        move.b  (a0,d0.l),d1            ; layer
        mulu.w  #12,d1
        move.l  d5,d2
        mulu.l  KEY_STRIDE(a5),d2
        add.l   d2,d1
        move.l  SOUNDS(a5),a3
        add.l   d1,a3                   ; the sound record
        move.l  KEYTAB(a5),a0
        lea     (a0,d5.l*8),a0          ; the key record
        moveq   #0,d1
        move.w  KE_ROOT(a0),d1
        lsl.l   #8,d1                   ; root * 256 bytes
        move.l  VOLUMES(a5),a1
        add.l   d1,a1
        move.w  (a1,d0.l*2),VO_VOLUME(a2)
        move.w  d5,VO_KEY(a2)
        move.l  a3,VO_SOUND(a2)
        move.w  KE_LEFT(a0),VO_PANL(a2)
        move.w  KE_RIGHT(a0),VO_PANR(a2)
        move.l  SERIAL(a5),VO_SERIAL(a2)
        move.w  #1,VO_KEYDOWN(a2)
        clr.l   VO_BLOCKS(a2)
        bsr     tone_multipliers        ; d0, d1: the new tone's
        cmp.w   #2,d6
        bne.s   .append
        ; waiting: the new note takes the queued start; the fade carries on
        moveq   #0,d2
        move.w  VO_QHEAD(a2),d2
        add.w   VO_QCOUNT(a2),d2
        subq.w  #1,d2
        and.w   #QUEUE-1,d2
        lsl.w   #4,d2
        lea     VO_QUEUE(a2,d2.l),a0
        bsr     fill_tone
        rts
.append:
        tst.w   d6
        beq.s   .now
        ; sounding: three fade levels, then the start
        moveq   #3,d2
        move.l  d4,d3
.fade:  bsr     queue_slot
        beq.s   .full
        move.l  d3,CH_AT(a0)
        move.w  d2,CH_Q(a0)
.full:  add.l   #FADE_STEP,d3
        subq.w  #1,d2
        bne.s   .fade
        move.l  d3,d4
.now:   move.l  d4,VO_START(a2)
        bsr     queue_slot
        beq.s   .lost
        move.l  d4,CH_AT(a0)
        clr.w   CH_Q(a0)
        bsr     fill_tone
.lost:  rts

; fill_tone: the queued change at a0 starts the voice a2's new tone: the
; sound at a3, multipliers d0 and d1.
fill_tone:
        move.w  SO_SAMPLE(a3),CH_SAMPLE(a0)
        move.l  SO_STEP(a3),CH_STEP(a0)
        move.w  d0,CH_LEFT(a0)
        move.w  d1,CH_RIGHT(a0)
        rts

; queue_slot: a0 = a new change at the end of voice a2's queue; Z set when
; the queue is full (the change is lost and counted).
queue_slot:
        movem.l d0/d1,-(sp)
        move.w  VO_QCOUNT(a2),d0
        cmp.w   #QUEUE,d0
        bcs.s   .room
        addq.l  #1,STATUS+ST_QUEUE_FULL.w
        movem.l (sp)+,d0/d1
        sub.l   a0,a0
        cmp.l   #0,a0
        rts
.room:  move.w  VO_QHEAD(a2),d1
        add.w   d0,d1
        and.w   #QUEUE-1,d1
        lsl.w   #4,d1
        and.l   #$ffff,d1
        lea     VO_QUEUE(a2,d1.l),a0
        addq.w  #1,VO_QCOUNT(a2)
        movem.l (sp)+,d0/d1
        cmp.l   #0,a0
        rts

; choose_voice: a2 = the voice for key d5: the voice sounding the key, else
; the lowest free one, else the one to steal (key up before key down, then
; the quietest, then the oldest).
choose_voice:
        lea     VOICE_ARRAY(a5),a2
        moveq   #VOICES-1,d0
.restrike:
        cmp.w   VO_KEY(a2),d5
        beq.s   .struck
        lea     VO_SIZE(a2),a2
        dbra    d0,.restrike
        lea     VOICE_ARRAY(a5),a2
        moveq   #VOICES-1,d0
.free:  tst.w   VO_KEY(a2)
        bmi.s   .found
        lea     VO_SIZE(a2),a2
        dbra    d0,.free
        ; steal
        lea     VOICE_ARRAY(a5),a0
        move.l  a0,a2                   ; the best so far
        moveq   #VOICES-2,d0
.steal: lea     VO_SIZE(a0),a0
        move.w  VO_KEYDOWN(a0),d1
        cmp.w   VO_KEYDOWN(a2),d1
        bcs.s   .better
        bne.s   .worse
        move.w  VO_VOLUME(a0),d1
        cmp.w   VO_VOLUME(a2),d1
        bcs.s   .better
        bne.s   .worse
        move.l  VO_SERIAL(a0),d1
        cmp.l   VO_SERIAL(a2),d1
        bcc.s   .worse
.better:
        move.l  a0,a2
.worse: dbra    d0,.steal
        addq.l  #1,STATUS+ST_STEALS.w
        rts
.struck:
        addq.l  #1,STATUS+ST_RESTRIKES.w
.found: rts

; 3. Mixing.
mix:
        lea     VOICE_ARRAY(a5),a4
        moveq   #VOICES-1,d0
.v:     move.w  d0,-(sp)
        bsr     mix_voice
        move.w  (sp)+,d0
        lea     VO_SIZE(a4),a4
        dbra    d0,.v
        rts

; mix_voice: the voice at a4 into the sums.
mix_voice:
        tst.w   VO_HASTONE(a4)
        beq.s   .changes
        bsr     sample_entry            ; a0 = its sample's record
        move.l  VO_TPHASE(a4),d0
        move.l  SE_LENGTH(a0),d1
.wrap:  cmp.l   d1,d0
        bcs.s   .wrapped
        sub.l   SE_LOOPLEN(a0),d0
        bra.s   .wrap
.wrapped:
        move.l  d0,VO_TPHASE(a4)
.changes:
        clr.l   OFFSET(a5)
.next:  tst.w   VO_QCOUNT(a4)
        beq.w   .last
        moveq   #0,d0
        move.w  VO_QHEAD(a4),d0
        lsl.w   #4,d0
        lea     VO_QUEUE(a4,d0.l),a3
        move.l  CH_AT(a3),d0
        sub.l   BEGIN(a5),d0
        cmp.l   #BLOCK,d0
        bge.w   .last                   ; due in a later block
        move.l  d0,-(sp)
        bsr     run                     ; up to the change
        move.l  (sp)+,OFFSET(a5)
        moveq   #0,d0
        move.w  VO_QHEAD(a4),d0
        lsl.w   #4,d0
        lea     VO_QUEUE(a4,d0.l),a3
        move.w  CH_Q(a3),d0
        beq.s   .start
        tst.w   VO_HASTONE(a4)
        beq.s   .pop
        move.w  d0,VO_TQ(a4)
        bra.s   .pop
.start: move.w  #1,VO_HASTONE(a4)
        move.w  #4,VO_TQ(a4)
        move.w  CH_SAMPLE(a3),VO_TSAMPLE(a4)
        move.l  CH_STEP(a3),VO_TSTEP(a4)
        move.w  CH_LEFT(a3),VO_TLEFT(a4)
        move.w  CH_RIGHT(a3),VO_TRIGHT(a4)
        clr.l   VO_TPHASE(a4)
        clr.w   VO_TFRAC(a4)
.pop:   move.w  VO_QHEAD(a4),d0
        addq.w  #1,d0
        and.w   #QUEUE-1,d0
        move.w  d0,VO_QHEAD(a4)
        subq.w  #1,VO_QCOUNT(a4)
        bra.w   .next
.last:  move.l  #BLOCK,d0
        bra     run

; sample_entry: a0 = the record of voice a4's tone's sample.
sample_entry:
        moveq   #0,d0
        move.w  VO_TSAMPLE(a4),d0
        lsl.l   #4,d0
        move.l  SAMPTAB(a5),a0
        add.l   d0,a0
        rts

; run: voice a4's tone from OFFSET up to sample d0 of the block.
run:
        tst.w   VO_HASTONE(a4)
        beq     .none
        sub.l   OFFSET(a5),d0
        ble     .none
        move.l  d0,RUNCOUNT(a5)
        ; d7: the right multiplier in the high word, the left in the low,
        ; each faded by its quarters (m * q >> 2).
        moveq   #0,d7
        move.w  VO_TRIGHT(a4),d7
        mulu.w  VO_TQ(a4),d7
        lsr.l   #2,d7
        swap    d7
        moveq   #0,d1
        move.w  VO_TLEFT(a4),d1
        mulu.w  VO_TQ(a4),d1
        lsr.l   #2,d1
        move.w  d1,d7
        bsr     sample_entry
        move.l  SAMPLES(a5),a1
        add.l   SE_OFFSET(a0),a1
        move.l  a1,a0                   ; the padded sample
        move.l  OFFSET(a5),d1
        lea     SUMS_L(a5),a2
        lea     (a2,d1.l*4),a2
        lea     SUMS_R(a5),a3
        lea     (a3,d1.l*4),a3
        move.l  VO_TPHASE(a4),d0
        move.w  VO_TFRAC(a4),d2
        move.l  VO_TSTEP(a4),d3
        move.w  d3,d1                   ; the step's fraction
        clr.w   d3
        swap    d3                      ; and its integer part
        move.l  RUNCOUNT(a5),d4
        lsr.l   #1,d4
        beq     .odd
        lea     (a2,d4.l*8),a1          ; the end of the pairs' left sums
.pair:
        ; left first
        move.l  (a0,d0.l*2),d4          ; s0 in the high word, s1 in the low
        move.l  d4,d6
        swap    d6
        sub.w   d6,d4                   ; s1 - s0
        move.w  d2,d5
        lsr.w   #1,d5                   ; f >> 1
        muls.w  d5,d4
        add.l   d4,d4
        swap    d4                      ; >> 15
        add.w   d6,d4                   ; the sample
        move.w  d4,d6
        muls.w  d7,d4
        add.l   d4,(a2)+
        swap    d7
        muls.w  d7,d6
        add.l   d6,(a3)+
        add.w   d1,d2
        addx.l  d3,d0
        ; right first
        move.l  (a0,d0.l*2),d4
        move.l  d4,d6
        swap    d6
        sub.w   d6,d4
        move.w  d2,d5
        lsr.w   #1,d5
        muls.w  d5,d4
        add.l   d4,d4
        swap    d4
        add.w   d6,d4
        move.w  d4,d6
        muls.w  d7,d4
        add.l   d4,(a3)+
        swap    d7
        muls.w  d7,d6
        add.l   d6,(a2)+
        add.w   d1,d2
        addx.l  d3,d0
        cmpa.l  a1,a2
        blo.w   .pair
.odd:   btst    #0,RUNCOUNT+3(a5)
        beq.s   .stored
        move.l  (a0,d0.l*2),d4
        move.l  d4,d6
        swap    d6
        sub.w   d6,d4
        move.w  d2,d5
        lsr.w   #1,d5
        muls.w  d5,d4
        add.l   d4,d4
        swap    d4
        add.w   d6,d4
        move.w  d4,d6
        muls.w  d7,d4
        add.l   d4,(a2)+
        swap    d7
        muls.w  d7,d6
        add.l   d6,(a3)+
        add.w   d1,d2
        addx.l  d3,d0
.stored:
        move.l  d0,VO_TPHASE(a4)
        move.w  d2,VO_TFRAC(a4)
.none:  rts

; 4. Out: the sums, shifted, clamped and split into the four channels'
; bytes, cleared as they are read; the block's checksum into d6 (a) and
; d7 (b).
out:
        lea     SUMS_L(a5),a0
        lea     SUMS_R(a5),a1
        move.l  OUTBUF(a5),a2           ; channel 0: left high
        lea     BLOCK(a2),a3            ; 1: right high
        lea     BLOCK(a3),a4            ; 2: right low
        lea     BLOCK(a4),a6            ; 3: left low
        moveq   #OUTPUT_SHIFT,d2
        move.l  #32767,d3
        move.l  #-32768,d4
        moveq   #0,d6
        moveq   #0,d7
        move.w  #BLOCK-1,d5
.s:     move.l  (a0),d0
        clr.l   (a0)+
        asr.l   d2,d0
        cmp.l   d3,d0
        ble.s   .lhigh
        move.l  d3,d0
        addq.l  #1,STATUS+ST_CLAMPED.w
.lhigh: cmp.l   d4,d0
        bge.s   .lok
        move.l  d4,d0
        addq.l  #1,STATUS+ST_CLAMPED.w
.lok:   moveq   #0,d1
        move.w  d0,d1
        add.l   d1,d6
        add.l   d6,d7
        asr.w   #8,d1
        move.b  d1,(a2)+
        move.b  d0,d1
        lsr.b   #2,d1
        move.b  d1,(a6)+
        move.l  (a1),d0
        clr.l   (a1)+
        asr.l   d2,d0
        cmp.l   d3,d0
        ble.s   .rhigh
        move.l  d3,d0
        addq.l  #1,STATUS+ST_CLAMPED.w
.rhigh: cmp.l   d4,d0
        bge.s   .rok
        move.l  d4,d0
        addq.l  #1,STATUS+ST_CLAMPED.w
.rok:   moveq   #0,d1
        move.w  d0,d1
        add.l   d1,d6
        add.l   d6,d7
        asr.w   #8,d1
        move.b  d1,(a3)+
        move.b  d0,d1
        lsr.b   #2,d1
        move.b  d1,(a4)+
        dbra    d5,.s
        rts

        if      LOG
; 5. The block's record into the log buffer: the checksum (d6, d7), then
; each voice as it is at the end of the block.
log_block:
        move.l  LOGMEM(a5),a0
        tst.l   LOGHALF(a5)
        beq.s   .half
        add.l   #LOG_HALF,a0
.half:  add.l   LOGPOS(a5),a0
        move.l  d6,(a0)+
        move.l  d7,(a0)+
        lea     VOICE_ARRAY(a5),a4
        moveq   #VOICES-1,d5
.v:     move.b  VO_KEY+1(a4),(a0)+      ; 0xFF when free
        tst.w   VO_HASTONE(a4)
        bne.s   .tone
        move.b  #SILENT,(a0)+
        move.w  VO_VOLUME(a4),(a0)+
        clr.l   (a0)+
        clr.l   (a0)+
        clr.w   (a0)+
        bra.s   .next
.tone:  move.b  VO_TSAMPLE+1(a4),(a0)+
        move.w  VO_VOLUME(a4),(a0)+
        moveq   #0,d0
        move.w  VO_TLEFT(a4),d0
        mulu.w  VO_TQ(a4),d0
        lsr.l   #2,d0
        move.w  d0,(a0)+
        moveq   #0,d0
        move.w  VO_TRIGHT(a4),d0
        mulu.w  VO_TQ(a4),d0
        lsr.l   #2,d0
        move.w  d0,(a0)+
        move.l  VO_TPHASE(a4),(a0)+
        move.w  VO_TFRAC(a4),(a0)+
.next:  lea     VO_SIZE(a4),a4
        dbra    d5,.v
        add.l   #LOG_BLOCK,LOGPOS(a5)
        cmp.l   #LOG_HALF,LOGPOS(a5)
        bcs.s   .room
        ; this buffer is full: hand it to the task, fill the other
        lea     LOGFULL0(a5),a0
        move.l  LOGHALF(a5),d0
        move.l  #1,(a0,d0.l*4)
        eor.l   #1,d0
        move.l  d0,LOGHALF(a5)
        clr.l   LOGPOS(a5)
        tst.l   (a0,d0.l*4)
        beq.s   .signal
        add.l   #LOG_HALF_BLOCKS,STATUS+ST_LOG_OVERRUNS.w
        clr.l   (a0,d0.l*4)             ; the task has not written it: overwrite
.signal:
        bsr     signal_task
.room:  rts
        endif

; 6. Another block, as the model decides: while events remain, or for
; LIMIT_BLOCKS after the last event's block while any voice sounds.
next_block:
        addq.l  #1,BLOCKNO(a5)
        add.l   #BLOCK,BEGIN(a5)
        tst.l   PENDING(a5)
        bne.s   .more
        move.l  LAST_BLOCK(a5),d0
        add.l   #LIMIT_BLOCKS,d0
        cmp.l   BLOCKNO(a5),d0
        bcs.s   .end
        lea     VOICE_ARRAY(a5),a0
        moveq   #VOICES-1,d0
.v:     tst.w   VO_KEY(a0)
        bpl.s   .more
        tst.w   VO_HASTONE(a0)
        bne.s   .more
        lea     VO_SIZE(a0),a0
        dbra    d0,.v
.end:   move.l  #1,FINISHED(a5)
        lea     CUSTOM,a0
        move.w  #INTF_AUD0,INTENA(a0)
        move.w  #$000f,DMACON(a0)
        bsr     signal_task
.more:  rts

signal_task:
        move.l  EXECBASE(a5),a6
        move.l  TASK(a5),a1
        move.l  SIGMASK(a5),d0
        jsr     _LVOSignal(a6)
        rts

        if      LOG
; write_header: the log's header, with the blocks made so far.
write_header:
        lea     header,a0
        move.l  #'P35L',(a0)
        move.w  #1,4(a0)
        move.w  #VOICES,6(a0)
        move.w  #BLOCK,8(a0)
        clr.w   10(a0)
        move.l  BLOCKNO(a5),12(a0)
        move.l  #LOG_HEADER,d3
        move.l  a0,d2
        bra.s   write

; write_full: write each log buffer the interrupt has handed over.
write_full:
        moveq   #0,d4
.half:  lea     LOGFULL0(a5),a0
        tst.l   (a0,d4.l*4)
        beq.s   .next
        move.l  LOGMEM(a5),d2
        tst.l   d4
        beq.s   .first
        add.l   #LOG_HALF,d2
.first: move.l  #LOG_HALF,d3
        bsr.s   write
        lea     LOGFULL0(a5),a0
        clr.l   (a0,d4.l*4)
.next:  addq.l  #1,d4
        cmp.l   #2,d4
        bcs.s   .half
        rts

; write_rest: the part-filled buffer, then the header again with the count.
write_rest:
        move.l  LOGMEM(a5),d2
        tst.l   LOGHALF(a5)
        beq.s   .first
        add.l   #LOG_HALF,d2
.first: move.l  LOGPOS(a5),d3
        beq.s   .header
        bsr.s   write
.header:
        move.l  DOSBASE(a5),a6
        move.l  LOGFILE(a5),d1
        moveq   #0,d2
        moveq   #OFFSET_BEGINNING,d3
        jsr     _LVOSeek(a6)
        bsr     write_header
        move.l  DOSBASE(a5),a6
        move.l  LOGFILE(a5),d1
        jsr     _LVOClose(a6)
        clr.l   LOGFILE(a5)
        rts

; write: d3 bytes from d2 to the log file; count them (not the header's).
write:
        move.l  DOSBASE(a5),a6
        move.l  LOGFILE(a5),d1
        move.l  d3,-(sp)
        jsr     _LVOWrite(a6)
        move.l  (sp)+,d3
        cmp.l   #LOG_HEADER,d3
        beq.s   .header
        add.l   d0,STATUS+ST_LOG_BYTES.w
.header:
        rts
        endif

; ---------------------------------------------------------------------------
; The clock, the filter, the pieces (as EXP-004's player has them).
; ---------------------------------------------------------------------------

; show_filter: the screen's filter light (register FILTER_LIGHT_REGISTER,
; drawn by the host beside the word "filter") lit while the filter is on
; (the CIA-A bit clear), dark while it is off.
show_filter:
        movem.l d2-d3/a6,-(sp)
        move.w  #FILTER_LIGHT_OFF,d1
        btst    #LED_BIT,ciaapra
        bne.s   .set
        move.w  #FILTER_LIGHT_ON,d1
.set:   move.w  d1,d3
        and.w   #$f,d3                  ; blue
        move.w  d1,d2
        lsr.w   #4,d2
        and.w   #$f,d2                  ; green
        lsr.w   #8,d1
        and.w   #$f,d1                  ; red
        move.l  screen,a0
        lea     sc_ViewPort(a0),a0
        moveq   #FILTER_LIGHT_REGISTER,d0
        CALLGFX SetRGB4
        movem.l (sp)+,d2-d3/a6
        rts

; Put the filter back as it was when the program started.
restore_filter:
        tst.w   led_known
        beq.s   .same
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
        move.l  EXECBASE(a5),a6
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
        move.l  EXECBASE(a5),a6
        tst.w   clock_on
        beq.s   .signal
        moveq   #INTB_VERTB,d0
        lea     vbint,a1
        jsr     _LVORemIntServer(a6)
        clr.w   clock_on
.signal:
        move.b  alarm_bit,d0
        ble.s   .out
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

; read_index: scores/index into pieces: each line a name, a space and a
; title; the names are ended with 0 in place. d0: 0 when it cannot.
read_index:
        lea     index_name(pc),a0
        moveq   #1,d2                   ; a 0 after the text
        bsr     load_file
        tst.l   d0
        beq.s   .out
        move.l  d0,index_mem
        move.l  d1,index_bytes
        move.l  d0,a0
        lea     files,a1
        moveq   #0,d1
.line:  tst.b   (a0)
        beq.s   .done
        cmp.b   #10,(a0)
        bne.s   .entry
        addq.l  #1,a0
        bra.s   .line
.entry: cmp.w   #MAX_PIECES,d1
        beq.s   .done
        move.l  a0,(a1)+                ; the name
.name:  move.b  (a0)+,d0
        beq.s   .last
        cmp.b   #10,d0
        beq.s   .eol
        cmp.b   #' ',d0
        bne.s   .name
        clr.b   -1(a0)
.title: move.b  (a0)+,d0
        beq.s   .last
        cmp.b   #10,d0
        bne.s   .title
.eol:   clr.b   -1(a0)
        addq.w  #1,d1
        bra.s   .line
.last:  subq.l  #1,a0
        addq.w  #1,d1
.done:  move.l  d1,pieces
        move.l  d1,STATUS+ST_PIECES.w
        moveq   #1,d0
.out:   rts

; load_scores: every piece's score now, so a choice never waits for the disk.
; d0: 0 when one cannot be loaded (ST_PIECE says which), else 1.
load_scores:
        movem.l d2-d4/a2,-(sp)
        move.l  STATUS+ST_VBLANKS.w,d3
        lea     score_table,a2
        moveq   #0,d4
.next:  cmp.l   pieces,d4
        beq.s   .done
        lea     files,a0
        move.l  (a0,d4.l*4),NAMEP(a5)
        lea     scoredir(pc),a0
        lea     scoreext(pc),a1
        bsr     make_path
        lea     PATH(a5),a0
        moveq   #0,d2
        bsr     load_file
        move.l  d0,(a2)+
        move.l  d1,(a2)+
        tst.l   d0
        beq.s   .bad
        addq.l  #1,d4
        bra.s   .next
.done:  move.l  STATUS+ST_VBLANKS.w,d0
        sub.l   d3,d0
        move.l  d0,STATUS+ST_PRELOAD_FRAMES.w
        moveq   #1,d0
.out:   movem.l (sp)+,d2-d4/a2
        rts
.bad:   move.l  d4,STATUS+ST_PIECE.w
        moveq   #0,d0
        bra.s   .out

free_scores:
        movem.l d2/a2,-(sp)
        lea     score_table,a2
        moveq   #MAX_PIECES-1,d2
.next:  move.l  a2,a0
        move.l  4(a2),d0
        bsr     free
        addq.l  #8,a2
        dbra    d2,.next
        movem.l (sp)+,d2/a2
        rts

; ---------------------------------------------------------------------------
; The screen: open it, show the picture, take choices, close it.
; ---------------------------------------------------------------------------

; open_display: graphics and Intuition, the screen and its window, the
; picture. d0: 0 when something is missing.
open_display:
        movem.l d2-d7/a2-a5,-(sp)
        move.l  ExecBase.w,a6
        lea     gfxname(pc),a1
        moveq   #37,d0
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,gfxbase
        beq     .fail
        lea     intname_lib(pc),a1
        moveq   #37,d0
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,intbase
        beq     .fail
        lea     picture_name(pc),a0
        moveq   #0,d2
        bsr     load_file
        move.l  ExecBase.w,a6
        move.l  d0,picture_mem
        move.l  d1,picture_bytes
        beq     .fail
        bsr     parse_ilbm
        tst.l   d0
        beq     .fail
        move.l  #BAND_BYTES*DEPTH,d0    ; the floor band's copy
        moveq   #MEMF_PUBLIC,d1
        jsr     _LVOAllocMem(a6)
        move.l  d0,band_copy
        beq     .fail
        bsr     make_rows

        lea     newscreen,a0
        CALLINT OpenScreen
        move.l  d0,screen
        beq     .fail
        lea     newwindow,a0
        move.l  d0,30(a0)               ; nw_Screen
        CALLINT OpenWindow
        move.l  d0,window
        beq     .fail
        move.l  d0,STATUS+ST_WINDOW.w
        move.l  screen,a0
        moveq   #0,d0
        CALLINT ShowTitle

        move.l  screen,a0
        lea     sc_BitMap(a0),a0
        lea     planes,a1
        moveq   #DEPTH-1,d0
.planes:
        move.l  bm_Planes(a0),(a1)+
        addq.l  #4,a0
        dbra    d0,.planes
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
        bsr     show_filter
        bsr     copy_band
        lea     picture_mem,a0
        move.l  picture_bytes,d0
        bsr     free
        moveq   #1,d0
        bra.s   .out
.fail:  moveq   #0,d0
.out:   move.l  ExecBase.w,a6
        movem.l (sp)+,d2-d7/a2-a5
        rts

; close_display: whatever open_display opened; safe to call twice.
close_display:
        move.l  ExecBase.w,a6
        moveq   #-1,d0
        bsr     highlight
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
.mem:   lea     picture_mem,a0
        move.l  picture_bytes,d0
        bsr     free
        lea     band_copy,a0
        move.l  #BAND_BYTES*DEPTH,d0
        bsr     free
        move.l  ExecBase.w,a6
        move.l  intbase,d0
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

; parse_ilbm: the ILBM's header, colours and body in picture_mem. d0: 0
; unless it is 320x200, 4 planes and uncompressed. Sets palette and body.
parse_ilbm:
        move.l  picture_mem,a0
        cmp.l   #'FORM',(a0)
        bne     .bad
        cmp.l   #'ILBM',8(a0)
        bne     .bad
        move.l  a0,a1
        add.l   picture_bytes,a1
        lea     12(a0),a0
        clr.l   body
        moveq   #0,d2
.chunk: lea     8(a0),a2
        cmp.l   a1,a2
        bhi     .done
        move.l  4(a0),d1
        cmp.l   #'BMHD',(a0)
        bne.s   .cmap
        cmp.w   #SCREEN_WIDTH,(a2)
        bne     .bad
        cmp.w   #SCREEN_HEIGHT,2(a2)
        bne     .bad
        cmp.b   #DEPTH,8(a2)
        bne     .bad
        tst.b   10(a2)
        bne     .bad
        moveq   #1,d2
        bra.s   .skip
.cmap:  cmp.l   #'CMAP',(a0)
        bne.s   .body
        lea     palette,a3
        move.l  d1,d3
        divu    #3,d3
        cmp.w   #16,d3
        bls.s   .count
        moveq   #16,d3
.count: move.l  a2,a4
        bra.s   .cnext
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
.cnext: dbra    d3,.colour
        bra.s   .skip
.body:  cmp.l   #'BODY',(a0)
        bne.s   .skip
        cmp.l   #PICTURE_BYTES,d1
        bcs.s   .bad
        move.l  a2,body
.skip:  addq.l  #1,d1
        and.w   #$fffe,d1
        lea     0(a2,d1.l),a0
        bra     .chunk
.done:  tst.l   d2
        beq.s   .bad
        tst.l   body
        beq.s   .bad
        moveq   #1,d0
        rts
.bad:   moveq   #0,d0
        rts

show_picture:
        movem.l d2-d3/a2,-(sp)
        move.l  body,a0
        moveq   #0,d2
        move.w  #SCREEN_HEIGHT-1,d3
.row:   lea     planes,a2
        moveq   #DEPTH-1,d1
.plane: move.l  (a2)+,a1
        add.l   d2,a1
        moveq   #ROW_BYTES/4-1,d0
.long:  move.l  (a0)+,(a1)+
        dbra    d0,.long
        dbra    d1,.plane
        add.l   #ROW_BYTES,d2
        dbra    d3,.row
        movem.l (sp)+,d2-d3/a2
        rts

copy_band:
        move.l  band_copy,a1
        lea     planes,a2
        moveq   #DEPTH-1,d1
.plane: move.l  (a2)+,a0
        add.l   #SCOPE_TOP*ROW_BYTES,a0
        move.w  #BAND_BYTES/4-1,d0
.long:  move.l  (a0)+,(a1)+
        dbra    d0,.long
        dbra    d1,.plane
        rts

; restore_band: the whole band back from band_copy, when a piece ends.
restore_band:
        tst.l   screen
        beq.s   .out
        move.l  band_copy,a0
        lea     planes,a2
        moveq   #DEPTH-1,d1
.plane: move.l  (a2)+,a1
        add.l   #SCOPE_TOP*ROW_BYTES,a1
        move.w  #BAND_BYTES/4-1,d0
.long:  move.l  (a0)+,(a1)+
        dbra    d0,.long
        dbra    d1,.plane
        lea     unit_drawn,a0
        moveq   #UNITS-1,d0
.u:     clr.w   (a0)+
        dbra    d0,.u
        clr.w   step_next
.out:   rts

make_rows:
        lea     row_offsets,a0
        moveq   #0,d0
        move.w  #SCREEN_HEIGHT-1,d1
.row:   move.w  d0,(a0)+
        add.w   #ROW_BYTES,d0
        dbra    d1,.row
        rts

; choose: take choices until Esc or Q (EXP-004's rules). While a piece
; plays, one scope unit is drawn after each vertical blank.
choose:
        bsr     fast_after              ; before the state, which the host waits for
        move.l  ExecBase.w,a6
        move.l  #3,STATUS+ST_STATE.w
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_SCREEN_AT.w
        move.l  #ROTATE_S,d0
        mulu    STATUS+ST_VBLANK_HZ+2.w,d0
        move.l  d0,rotate_frames
        clr.l   STATUS+ST_NEXT.w
        bsr     arm_rotation
.loop:  tst.l   PIECE_ON(a5)
        beq.s   .idle
        tst.l   FINISHED(a5)
        beq.s   .draw
        moveq   #-1,d0
        bsr     end_piece               ; it played to its end
        bsr     arm_rotation
        bra.s   .loop
.draw:  bsr     scope_tick
        if      LOG
        bsr     write_full
        endif
        move.l  ExecBase.w,a6
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
        tst.l   d1
        beq.s   .loop
        cmp.l   #-1,STATUS+ST_ROTATE_AT.w
        beq.s   .loop
        bsr     arm_rotation
        bra.s   .loop
.act:   cmp.l   #-1,d0
        beq     .quit
        cmp.l   #-2,d0
        beq     .hold
        subq.l  #1,d0
.play:  move.l  d0,-(sp)
        addq.l  #1,d0
        cmp.l   pieces,d0
        bcs.s   .next
        moveq   #0,d0
.next:  move.l  d0,STATUS+ST_NEXT.w
        bsr     hold_rotation
        tst.l   PIECE_ON(a5)
        beq.s   .start
        move.l  #1,STATUS+ST_STOPPED.w
        move.l  (sp),d0
        bsr     end_piece               ; and its line gold at once
.start: move.l  (sp)+,d0
        bsr     start_piece
        tst.l   d0
        beq     .loop
        bsr     arm_rotation
        bra     .loop
.rotate:
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_CHOSEN_AT.w
        addq.l  #1,STATUS+ST_ROTATED.w
        move.l  STATUS+ST_NEXT.w,d0
        bra.s   .play
.hold:  bsr     hold_rotation
        tst.l   PIECE_ON(a5)
        beq     .loop
        move.l  #1,STATUS+ST_STOPPED.w
        moveq   #-1,d0
        bsr     end_piece
        bra     .loop
.quit:  bsr     hold_rotation
        tst.l   PIECE_ON(a5)
        beq.s   .out
        move.l  #1,STATUS+ST_STOPPED.w
        moveq   #-1,d0
        bsr     end_piece
.out:   rts

arm_rotation:
        tst.l   pieces
        beq.s   hold_rotation
        move.l  STATUS+ST_VBLANKS.w,d0
        add.l   rotate_frames,d0
        clr.w   alarm_on
        move.l  d0,alarm_at
        move.l  d0,STATUS+ST_ROTATE_AT.w
        move.w  #1,alarm_on
        rts

hold_rotation:
        clr.w   alarm_on
        move.l  #-1,STATUS+ST_ROTATE_AT.w
        rts

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

; next_choice: the window's messages. d0: -1 to quit, -2 to stop and hold
; (Space), n + 1 for piece n, 0 for nothing; d1: key presses and clicks.
next_choice:
        movem.l d2-d5/a2,-(sp)
        moveq   #0,d4
        moveq   #0,d5
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
        move.l  d0,a2
        jsr     _LVOReplyMsg(a6)
        cmp.l   #RAWKEY,d2
        bne.s   .mouse
        addq.l  #1,STATUS+ST_KEYS.w
        and.l   #$ffff,d3
        move.l  d3,STATUS+ST_KEY.w
        btst    #7,d3
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
        cmp.w   #LIST_LEFT-4,d1
        blt     .next
        swap    d1
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
        beq     .next
        move.l  d0,d4
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_CHOSEN_AT.w
        bra     .next
.hold:  cmp.l   #-1,d4
        beq     .next
        moveq   #-2,d4
        bra     .next
.filter:
        bchg    #LED_BIT,ciaapra        ; the filter and the power LED, by the task
        addq.l  #1,STATUS+ST_FILTER_KEYS.w
        bsr     show_filter
        bra     .next
.quit:  moveq   #-1,d4
        bra     .next
.out:   move.l  d4,d0
        move.l  d5,d1
        movem.l (sp)+,d2-d5/a2
        rts

; highlight: line d0 in gold with a user copper list (EXP-004's), -1 for none.
highlight:
        movem.l d2-d3/a2-a3,-(sp)
        move.l  ExecBase.w,a6
        move.l  screen,d1
        beq     .out
        cmp.l   STATUS+ST_HIGHLIGHT.w,d0
        beq     .already
        move.l  d0,d2
        sub.l   a2,a2
        tst.l   d2
        bmi     .set
        moveq   #ucl_SIZEOF,d0
        move.l  #MEMF_PUBLIC|MEMF_CLEAR,d1
        jsr     _LVOAllocMem(a6)
        tst.l   d0
        beq     .out
        move.l  d0,a2
        move.l  a2,a0
        moveq   #5,d0
        CALLGFX UCopperListInit
        lea     line_tops(pc),a0
        add.w   d2,d2
        move.w  0(a0,d2.w),d3
        move.l  a2,a1
        move.w  d3,d0
        moveq   #0,d1
        CALLGFX CWait
        move.l  a2,a1
        CALLGFX CBump
        move.l  a2,a1
        move.l  #COLOR13,d0
        move.w  #HIGHLIGHT_COLOUR,d1
        CALLGFX CMove
        move.l  a2,a1
        CALLGFX CBump
        move.l  a2,a1
        move.w  d3,d0
        add.w   #LINE_ROWS,d0
        moveq   #0,d1
        CALLGFX CWait
        move.l  a2,a1
        CALLGFX CBump
        move.l  a2,a1
        move.l  #COLOR13,d0
        move.w  #TEXT_COLOUR,d1
        CALLGFX CMove
        move.l  a2,a1
        CALLGFX CBump
        move.l  a2,a1
        move.w  #10000,d0
        move.w  #255,d1
        CALLGFX CWait
        move.l  a2,a1
        CALLGFX CBump
        lsr.w   #1,d2
.set:   jsr     _LVOForbid(a6)
        move.l  screen,a0
        move.l  sc_ViewPort+vp_UCopIns(a0),a3
        move.l  a2,sc_ViewPort+vp_UCopIns(a0)
        jsr     _LVOPermit(a6)
        move.l  screen,a0
        CALLINT MakeScreen
        CALLINT RethinkDisplay
        move.l  d2,STATUS+ST_HIGHLIGHT.w
        bmi.s   .gone
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_GOLD_AT.w
.gone:  move.l  a3,d0
        beq.s   .out
        CALLGFX WaitTOF
        move.l  ucl_FirstCopList(a3),a0
        CALLGFX FreeCopList
        move.l  a3,a1
        moveq   #ucl_SIZEOF,d0
        jsr     _LVOFreeMem(a6)
.out:   movem.l (sp)+,d2-d3/a2-a3
        rts
.already:
        tst.l   d0
        bmi.s   .out
        move.l  STATUS+ST_GOLD_AT.w,d1
        cmp.l   STATUS+ST_CHOSEN_AT.w,d1
        bcc.s   .out
        move.l  STATUS+ST_VBLANKS.w,STATUS+ST_GOLD_AT.w
        bra.s   .out

; start_piece: piece d0 (from 0): its line gold first, then its score.
; d0: 0 when it plays.
start_piece:
        movem.l d2-d7/a2-a4,-(sp)
        move.l  d0,d6
        lea     score_table,a0
        move.l  (a0,d6.l*8),d1
        beq.s   .none
        move.l  d1,SCORE(a5)
        lea     files,a0
        move.l  (a0,d6.l*4),NAMEP(a5)
        move.l  d6,d0
        bsr     highlight
        move.l  d6,STATUS+ST_PIECE.w
        bsr     begin_piece
        bne.s   .none
        moveq   #0,d0
        bra.s   .out
.none:  moveq   #1,d0
.out:   move.l  ExecBase.w,a6
        movem.l (sp)+,d2-d7/a2-a4
        rts

; end_piece: stop the piece, put line d0 in gold (-1 for none), clear the
; scopes.
end_piece:
        movem.l d2-d7/a2-a4,-(sp)
        move.l  d0,d6
        bsr     finish_piece
        move.l  #3,STATUS+ST_STATE.w
        move.l  d6,d0
        bsr     highlight
        bsr     restore_band
        movem.l (sp)+,d2-d7/a2-a4
        rts

; ---------------------------------------------------------------------------
; The scopes.
; ---------------------------------------------------------------------------

; scope_tick: after the vertical blank, one step of the scopes' cycle (make
; the traces, or draw one unit), and only one a block: a vertical blank in
; the same block as the last step does nothing. The step's E-clock ticks,
; less the interrupt's, go to the block being made (TASK_E_PENDING), where
; the handler adds them to its own.
scope_tick:
        movem.l d2-d7/a2-a4,-(sp)
        CALLGFX WaitTOF
        move.l  BLOCKNO(a5),d0
        cmp.l   step_block,d0
        beq     .out                    ; this block has had its step
        move.l  d0,step_block
        bsr     beam_clear
        move.l  STATUS+ST_TOTAL_E.w,W_MIX(a5)
        move.l  TIMERBASE(a5),a6
        lea     W0(a5),a0
        jsr     _LVOReadEClock(a6)
        move.w  step_next,d0
        bne.s   .draw
        bsr     make_traces
        bra.s   .timed
.draw:  bsr     draw_unit_step
.timed: addq.w  #1,step_next
        cmp.w   #STEPS,step_next
        bcs.s   .watch
        clr.w   step_next
.watch: move.l  TIMERBASE(a5),a6
        lea     W1(a5),a0
        jsr     _LVOReadEClock(a6)
        move.l  W1+4(a5),d0
        sub.l   W0+4(a5),d0
        move.l  STATUS+ST_TOTAL_E.w,d1
        sub.l   W_MIX(a5),d1
        sub.l   d1,d0                   ; less the mixing that came between
        bpl.s   .pos
        moveq   #0,d0
.pos:   add.l   d0,TASK_E_PENDING(a5)
        add.l   d0,STATUS+ST_TASK_E.w
        addq.l  #1,STATUS+ST_UNITS.w
        cmp.l   STATUS+ST_UNIT_MAX_E.w,d0
        bls.s   .out
        move.l  d0,STATUS+ST_UNIT_MAX_E.w
.out:   move.l  ExecBase.w,a6
        movem.l (sp)+,d2-d7/a2-a4
        rts

; make_traces: the block Paula is playing, the left channel's high bytes
; and the right's, as rows from the centre.
make_traces:
        lea     traces,a2
        move.l  PLAYING(a5),d0
        eor.l   #1,d0
        lsl.l   #2,d0
        mulu.w  #BLOCK,d0
        move.l  CHIPMEM(a5),a0
        add.l   d0,a0                   ; channel 0: left high bytes
        bsr.s   trace_channel
        lea     BLOCK(a0),a0            ; channel 1: right
; trace_channel: STEREO_WIDTH columns from the bytes at a0 into a2.
trace_channel:
        move.l  a0,a1
        moveq   #STEREO_WIDTH-1,d7
.col:   move.b  (a1),d0
        ext.w   d0
        asr.w   #SCOPE_SHIFT,d0
        cmp.w   #SCOPE_HALF,d0
        ble.s   .low
        moveq   #SCOPE_HALF,d0
.low:   cmp.w   #-SCOPE_HALF,d0
        bge.s   .high
        moveq   #-SCOPE_HALF,d0
.high:  move.b  d0,(a2)+
        addq.l  #SCOPE_STRIDE,a1
        dbra    d7,.col
        rts

; draw_unit_step: unit step_next - 1, from unit_table: take back its old
; points, plot its new ones.
draw_unit_step:
        move.w  step_next,d7
        subq.w  #1,d7                   ; the unit
        lea     unit_table(pc),a1
        move.w  d7,d0
        lsl.w   #3,d0
        add.w   d0,a1
        moveq   #0,d0
        move.w  (a1)+,d0                ; its first point among the traces
        lea     traces,a0
        add.l   d0,a0
        lea     old_points,a2
        add.l   d0,a2
        add.l   d0,a2
        move.w  (a1)+,d4                ; its left column
        move.w  (a1)+,d6                ; its points
        move.w  (a1)+,d3                ; 0 for colour 14, 1 for 15
        lea     unit_drawn,a1
        add.w   d7,a1
        add.w   d7,a1
        bra     draw_unit

; draw_unit (EXP-004's): d6 points from the trace a0, from column d4; d3 0
; for colour 14, 1 for 15; a2 its points from last time; a1 its drawn flag.
draw_unit:
        movem.l d7/a1/a5/a6,-(sp)
        movem.l planes,a3-a6
        tst.w   (a1)
        beq.s   .plot
        movem.l a0/a2,-(sp)
        move.l  a2,a1
        move.l  band_copy,a0
        sub.l   #SCOPE_TOP*ROW_BYTES,a0
        move.w  d6,d7
        subq.w  #1,d7
.back:  move.w  (a1)+,d0
        move.b  0(a0,d0.w),0(a3,d0.w)
        move.b  BAND_BYTES(a0,d0.w),0(a4,d0.w)
        move.b  2*BAND_BYTES(a0,d0.w),0(a5,d0.w)
        move.b  3*BAND_BYTES(a0,d0.w),0(a6,d0.w)
        dbra    d7,.back
        movem.l (sp)+,a0/a2
.plot:  lea     row_offsets+SCOPE_CENTRE*2,a1
        move.w  d4,d5
        lsr.w   #3,d4
        not.w   d5
        and.w   #7,d5
        move.w  d6,d7
        subq.w  #1,d7
.point: move.b  (a0)+,d0
        ext.w   d0
        add.w   d0,d0
        move.w  0(a1,d0.w),d2
        add.w   d4,d2
        move.w  d2,(a2)+
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
.same:  dbra    d7,.point
        movem.l (sp)+,d7/a1/a5/a6
        move.w  #1,(a1)
        rts

; beam_clear: wait until the beam is not on the band or within BEAM_GUARD
; lines above it.
beam_clear:
.wait:  move.l  CUSTOM+VPOSR,d0
        lsr.l   #8,d0
        and.w   #$1ff,d0
        cmp.w   band_first,d0
        bcs.s   .clear
        cmp.w   band_last,d0
        bls.s   .wait
.clear: rts

volumes:
        dc.w    64,64,1,1               ; channels 0-3: L high, R high, R low, L low

        SCREEN_TABLES                   ; line_tops (screen.i)

; The drawing units: first point among the traces, left column, points,
; colour (0 for 14, 1 for 15). The traces are the left scope's, then the
; right's; both are drawn in colour 15.
unit_table:
        dc.w    0,STEREO_LEFT_L,HALF_WIDTH,1
        dc.w    HALF_WIDTH,STEREO_LEFT_L+HALF_WIDTH,HALF_WIDTH,1
        dc.w    STEREO_WIDTH,STEREO_LEFT_R,HALF_WIDTH,1
        dc.w    STEREO_WIDTH+HALF_WIDTH,STEREO_LEFT_R+HALF_WIDTH,HALF_WIDTH,1

dosname:
        dc.b    "dos.library",0
timername:
        dc.b    "timer.device",0
gfxname:
        dc.b    "graphics.library",0
intname_lib:
        dc.b    "intuition.library",0
intrname:
        dc.b    "piano3500",0
tabname:
        dc.b    "piano.tab",0
samname:
        dc.b    "samples.bin",0
index_name:
        dc.b    "scores/index",0
picture_name:
        dc.b    "title.ilbm",0
scoredir:
        dc.b    "scores/",0
scoreext:
        dc.b    ".score",0
logdir:
        dc.b    "logs/",0
logext:
        dc.b    ".log",0
statext:
        dc.b    ".stat",0
        even

        section tables,data
newscreen:      dc.w 0,0,SCREEN_WIDTH,SCREEN_HEIGHT,DEPTH
                dc.b 0,1
                dc.w 0
                dc.w CUSTOMSCREEN|SCREENQUIET
                dc.l 0,0,0,0
newwindow:      dc.w 0,0,SCREEN_WIDTH,SCREEN_HEIGHT
                dc.b 0,1
                dc.l MOUSEBUTTONS|RAWKEY
                dc.l BACKDROP|BORDERLESS|ACTIVATE|RMBTRAP|SIMPLE_REFRESH|NOCAREREFRESH
                dc.l 0,0,0
                dc.l 0                  ; the screen (nw_Screen, 30)
                dc.l 0
                dc.w 0,0,0,0
                dc.w CUSTOMSCREEN
vbint:          dc.l 0,0
                dc.b NT_INTERRUPT,0
                dc.l intrname,0,vb_handler
        include "menu.i"                ; ROTATE_S, and piece_keys
        even

        section vars,bss
vars:   ds.b    VARS_SIZE
timereq:
        ds.b    IOTV_SIZE
intr:   ds.b    22
header: ds.b    LOG_HEADER
        cnop    0,4
screen_vars:
gfxbase:        ds.l 1
intbase:        ds.l 1
screen:         ds.l 1
window:         ds.l 1
planes:         ds.l DEPTH
picture_mem:    ds.l 1
picture_bytes:  ds.l 1
body:           ds.l 1
band_copy:      ds.l 1
task:           ds.l 1
alarm_mask:     ds.l 1
alarm_at:       ds.l 1
rotate_frames:  ds.l 1
pieces:         ds.l 1
files:          ds.l MAX_PIECES
index_mem:      ds.l 1
index_bytes:    ds.l 1
score_table:    ds.l 2*MAX_PIECES       ; each piece's score: memory and size
palette:        ds.w 16
row_offsets:    ds.w SCREEN_HEIGHT
band_first:     ds.w 1
band_last:      ds.w 1
unit_drawn:     ds.w UNITS
step_next:      ds.w 1
step_block:     ds.l 1
alarm_on:       ds.w 1
clock_on:       ds.w 1
led_known:      ds.w 1
old_points:     ds.w 2*STEREO_WIDTH
traces:         ds.b 2*STEREO_WIDTH
alarm_bit:      ds.b 1
led_start:      ds.b 1
        cnop    0,4
screen_vars_end:
