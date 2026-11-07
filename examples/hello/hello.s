; hello.s: print one line to the CLI through dos.library.
;
; Targets the baseline A500: a 68000 on Kickstart 1.2 (exec and dos
; version 33). Build and boot it with:
;
;   make hello
;   uv run amiga-env a500 build/hello.adf
;
; The library vector offsets come from the NDK FD files (exec_lib.fd and
; dos_lib.fd): each function is 6 bytes further below the library base,
; starting at the ##bias. They are written out here so the example
; assembles without the licensed NDK includes.

_LVOOpenLibrary  equ -552
_LVOCloseLibrary equ -414
_LVOOutput       equ -60
_LVOWrite        equ -48

ExecBase         equ 4

        section code,code

start:
        move.l  ExecBase.w,a6
        lea     dosname(pc),a1
        moveq   #0,d0                   ; any version
        jsr     _LVOOpenLibrary(a6)
        tst.l   d0
        beq.s   nodos
        move.l  d0,a6                   ; a6 = DOSBase

        jsr     _LVOOutput(a6)          ; d0 = the CLI's output handle
        move.l  d0,d1
        beq.s   close
        ; An absolute address on purpose: it makes the executable carry a
        ; relocation, which tests that the hunk format suits Kickstart 1.2.
        move.l  #message,d2
        moveq   #message_end-message,d3
        jsr     _LVOWrite(a6)

close:
        move.l  a6,a1
        move.l  ExecBase.w,a6
        jsr     _LVOCloseLibrary(a6)
        moveq   #0,d0                   ; return code 0
        rts

nodos:
        moveq   #20,d0                  ; RETURN_FAIL
        rts

dosname:
        dc.b    "dos.library",0
message:
        dc.b    "Hello from 68000 assembly on Kickstart 1.2",10
message_end:
