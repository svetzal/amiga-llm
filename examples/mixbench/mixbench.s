; mixbench.s: how long a 68030 takes to mix piano voices in software.
;
; For the A3500 (68030 at 25 MHz, 68882, ECS, Kickstart 2.04 or later, fast
; RAM). It is the timing test for EXP-005: before the A3500 piano is built
; on software mixing, measure what the mixing costs on the real machine.
;
; Build and boot it with:
;
;   amiga-env bootdisk examples/mixbench/mixbench.s
;   amiga-env a3500 build/mixbench.adf
;
; or boot build/mixbench.adf on the real machine from a floppy. It runs six
; tests of about 4 seconds each, plays a chord through all four Paula
; channels while it does, prints a line for each test, and writes the same
; numbers to a status block at $100 for the host (see STATUS).
;
; What it mixes. Each voice reads its own copy of a 32,768-sample waveform
; in fast RAM (so the reads stream through memory as a piano's samples
; would, not from the data cache), at its own pitch: a 16.16 phase step,
; with no interpolation. Half the voices go to the left, half to the right.
; Two ways to scale a voice by its volume:
;
;   A  8-bit samples and a volume table: one 256-word table per volume
;      level (65 levels, 33 KB), indexed by the sample byte. The voice
;      keeps 8 bits of detail at any volume, as on a Paula channel.
;   B  16-bit samples and MULS.W by the volume, then ADD.L of the 32-bit
;      product to a longword sum (the A3500 piano's mixer, EXP-006).
;
; Way A sums each side into a 16-bit word per output sample, with headroom
; for 8 voices at full volume. Way B sums into a longword per output sample;
; its out step shifts each sum right by 14 and clamps it to 16 bits. Either
; way the sum goes out as 14 bits: the high byte on a channel at volume 64
; and the next 6 bits on a channel at volume 1 (left: channels 0 and 3;
; right: 1 and 2).
;
; How it is timed. Paula plays blocks of 512 samples at period 128 (27,965
; Hz on NTSC, 18.3 ms a block) from two buffers in chip RAM. Channel 0's
; audio interrupt comes when Paula takes a block; the handler points the
; four channels at the other buffer and mixes into it, so the mixing for a
; block has one block's time to finish. The handler reads the E-clock
; (timer.device's ReadEClock, which may be called from interrupts) before
; and after; a block lasts 512 * 128 / 5 = 13,107.2 E-clock ticks on NTSC
; and PAL alike, since Paula's clock is five times the E-clock. After
; RUN_BLOCKS blocks the handler stops the sound itself and signals the
; program, so a test that overruns its time cannot lock the machine.
;
; The first line gives the data and instruction cache settings the program
; found (CacheControl), and the E-clock ticks for 1,000,000 turns of a
; SUBQ.L and BNE loop, which compares the emulator's CPU speed with the real
; machine's. Each test's line gives the mean and worst E-clock ticks for one
; block's mixing, and those as a share of the block's 13,107.2.

        machine 68030

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
_LVORawDoFmt        equ -522
_LVOOpenLibrary     equ -552
_LVOCacheControl    equ -648        ; exec V37
_LVOOutput          equ -60         ; dos
_LVOWrite           equ -48
_LVOReadEClock      equ -60         ; timer.device V36

ExecBase        equ 4
MEMF_CHIP       equ 2
MEMF_FAST       equ 4
MEMF_CLEAR      equ $10000
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
AUD0LC          equ $0a0        ; channel n at AUD0LC + n * 16
AUDLEN          equ 4
AUDPER          equ 6
AUDVOL          equ 8

VOICES          equ 16
N               equ 512         ; samples a block
PERIOD          equ 128
WAVE            equ 32768       ; samples in a voice's loop
PAD             equ 4096        ; read past the loop's end within a block (step <= 4)
VOICE_BYTES     equ WAVE+PAD
LEVEL           equ 48          ; every voice's volume, of 64
RUN_BLOCKS      equ 218         ; about 4 seconds
BLOCK_E10       equ N*PERIOD*2  ; ten times a block's E-clock ticks
CALIB_TURNS     equ 1000000

; A voice
VO_BASE         equ 0           ; its samples, for the test's way
VO_PHASE        equ 4           ; integer part of the phase, in samples
VO_FRAC         equ 8           ; fraction, of 65,536
VO_STEPF        equ 10
VO_STEPI        equ 12
VO_TABLE        equ 16          ; A: the middle of its level's table
VO_VOL          equ 20          ; B: MULS.W factor
VO_ACC          equ 22          ; its side's sums
VO_BASEA        equ 26
VO_BASEB        equ 30
VO_SIZE         equ 34

; Status block, read by the host through the emulator's memory.
STATUS          equ $100
ST_MAGIC        equ 0           ; 'MIXB'
ST_STATE        equ 4           ; 0 running, 1 done, -1 failed
ST_EFREQ        equ 8           ; E-clock ticks a second
ST_CALIB        equ 12          ; E-clock ticks for CALIB_TURNS turns
ST_RUNS         equ 16          ; tests done
ST_CACR         equ 20          ; CacheControl's bits at the start
ST_RUN          equ 24          ; the tests, RU_SIZE bytes each
RU_WAY          equ 0           ; 'A' or 'B'
RU_VOICES       equ 4
RU_DCACHE       equ 8           ; 1 with the data cache on
RU_BLOCKS       equ 12
RU_TOTAL        equ 16          ; E-clock ticks mixing, all blocks
RU_WORST        equ 20          ; the most for one block
RU_MEAN         equ 24
RU_SIZE         equ 28

        section code,code

start:
        movem.l d2-d7/a2-a6,-(sp)
        lea     vars(pc),a5
        st      SIGBIT(a5)              ; -1: no signal yet
        move.l  #'MIXB',STATUS+ST_MAGIC.w
        clr.l   STATUS+ST_STATE.w
        clr.l   STATUS+ST_RUNS.w
        move.l  ExecBase.w,a6
        move.l  a6,EXECBASE(a5)

        lea     dosname(pc),a1
        moveq   #36,d0
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,DOSBASE(a5)
        beq     failed
        move.l  d0,a6
        jsr     _LVOOutput(a6)
        move.l  d0,OUTPUT(a5)

        move.l  EXECBASE(a5),a6
        lea     timername(pc),a0
        moveq   #0,d0                   ; UNIT_MICROHZ
        lea     timereq(pc),a1
        moveq   #0,d1
        jsr     _LVOOpenDevice(a6)
        tst.l   d0
        bne     nodev
        move.l  timereq+IO_DEVICE(pc),TIMERBASE(a5)

        move.l  #DATA_BYTES,d0
        move.l  #MEMF_FAST|MEMF_CLEAR,d1
        jsr     _LVOAllocMem(a6)
        move.l  d0,FASTMEM(a5)
        beq     nomem
        move.l  #8*N,d0
        move.l  #MEMF_CHIP|MEMF_CLEAR,d1
        jsr     _LVOAllocMem(a6)
        move.l  d0,CHIPMEM(a5)
        beq     nochip

        moveq   #-1,d0
        jsr     _LVOAllocSignal(a6)
        move.b  d0,SIGBIT(a5)
        bmi     nosig
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

        bsr     make_data
        bsr     calibrate
        lea     line(pc),a1
        move.l  CACR(a5),(a1)
        move.l  CALIB(a5),4(a1)
        move.l  EFREQ(a5),8(a1)
        lea     head(pc),a0
        bsr     print

        lea     intr(pc),a1
        move.b  #NT_INTERRUPT,8(a1)     ; ln_Type
        lea     intrname(pc),a0
        move.l  a0,10(a1)               ; ln_Name
        move.l  a5,14(a1)               ; is_Data
        lea     handler(pc),a0
        move.l  a0,18(a1)               ; is_Code
        moveq   #INTB_AUD0,d0
        jsr     _LVOSetIntVector(a6)
        move.l  d0,OLDINT(a5)

        lea     tests(pc),a4
.next:  move.l  (a4)+,d0
        beq.s   .done
        move.l  (a4)+,d1
        move.l  (a4)+,d2
        movem.l a4,-(sp)
        bsr     run_test
        movem.l (sp)+,a4
        bra.s   .next
.done:
        move.l  EXECBASE(a5),a6
        moveq   #INTB_AUD0,d0
        move.l  OLDINT(a5),a1
        jsr     _LVOSetIntVector(a6)
        move.l  CACR(a5),d0
        move.l  #CACRF_EnableD,d1
        jsr     _LVOCacheControl(a6)
        move.l  #1,STATUS+ST_STATE.w
        moveq   #0,d7
        bra.s   cleanup

failed: moveq   #20,d7
        move.l  #-1,STATUS+ST_STATE.w
        bra.s   close_dos
nodev:  lea     msg_nodev(pc),a0
        bra.s   failmsg
nomem:  lea     msg_nomem(pc),a0
        bra.s   failmsg
nochip: lea     msg_nochip(pc),a0
failmsg:
        bsr     print
        move.l  #-1,STATUS+ST_STATE.w
        moveq   #20,d7
        bra.s   cleanup
nosig:  moveq   #20,d7
        move.l  #-1,STATUS+ST_STATE.w

cleanup:
        move.l  EXECBASE(a5),a6
        move.b  SIGBIT(a5),d0
        bmi.s   .nosig
        jsr     _LVOFreeSignal(a6)
.nosig: move.l  CHIPMEM(a5),d0
        beq.s   .nochip
        move.l  d0,a1
        move.l  #8*N,d0
        jsr     _LVOFreeMem(a6)
.nochip:
        move.l  FASTMEM(a5),d0
        beq.s   .nofast
        move.l  d0,a1
        move.l  #DATA_BYTES,d0
        jsr     _LVOFreeMem(a6)
.nofast:
        tst.l   TIMERBASE(a5)
        beq.s   close_dos
        lea     timereq(pc),a1
        jsr     _LVOCloseDevice(a6)
close_dos:
        move.l  EXECBASE(a5),a6
        move.l  DOSBASE(a5),d0
        beq.s   .out
        move.l  d0,a1
        jsr     _LVOCloseLibrary(a6)
.out:   move.l  d7,d0
        movem.l (sp)+,d2-d7/a2-a6
        rts

; Fast RAM: the samples for way A and way B, the volume tables, and the two
; sides' sums.
SAMPLES_A       equ 0
SAMPLES_B       equ SAMPLES_A+VOICES*VOICE_BYTES
TABLES          equ SAMPLES_B+VOICES*VOICE_BYTES*2
ACC_L           equ TABLES+65*512
ACC_R           equ ACC_L+N*4       ; longwords for way B, words for way A
DATA_BYTES      equ ACC_R+N*4

; make_data: the waveforms, the tables and the voices.
make_data:
        move.l  FASTMEM(a5),a0
        lea     SAMPLES_A(a0),a1
        lea     SAMPLES_B(a0),a2
        moveq   #VOICES-1,d7
.voice: move.l  #VOICE_BYTES-1,d6
        moveq   #0,d5                   ; sample index
.samp:  move.w  d5,d0
        and.w   #255,d0                 ; a triangle, 256 samples a cycle
        add.w   d0,d0
        cmp.w   #256,d0
        bhs.s   .down
        sub.w   #128,d0                 ; -128 .. 126
        bra.s   .put
.down:  neg.w   d0
        add.w   #383,d0                 ; 127 .. -127
.put:   move.b  d0,(a1)+
        lsl.w   #8,d0
        move.w  d0,(a2)+
        addq.l  #1,d5
        subq.l  #1,d6
        bpl.s   .samp
        dbra    d7,.voice

        ; Table for level L (0-64) at TABLES + L * 512, entry for sample s
        ; (-128 to 127) at its middle + s * 2: s * L * 4095 / 8192.
        lea     TABLES(a0),a1
        moveq   #0,d7                   ; L
.level: move.w  #-128,d6
.entry: move.w  d6,d0
        muls.w  d7,d0
        muls.l  #4095,d0
        asr.l   #8,d0
        asr.l   #5,d0
        move.w  d0,(a1)+
        addq.w  #1,d6
        cmp.w   #128,d6
        blt.s   .entry
        addq.w  #1,d7
        cmp.w   #65,d7
        blt.s   .level

        lea     voices(pc),a1
        lea     steps(pc),a2
        moveq   #0,d7
.vinit: move.l  d7,d0
        mulu.l  #VOICE_BYTES,d0
        lea     SAMPLES_A(a0,d0.l),a3
        move.l  a3,VO_BASEA(a1)
        lea     SAMPLES_B(a0,d0.l*2),a3
        move.l  a3,VO_BASEB(a1)
        move.l  d7,d0
        mulu.w  #1999,d0
        and.l   #WAVE-1,d0
        move.l  d0,VO_PHASE(a1)
        clr.w   VO_FRAC(a1)
        move.l  (a2)+,d0                ; 16.16 step
        move.w  d0,VO_STEPF(a1)
        clr.w   d0
        swap    d0
        move.l  d0,VO_STEPI(a1)
        lea     TABLES+LEVEL*512+256(a0),a3
        move.l  a3,VO_TABLE(a1)
        move.w  #LEVEL<<5,VO_VOL(a1)    ; the same level as LEVEL<<7 and SWAP
        lea     ACC_L(a0),a3
        btst    #0,d7
        beq.s   .left
        lea     ACC_R(a0),a3
.left:  move.l  a3,VO_ACC(a1)
        lea     VO_SIZE(a1),a1
        addq.w  #1,d7
        cmp.w   #VOICES,d7
        blt.s   .vinit
        rts

; calibrate: E-clock ticks for CALIB_TURNS turns of SUBQ.L and BNE.
calibrate:
        move.l  EXECBASE(a5),a6
        jsr     _LVOForbid(a6)
        move.l  TIMERBASE(a5),a6
        lea     T0(a5),a0
        jsr     _LVOReadEClock(a6)
        move.l  d0,EFREQ(a5)
        move.l  d0,STATUS+ST_EFREQ.w
        move.l  #CALIB_TURNS,d0
.turn:  subq.l  #1,d0
        bne.s   .turn
        lea     T1(a5),a0
        jsr     _LVOReadEClock(a6)
        move.l  T1+4(a5),d0
        sub.l   T0+4(a5),d0
        move.l  d0,CALIB(a5)
        move.l  d0,STATUS+ST_CALIB.w
        move.l  EXECBASE(a5),a6
        jsr     _LVOPermit(a6)
        rts

; run_test: d0 = way ('A' or 'B'), d1 = voices, d2 = 1 for the data cache.
run_test:
        move.l  d0,WAY(a5)
        move.l  d1,NVOICES(a5)
        move.l  d2,DCACHE(a5)
        clr.l   TOTAL(a5)
        clr.l   WORST(a5)
        clr.l   BLOCKS(a5)
        clr.l   PLAYING(a5)

        move.l  EXECBASE(a5),a6
        moveq   #0,d0
        tst.l   d2
        beq.s   .cache
        move.l  #CACRF_EnableD,d0
.cache: move.l  #CACRF_EnableD,d1
        jsr     _LVOCacheControl(a6)

        lea     voices(pc),a0
        moveq   #VOICES-1,d7
.base:  move.l  VO_BASEA(a0),VO_BASE(a0)
        cmp.l   #'A',WAY(a5)
        beq.s   .a
        move.l  VO_BASEB(a0),VO_BASE(a0)
.a:     lea     VO_SIZE(a0),a0
        dbra    d7,.base

        move.l  CHIPMEM(a5),a0
        move.w  #8*N/4-1,d7
.clear: clr.l   (a0)+
        dbra    d7,.clear

        moveq   #0,d0
        move.l  SIGMASK(a5),d1
        jsr     _LVOSetSignal(a6)       ; clear ours

        lea     CUSTOM,a0
        move.w  #$000f,DMACON(a0)
        move.l  CHIPMEM(a5),d0
        moveq   #3,d7
        lea     AUD0LC(a0),a1
        lea     volumes(pc),a2
.chan:  move.l  d0,(a1)
        move.w  #N/2,AUDLEN(a1)
        move.w  #PERIOD,AUDPER(a1)
        move.w  (a2)+,AUDVOL(a1)
        add.l   #N,d0
        lea     16(a1),a1
        dbra    d7,.chan
        move.w  #INTF_AUD0,INTREQ(a0)
        move.w  #$8000|INTF_AUD0,INTENA(a0)
        move.w  #$820f,DMACON(a0)

        move.l  SIGMASK(a5),d0
        jsr     _LVOWait(a6)

        move.l  STATUS+ST_RUNS.w,d0
        mulu.w  #RU_SIZE,d0
        lea     STATUS+ST_RUN.w,a0
        add.l   d0,a0
        move.l  WAY(a5),RU_WAY(a0)
        move.l  NVOICES(a5),RU_VOICES(a0)
        move.l  DCACHE(a5),RU_DCACHE(a0)
        move.l  BLOCKS(a5),d1
        move.l  d1,RU_BLOCKS(a0)
        move.l  TOTAL(a5),d0
        move.l  d0,RU_TOTAL(a0)
        move.l  WORST(a5),RU_WORST(a0)
        divu.l  d1,d0
        move.l  d0,RU_MEAN(a0)
        addq.l  #1,STATUS+ST_RUNS.w

        ; The line: way, voices, cache, mean and worst ticks and per mille.
        lea     line(pc),a1
        move.l  WAY(a5),(a1)+
        move.l  NVOICES(a5),(a1)+
        lea     off(pc),a2
        tst.l   DCACHE(a5)
        beq.s   .off
        lea     on(pc),a2
.off:   move.l  a2,(a1)+
        move.l  d0,(a1)+                ; mean
        bsr     permille
        move.l  WORST(a5),d0
        move.l  d0,(a1)+
        bsr     permille
        lea     fmt_run(pc),a0
        lea     line(pc),a1
        bra     print

; permille: d0 E-clock ticks for a block -> two longs at (a1)+: the share of
; the block's time in per cent, and its tenths.
permille:
        mulu.l  #10000,d0
        divu.l  #BLOCK_E10,d0
        divul.l #10,d1:d0               ; d0 per cent, d1 tenths
        move.l  d0,(a1)+
        move.l  d1,(a1)+
        rts

; print: RawDoFmt the format at a0 with the data at a1, and write it.
print:
        movem.l a2-a3/a6,-(sp)
        move.l  EXECBASE(a5),a6
        lea     putch(pc),a2
        lea     textbuf(pc),a3
        jsr     _LVORawDoFmt(a6)
        lea     textbuf(pc),a0
        move.l  a0,d2
        moveq   #-1,d3
.len:   addq.l  #1,d3
        tst.b   (a0)+
        bne.s   .len
        move.l  DOSBASE(a5),a6
        move.l  OUTPUT(a5),d1
        beq.s   .none
        jsr     _LVOWrite(a6)
.none:  movem.l (sp)+,a2-a3/a6
        rts
putch:  move.b  d0,(a3)+
        rts

; The audio interrupt for channel 0 (SetIntVector): a1 = vars. Paula has
; just taken the block the registers point at; point them at the other
; buffer and mix into it.
handler:
        move.w  #INTF_AUD0,CUSTOM+INTREQ
        movem.l d2-d7/a2-a4,-(sp)
        move.l  a1,a5
        move.l  TIMERBASE(a5),a6
        lea     T0(a5),a0
        jsr     _LVOReadEClock(a6)

        move.l  PLAYING(a5),d0
        eor.l   #1,d0
        move.l  d0,PLAYING(a5)
        lsl.l   #2,d0                   ; buffer * 4 channels
        mulu.w  #N,d0
        add.l   CHIPMEM(a5),d0
        move.l  d0,a3                   ; channel 0's buffer: left, high
        lea     CUSTOM+AUD0LC,a0
        move.l  d0,(a0)
        add.l   #N,d0
        move.l  d0,$10(a0)
        add.l   #N,d0
        move.l  d0,$20(a0)
        add.l   #N,d0
        move.l  d0,$30(a0)
        move.l  a3,BUFFER(a5)

        lea     voices(pc),a4
        move.l  NVOICES(a5),d0
        subq.l  #1,d0
        move.l  d0,LEFT(a5)
.voice: move.l  VO_BASE(a4),a0
        move.l  VO_ACC(a4),a2
        move.l  VO_PHASE(a4),d0
        move.w  VO_STEPF(a4),d1
        move.w  VO_FRAC(a4),d2
        move.l  VO_STEPI(a4),d3
        move.w  #N/4-1,d7
        cmp.l   #'A',WAY(a5)
        bne.s   .b
        move.l  VO_TABLE(a4),a3
        bsr     mix_a
        bra.s   .mixed
.b:     move.w  VO_VOL(a4),d6
        bsr     mix_b
.mixed: cmp.l   #WAVE,d0
        blo.s   .inloop
        sub.l   #WAVE,d0
.inloop:
        move.l  d0,VO_PHASE(a4)
        move.w  d2,VO_FRAC(a4)
        lea     VO_SIZE(a4),a4
        subq.l  #1,LEFT(a5)
        bpl.s   .voice

        ; Out: each side's sums to its two channels, clearing the sums.
        move.l  FASTMEM(a5),a0
        lea     ACC_L(a0),a2
        move.l  BUFFER(a5),a3           ; channel 0
        lea     3*N(a3),a1              ; channel 3
        bsr     out
        move.l  FASTMEM(a5),a0
        lea     ACC_R(a0),a2
        move.l  BUFFER(a5),a3
        lea     2*N(a3),a1              ; channel 2
        lea     N(a3),a3                ; channel 1
        bsr     out

        move.l  TIMERBASE(a5),a6
        lea     T1(a5),a0
        jsr     _LVOReadEClock(a6)
        move.l  T1+4(a5),d0
        sub.l   T0+4(a5),d0
        add.l   d0,TOTAL(a5)
        cmp.l   WORST(a5),d0
        bls.s   .notworst
        move.l  d0,WORST(a5)
.notworst:
        addq.l  #1,BLOCKS(a5)
        cmp.l   #RUN_BLOCKS,BLOCKS(a5)
        blo.s   .out
        lea     CUSTOM,a0
        move.w  #INTF_AUD0,INTENA(a0)
        move.w  #$000f,DMACON(a0)
        move.w  #INTF_AUD0,INTREQ(a0)
        move.l  EXECBASE(a5),a6
        move.l  TASK(a5),a1
        move.l  SIGMASK(a5),d0
        jsr     _LVOSignal(a6)
.out:   movem.l (sp)+,d2-d7/a2-a4
        rts

; Way A, one voice into its side: a0 samples, d0 phase, d2 fraction, d1
; and d3 the step's fraction and integer, a3 the middle of its level's
; table, a2 the sums, d7 = N / 4 - 1.
mix_a:
.turn:
        rept    4
        move.b  (a0,d0.l),d4
        ext.w   d4
        move.w  (a3,d4.w*2),d5
        add.w   d5,(a2)+
        add.w   d1,d2
        addx.l  d3,d0
        endr
        dbra    d7,.turn
        rts

; Way B, as way A with 16-bit samples, d6 the volume and longword sums.
mix_b:
.turn:
        rept    4
        move.w  (a0,d0.l*2),d4
        muls.w  d6,d4
        add.l   d4,(a2)+
        add.w   d1,d2
        addx.l  d3,d0
        endr
        dbra    d7,.turn
        rts

; out: the out step for the test's way, from the sums at a2.
out:    cmp.l   #'A',WAY(a5)
        beq.s   out14
        bra.s   out14l

; out14: N sums at a2 (cleared as read) -> high bytes at a3, low 6 bits at a1.
out14:
        move.w  #N-1,d7
.s:     move.w  (a2),d0
        clr.w   (a2)+
        move.w  d0,d1
        asr.w   #8,d0
        move.b  d0,(a3)+
        lsr.b   #2,d1
        move.b  d1,(a1)+
        dbra    d7,.s
        rts

; out14l: N longword sums at a2 (cleared as read), each shifted right by 14
; and clamped to 16 bits -> high bytes at a3, low 6 bits at a1.
out14l:
        move.w  #N-1,d7
        moveq   #14,d3
        move.l  #32767,d4
        move.l  #-32768,d5
.s:     move.l  (a2),d0
        clr.l   (a2)+
        asr.l   d3,d0
        cmp.l   d4,d0
        ble.s   .nothigh
        move.l  d4,d0
.nothigh:
        cmp.l   d5,d0
        bge.s   .split
        move.l  d5,d0
.split: move.w  d0,d1
        asr.w   #8,d0
        move.b  d0,(a3)+
        lsr.b   #2,d1
        move.b  d1,(a1)+
        dbra    d7,.s
        rts

; The tests: way, voices, data cache.
tests:  dc.l    'A',8,0
        dc.l    'A',16,0
        dc.l    'B',8,0
        dc.l    'B',16,0
        dc.l    'A',16,1
        dc.l    'B',16,1
        dc.l    0

; Pitch steps in 16.16, a chord over three octaves.
steps:  dc.l    32768,41285,49152,55109,65536,73562,82570,98304
        dc.l    110218,131072,147123,165140,196608,220436,247414,262144

volumes:
        dc.w    64,64,1,1               ; channels 0-3: L high, R high, R low, L low

head:   dc.b    "mixbench: 14-bit stereo, 512-sample blocks, period 128",10
        dc.b    "cache $%08lx  loop %ld E  E-clock %ld Hz",10,0
fmt_run:
        dc.b    "%lc %2ldv dcache %-3s  mean %4ld E %2ld.%ld%%  worst %4ld E %2ld.%ld%%",10,0
msg_nodev:
        dc.b    "mixbench: cannot open timer.device",10,0
msg_nomem:
        dc.b    "mixbench: not enough fast RAM (needs about 1.8 MB)",10,0
msg_nochip:
        dc.b    "mixbench: not enough chip RAM",10,0
off:    dc.b    "off",0
on:     dc.b    "on",0
dosname:
        dc.b    "dos.library",0
timername:
        dc.b    "timer.device",0
intrname:
        dc.b    "mixbench",0
        even

; Variables, at offsets from a5.
EXECBASE        equ 0
DOSBASE         equ 4
OUTPUT          equ 8
TIMERBASE       equ 12
FASTMEM         equ 16
CHIPMEM         equ 20
SIGMASK         equ 24
TASK            equ 28
CACR            equ 32
OLDINT          equ 36
EFREQ           equ 40
CALIB           equ 44
WAY             equ 48
NVOICES         equ 52
DCACHE          equ 56
TOTAL           equ 60
WORST           equ 64
BLOCKS          equ 68
PLAYING         equ 72
BUFFER          equ 76
LEFT            equ 80
T0              equ 84          ; EClockVal: high, low
T1              equ 92
SIGBIT          equ 100
VARS_SIZE       equ 102

vars:   ds.b    VARS_SIZE
        even
timereq:
        ds.b    IOTV_SIZE
intr:   ds.b    22
voices: ds.b    VOICES*VO_SIZE
line:   ds.l    12
textbuf: ds.b   256
