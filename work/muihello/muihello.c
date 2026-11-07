/*
 * A minimal MUI program: one window with a line of text and a button.
 * Built on the A3000 with SAS/C 6.50 against the 3.1 Developer Update and
 * the MUI 3.8 developer includes. The button or the close gadget ends it.
 */
#include <exec/types.h>
#include <dos/dos.h>
#include <libraries/mui.h>
#include <proto/exec.h>
#include <proto/intuition.h>
#include <proto/muimaster.h>
#include <clib/alib_protos.h>
#include <stdio.h>

#ifndef MAKE_ID
#define MAKE_ID(a, b, c, d) \
    ((ULONG)(a) << 24 | (ULONG)(b) << 16 | (ULONG)(c) << 8 | (ULONG)(d))
#endif

struct Library *MUIMasterBase;

static BOOL window_is_open(Object *window)
{
    ULONG open = FALSE;

    get(window, MUIA_Window_Open, &open);
    return (BOOL)open;
}

int main(void)
{
    Object *app, *window, *quit;
    ULONG signals = 0;

    MUIMasterBase = OpenLibrary(MUIMASTER_NAME, MUIMASTER_VMIN);
    if (MUIMasterBase == NULL) {
        printf("could not open %s\n", MUIMASTER_NAME);
        return RETURN_FAIL;
    }

    app = ApplicationObject,
        MUIA_Application_Title, "MUIHello",
        MUIA_Application_Base, "MUIHELLO",
        SubWindow, window = WindowObject,
            MUIA_Window_Title, "Hello from MUI",
            MUIA_Window_ID, MAKE_ID('H', 'E', 'L', 'O'),
            WindowContents, VGroup,
                Child, TextObject,
                    MUIA_Text_Contents, "\33cHello from SAS/C 6.50 and MUI 3.8",
                End,
                Child, quit = SimpleButton("_Quit"),
            End,
        End,
    End;

    if (app == NULL) {
        printf("could not create the application\n");
        CloseLibrary(MUIMasterBase);
        return RETURN_FAIL;
    }

    DoMethod(window, MUIM_Notify, MUIA_Window_CloseRequest, TRUE,
             app, 2, MUIM_Application_ReturnID, MUIV_Application_ReturnID_Quit);
    DoMethod(quit, MUIM_Notify, MUIA_Pressed, FALSE,
             app, 2, MUIM_Application_ReturnID, MUIV_Application_ReturnID_Quit);

    set(window, MUIA_Window_Open, TRUE);
    printf("window open: %s\n", window_is_open(window) ? "yes" : "no");
    fflush(stdout);

    while (DoMethod(app, MUIM_Application_NewInput, &signals)
           != MUIV_Application_ReturnID_Quit) {
        if (signals) {
            signals = Wait(signals | SIGBREAKF_CTRL_C);
            if (signals & SIGBREAKF_CTRL_C)
                break;
        }
    }

    MUI_DisposeObject(app);
    CloseLibrary(MUIMasterBase);
    printf("closed\n");
    return RETURN_OK;
}
