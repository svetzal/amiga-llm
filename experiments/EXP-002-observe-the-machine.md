---
id: EXP-002
gloss: the observation channels
status: planned
---

# EXP-002: Which channel lets an agent observe the emulated Amiga reliably?

## Question

coco-llm captured its emulator by finding the XRoar window by process id,
cropping the frame and retrying when the display slept. An agent could not
observe the machine reliably. Which channel works here?

## Candidates

1. A mounted host directory (EXP-001, the headless boot, establishes it):
   programs write results as files.
2. The serial port bridged to a host TCP socket: a text console in both
   directions.
3. Amiberry screenshots taken on demand.
4. A libretro host around the released Amiberry core: step frames, inject
   keys, read the frame buffer.

## Hypothesis

Channels 1 and 2 together are enough for every planned experiment that does
not test the display, and each delivers 100 of 100 scripted round trips with
no retry logic. Screenshots are needed only for display experiments.

Refuted if either channel loses or corrupts a round trip, or needs retries.

## Procedure

To be written once EXP-001, the headless boot, is supported.

## Evidence tier

Machine level (Amiberry).

## Results

None yet.
