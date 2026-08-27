Flashcards und einfache Fragestellungen. 

Ziel ist es, eine einfache Webseite zu erstellen, auf der Flashkarten oder einfache Fragen mit A, B, C und so weiter dargestellt werden. Jede Webseite erhält einen eindeutigen Link, der aus drei Wörtern besteht. Innerhalb dieser drei Links werden dann eine entsprechende Menge an Flashcards oder Fragen bereitgestellt. Bei einer Frageseite möchte ich am Ende immer mein Ergebnis sehen. Das bedeutet, wenn ich eine Frage beantwortet habe, dreht sie sich um und zeigt mir das Ergebnis, ob ich richtig oder falsch lag, und gibt mir die entsprechende Korrektur. Am Ende möchte ich dann natürlich ein Gesamtresultat erhalten. Ich möchte immer eine Übersicht sehen. Frage 1 von "xx". Ich brauche Steuerbefehle wie "vor", "zurück" und "beenden". 
Am Anfang gibt es einen Start-Button, der das Thema startet. Dieser kann entweder eine Flashcard-Abfrage oder eine Frageliste aktivieren, oder sogar eine Mischung aus beidem. Das ist dann ein Hybrid, den ich hier gerne darstellen möchte. 

Zur Technologie: Das Ganze soll ein Webserver sein, der innerhalb eines Docker-Containers läuft. Die Daten der Flashcards oder Fragen sollen aus einem Postgres-Container, beziehungsweise einer Postgres-Datenbank, stammen, die innerhalb dieses Docker-Containers läuft.

Zum Befüllen der Flashcards möchte ich keinen administrativen Zugang haben, sondern einen MCP-Zugang. Das heißt, ein KI-Agent soll diese Flashcards oder Fragelisten erstellen können und dann immer in einem Bundle starten. Die Datenbank hält dann eine Flashcard-Seite mit einem Drei-Wortsatz, welcher nachher die URL der Seite bildet. Innerhalb dieser Seite werden dann die entsprechenden Flashcards oder Fragen geladen.

Es gibt keine Benutzeranmeldung, das heißt, wer den Link kennt, kann direkt mit diesem Projekt, also mit dieser Frageliste, anfangen. Der Hintergrund dieser ganzen Geschichte ist, dass das Ganze für eine Schule ist und die Lehrerin mit Cloud Code als Agent aus dem Arbeitsplatz die entsprechenden Flashcards oder Fragelisten erzeugt. 

Der Agent muss mittels MCP in der Lage sein, einen neuen Flashcard-Ordner anzulegen. Er muss dort die Fragen eintragen, editieren oder löschen können. 

Abgesichert soll der MCP-Server oder Bearer-Token sein, der in der ENV-Datei gepflegt wird. 
Die Zugangsgänge für PostgreSQL sowie alle Passwörter sollen in der ENV-Datei gespeichert werden. 

Das Design möchte ich gerne zusammen mit dem Agenten besprechen und vorher einen Prototypen bauen, um zu sehen, wie das Ganze aussieht. Die Flashcards selbst sollen immer wie Post-its aussehen. Wenn man darauf klickt, klappen sie um. Bei einer Frage habe ich dann eine Auswahl zwischen A, B, C und D. Diese sollen natürlich mit der Tastatur oder der Maus bedienbar sein. Wenn ich sie umdrehe, also wenn ich darauf klicke, wird das Ergebnis präsentiert und es wird angezeigt, ob es grün oder rot ist. Bei rot wird mir angezeigt, welche Antwort richtig war. 

Die Speicherung der Daten hat einen Unterschied zwischen Flashcards und Fragelisten. Bei den Fragelisten steht immer die Frage, und die Antwortmöglichkeiten sind einem JSON-Dokument hinterlegt. Es gibt immer die richtige Antwort. Die Punkte zeigen an, ob du richtig oder falsch geantwortet hast. Das bedeutet, am Ende habe ich 20 Fragen, davon 20 richtig beantwortet, mehr nicht. Dann gibt es die Option, noch einmal zu starten, und der Counter wird zurückgesetzt, ohne Cookies zu setzen, sondern einfach nur insgesamt speichern. 

Der KRI-Agent muss per MCP die Möglichkeit haben, eine Flashcard-Seite zu löschen, damit sie nicht mehr aktiv ist. Er muss außerdem Zugang zu allen Flashcards beziehungsweise drei Wort-URLs haben, die in der Datenbank vorhanden sind. Es macht Sinn, eine kleine Beschreibung hinzuzufügen, also Titel und Beschreibung, um was es sich bei dieser Flashcard handelt. Eventuell sollte auch die Klasse angegeben werden, damit die Lehrerin die Flashcards den entsprechenden Klassen zuordnen kann. 
