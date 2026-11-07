; player.s: EXP-004's piano player for the baseline A500.
;
; A 68000 on Kickstart 1.2 with OCS: plays recorded piano performances
; (score byte streams) through Paula's four voices with 8-bit samples,
; exactly as the host model in tools/amiga_env/piano/player.py does, so
; that the two voice logs can be compared byte for byte.
;
; Build it with `amiga-env piano-disk examples/piano/piano.toml`, which
; makes the data in runs/exp004/m68k/ and assembles this file with that
; folder on the include path. `-DLOG=1` makes the test build, which also
; writes the voice log (see m68k.py for its layout).
;
; The program holds the samples (in chip RAM) and the tables. The pieces
; are files on the disk: scores/index has one line a piece, in menu order,
; the score's file name, a space and the title; each score is loaded with
; dos.library when it is chosen, played, and freed. Paths are relative to
; the current directory, which is the disk's root when the disk boots.
;
; Usage from a CLI or the startup-sequence:
;   piano            the menu: a numbered list in the CLI window; a key
;                    chooses a piece (1 to 9, then letters, Q quits), and
;                    a key during a piece stops it
;   piano 3 1        plays pieces 3 and 1 (the menu's keys), then ends
;
; The menu reads single key presses: it opens the CLI's window ("*") and
; puts its console handler in raw mode with an ACTION_SCREEN_MODE packet
; (Kickstart 1.2 has no SetMode), and back to cooked mode at the end.
; Input() is not used, because in the startup-sequence it is the script.
;
; How a piece plays. The program takes CIA-B timer A through ciab.resource
; as a 1 kHz interrupt and the four audio interrupt vectors with
; SetIntVector, and drives Paula directly. Every millisecond the CIA
; interrupt steps the fades, reads the score's events for that millisecond,
; and on a frame tick (tick k at k * 1000 // 60 ms) decays every voice. Each
; note starts Paula on the whole sample; the channel's audio interrupt,
; which Paula raises once it has taken the start and length, writes the
; loop's start and length so that Paula goes round the loop when the sample
; ends. The task itself only waits: for a key (WaitForChar) or for the end.
; When the piece is over it gives everything back and prints what it
; measured.
;
; Status for the host, at the unused 68000 vectors from $100 (see STATUS).

        ifnd    LOG
LOG     equ     0
        endif

; exec.library (V33), from the NDK's exec_lib.fd
_LVOFreeMem         equ -210
_LVOAvailMem        equ -216
_LVOFindTask        equ -294
_LVOSetSignal       equ -306
_LVOSetIntVector    equ -162
_LVOAllocMem        equ -198
_LVOPutMsg          equ -366
_LVOGetMsg          equ -372
_LVOWaitPort        equ -384
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
_LVODelay           equ -198
_LVOWaitForChar     equ -204
; ciab.resource (cia_lib.fd)
_LVOAddICRVector    equ -6
_LVORemICRVector    equ -12
_LVOAbleICR         equ -18

ExecBase        equ 4
MEMF_PUBLIC     equ 1
MEMF_CHIP       equ 2
NT_INTERRUPT    equ 2
NT_MESSAGE      equ 5
INTB_AUD0       equ 7
CIAICRB_TA      equ 0
SIGBREAKF_CTRL_C equ $1000

MODE_OLDFILE    equ 1005
OFFSET_BEGINNING equ -1
OFFSET_END      equ 1
ACTION_SCREEN_MODE equ 994      ; dp_Arg1 -1 raw, 0 cooked
pr_MsgPort      equ $5c         ; in struct Process
fh_Type         equ 8           ; in struct FileHandle: the handler's port
LN_TYPE         equ 8
LN_NAME         equ 10
MN_REPLYPORT    equ 14
MN_LENGTH       equ 18
MESSAGE_SIZE    equ 20
dp_Link         equ 0
dp_Port         equ 4
dp_Type         equ 8
dp_Res1         equ 12
dp_Arg1         equ 20
DOSPACKET_SIZE  equ 48

custom          equ $dff000
DMACON          equ $096
INTENA          equ $09a
INTREQ          equ $09c
AUD0LC          equ $0a0        ; then LEN +4, PER +6, VOL +8; channels $10 apart

ciabtalo        equ $bfd400
ciabtahi        equ $bfd500
ciabcra         equ $bfde00

; 716 E-clock ticks (715,909 Hz on NTSC) between interrupts: 1.000127 ms.
TIMER_LATCH     equ 715
TIMER_PERIOD    equ TIMER_LATCH+1
VOICES          equ 4
FADE_MS         equ 5           ; as player.FADE_MS
LOG_BYTES       equ 400000      ; 16,666 ticks, 277 s
MAX_PIECES      equ 34          ; 1-9 and A-Z without Q
WAIT_US         equ 20000       ; how long one WaitForChar waits for a key

; Status block, read by the host through the emulator's memory.
STATUS          equ $100
ST_MAGIC        equ 0           ; 'PIAN'
ST_STATE        equ 4           ; 0 starting, 1 playing, 2 ended, 3 menu, -1 failed
ST_LOGBASE      equ 8
ST_LOGBYTES     equ 12
ST_SAMPLES      equ 16          ; where the samples are in chip RAM
ST_COPIED       equ 20          ; 0: LoadSeg put the chip hunk in chip RAM; 1: copied
ST_TOTAL_E      equ 24          ; E-clock ticks spent in the player's interrupts
ST_MS           equ 28          ; milliseconds played
ST_MAX_FRAME_E  equ 32          ; most E-clock ticks in one frame (16 or 17 ms)
ST_FRAMES       equ 36
ST_MAX_MS_E     equ 40          ; most in one millisecond's interrupt
ST_PIECE        equ 44          ; the piece playing or last played, from 0 in menu order
ST_ENTRY_E      equ 48          ; E-clock ticks from the timer running out to the handler
ST_PLAYED       equ 52          ; pieces played to their end or stopped
ST_STOPPED      equ 56          ; 1 when the last piece was stopped by a key
ST_PIECES       equ 60          ; pieces in the index
ST_SCORE        equ 64          ; where the score is
ST_SCORE_BYTES  equ 68
ST_CHIP_FREE    equ 72          ; AvailMem while the score is loaded: chip RAM
ST_OTHER_FREE   equ 76          ; and all other memory
ST_KEY          equ 80          ; the last key read: its character, or what Read returned
ST_KEYS         equ 84          ; keys read
ST_END          equ 88
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
V_SIZE          equ 20

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

; Interrupt structure
IS_SIZE         equ 22

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
        move.l  #'PIAN',STATUS+ST_MAGIC.w

        lea     dosname(pc),a1
        moveq   #0,d0
        jsr     _LVOOpenLibrary(a6)
        move.l  d0,dosbase
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
        bmi.s   .menu
        bsr     play_arguments
        bra.s   .ended
.menu:  bsr     menu
.ended: move.l  #2,STATUS+ST_STATE.w
        bra.s   close

no_memory:
        lea     memory_text(pc),a0
        bsr     print
failed: move.l  #-1,STATUS+ST_STATE.w
close:  move.l  index_mem,d0
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
        move.l  dosbase,d0
        beq.s   .out
        move.l  d0,a1
        jsr     _LVOCloseLibrary(a6)
.out:   moveq   #0,d0
        rts

; ---------------------------------------------------------------------------
; The pieces: the index, the menu, the arguments.
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

; The menu: list the pieces, read a key, play the piece, until Q.
menu:
        lea     console_name(pc),a0
        move.l  a0,d1
        move.l  #MODE_OLDFILE,d2
        move.l  dosbase,a6
        jsr     _LVOOpen(a6)
        move.l  ExecBase.w,a6
        move.l  d0,console
        bne.s   .open
        lea     no_console_text(pc),a0
        bra     print
.open:  moveq   #-1,d0
        bsr     console_mode
.list:  bsr     print_menu
        move.l  #3,STATUS+ST_STATE.w
.key:   bsr     read_key
        bmi.s   .quit                   ; the window is gone
        cmp.b   #'Q',d0
        beq.s   .quit
        bsr     piece_for_key
        bmi.s   .key
        bsr     play_piece
        bra.s   .list
.quit:  lea     bye_text(pc),a0
        bsr     print
        moveq   #0,d0
        bsr     console_mode
        move.l  console,d1
        move.l  dosbase,a6
        jsr     _LVOClose(a6)
        move.l  ExecBase.w,a6
        rts

print_menu:
        movem.l d2-d3/a2-a3,-(sp)
        lea     menu_keys(pc),a2
        lea     titles,a3
        move.l  pieces,d2
        bra.s   .next
.line:  lea     fmt_args,a1
        lea     keystr,a0
        move.b  (a2)+,(a0)
        move.l  a0,(a1)
        move.l  (a3)+,4(a1)
        lea     menu_line(pc),a0
        bsr     print
.next:  dbf     d2,.line
        lea     menu_tail(pc),a0
        bsr     print
        movem.l (sp)+,d2-d3/a2-a3
        rts

; d0: the piece for the key in d0 (from 0), negative when there is none.
piece_for_key:
        cmp.b   #'a',d0
        bcs.s   .upper
        cmp.b   #'z',d0
        bhi.s   .upper
        sub.b   #'a'-'A',d0
.upper: lea     menu_keys(pc),a0
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

; d0: the next key from the window, upper case for letters; negative when
; the window cannot be read.
read_key:
        movem.l d2-d3/a6,-(sp)
        move.l  dosbase,a6
        move.l  console,d1
        move.l  #keybuf,d2
        moveq   #1,d3
        jsr     _LVORead(a6)
        movem.l (sp)+,d2-d3/a6
        addq.l  #1,STATUS+ST_KEYS.w
        move.l  d0,STATUS+ST_KEY.w
        cmp.l   #1,d0
        bne.s   .none
        moveq   #0,d0
        move.b  keybuf,d0
        move.l  d0,STATUS+ST_KEY.w
        cmp.b   #'a',d0
        bcs.s   .out
        cmp.b   #'z',d0
        bhi.s   .out
        sub.b   #'a'-'A',d0
.out:   tst.l   d0                      ; the caller tests the sign
        rts
.none:  moveq   #-1,d0
        rts

; Put the window's console handler in raw mode (d0 = -1) or cooked mode
; (d0 = 0) with an ACTION_SCREEN_MODE packet, sent from this process's
; message port and waited for there.
console_mode:
        movem.l d2/a2-a3,-(sp)
        move.l  d0,d2
        move.l  console,d0
        lsl.l   #2,d0                   ; a BPTR
        move.l  d0,a0
        move.l  fh_Type(a0),d0
        beq.s   .out                    ; no handler (NIL:)
        move.l  d0,a3
        sub.l   a1,a1
        jsr     _LVOFindTask(a6)
        move.l  d0,a2
        lea     pr_MsgPort(a2),a2
        lea     packet,a1
        lea     MESSAGE_SIZE(a1),a0
        move.b  #NT_MESSAGE,LN_TYPE(a1)
        move.l  a0,LN_NAME(a1)
        move.l  a2,MN_REPLYPORT(a1)
        move.w  #DOSPACKET_SIZE,MN_LENGTH(a1)
        move.l  a1,dp_Link(a0)
        move.l  a2,dp_Port(a0)
        move.l  #ACTION_SCREEN_MODE,dp_Type(a0)
        move.l  d2,dp_Arg1(a0)
        move.l  a3,a0
        jsr     _LVOPutMsg(a6)
        move.l  a2,a0
        jsr     _LVOWaitPort(a6)
        move.l  a2,a0
        jsr     _LVOGetMsg(a6)
.out:   movem.l (sp)+,d2/a2-a3
        rts

; The pieces named in the arguments, one menu key each, in order; d0 is
; the first key.
play_arguments:
.piece: bsr     piece_for_key
        bmi.s   .next                   ; not a key on the menu
        bsr     play_piece
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
; One piece: load its score, play it, free it, say what it measured.
; ---------------------------------------------------------------------------

; Play piece d0 (from 0).
play_piece:
        movem.l d2-d7/a2-a5,-(sp)
        move.l  d0,d6
        move.l  d0,d7
        lsl.l   #2,d7
        lea     fmt_args,a1
        lea     titles,a0
        move.l  0(a0,d7.l),(a1)
        lea     loading_text(pc),a0
        bsr     print
        lea     files,a0
        move.l  0(a0,d7.l),a0
        bsr     load_file
        tst.l   d0
        bne.s   .loaded
        lea     no_score_text(pc),a0
        bsr     print
        bra     .out
.loaded:
        move.l  d0,score_mem
        move.l  d1,score_bytes
        bsr     reset_piece
        move.l  d6,STATUS+ST_PIECE.w
        move.l  score_mem,score_ptr
        move.l  score_mem,STATUS+ST_SCORE.w
        move.l  score_bytes,STATUS+ST_SCORE_BYTES.w
        moveq   #MEMF_CHIP,d1
        jsr     _LVOAvailMem(a6)
        move.l  d0,STATUS+ST_CHIP_FREE.w
        moveq   #0,d1
        jsr     _LVOAvailMem(a6)
        sub.l   STATUS+ST_CHIP_FREE.w,d0
        move.l  d0,STATUS+ST_OTHER_FREE.w
        lea     fmt_args,a1
        move.l  score_bytes,(a1)
        move.l  score_mem,4(a1)
        move.l  STATUS+ST_CHIP_FREE.w,8(a1)
        move.l  STATUS+ST_OTHER_FREE.w,12(a1)
        lea     playing_text(pc),a0
        bsr     print
        lea     stop_hint(pc),a0
        tst.l   console
        bne.s   .hint
        lea     play_hint(pc),a0
.hint:  bsr     print
        bsr     take_audio
        bsr     take_timer
        tst.l   d0
        bne.s   .busy
        move.l  #1,STATUS+ST_STATE.w
        bsr     wait_for_end
        bsr     give_timer
.busy:  bsr     give_audio

        move.l  score_mem,a1
        move.l  score_bytes,d0
        addq.l  #1,d0
        jsr     _LVOFreeMem(a6)
        addq.l  #1,STATUS+ST_PLAYED.w
        bsr     print_results
.out:   movem.l (sp)+,d2-d7/a2-a5
        rts

; Wait for the interrupts to finish the piece, or for a key in the window,
; or for CTRL-C. The task sleeps in WaitForChar or Delay meanwhile.
wait_for_end:
.wait:  tst.w   finished
        bne.s   .out
        moveq   #0,d0
        moveq   #0,d1
        jsr     _LVOSetSignal(a6)
        and.l   #SIGBREAKF_CTRL_C,d0
        bne.s   .stop
        move.l  dosbase,a6
        move.l  console,d1
        beq.s   .delay
        move.l  #WAIT_US,d2
        jsr     _LVOWaitForChar(a6)
        move.l  ExecBase.w,a6
        tst.l   d0
        beq.s   .wait
        bsr     read_key                ; take the key that stopped it
.stop:  move.l  #1,STATUS+ST_STOPPED.w
        rts
.delay: moveq   #1,d1                   ; 1/50 s
        jsr     _LVODelay(a6)
        move.l  ExecBase.w,a6
        bra.s   .wait
.out:   rts

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
        tst.w   timer_busy
        beq.s   .say
        lea     busy_text(pc),a0
        bra.s   .print
.say:   tst.l   STATUS+ST_STOPPED.w
        beq.s   .print
        lea     stopped(pc),a0
.print: bsr     print
        if      LOG
        lea     log_text(pc),a0
        lea     fmt_args,a1
        move.l  STATUS+ST_LOGBYTES.w,(a1)
        move.l  STATUS+ST_LOGBASE.w,4(a1)
        bsr     print
        endif
        rts

; Load the file named a0 (a C string) into new public memory, with a 0
; after it. d0: the memory, or 0 when the file or the memory is missing;
; d1: the file's size. Free it with FreeMem(d0, d1 + 1).
load_file:
        movem.l d2-d5/a2,-(sp)
        move.l  dosbase,a6
        move.l  a0,d1
        move.l  #MODE_OLDFILE,d2
        jsr     _LVOOpen(a6)
        move.l  d0,d4
        beq.s   .fail
        move.l  d4,d1
        moveq   #0,d2
        moveq   #OFFSET_END,d3
        jsr     _LVOSeek(a6)
        move.l  d4,d1
        moveq   #0,d2
        moveq   #OFFSET_BEGINNING,d3
        jsr     _LVOSeek(a6)            ; returns where it was: the end
        move.l  d0,d5
        ble.s   .close
        move.l  ExecBase.w,a6
        move.l  d5,d0
        addq.l  #1,d0
        move.l  #MEMF_PUBLIC|$10000,d1  ; cleared, so the 0 after it is there
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
        movem.l d2-d3/a2-a3/a6,-(sp)
        lea     putchar(pc),a2
        lea     textbuf,a3
        jsr     _LVORawDoFmt(a6)
        lea     textbuf,a0
        moveq   #-1,d3
.len:   addq.l  #1,d3
        tst.b   (a0)+
        bne.s   .len
        move.l  dosbase,a6
        jsr     _LVOOutput(a6)
        move.l  d0,d1
        beq.s   .out
        move.l  #textbuf,d2
        jsr     _LVOWrite(a6)
.out:   movem.l (sp)+,d2-d3/a2-a3/a6
        rts

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

; Stop voice d7's channel. Uses d0, a0.
stop_voice:
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
        rts


dosname:        dc.b "dos.library",0
ciabname:       dc.b "ciab.resource",0
console_name:   dc.b "*",0
index_name:     dc.b "scores/index",0
menu_keys:      dc.b "123456789ABCDEFGHIJKLMNOPRSTUVWXYZ"
banner:         dc.b "EXP-004, the expressive piano: %ld pieces.",10
                dc.b "Samples: %ld bytes at $%lx in chip RAM,",10
                dc.b "%s.",10,0
loaded:         dc.b "where LoadSeg put them",0
copied:         dc.b "copied there from elsewhere",0
menu_line:      dc.b " %s  %s",10,0
menu_tail:      dc.b " Q  Quit",10
                dc.b "Press a key: ",0
loading_text:   dc.b 10,"%s",10,0
playing_text:   dc.b "Score: %ld bytes at $%lx.",10
                dc.b "Free memory: %ld bytes chip, %ld other.",10,0
stop_hint:      dc.b "Playing; press any key to stop.",10,0
play_hint:      dc.b "Playing.",10,0
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
no_console_text: dc.b "Cannot open the CLI window (*) for the menu.",10,0
bye_text:       dc.b 10,"Bye.",10,0
        if      LOG
log_text:       dc.b "Voice log: %ld bytes at $%lx.",10,0
        endif
intname:        dc.b "EXP-004 piano",0
        even

        section tables,data

ciaint:         dc.l 0,0
                dc.b NT_INTERRUPT,0
                dc.l intname,0,cia_handler
audints:
        rept    VOICES
                dc.l 0,0
                dc.b NT_INTERRUPT,0
                dc.l intname,REPTN,aud_handler
        endr
keys:           incbin "keys.bin"
sampletab:      incbin "samples.tab"
velocity:       incbin "velocity.bin"
        even

        section samples,data_c

samples:        incbin "samples.bin"
samples_end:

        section state,bss

bss_start:
packet:         ds.b MESSAGE_SIZE+DOSPACKET_SIZE    ; first: longword aligned
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
score_ptr:      ds.l 1
old_audio:      ds.l VOICES
samples_base:   ds.l 1
dosbase:        ds.l 1
ciabbase:       ds.l 1
console:        ds.l 1                  ; the CLI window, for the menu; 0 without it
args:           ds.l 1
args_len:       ds.l 1
pieces:         ds.l 1
files:          ds.l MAX_PIECES
titles:         ds.l MAX_PIECES
index_mem:      ds.l 1
index_bytes:    ds.l 1
score_mem:      ds.l 1
score_bytes:    ds.l 1
log_ptr:        ds.l 1
log_end:        ds.l 1
fmt_args:       ds.l 4
timer_busy:     ds.w 1
keybuf:         ds.b 2
keystr:         ds.b 2
textbuf:        ds.b 512
bss_end:
