#!/usr/bin/env python3
"""Supervisor-Eventlistener fuer den App-Prozess.

Ohne das koennte der App-Prozess dauerhaft (FATAL) ausfallen, waehrend
supervisord und damit PID 1 (tini) weiterlaufen - der Container gilt fuer
Docker/Coolify dann weiter als "up". Ein HEALTHCHECK allein macht das nur
sichtbar (Status "unhealthy"), beendet den Container aber nicht. Dieser
Listener beendet den Container aktiv, sobald der App-Prozess dauerhaft
gescheitert ist, statt ihn scheintot weiterlaufen zu lassen.

Implementiert das Supervisor-Eventlistener-Protokoll:
https://supervisord.org/events.html#event-listeners-and-event-notifications
"""

import os
import signal
import sys


def _schreibe(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _lies_ereignis() -> tuple[dict, dict]:
    _schreibe("READY\n")
    kopfzeile = sys.stdin.readline()
    kopf = dict(feld.split(":", 1) for feld in kopfzeile.split() if ":" in feld)
    nutzlast = sys.stdin.read(int(kopf.get("len", "0")))
    daten = dict(feld.split(":", 1) for feld in nutzlast.split() if ":" in feld)
    return kopf, daten


def main() -> None:
    while True:
        kopf, daten = _lies_ereignis()
        ist_app_fatal = (
            kopf.get("eventname") == "PROCESS_STATE_FATAL"
            and daten.get("processname") == "app"
        )
        if ist_app_fatal:
            sys.stderr.write(
                "FEHLER: Der App-Prozess ist dauerhaft (FATAL) gescheitert. "
                "Beende den Container, statt ihn scheintot weiterlaufen zu "
                "lassen.\n"
            )
            sys.stderr.flush()
            _schreibe("RESULT 2\nOK")
            # SIGTERM an PID 1 (tini) - genau das, was auch "docker stop"
            # ausloest. tini reicht es an supervisord weiter, das dann den
            # gewohnten, geordneten Shutdown aller Programme durchfuehrt
            # (siehe stopsignal/stopwaitsecs in supervisord.conf).
            os.kill(1, signal.SIGTERM)
        else:
            _schreibe("RESULT 2\nOK")


if __name__ == "__main__":
    main()
