# Work:

This folder is the `Work:` volume of the `a3000-dev` machine (see
`amiga.toml`). Put source here to edit it on the Mac and build it on the
Amiga with SAS/C. Git tracks the sources; what the Amiga writes here
(objects, programs, icons, output) is ignored.

Each example has a `test.amigados` script that builds and runs it with no
person present:

```sh
uv run amiga-env exec a3000-dev work/hello/test.amigados
uv run amiga-env exec a3000-dev work/muihello/test.amigados --screenshot runs/muihello.png
```

- `hello/`: a C program that prints one line. Its output is left in
  `hello/output.txt`.
- `muihello/`: a MUI window with a line of text and a Quit button.
