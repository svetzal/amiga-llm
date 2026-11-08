; player.s: EXP-006's A3500 piano player, the 68030 counterpart of
; tools/amiga_env/piano/player3500.py.
;
; For the A3500 (68030 at 25 MHz, ECS, NTSC, Kickstart 2.04 or later) with
; about 12 MB of fast RAM free. It plays one piece and returns:
;
;   player RUN NAME
;
; RUN is a number the host waits for in the status block; NAME is a piece,
; read from scores/NAME.score. It loads piano.tab and samples.bin (see
; tools/amiga_env/piano/m68k3500.py) from the current directory. The test
; build (LOG=1) writes the voice log to logs/NAME.log as it plays.
;
; The host passes the model's constants with -D (amiga-env piano3500-run):
; VOICES, BLOCK, PERIOD, FADE_STEP, STOP_VOLUME, LIMIT_BLOCKS, OUTPUT_SHIFT,
; QUEUE and LOG. They are not written here, so they cannot drift from the
; model's.
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
; The task loads everything, starts the sound, then waits. The test build's
; log goes through two buffers: the interrupt fills one while the task
; writes the other to the file.
;
; Status block at $100 (longs), read by the host: see STATUS below.

        machine 68030

        ifnd    VOICES
        fail    "assemble with the model's constants (amiga-env piano3500-run)"
        endif

_LVOForbid          equ -132
_LVOPermit          equ -138
_LVOSetIntVector    equ -162
_LVOAllocMem        equ -198
_LVOFreeMem         equ -210
_LVOFindTask        equ -294
_LVOSetSignal       equ -306
_LVOWait            equ -318
_LVOSignal          equ -324
_LVOAllocSignal     equ -330
_LVOFreeSignal      equ -336
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

ExecBase        equ 4
MEMF_CHIP       equ 2
MEMF_FAST       equ 4
MEMF_CLEAR      equ $10000
MODE_OLDFILE    equ 1005
MODE_NEWFILE    equ 1006
OFFSET_BEGINNING equ -1
OFFSET_END      equ 1
CACRF_EnableD   equ $100
INTB_AUD0       equ 7
INTF_AUD0       equ $0080
NT_INTERRUPT    equ 2
IO_DEVICE       equ 20
IOTV_SIZE       equ 40

CUSTOM          equ $dff000
DMACON          equ $096
INTENA          equ $09a
INTREQ          equ $09c
AUD0LC          equ $0a0
AUDLEN          equ 4
AUDPER          equ 6
AUDVOL          equ 8

BLOCK_E         equ BLOCK*PERIOD/5  ; E-clock ticks a block (13,107.2 rounded down)
LOG_VOICE       equ 14
LOG_BLOCK       equ 8+VOICES*LOG_VOICE
LOG_HALF_BLOCKS equ 64
LOG_HALF        equ LOG_HALF_BLOCKS*LOG_BLOCK
LOG_HEADER      equ 16
SILENT          equ $ff

; Status block (longs at $100).
STATUS          equ $100
ST_MAGIC        equ 0           ; 'P35P'
ST_STATE        equ 4           ; 0 loading, 1 playing, 2 done, -1 failed
ST_ERROR        equ 8           ; why it failed (ERR_ below)
ST_RUN          equ 12          ; RUN from the command line
ST_BLOCKS       equ 16          ; blocks made
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
ST_SIZE         equ 72

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
TABLES          rs.l 1
TABLES_SIZE     rs.l 1
SAMPLES         rs.l 1
SAMPLES_SIZE    rs.l 1
SCORE           rs.l 1
SCORE_SIZE      rs.l 1
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
PLAYING         rs.l 1          ; the buffer Paula plays next
OUTBUF          rs.l 1          ; channel 0's half of the buffer being made
FINISHED        rs.l 1
OFFSET          rs.l 1          ; where the run being mixed starts, in samples
RUNCOUNT        rs.l 1
LOGHALF         rs.l 1          ; the log buffer the interrupt fills, 0 or 1
LOGPOS          rs.l 1          ; bytes in it
LOGFULL0        rs.l 1          ; a full buffer waiting for the task
LOGFULL1        rs.l 1
T0              rs.l 2
T1              rs.l 2
RUNNO           rs.l 1
NAMEP           rs.l 1
VOICE_ARRAY     rs.b VOICES*VO_SIZE
SUMS_L          rs.l BLOCK
SUMS_R          rs.l BLOCK
PATH            rs.b 128
VARS_SIZE       rs.b 0

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
        move.l  ExecBase.w,a6
        move.l  a6,EXECBASE(a5)
        moveq   #-1,d0
        move.l  d0,SIGBIT(a5)
        lea     STATUS.w,a0
        moveq   #ST_SIZE/4-1,d0
.clrst: clr.l   (a0)+
        dbra    d0,.clrst
        move.l  #'P35P',STATUS+ST_MAGIC.w

        bsr     parse_args
        bne     failed
        move.l  RUNNO(a5),STATUS+ST_RUN.w

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

        ; The data.
        lea     tabname(pc),a0
        bsr     load_file
        moveq   #ERR_TABLES,d7
        tst.l   d0
        beq     failed
        move.l  d0,TABLES(a5)
        move.l  d1,TABLES_SIZE(a5)
        bsr     tables
        bne     failed
        lea     samname(pc),a0
        bsr     load_file
        moveq   #ERR_SAMPLES,d7
        tst.l   d0
        beq     failed
        move.l  d0,SAMPLES(a5)
        move.l  d1,SAMPLES_SIZE(a5)
        move.l  d0,STATUS+ST_SAMPLES.w
        lea     scoredir(pc),a0
        lea     scoreext(pc),a1
        bsr     make_path
        lea     PATH(a5),a0
        bsr     load_file
        moveq   #ERR_SCORE,d7
        tst.l   d0
        beq     failed
        move.l  d0,SCORE(a5)
        move.l  d1,SCORE_SIZE(a5)

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
        beq     failed
        bsr     write_header            ; a header with 0 blocks, until the end
        endif

        ; The player's state, and the first event.
        bsr     reset_voices
        move.l  SCORE(a5),SCOREP(a5)
        bsr     next_event
        bne     failed

        move.l  EXECBASE(a5),a6
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

        moveq   #0,d0
        move.l  SIGMASK(a5),d1
        jsr     _LVOSetSignal(a6)
        move.l  #1,STATUS+ST_STATE.w
        bsr     start_sound

.wait:  move.l  EXECBASE(a5),a6
        move.l  SIGMASK(a5),d0
        jsr     _LVOWait(a6)
        if      LOG
        bsr     write_full
        endif
        tst.l   FINISHED(a5)
        beq.s   .wait

        if      LOG
        bsr     write_full
        bsr     write_rest
        endif
        move.l  #2,STATUS+ST_STATE.w
        moveq   #0,d7
        bsr     write_status
        bra     cleanup

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
.nosig: move.l  LOGFILE(a5),d1
        beq.s   .nofile
        move.l  DOSBASE(a5),a6
        jsr     _LVOClose(a6)
        move.l  EXECBASE(a5),a6
.nofile:
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
        lea     SCORE(a5),a0
        move.l  SCORE_SIZE(a5),d0
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
; ended with a zero byte in place). Z set when it is good, else d7 = ERR_ARGS.
parse_args:
        moveq   #ERR_ARGS,d7
        clr.b   -1(a2,d2.l)             ; the line ends with a newline: end it there
        moveq   #0,d0
.space: move.b  (a2)+,d1
        beq.s   .bad
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
.bad:   moveq   #1,d0
        rts

; make_path: PATH = the string at a0, the name, the string at a1.
make_path:
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
        rts

; load_file: the file named at a0, whole, into new fast RAM. d0 = its address
; (0 when it failed), d1 = its size.
load_file:
        movem.l d2-d6/a6,-(sp)
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
        move.l  EXECBASE(a5),a6
        move.l  d5,d0
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
        beq.s   .close
        move.l  EXECBASE(a5),a6         ; short: give the memory back
        move.l  d6,a1
        move.l  d5,d0
        jsr     _LVOFreeMem(a6)
        moveq   #0,d6
.close: move.l  DOSBASE(a5),a6
        move.l  d4,d1
        jsr     _LVOClose(a6)
.out:   move.l  d6,d0
        move.l  d5,d1
        movem.l (sp)+,d2-d6/a6
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
        lea     VOICE_ARRAY(a5),a0
        moveq   #VOICES-1,d0
.v:     move.w  #-1,VO_KEY(a0)
        lea     VO_SIZE(a0),a0
        dbra    d0,.v
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
        lea     CUSTOM+AUD0LC,a0
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

volumes:
        dc.w    64,64,1,1               ; channels 0-3: L high, R high, R low, L low
dosname:
        dc.b    "dos.library",0
timername:
        dc.b    "timer.device",0
intrname:
        dc.b    "piano3500",0
tabname:
        dc.b    "piano.tab",0
samname:
        dc.b    "samples.bin",0
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

        section vars,bss
vars:   ds.b    VARS_SIZE
timereq:
        ds.b    IOTV_SIZE
intr:   ds.b    22
header: ds.b    LOG_HEADER
