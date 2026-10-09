# Copyright Olivenda (Oliver Petz) 2026
"""English UI text. The game is written in German; draw_text() runs every string through i18n.tr().

EXACT     - whole strings (case-insensitive, all-caps sources stay all-caps)
TEMPLATES - '{}' captures text that is translated again (names stay as they are), '{#}' captures a
            number, '{2}' in the English side reorders captures
PATTERNS  - raw regexes for the few strings that need code
"""

from __future__ import annotations

import re

EXACT: dict[str, str] = {
    # ---------------------------------------------------------------- general
    "Du": "You", "DU": "YOU", "Du (Spieler)": "You (Player)", "(du)": "(you)", "An": "On", "Aus": "Off",
    "an": "on", "aus": "off", "Ja": "Yes", "Nein": "No", "Leicht": "Easy", "Mittel": "Medium", "Schwer": "Hard",
    "Voll": "Full", "Leise": "Quiet", "Laut": "Loud", "Normal": "Normal", "Doppelt": "Double",
    "keine": "none", "- keine -": "- none -", "- leer -": "- empty -", "ZURÜCK": "BACK", "WEITER": "CONTINUE",
    "SPEICHERN": "SAVE", "START": "START", "BEENDEN": "QUIT", "PAUSE": "PAUSE", "FERTIG": "DONE",
    "EMPFOHLEN": "RECOMMENDED", "NEUTRAL": "NEUTRAL", "MAX": "MAX", "Status": "Status", "Sound": "Sound",
    "ENTER/ESC zurück": "ENTER/ESC back", "ENTER: weiter": "ENTER: continue", "Strecke": "Track",
    "Modus": "Mode", "Gegner": "Opponents", "Dein Team": "Your team", "Startreifen": "Starting tyres",
    "Fahrzeug-Setup": "Car setup", "Fahrerfeld": "Driver field", "English": "English", "Deutsch": "Deutsch",
    "Gulivers Gieles F1 Game": "Gulivers Gieles F1 Game", "Team": "Team", "Teams": "Teams",
    "Referenz": "Reference", "Referenzauto": "Reference car", "Player Racing": "Player Racing",
    "Dein KI-Klon": "Your AI clone", "Trained on You": "Trained on You", "Kontakt": "Contact",
    "Leader": "Leader", "beste": "best", "Durchschnitt": "Average",
    # ---------------------------------------------------------------- main menu & modes
    "EINZELSPIELER": "SINGLE PLAYER", "KARRIERE": "CAREER", "WELTMEISTERSCHAFT": "CHAMPIONSHIP",
    "ZUSCHAUEN": "SPECTATE", "EINSTELLUNGEN": "SETTINGS", "ZUSCHAUER-RENNEN": "SPECTATOR RACE",
    "KI-TRAINING": "AI TRAINING", "GRAND PRIX": "GRAND PRIX",
    "Fahre selbst ein Rennwochenende gegen die KI": "Drive a race weekend yourself against the AI",
    "Fahrer-Karriere mit Verträgen & Rivalen oder eigenes Team als Teamchef":
        "Driver career with contracts & rivals, or run your own team as team principal",
    "Saison über alle Strecken mit WM-Punkten, Fahrer- und Teamwertung":
        "A season across all tracks with championship points, driver and team standings",
    "Nur KI-Fahrer - lehn dich zurück, TV-Regie inklusive": "AI drivers only - sit back, TV director included",
    "Neuronale Netze live trainieren oder deinen Klon erzeugen": "Train neural networks live or create your clone",
    "Name, Fahrhilfen, Ansicht, Schaden, Reifen, Sound, Vollbild":
        "Name, assists, view, damage, tyres, sound, fullscreen",
    "Neuronale KI · Karriere · WM · Aktive Aero · Setup · Sound · 2D/3D":
        "Neural AI · Career · Championship · Aero · Setup · Sound · 2D/3D",
    "Pfeile wählen · ENTER bestätigen · ESC beenden": "Arrows select · ENTER confirm · ESC quit",
    "TEAMS  ·  FAHRZEUG-WERTUNG  (data/teams.json)": "TEAMS  ·  CAR RATINGS  (data/teams.json)",
    "Rennwochenende": "Race weekend", "Freies Training": "Free practice", "Qualifying": "Qualifying",
    "Rennen": "Race", "Nur Rennen": "Race only", "Training + Qualifying + Rennen": "Practice + Qualifying + Race",
    "Qualifying + Rennen": "Qualifying + Race",
    "Training -> Qualifying (3 Runden) -> Rennen mit Podium": "Practice -> Qualifying (3 laps) -> Race with podium",
    "Freie Fahrt mit Live-Zeitentabelle": "Free running with live timing",
    "3 gezeitete Runden bestimmen die Startaufstellung": "3 timed laps decide the starting grid",
    "Zufällige Startaufstellung, direkt zur Ampel": "Random grid, straight to the start lights",
    "Nur KI-Fahrer · TV-Regie wählt die spannendsten Zweikämpfe":
        "AI drivers only · the TV director picks the closest battles",
    "Dein Team, deine Reifen - gegen trainierte neuronale Netze": "Your team, your tyres - against trained neural networks",
    "RENNEN STARTEN": "START RACE", "Aero / Grip": "Aero / Grip", "GEHIRN / STAND": "BRAIN / STAGE",
    "TEST-RUNDE": "TEST LAP", "STARTERFELD": "GRID",
    # ---------------------------------------------------------------- tracks
    "Monte Carlo": "Monte Carlo", "Italien": "Italy", "Großbritannien": "Great Britain", "Belgien": "Belgium",
    "Brasilien": "Brazil", "Singapur": "Singapore",
    "Enger Stadtkurs - Mauern direkt an der Strecke, kaum Platz zum Überholen.":
        "Tight street circuit - walls right next to the track, hardly any room to overtake.",
    "Tempel der Geschwindigkeit - lange Geraden, Schikanen, viel Windschatten.":
        "Temple of speed - long straights, chicanes, lots of slipstream.",
    "Schnelle Kurvenkombinationen - Maggotts/Becketts belohnen Präzision.":
        "Fast corner sequences - Maggotts/Becketts reward precision.",
    "Lang und schnell: La Source, Eau Rouge, Kemmel-Gerade und die Bus-Stop-Schikane.":
        "Long and fast: La Source, Eau Rouge, the Kemmel straight and the Bus Stop chicane.",
    "Kompakt und hügelig: Senna-S, lange Gegengerade und ein verwinkeltes Infield.":
        "Compact and hilly: Senna S, a long back straight and a twisty infield.",
    "Nächtlicher Stadtkurs: 90-Grad-Ecken zwischen Mauern - Präzision vor Tempo.":
        "Night street circuit: 90-degree corners between walls - precision over pace.",
    # ---------------------------------------------------------------- settings
    "Sprache": "Language", "Spielername": "Player name", "Fahrhilfen": "Assists", "Ansicht": "View",
    "Schaden": "Damage", "Reifenverschleiß": "Tyre wear", "Safety Car": "Safety car",
    "TV-Regie (Zuschauer)": "TV director (spectator)", "FPS anzeigen": "Show FPS", "Vollbild": "Fullscreen",
    "Einheiten": "Units", "Bildrate": "Frame rate", "Partikel & Effekte": "Particles & effects",
    "Bremsspuren": "Skid marks",
    "Tippen zum Ändern, Rücktaste löscht. Erscheint in Zeitentabellen und auf dem Podium.":
        "Type to change, backspace deletes. Shown in timing tables and on the podium.",
    "Mittel: Stabilitätskontrolle + farbige Bremslinie. Voll: zusätzlich automatische Bremshilfe vor Kurven.":
        "Medium: stability control + coloured braking line. Full: also automatic braking assist before corners.",
    "Startansicht im Rennen. Im Rennen jederzeit mit V umschalten.":
        "Starting view in the race. Switch any time with V.",
    "An: Treffer beschädigen Frontflügel, Heck und Aufhängung (weniger Grip/Tempo, Auto zieht). Reparatur beim "
    "Boxenstopp. Mit Ausfällen: zerstörte Aufhängung = DNF.":
        "On: hits damage the front wing, rear and suspension (less grip/pace, car pulls to one side). Repaired at "
        "pit stops. With retirements: broken suspension = DNF.",
    "Doppelt macht Strategie und Boxenstopps wichtiger, Aus deaktiviert den Verschleiß.":
        "Double makes strategy and pit stops more important, Off disables wear.",
    "Die Kamera springt automatisch zu engen Zweikämpfen (im Rennen mit A umschalten).":
        "The camera jumps to close battles automatically (toggle with A in the race).",
    "Sprache des Spiels / game language. Standard: English.": "Game language / Sprache des Spiels. Default: English.",
    "Bei Ausfällen und schweren Unfällen: Safety Car (Feld fährt geschlossen hinter dem SC, Restart) oder "
    "Virtuelles Safety Car (alle langsamer). Gelbe Flaggen, Reifenschäden.":
        "After retirements and big crashes: safety car (field bunches up behind the SC, restart) or virtual "
        "safety car (everyone slows down). Yellow flags, punctures.",
    "V6-Turbo-Motor mit Zündfolge, Turbopfeifen, Getriebesurren, Schaltrucken und Fehlzündungen beim "
    "Gaswegnehmen, Reifenquietschen, Kies, Fahrtwind, Einschläge und Startampel - Gegner in Stereo mit "
    "Dopplereffekt. Alles live erzeugt, ohne Audiodateien.":
        "V6 turbo engine with firing order, turbo whistle, gearbox whine, shift kicks and backfires when lifting, "
        "tyre squeal, gravel, wind, impacts and start lights - opponents in stereo with Doppler effect. All "
        "generated live, no audio files.",
    "Bildrate unten rechts einblenden (im Rennen auch mit F3).": "Show the frame rate bottom right (F3 in the race).",
    "Skaliert das Spiel auf den ganzen Bildschirm.": "Scales the game to the whole screen.",
    "Einstellungen werden automatisch gespeichert.": "Settings are saved automatically.",
    "Geschwindigkeit in km/h oder mph - im HUD, in der Garage und in der Analyse.":
        "Speed in km/h or mph - in the HUD, the garage and the race analysis.",
    "Höhere Bildrate = flüssiger, braucht mehr Rechenleistung.": "Higher frame rate = smoother, needs more CPU.",
    "Reifenrauch, Funken bei Einschlägen, Staub neben der Strecke und Bremsspuren auf dem Asphalt.":
        "Tyre smoke, sparks on impacts, dust off track and skid marks on the tarmac.",
    "3D-Verfolgerkamera": "3D chase camera", "2D-Draufsicht": "2D top-down view",
    "Mittel (Stabilität + Bremslinie)": "Medium (stability + braking line)",
    "Voll (+ automatische Bremshilfe)": "Full (+ automatic braking assist)", "An + Ausfälle": "On + retirements",
    "Pfeile hoch/runter wählen · links/rechts ändern · ESC zurück": "Up/down select · left/right change · ESC back",
    "Gespeichert in data/settings.json": "Saved in data/settings.json",
    # ---------------------------------------------------------------- weekend / race
    "Startaufstellung": "Starting grid", "Ergebnis Freies Training": "Free practice result",
    "weiter zum Qualifying": "on to qualifying", "zurück zum Menü": "back to menu", "zum Rennen": "to the race",
    "zur Karriere": "to the career", "zur WM-Wertung": "to the standings", "zurück zum Hauptmenü": "back to main menu",
    "zur Rennanalyse": "to the race analysis", "ESC: abbrechen": "ESC: cancel",
    "POS": "POS", "FAHRER": "DRIVER", "TEAM": "TEAM", "BESTZEIT": "BEST TIME", "ABSTAND": "GAP",
    "RUNDEN": "LAPS", "RUNDENZEITEN": "LAP TIMES", "ABSTAND (+STRAFE)": "GAP (+PENALTY)", "BESTE RUNDE": "BEST LAP",
    "ABSTAND ZUM FÜHRENDEN": "GAP TO LEADER", "VOR DIR": "AHEAD", "HINTER DIR": "BEHIND",
    "DELTA ZUR BESTZEIT": "DELTA TO BEST", "RENNINGENIEUR": "RACE ENGINEER", "PROGNOSE": "FORECAST",
    "RENNLEITUNG": "RACE CONTROL", "FUNK": "RADIO", "PROTOKOLL": "LOG", "KLASSEMENT": "CLASSIFICATION",
    "FAHRERWERTUNG": "DRIVER STANDINGS", "TEAMWERTUNG": "TEAM STANDINGS", "RENNANALYSE": "RACE ANALYSIS",
    "FAKTEN": "FACTS", "GAS": "THR", "BREMSE": "BRK", "BREMSHILFE": "BRAKE ASSIST", "GERADE": "STRAIGHT",
    "KURVE": "CORNER", "SOG": "TOW", "RUNDE": "LAP", "LETZTE": "LAST", "BOX": "BOX", "ZIEL": "FINISH",
    "SAFETY CAR IN THIS LAP": "SAFETY CAR IN THIS LAP", "RESTART AN DER ZIELLINIE": "RESTART AT THE LINE",
    "RASEN!": "GRASS!", "PIT LIMITER  100 km/h": "PIT LIMITER  100 km/h",
    "Auto abstellen. Das war's für heute.": "Park the car. That's it for today.",
    "Limiter an, rein in die Box.": "Limiter on, into the pits.",
    "Reifenschaden! Langsam zurück an die Box.": "Puncture! Bring it back to the pits slowly.",
    "Restart kommt - Reifen warm halten, bereit machen!": "Restart coming - keep the tyres warm, get ready!",
    "Safety Car! Abstand halten, nicht überholen.": "Safety car! Keep your distance, no overtaking.",
    "VSC - Tempo halten, Delta beachten.": "VSC - hold your pace, watch the delta.",
    "Schaden am Auto! Box für Reparatur empfohlen.": "Car damage! Pit for repairs recommended.",
    "Reifen sind am Ende - jetzt reinkommen!": "Tyres are finished - box now!",
    "Blaue Flagge - lass ihn vorbei.": "Blue flag - let him through.",
    "Reifen halten nicht bis ins Ziel - Box mit B.": "Tyres won't last to the end - box with B.",
    "Im Windschatten - Gerade-Modus nutzen!": "In the slipstream - use straight mode!",
    "Gute Runde! Persönliche Bestzeit.": "Good lap! Personal best.",
    "Reifen schaffen es bis ins Ziel. Tempo halten.": "Tyres will make it to the end. Hold the pace.",
    "Alles im grünen Bereich.": "All good.", "B: Box-Anweisung · TAB: 2. Fahrer": "B: pit order · TAB: 2nd driver",
    "Prognose nach der ersten Runde": "Forecast after the first lap", "Reifen über dem Limit!": "Tyres past the limit!",
    "reicht bis ins Ziel": "lasts to the finish", "Frontflügel": "Front wing", "Aufhängung": "Suspension",
    "Heck": "Rear", "Front": "Front", "Auto: keine Schäden": "Car: no damage",
    "V 2D/3D · K Kamera · M Karte · B Box · P Pause · C/1-0 Fahrer · H HUD · I KI · L Linie · R Reset":
        "V 2D/3D · K camera · M map · B box · P pause · C/1-0 driver · H HUD · I AI · L line · R reset",
    "Pfeile/1-0/Klick Fahrer · A TV-Regie · +/- Zeitraffer · V 2D/3D · K Kamera · M Karte · H HUD · P Pause":
        "Arrows/1-0/click driver · A TV director · +/- time warp · V 2D/3D · K camera · M map · H HUD · P pause",
    "P: Weiter    ESC: Hauptmenü": "P: resume    ESC: main menu", "GO!": "GO!",
    "TV-Regie aus (A schaltet sie wieder ein)": "TV director off (A turns it back on)",
    "TV-Regie an": "TV director on", "TV-Regie aus": "TV director off",
    "Entscheidung der Rennleitung": "Race control decision", "Boxenstopp abgesagt": "Pit stop cancelled",
    "Teamchef: Bleib draußen, kein Stopp.": "Team principal: stay out, no stop.",
    "Copy, ich bleibe draußen.": "Copy, staying out.", "Reifen sind noch gut!": "Tyres are still good!",
    "Nur noch eine Runde - auf keinen Fall!": "Only one lap to go - no way!",
    "Ich habe gerade frische Reifen drauf!": "I've only just fitted fresh tyres!",
    "Bin im Zweikampf - noch eine Runde!": "I'm in a fight - one more lap!",
    "Okay, du bist der Chef. Komme rein.": "Okay, you're the boss. Boxing.",
    "Aufhängung gebrochen": "Broken suspension", "BOXENGASSE - Limiter an": "PIT LANE - limiter on",
    "FREIES TRAINING - lerne die Strecke kennen": "FREE PRACTICE - learn the track",
    "ENTER beendet die Session  ·  G Garage (Setup)": "ENTER ends the session  ·  G garage (setup)",
    "Neues Setup montiert": "New setup fitted", "Die Bestzeit bestimmt deinen Startplatz": "Your best time sets your grid slot",
    "Qualifying beendet - die übrigen Fahrer werden simuliert": "Qualifying over - the remaining drivers are simulated",
    "ZUSCHAUER-RENNEN  ·  C Kamera  ·  A TV-Regie  ·  +/- Zeitraffer":
        "SPECTATOR RACE  ·  C camera  ·  A TV director  ·  +/- time warp",
    "ZU FRÜH GAS - Räder drehen durch!": "TOO EARLY ON THE THROTTLE - wheelspin!", "LETZTE RUNDE!": "FINAL LAP!",
    "SAFETY CAR - nicht überholen!": "SAFETY CAR - no overtaking!",
    "VIRTUAL SAFETY CAR - Tempo reduzieren": "VIRTUAL SAFETY CAR - slow down",
    "Günstiger Stopp unter Neutralisation möglich (B)": "Cheap pit stop possible under neutralisation (B)",
    "GRÜNE FLAGGE - Rennen freigegeben": "GREEN FLAG - racing resumes", "GRÜN! RESTART!": "GREEN! RESTART!",
    "VSC ENDE - GRÜN!": "VSC ENDING - GREEN!", "Safety Car kommt in dieser Runde rein": "Safety car in this lap",
    "Position zurückgegeben - keine Strafe": "Position given back - no penalty",
    "abgefahrener Reifen": "worn-out tyre", "REIFENSCHADEN! Sofort an die Box (B)": "PUNCTURE! Box immediately (B)",
    "TRACK LIMITS - Runde gestrichen": "TRACK LIMITS - lap deleted",
    "SCHWARZ-WEISSE FLAGGE - nächster Verstoß wird bestraft": "BLACK AND WHITE FLAG - next offence will be penalised",
    "wiederholte Track-Limits-Verstöße": "repeated track limits violations",
    "Verfolger": "Chase", "Weit": "Wide", "Onboard": "Onboard", "TV-Helikopter": "TV helicopter",
    "SIEG! Herzlichen Glückwunsch!": "VICTORY! Congratulations!", "Platz 2 - starkes Rennen!": "P2 - strong race!",
    "Platz 3 - aufs Podium gefahren!": "P3 - onto the podium!", "Ausgefallen - nächstes Mal!": "Retired - next time!",
    "FAHRER DES TAGES": "DRIVER OF THE DAY", "Teilnahme": "Participation", "SAISON ABBRECHEN": "ABANDON SEASON",
    "SAISON STARTEN": "START SEASON", "NEUE SAISON": "NEW SEASON", "HAUPTMENÜ": "MAIN MENU",
    "WIRKLICH ABBRECHEN? ENTER = JA": "REALLY ABANDON? ENTER = YES",
    "Der Stand wird nach jedem Rennen gespeichert (data/championship.json).":
        "Standings are saved after every race (data/championship.json).",
    "Zuschauer (nur KI)": "Spectator (AI only)", "Zuschauer": "Spectator",
    "Pfeile wählen · ENTER bestätigen · ESC Hauptmenü": "Arrows select · ENTER confirm · ESC main menu",
    "Schnellste Runde": "Fastest lap", "Meiste Plätze gewonnen": "Most places gained",
    "Meiste Plätze verloren": "Most places lost", "Ausfälle": "Retirements", "Boxenstopps gesamt": "Total pit stops",
    "Safety Car / VSC": "Safety car / VSC", "gelber Punkt = Boxenstopp": "yellow dot = pit stop",
    "Höchstgeschwindigkeit": "Top speed", "Speedtrap": "Speed trap",
    # ---------------------------------------------------------------- garage / setup
    "GARAGE · FAHRZEUG-SETUP": "GARAGE · CAR SETUP", "Flügel / Abtrieb": "Wing / downforce",
    "Aero-Balance": "Aero balance", "Getriebe-Übersetzung": "Gear ratios", "Bremsbalance": "Brake bias",
    "Federung": "Suspension", "Reifendruck": "Tyre pressure", "wenig": "low", "viel": "high", "kurz": "short",
    "lang": "long", "hinten": "rear", "vorne": "front", "weich": "soft", "hart": "stiff", "niedrig": "low",
    "hoch": "high",
    "Mehr Flügel = mehr Grip in Kurven, aber mehr Luftwiderstand und weniger Topspeed. Monza/Silverstone: wenig. "
    "Monaco/Marina Bay: viel.":
        "More wing = more grip in corners, but more drag and less top speed. Monza/Silverstone: low. "
        "Monaco/Marina Bay: high.",
    "Richtung Front lenkt das Auto schärfer ein, das Heck wird aber nervöser. Richtung Heck: stabil, aber "
    "Untersteuern.":
        "Towards the front the car turns in sharper but the rear gets nervous. Towards the rear: stable but "
        "understeer.",
    "Kurze Gänge beschleunigen besser, laufen aber im Windschatten/Gerade-Modus in den Drehzahlbegrenzer. Lange "
    "Gänge: höchster Endspeed, träger aus Kurven.":
        "Short gears accelerate better but hit the rev limiter in the slipstream/straight mode. Long gears: "
        "highest top speed, slower out of corners.",
    "Optimal leicht vorne (+1). Zu weit vorne: Untersteuern beim Anbremsen. Zu weit hinten: das Heck bricht beim "
    "Bremsen aus.":
        "Best slightly forward (+1). Too far forward: understeer on corner entry. Too far back: the rear steps "
        "out under braking.",
    "Hart = etwas mehr Grip auf glattem Asphalt, aber mehr Reifenverschleiß und schlechter neben der Strecke. "
    "Weich = reifenschonend.":
        "Stiff = a little more grip on smooth tarmac, but more tyre wear and worse off track. Soft = easy on "
        "the tyres.",
    "Niedriger Druck = mehr Grip, aber mehr Verschleiß und minimal weniger Topspeed. Hoher Druck schont die "
    "Reifen.":
        "Low pressure = more grip, but more wear and slightly less top speed. High pressure saves the tyres.",
    "Grünes Dreieck = empfohlener Wert für diese Strecke": "Green triangle = recommended value for this track",
    "Pfeile wählen/ändern · ENTER/ESC übernehmen": "Arrows select/change · ENTER/ESC apply",
    "Topspeed (Kurven-Modus)": "Top speed (corner mode)", "mit Gerade-Modus + Windschatten": "with straight mode + slipstream",
    "(Begrenzer!)": "(limiter!)", "Kurvengrip": "Cornering grip", "Beschleunigung": "Acceleration",
    "Bremsleistung": "Braking", "Einlenken": "Turn-in", "Heck-Stabilität": "Rear stability",
    "Empfohlen: Basis-Setup für diese Strecke (Flügel nach Vollgas-Anteil). Die KI-Teams fahren dieses Setup.":
        "Recommended: base setup for this track (wing by full-throttle share). The AI teams run this setup.",
    # ---------------------------------------------------------------- sensors / training
    "Rutschen": "Slip", "Querpos.": "Lateral", "Winkel": "Angle", "Radar VL": "Radar FL", "Radar VM": "Radar FC",
    "Radar VR": "Radar FR", "Seite L": "Side L", "Seite R": "Side R", "Annäherung": "Closing", "Lenkung": "Steering",
    "Gas/Bremse": "Throttle/brake", "Generationen": "Generations", "Population": "Population",
    "Basis (Fahren lernen)": "Base (learn to drive)", "Ausgewogen": "Balanced", "Aggressiv": "Aggressive",
    "Vorsichtig": "Cautious", "Klon (deine Daten)": "Clone (your data)",
    "Solo von Null: weit fahren, Mauern und Rasen meiden.": "Solo from scratch: drive far, avoid walls and grass.",
    "Verkehr: Positionen gewinnen, Kontakt vermeiden.": "Traffic: gain positions, avoid contact.",
    "Verkehr: Positionen zählen viel, Kontakt kaum bestraft, Druck lohnt sich.":
        "Traffic: positions count a lot, contact barely punished, pressure pays off.",
    "Verkehr: Kontakt teuer, dichtes Auffahren bestraft.": "Traffic: contact is expensive, tailgating punished.",
    "Lernt deinen Fahrstil aus Aufnahmen, danach kurz verfeinert.":
        "Learns your driving style from recordings, then briefly refined.",
    "Warmstart: Population aus dem vorhandenen Basis-Netz": "Warm start: population from the existing base network",
    "Zu wenige Fahrdaten für einen Klon - fahre zuerst ein paar Runden (Training/Qualifying/Rennen werden "
    "automatisch aufgezeichnet).":
        "Not enough driving data for a clone - drive a few laps first (practice/qualifying/races are recorded "
        "automatically).",
    "Zuerst das Basis-Netz trainieren.": "Train the base network first.",
    "Neuroevolution: Netze fahren, die besten vererben ihre Gewichte weiter.":
        "Neuroevolution: networks drive, the best pass their weights on.",
    "TRAINING STARTEN": "START TRAINING", "Belohnungsfunktion (Fitness):": "Reward function (fitness):",
    "+ gefahrene Strecke (px)": "+ distance driven (px)", "- 400 pro Unfall,  - 250 pro Track-Limits-Verstoß":
        "- 400 per crash,  - 250 per track limits violation",
    "Jede deiner Sessions wird automatisch aufgezeichnet.": "Every one of your sessions is recorded automatically.",
    "ENTER Start · ESC zurück · Pfeiltasten wählen": "ENTER start · ESC back · arrow keys select",
    "TURBO - Darstellung aus, volle Rechenleistung fürs Training": "TURBO - rendering off, full power for training",
    "NETZ DES FÜHRENDEN GENOMS (live)": "NETWORK OF THE LEADING GENOME (live)",
    "TRAINING ABGESCHLOSSEN": "TRAINING COMPLETE",
    "ENTER: zurück zum Menü (neue Gehirne werden sofort verwendet)": "ENTER: back to menu (new brains are used right away)",
    "T Turbo · ESC abbrechen (ohne Speichern)": "T turbo · ESC cancel (without saving)",
    "FITNESS PRO GENERATION": "FITNESS PER GENERATION", "Kurve erscheint nach der 2. Generation":
        "Curve appears after the 2nd generation",
    "Keine trainierten KI-Gehirne gefunden - bitte zuerst 'python train.py all' ausführen oder im Menü "
    "'KI-Training' starten.":
        "No trained AI brains found - run 'python train.py all' first or start 'AI training' in the menu.",
    # ---------------------------------------------------------------- career: general
    "Motor (Beschleunigung)": "Engine (acceleration)", "Aerodynamik (Kurvengrip)": "Aerodynamics (cornering grip)",
    "Luftwiderstand (Topspeed)": "Drag (top speed)", "Bremsen": "Brakes", "Reifenschonung": "Tyre management",
    "Windkanal": "Wind tunnel", "Projekte schneller fertig (+Erfolgschance)": "Projects finish faster (+success chance)",
    "Simulator": "Simulator", "Deine Fahrer verbessern sich während der Saison": "Your drivers improve during the season",
    "Fabrik": "Factory", "Entwicklungsprojekte 8 % billiger je Stufe": "Development projects 8 % cheaper per level",
    "Manager": "Manager", "PR-Berater": "PR adviser", "Mentaltrainer": "Mental coach",
    "Bessere Vertragsangebote: +6 % Gehalt und mehr Verhandlungsspielraum je Stufe":
        "Better contract offers: +6 % salary and more negotiating room per level",
    "+0.4 Ruf nach jedem Rennen je Stufe": "+0.4 reputation after every race per level",
    "+0.5 Vertrauen pro Rennen, verfehlte Wochenendziele kosten weniger Vertrauen":
        "+0.5 trust per race, missed weekend goals cost less trust",
    "Hol dir im Fahrermarkt einen Teamkollegen.": "Sign a team-mate in the driver market.",
    "Hol dir im Fahrermarkt zwei Fahrer.": "Sign two drivers in the driver market.",
    "Willkommen in der Formel 1! Wähle deinen ersten Vertrag.": "Welcome to Formula 1! Choose your first contract.",
    "Zuerst einen Vertrag unterschreiben": "Sign a contract first",
    "Zuerst einen Titelsponsor für diese Saison wählen": "Choose a title sponsor for this season first",
    "Noch ein freies Cockpit - im Fahrermarkt einen Fahrer verpflichten":
        "A seat is still free - sign a driver in the driver market",
    "Saison beendet - Saisonabschluss öffnen": "Season over - open the season review",
    "Nummer-1-Fahrer": "Number 1 driver", "Stammfahrer": "Regular driver", "unter Beobachtung": "under review",
    "Cockpit in Gefahr": "Seat in danger", "Ruf": "Reputation", "Vertrauen": "Trust", "Teamruf": "Team reputation",
    "Sponsor": "Sponsor", "keine Auswirkung": "no effect", "dein Rivale": "your rival",
    "der Konkurrenz": "the competition", "Motor": "Engine", "Aero": "Aero", "Speed": "Speed",
    "ausgeschieden (DNF)": "retired (DNF)", "Du wurdest ausgeschieden (DNF).": "You retired (DNF).",
    "ACHTUNG: Budget im Minus - keine Upgrades oder Verpflichtungen möglich!":
        "WARNING: budget in the red - no upgrades or signings possible!",
    "Für diesen Bereich läuft bereits ein Projekt": "A project is already running for this area",
    "Maximale Stufe erreicht": "Maximum level reached", "Zuverlässigkeit": "Reliability",
    "Maximale Ausbaustufe": "Fully upgraded", "Boxencrew bereits auf Maximalstufe": "Pit crew already at max level",
    "Kein freies Cockpit - zuerst einen Fahrer entlassen": "No free seat - release a driver first",
    "Dieser Name ist schon vergeben": "This name is already taken", "Diesen Namen gibt es schon": "This name already exists",
    "Neu: Jedes Team startet jetzt mit zwei Autos - volles Starterfeld wie in der echten F1.":
        "New: every team now starts with two cars - a full grid like in real F1.",
    "Neues Teil": "New part", "Blaue Flagge ignoriert - Verwarnung! Lass ihn vorbei": "Blue flag ignored - warning! Let him through",
    "Niedrig": "Low", "Hoch": "High", "P: Weiter    R: Neustart    ESC: Hauptmenü": "P: resume    R: restart    ESC: main menu",
    "R: Zufallsrennen (Strecke, Team, Reifen)": "R: random race (track, team, tyres)", "Rennen gesamt": "Races", "Aerodynamik": "Aerodynamics", "Luftwiderstand": "Drag", "AKTUELL": "CURRENT",
    "Rasen": "Grass", "REIFENVERSCHLEISS": "TYRE WEAR", "Eigenes": "Custom", "Empfohlen": "Recommended",
    # ---------------------------------------------------------------- career: achievements
    "Erste Punkte": "First points", "Hol die ersten WM-Punkte": "Score your first championship points",
    "Aufs Treppchen": "On the podium", "Fahre zum ersten Mal aufs Podium": "Finish on the podium for the first time",
    "Erster Sieg": "First win", "Gewinne einen Grand Prix": "Win a Grand Prix", "Pole Position": "Pole position",
    "Starte ein Rennen von Platz 1": "Start a race from P1", "Seriensieger": "Serial winner",
    "Gewinne 5 Rennen": "Win 5 races", "Legende": "Legend", "Gewinne 20 Rennen": "Win 20 races",
    "Dauerbrenner": "Ironman", "Bestreite 50 Rennen": "Start 50 races", "Erzrivale": "Arch-rival",
    "Schlage deinen Rivalen 5-mal in einer Saison": "Beat your rival 5 times in one season",
    "Klare Nummer 1": "Clear number 1", "Sei in jedem Rennen einer Saison vor deinem Teamkollegen":
        "Finish ahead of your team-mate in every race of a season",
    "Musterschüler": "Model student", "Erfülle alle Wochenendziele einer Saison": "Meet every weekend goal of a season",
    "Im Topteam": "Top team", "Unterschreibe bei einem Team mit Top-3-Auto": "Sign for a team with a top-3 car",
    "Gut verdient": "Well paid", "Spare 25 Mio auf deinem Konto an": "Save 25 M in your account",
    "Weltmeister": "World champion", "Gewinne die Fahrer-WM": "Win the drivers' championship",
    "Dynastie": "Dynasty", "Gewinne 3 Fahrer-Titel": "Win 3 drivers' titles",
    "Konstrukteurs-Champion": "Constructors' champion", "Gewinne die Konstrukteurs-WM": "Win the constructors' championship",
    "Ingenieurskunst": "Engineering excellence", "Bringe einen Entwicklungsbereich auf die Maximalstufe":
        "Take a development area to the maximum level",
    "Hightech-Campus": "High-tech campus", "Baue alle Einrichtungen voll aus": "Fully upgrade every facility",
    "Boxen-Weltrekord": "Pit stop world record", "Trainiere die Boxencrew auf die Maximalstufe":
        "Train the pit crew to the maximum level",
    "Königstransfer": "Star signing", "Verpflichte einen Fahrer mit Wertung 88+": "Sign a driver rated 88+",
    "Finanzimperium": "Financial empire", "Erreiche 100 Mio Budget": "Reach a budget of 100 M",
    "Veteran": "Veteran", "Schließe 5 Saisons ab": "Complete 5 seasons",
    # ---------------------------------------------------------------- career: press & events
    "Sieg! Was war heute der Schlüssel?": "A win! What was the key today?",
    "Das Team hat mir ein fantastisches Auto hingestellt.": "The team gave me a fantastic car.",
    "Ich habe heute den Unterschied gemacht.": "I made the difference today.",
    "Wir bleiben auf dem Boden, die Saison ist lang.": "We stay grounded, the season is long.",
    "Podium! Bist du zufrieden?": "Podium! Are you happy?",
    "Absolut, ein starkes Ergebnis fürs ganze Team.": "Absolutely, a strong result for the whole team.",
    "Nein. Ich will gewinnen, nicht Dritter werden.": "No. I want to win, not finish third.",
    "Das Auto hat heute noch nicht für mehr gereicht.": "The car wasn't good enough for more today.",
    "Ausfall. Was ist passiert?": "A retirement. What happened?",
    "Das passiert im Motorsport. Wir kommen stärker zurück.": "That's motorsport. We'll come back stronger.",
    "Das Team muss die Zuverlässigkeit in den Griff kriegen!": "The team has to get the reliability under control!",
    "Kein Kommentar.": "No comment.", "Ein schwieriges Rennen. Woran lag es?": "A difficult race. What went wrong?",
    "Mein Fehler, ich muss mich steigern.": "My mistake, I need to improve.",
    "Das Auto war einfach nicht schnell genug.": "The car simply wasn't fast enough.",
    "Wir analysieren die Daten und lernen daraus.": "We'll analyse the data and learn from it.",
    "Er hatte heute das bessere Paket. Respekt.": "He had the better package today. Respect.",
    "Das wird nicht wieder passieren.": "That won't happen again.",
    "Er hatte Glück mit der Strategie.": "He got lucky with the strategy.",
    "Er ist ein starker Gegner, das war harte Arbeit.": "He's a strong opponent, that was hard work.",
    "Er sollte sich warm anziehen.": "He'd better watch out.", "Ich konzentriere mich nur auf mich.": "I only focus on myself.",
    "Wie läuft das Duell mit deinem Teamkollegen?": "How is the battle with your team-mate going?",
    "Wir pushen uns gegenseitig - gut fürs Team.": "We push each other - good for the team.",
    "Ich will die klare Nummer 1 sein.": "I want to be the clear number 1.",
    "Die Ergebnisse sprechen für sich.": "The results speak for themselves.",
    "Starkes Wochenende. Woher kommt der Aufschwung?": "A strong weekend. Where does the upturn come from?",
    "Unsere Partner machen diese Entwicklung möglich.": "Our partners make this development possible.",
    "Die Fahrer haben überragend gearbeitet.": "The drivers did an outstanding job.",
    "Wir sind noch lange nicht am Ziel.": "We're far from done.",
    "Wieder keine Punkte. Wie geht es weiter?": "No points again. What's next?",
    "Wir investieren massiv in die Entwicklung.": "We're investing heavily in development.",
    "Die Fahrer müssen mehr liefern.": "The drivers have to deliver more.",
    "Geduld - Rom wurde nicht an einem Tag erbaut.": "Patience - Rome wasn't built in a day.",
    "Ein technischer Defekt. Ist die Zuverlässigkeit ein Problem?": "A technical failure. Is reliability a problem?",
    "Wir haben das im Griff, ein Einzelfall.": "We have it under control, a one-off.",
    "Ja, und wir investieren jetzt gezielt dort.": "Yes, and we're now investing specifically there.",
    "Wir wollen sie diese Saison schlagen.": "We want to beat them this season.",
    "Wir schauen nur auf uns.": "We only look at ourselves.", "Sie haben mehr Budget - das ist unfair.":
        "They have more budget - that's unfair.",
    "Vor dem Teamkollegen ins Ziel": "Finish ahead of your team-mate", "Punkte holen (Top 10)": "Score points (top 10)",
    "Feste Zahlung pro Rennen - kein Risiko": "Fixed payment per race - no risk",
    "Weniger Grundgehalt, +0.3 Mio je WM-Punkt": "Lower base pay, +0.3 M per championship point",
    "+3 Mio je Podium, +5 Mio für einen Sieg": "+3 M per podium, +5 M for a win",
    "Motorschaden": "engine failure", "Getriebeschaden": "gearbox failure", "Hydraulikproblem": "hydraulics problem",
    "Elektrikdefekt": "electrical fault", "Bremsdefekt": "brake failure", "Überhitzung": "overheating",
    # ---------------------------------------------------------------- career: screens
    "KARRIERE STARTEN": "START CAREER", "FAHRER-KARRIERE": "DRIVER CAREER", "TEAM-KARRIERE": "TEAM CAREER",
    "Teamname": "Team name", "Teamfarbe": "Team colour", "Selbst fahren": "Drive yourself", "Fahrername": "Driver name",
    "Dein Name": "Your name", "Kürzel": "Code", "Startnummer": "Race number", "Nationalität": "Nationality",
    "Helmfarbe": "Helmet colour", "Format": "Format", "Rennrunden": "Race laps", "KI-Stärke": "AI strength",
    "Auto: Farbton": "Car: hue", "Auto: Sättigung": "Car: saturation", "Auto: Helligkeit": "Car: brightness",
    "Helm: Farbton": "Helmet: hue", "Helm: Sättigung": "Helmet: saturation", "Helm: Helligkeit": "Helmet: brightness",
    "(Namen eintippen)": "(type a name)", "(Timing-Tower)": "(timing tower)",
    "Ja - Teamchef und Fahrer": "Yes - team principal and driver",
    "Nein - nur Teamchef (2 Fahrer verpflichten)": "No - team principal only (sign 2 drivers)",
    "Dein Name, deine Nummer, dein Helm - Verträge, Rivalen, Budget und Entwicklung":
        "Your name, your number, your helmet - contracts, rivals, budget and development",
    "Du startest als Rookie bei einem kleinen Team. Punkte, Siege gegen Teamkollegen und Rivalen bringen Ruf. Mit "
    "deinem Gehalt investierst du in Manager, PR und Mentaltrainer. Am Saisonende kommen Vertragsangebote - mit "
    "genug Ruf auch von den Top-Teams.":
        "You start as a rookie at a small team. Points and beating your team-mate and rival earn reputation. Invest "
        "your salary in a manager, PR and a mental coach. Contract offers arrive at the end of each season - with "
        "enough reputation from the top teams too.",
    "Die Autofarbe kommt von deinem Team - Helm und Nummer gehören dir.":
        "The car colour comes from your team - the helmet and number are yours.",
    "Bitte einen Namen eingeben": "Please enter a name",
    "Diesen Namen trägt schon ein Fahrer oder Team": "A driver or team already has this name",
    "Bitte einen Teamnamen eingeben": "Please enter a team name", "Diesen Teamnamen gibt es schon": "This team name already exists",
    "VERTRAGSANGEBOTE": "CONTRACT OFFERS", "AKTUELLES TEAM": "CURRENT TEAM", "VERHANDLUNG": "NEGOTIATION",
    "kein Risiko": "no risk", "geringes Risiko": "low risk", "mittleres Risiko": "medium risk", "hohes Risiko!": "high risk!",
    "Links/Rechts: Gehalt fordern (80-150 % des Angebots). TAB: Laufzeit 1-3 Saisons. Je höher dein Ruf (und beim "
    "eigenen Team das Vertrauen), desto mehr ist ein Team bereit zu zahlen. Verlangst du zu viel, zieht es sein "
    "Angebot zurück - weniger zu fordern ist immer sicher.":
        "Left/right: ask for salary (80-150 % of the offer). TAB: length 1-3 seasons. The higher your reputation "
        "(and, at your own team, their trust), the more a team is willing to pay. Ask too much and they withdraw "
        "the offer - asking for less is always safe.",
    "Pfeile wählen/fordern · TAB Laufzeit · ENTER unterschreiben": "Arrows select/ask · TAB length · ENTER sign",
    "SAISONABSCHLUSS": "SEASON REVIEW", "SPONSOR WÄHLEN": "CHOOSE SPONSOR", "SIMULIEREN": "SIMULATE",
    "GARAGE": "GARAGE", "ENTWICKLUNG": "DEVELOPMENT", "FAHRERMARKT": "DRIVER MARKET", "PERSÖNLICH": "PERSONAL",
    "DESIGN": "DESIGN", "AUTO-VERGLEICH": "CAR COMPARISON", "STATISTIK": "STATISTICS", "ERFOLGE": "ACHIEVEMENTS",
    "HISTORIE": "HISTORY", "OPTIONEN": "OPTIONS", "SPIELSTÄNDE": "SAVE SLOTS", "LÖSCHEN": "DELETE",
    "WIRKLICH LÖSCHEN?": "REALLY DELETE?", "ohne Vertrag": "no contract", "OHNE TEAM": "NO TEAM",
    "ohne Team": "no team", "noch kein Rennen": "no race yet", "WOCHENENDZIEL DES TEAMS": "TEAM'S WEEKEND GOAL",
    "Saison beendet": "Season over", "RIVALE": "RIVAL", "SPONSOR-LAUNE": "SPONSOR MOOD",
    "Kein Titelsponsor gewählt!": "No title sponsor chosen!", "Zuverl.": "Reliab.",
    "Keine Entwicklungsprojekte laufen": "No development projects running", "- freies Cockpit -": "- free seat -",
    "FAHRER-WM": "DRIVERS' CHAMPIONSHIP", "KALENDER": "CALENDAR", "NACHRICHTEN": "NEWS",
    "SAISON BEENDET": "SEASON OVER", "Weiter zum Saisonabschluss": "On to the season review",
    "NÄCHSTES RENNEN": "NEXT RACE", "FORM (LETZTE 5 RENNEN)": "FORM (LAST 5 RACES)",
    "FORM (BESTES TEAMAUTO)": "FORM (BEST TEAM CAR)", "noch keine Rennen": "no races yet", "LETZTE RENNEN": "RECENT RACES",
    "Boxencrew (sofort)": "Pit crew (instant)", "Arbeit": "Work", "INFRASTRUKTUR": "INFRASTRUCTURE",
    "BUDGETOBERGRENZE (ENTWICKLUNG)": "COST CAP (DEVELOPMENT)", "LAUFENDE PROJEKTE": "RUNNING PROJECTS",
    "TITELSPONSOR": "TITLE SPONSOR", "SICHERHEIT": "SECURITY", "LEISTUNG": "PERFORMANCE", "RISIKO": "RISK",
    "pro Rennen (Grundbetrag)": "per race (base amount)",
    "Die Sponsor-Laune (Presse, Punkte, Defekte) verändert den Grundbetrag um -20 % bis +20 %.":
        "Sponsor mood (press, points, failures) changes the base amount by -20 % to +20 %.",
    "Pfeile wählen · ENTER unterschreiben · ESC zurück": "Arrows select · ENTER sign · ESC back",
    "PRESSEKONFERENZ": "PRESS CONFERENCE", "Deine Antwort hat Folgen - wähle mit Bedacht":
        "Your answer has consequences - choose carefully",
    "JOURNALIST": "JOURNALIST", "Pfeile wählen · ENTER antworten": "Arrows select · ENTER answer",
    "SAISON": "SEASON", "TEAM-WM": "TEAMS' CHAMPIONSHIP", "SIEGE": "WINS", "PODIEN": "PODIUMS",
    "PUNKTE": "POINTS", "WELTMEISTER": "WORLD CHAMPION", "GESAMT": "TOTAL",
    "Noch keine Saison abgeschlossen.": "No season completed yet.", "Titel": "Titles", "Rennen gesamt": "Races", "Siege": "Wins", "Podien": "Podiums", "Punkte": "Points",
    "Sortiert nach Wertung": "Sorted by rating", "Sortiert nach Gehalt": "Sorted by salary",
    "Sortiert nach Alter": "Sorted by age", "LAND": "NAT", "ALTER": "AGE", "WERTUNG": "RATING",
    "POTENZIAL": "POTENTIAL", "STIL": "STYLE", "GEHALT": "SALARY", "RUF": "REP", "Wertung": "Rating",
    "Tempo": "Pace", "KI-Erfahrung": "AI experience", "Reifenmanagement": "Tyre management", "Gehalt": "Salary",
    "Ablöse": "Transfer fee", "Würde unterschreiben": "Would sign", "ENTER: verpflichten": "ENTER: sign",
    "Pfeile hoch/runter wählen · links/rechts Vertragslänge · TAB sortieren · ESC zurück":
        "Up/down select · left/right contract length · TAB sort · ESC back",
    "aggressive": "aggressive", "balanced": "balanced", "cautious": "cautious", "base": "base",
    "SAISONZIEL ERREICHT!": "SEASON GOAL MET!", "Saisonziel verfehlt": "Season goal missed",
    "Gehalt + Prämien": "Salary + bonuses", "Duelle gegen Rivalen": "Duels against rival",
    "Duelle gegen Teamkollegen": "Duels against team-mate", "Vertrag": "Contract", "Einnahmen": "Income",
    "Ausgaben": "Expenses", "Preisgeld Konstrukteure": "Constructors' prize money", "Budget jetzt": "Budget now",
    "AUSLAUFENDE VERTRÄGE": "EXPIRING CONTRACTS", "Keine - alle Fahrer bleiben.": "None - all drivers stay.",
    "Am Saisonende kommen neue Vertragsangebote.": "New contract offers arrive at the end of the season.",
    "Dein Vertrag läuft weiter - du kannst trotzdem wechseln.": "Your contract continues - you can still move.",
    "VERTRAGSANGEBOTE ANSEHEN": "VIEW CONTRACT OFFERS", "ENTER: verlängern (+10 % Gehalt)": "ENTER: extend (+10 % salary)",
    "Nicht verlängerte Fahrer verlassen das Team zur neuen Saison.": "Drivers not extended leave the team for the new season.",
    "Nochmal ENTF: Spielstand wirklich löschen?": "Press DEL again: really delete this save?",
    "Spielstand beschädigt - mit ENTF löschen": "Save is damaged - delete with DEL",
    "KARRIERE · SPIELSTÄNDE": "CAREER · SAVE SLOTS",
    "3 Slots pro Karriere-Art · jeder Slot ist eine eigene Datei in data/careers/":
        "3 slots per career type · every slot is its own file in data/careers/",
    "ENTER: neue Karriere starten": "ENTER: start a new career", "ENTF = LÖSCHEN": "DEL = DELETE",
    "Pfeile wählen · ENTER laden/neu · ENTF löschen · ESC Hauptmenü": "Arrows select · ENTER load/new · DEL delete · ESC main menu",
    "Topspeed": "Top speed", "Reifen": "Tyres", "REIFEN": "TYRES", "MOTOR": "ENGINE", "AERO": "AERO", "SPEED": "SPEED",
    "Noch kein Team": "No team yet", "weiß = Feld-Schnitt · gold = bestes Auto": "white = field average · gold = best car",
    "DESIGN-STUDIO": "DESIGN STUDIO", "Lackierung, Helm, Startnummer und Namen anpassen":
        "Customise livery, helmet, race number and names",
    "SO SIEHT ES IM TIMING-TOWER AUS": "HOW IT LOOKS IN THE TIMING TOWER",
    "Die Autofarbe bestimmt dein Team - Helm, Nummer, Kürzel und Name gehören dir.":
        "Your team decides the car colour - helmet, number, code and name are yours.",
    "Pfeile wählen/ändern (halten = schnell) · Tippen für Text · ENTER speichern · ESC zurück":
        "Arrows select/change (hold = fast) · type for text · ENTER save · ESC back",
    "Der Name darf nicht leer sein": "The name can't be empty", "Design gespeichert": "Design saved",
    "PERSÖNLICHES TEAM": "PERSONAL TEAM", "KONTO": "ACCOUNT",
    "Dein Gehalt wird nach jedem Rennen anteilig ausgezahlt, dazu Punkteprämien und Boni für Wochenendziele. "
    "Investitionen wirken sofort und für den Rest der Karriere.":
        "Your salary is paid out after every race, plus points bonuses and weekend goal bonuses. Investments take "
        "effect immediately and for the rest of your career.",
    "Bestes Ergebnis": "Best result", "Ø Zielplatz": "Avg finish", "Pole Positions": "Pole positions",
    "Noch keine Rennen gefahren.": "No races driven yet.", "PUNKTE UND PLATZIERUNG PRO SAISON":
        "POINTS AND POSITION PER SEASON",
    "KARRIERE-OPTIONEN": "CAREER OPTIONS", "Gespeichert - gilt ab dem nächsten Rennen": "Saved - applies from the next race",
    "Mehr Runden machen Reifen und Boxenstopps wichtiger, weniger Runden machen die Karriere schneller. Die "
    "KI-Stärke bestimmt das Tempo der Gegner. Das Format legt fest, ob es vor dem Rennen Training und Qualifying "
    "gibt. Fortschritt, Verträge und Erfolge bleiben erhalten.":
        "More laps make tyres and pit stops more important, fewer laps make the career faster. AI strength sets the "
        "opponents' pace. The format decides whether there is practice and qualifying before the race. Progress, "
        "contracts and achievements are kept.",
    "Ungespeicherte Änderungen": "Unsaved changes",
    # ---------------------------------------------------------------- wheel / controller
    "Lenkrad & Controller": "Wheel & controller", "nur Tastatur": "keyboard only", "kein Gerät": "no device",
    "ENTER öffnet die Einrichtung: Wheelbase, Pedale und Gamepads kalibrieren, Lenkbereich, Totzone, Vibration und "
    "Tastenbelegung.": "ENTER opens the setup: calibrate wheelbase, pedals and gamepads, steering range, deadzone, "
                       "vibration and button mapping.",
    "Wheelbase, Pedale und Gamepads · gespeichert in data/controls.json":
        "Wheelbase, pedals and gamepads · saved in data/controls.json",
    "Gerät": "Device", "Controller-Eingabe": "Controller input", "Gerätetyp": "Device type",
    "Lenkung kalibrieren": "Calibrate steering", "Gaspedal kalibrieren": "Calibrate throttle",
    "Bremspedal kalibrieren": "Calibrate brake", "Lenkbereich": "Steering range", "Lenk-Totzone": "Steering deadzone",
    "Lenk-Linearität": "Steering linearity", "Pedal-Totzone": "Pedal deadzone",
    "Vibration / Force-Feedback": "Vibration / force feedback", "Standard wiederherstellen": "Restore defaults",
    "Lenkrad + Pedale": "Wheel + pedals", "Gamepad": "Gamepad", "Lenkung": "Steering", "Gaspedal": "Throttle",
    "Bremspedal": "Brake", "nicht belegt": "unassigned", "LIVE-EINGABE": "LIVE INPUT", "Rohachsen": "Raw axes",
    "KALIBRIERUNG": "CALIBRATION", "TASTE BELEGEN": "ASSIGN BUTTON", "TASTENBELEGUNG": "BUTTON MAPPING",
    "... warte auf Eingabe ...": "... waiting for input ...",
    "Gerade-Modus / DRS": "Straight mode / DRS", "Boxenstopp anfordern": "Pit stop menu",
    "Kamera wechseln": "Change camera", "2D / 3D": "2D / 3D", "Auto zurücksetzen": "Reset car",
    "Streckenübersicht": "Track overview", "Menü / Verlassen (ESC)": "Menu / leave (ESC)",
    "Weiter / Training beenden": "Continue / end practice",
    "Pfeile wählen · links/rechts ändern · ENTER kalibrieren/belegen · ESC zurück":
        "Arrows select · left/right change · ENTER calibrate/assign · ESC back",
    "Kein Lenkrad oder Controller gefunden. Gerät anschließen - es wird automatisch erkannt.":
        "No wheel or controller found. Plug one in - it is detected automatically.",
    "Angeschlossene Lenkräder und Controller. Links/rechts wechselt das aktive Gerät. Geräte können auch während des "
    "Spiels angesteckt werden.": "Connected wheels and controllers. Left/right switches the active device. Devices "
                                 "can be plugged in while the game is running.",
    "Aus = nur Tastatur. Tastatur funktioniert immer zusätzlich.":
        "Off = keyboard only. The keyboard always works as well.",
    "Lenkrad: Lenkachse wird direkt ohne Glättung übernommen. Gamepad: Stick wird bei hohem Tempo leicht entschärft.":
        "Wheel: the steering axis is used directly without smoothing. Gamepad: the stick is softened slightly at "
        "high speed.",
    "ENTER, dann Lenkrad bzw. Stick ganz nach rechts drehen und kurz halten. Die Mittelstellung wird beim Start der "
    "Kalibrierung gemessen - Lenkrad gerade halten!":
        "ENTER, then turn the wheel / push the stick fully right and hold briefly. The centre is measured when "
        "calibration starts - keep the wheel straight!",
    "ENTER mit losgelassenem Pedal, dann voll durchtreten und kurz halten. Invertierte und kombinierte Pedalachsen "
    "werden automatisch erkannt.":
        "ENTER with the pedal released, then press it fully and hold briefly. Inverted and combined pedal axes are "
        "detected automatically.",
    "ENTER mit losgelassenem Pedal, dann voll durchtreten und kurz halten.":
        "ENTER with the pedal released, then press it fully and hold briefly.",
    "Anteil des Lenkwegs, der schon vollen Einschlag ergibt. Lenkrad mit 900°: 50% = voller Einschlag bei 225° pro "
    "Seite. Kleiner = direktere Lenkung.":
        "Share of the steering travel that already gives full lock. 900° wheel: 50% = full lock at 225° per side. "
        "Smaller = more direct steering.",
    "Ignorierter Bereich um die Mitte. Gamepad-Sticks ~6%, Lenkräder 0%.":
        "Ignored zone around the centre. Gamepad sticks ~6%, wheels 0%.",
    "1.0 = linear. Höher = feinfühliger um die Mitte, schneller am Anschlag.":
        "1.0 = linear. Higher = finer around the centre, quicker towards full lock.",
    "Ignorierter Weg am Anfang und Ende der Pedale (gegen Rauschen).":
        "Ignored travel at the start and end of the pedals (against noise).",
    "Stöße bei Einschlägen, Kies, Rutschen und durchdrehenden Rädern. Gamepads vibrieren; Lenkräder bekommen "
    "Rüttel-Impulse, soweit der Treiber SDL-Rumble unterstützt.":
        "Jolts for impacts, gravel, slides and wheelspin. Gamepads vibrate; wheels get rumble pulses where the "
        "driver supports SDL rumble.",
    "Setzt Achsen, Tasten und Lenkgefühl dieses Geräts zurück.":
        "Resets axes, buttons and steering feel of this device.",
    "Wird automatisch in data/controls.json gespeichert (pro Gerät).":
        "Saved automatically in data/controls.json (per device).",
    "ENTER, dann den gewünschten Knopf drücken. Jede Aktion geht weiterhin auch über die Tastatur.":
        "ENTER, then press the button you want. Every action still works on the keyboard too.",
    "Lenkrad ganz nach RECHTS drehen (Stick nach rechts) und halten ...":
        "Turn the wheel fully RIGHT (stick right) and hold ...",
    "Gaspedal VOLL durchtreten (Gas-Trigger ganz drücken) und halten ...":
        "Press the throttle FULLY (throttle trigger all the way) and hold ...",
    "Bremspedal VOLL durchtreten (Brems-Trigger ganz drücken) und halten ...":
        "Press the brake FULLY (brake trigger all the way) and hold ...",
    # ---------------------------------------------------------------- setup: wings, ride height, fuel, plank
    "Frontflügel-Winkel": "Front wing angle", "Heckflügel-Winkel": "Rear wing angle", "Bodenfreiheit": "Ride height",
    "flach": "flat", "steil": "steep", "tief": "low", "Planken-Abrieb": "Plank wear",
    "SPRIT BEIM RENNSTART": "FUEL AT RACE START", "genau Renndistanz": "exactly race distance",
    "Mehr Frontflügel = mehr Grip an der Vorderachse: das Auto lenkt schärfer ein, das Heck wird nervöser. Kostet "
    "wenig Topspeed. Kann beim Boxenstopp verstellt werden.":
        "More front wing = more front grip: sharper turn-in, a nervous rear. Costs little top speed. Can be adjusted "
        "at a pit stop.",
    "Mehr Heckflügel = mehr Grip und ein stabiles Heck, aber deutlich mehr Luftwiderstand. Monza/Spa: flach. Monaco: "
    "steil. Front steiler als Heck = Übersteuern, umgekehrt Untersteuern.":
        "More rear wing = more grip and a stable rear, but much more drag. Monza/Spa: flat. Monaco: steep. Front "
        "steeper than rear = oversteer, the other way round = understeer.",
    "Tiefer = mehr Abtrieb (Bodeneffekt) und etwas weniger Luftwiderstand, aber die Bodenplatte (Planke) schleift "
    "stärker. Mehr als 1,0 mm Abrieb nach dem Rennen = Disqualifikation! Die Planke wird beim Boxenstopp NICHT "
    "getauscht.":
        "Lower = more downforce (ground effect) and a little less drag, but the plank under the car scrapes more. "
        "More than 1.0 mm of wear after the race = disqualification! The plank is NOT replaced at pit stops.",
    "Hart = etwas mehr Grip auf glattem Asphalt, aber mehr Reifenverschleiß und schlechter neben der Strecke. Weich = "
    "reifenschonend, setzt aber öfter auf (Planke).":
        "Stiff = a bit more grip on smooth tarmac, but more tyre wear and worse off track. Soft = easy on the tyres, "
        "but bottoms out more (plank).",
    "Mehr Sprit = Reserve für Safety-Car-Phasen, aber jedes kg kostet Beschleunigung, Grip und Bremsweg. Weniger als "
    "die Renndistanz = leichter und schneller, dann muss aber getankt werden (Boxenstopp-Menü mit B) oder Sprit "
    "gespart werden (früher vom Gas).":
        "More fuel = reserve for safety car periods, but every kg costs acceleration, grip and braking distance. "
        "Less than race distance = lighter and faster, but you have to refuel (pit menu with B) or save fuel (lift "
        "earlier).",
    # ---------------------------------------------------------------- pit menu, fuel, scrutineering
    "BOXENSTOPP PLANEN": "PLAN PIT STOP", "angefordert": "requested", "Tanken": "Refuel", "Reparatur": "Repair",
    "nicht wechseln": "no change", "BOX ANFORDERN": "REQUEST PIT STOP", "BOXENSTOPP ABSAGEN": "CANCEL PIT STOP",
    "Boxenstopp abgesagt": "Pit stop cancelled",
    "Nichts zu tun - Boxenstopp nicht angefordert": "Nothing to do - no pit stop requested",
    "ohne Reifenwechsel": "no tyre change", "Reifen bleiben drauf": "Tyres stay on",
    "Box, Box! Die Crew ist bereit.": "Box, box! The crew is ready.", "-> Box": "-> Box",
    "Kein Sprit mehr! Auto ausrollen lassen.": "Out of fuel! Let the car roll to a stop.",
    "Sprit reicht nicht! Lift and Coast oder zum Tanken an die Box.":
        "Not enough fuel! Lift and coast or box to refuel.",
    "Planke fast am Limit! Randsteine meiden, sonst Disqualifikation.":
        "Plank almost at the limit! Stay off the kerbs or face disqualification.",
    "Kein Benzin mehr": "Out of fuel",
    # ---------------------------------------------------------------- practice data analysis
    "DATENANALYSE · FREIES TRAINING": "DATA ANALYSIS · FREE PRACTICE", "zur Datenanalyse": "to data analysis",
    "RD.": "LAP", "ZEIT": "TIME", "VERSCHL.": "WEAR", "SPRIT": "FUEL", "PLANKE": "PLANK", "VMAX": "VMAX",
    "RUNDENZEIT & REIFENVERSCHLEISS": "LAP TIME & TYRE WEAR", "RENNINGENIEUR · AUSWERTUNG": "RACE ENGINEER · DEBRIEF",
    "Keine gezeitete Runde gefahren.": "No timed lap driven.",
    "Mindestens 2 Runden für den Verlauf.": "At least 2 laps needed for the chart.",
    "Balken = Rundenzeit (höher = schneller) · gelb = Reifenverschleiß · braun = Boxenrunde":
        "Bars = lap time (taller = faster) · yellow = tyre wear · brown = pit lap",
    "Zu wenig Daten": "Not enough data", "Fahre mindestens 2 volle Runden ohne Boxenstopp.":
        "Drive at least 2 full laps without a pit stop.",
    "Pace": "Pace", "Sprit": "Fuel", "Planke": "Plank", "kein Stopp nötig": "no stop needed",
    "DISQUALIFIKATION droht - Bodenfreiheit erhöhen!": "DISQUALIFICATION risk - raise the ride height!",
    "knapp - Randsteine meiden oder höher fahren": "tight - stay off the kerbs or run higher",
    "sicher - Bodenfreiheit könnte tiefer": "safe - ride height could go lower",
    "im grünen Bereich": "within limits",
    # ---------------------------------------------------------------- weather
    "Wetter": "Weather", "Trocken": "Dry", "Wechselhaft": "Changeable", "Regen": "Rain", "Starkregen": "Heavy rain",
    "Nieselregen": "Drizzle", "Nass, trocknet ab": "Wet, drying", "Feucht": "Damp",
    "Intermediate": "Intermediate", "Wet": "Wet",
    "Trocken: nie Regen. Wechselhaft: Schauer können kommen und gehen - Strecke wird nass und trocknet wieder ab. "
    "Regen: nasses Rennen. Bei Nässe Intermediates (grün) oder Wets (blau) holen.":
        "Dry: never rains. Changeable: showers can come and go - the track gets wet and dries again. Rain: a wet "
        "race. In the wet, fit intermediates (green) or full wets (blue).",
    "Strecke ist nass - Box für Intermediates! (B)": "Track is wet - box for intermediates! (B)",
    "Starkregen - wir brauchen Full Wets! (B)": "Heavy rain - we need full wets! (B)",
    "Strecke trocknet ab - Slicks sind jetzt schneller! (B)": "Track is drying - slicks are faster now! (B)",
    # ---------------------------------------------------------------- damage
    "Flügel": "Wing", "Aufh. L": "Susp. L", "Aufh. R": "Susp. R", "Boden": "Floor", "Kühler": "Radiator",
    "Motor überhitzt": "Engine overheated",
    "Kühler beschädigt - Motor wird heiß, Leistung reduziert. Box!":
        "Radiator damaged - engine running hot, power turned down. Box!",
    "Aufhängung links beschädigt - das Auto zieht! Box empfohlen.":
        "Left suspension damaged - the car is pulling! Box recommended.",
    "Aufhängung rechts beschädigt - das Auto zieht! Box empfohlen.":
        "Right suspension damaged - the car is pulling! Box recommended.",
    "Frontflügel beschädigt! Box für Reparatur empfohlen.": "Front wing damaged! Box for repairs recommended.",
    "Unterboden beschädigt - weniger Abtrieb. Lässt sich in der Box nicht tauschen.":
        "Floor damaged - less downforce. It can't be replaced in the pits.",
    # ---------------------------------------------------------------- keyboard bindings, pedals, gearbox
    "Gas": "Throttle", "Bremse": "Brake", "Links lenken": "Steer left", "Rechts lenken": "Steer right",
    "Hochschalten": "Shift up", "Runterschalten": "Shift down", "Tastatur zurücksetzen": "Reset keyboard",
    "Pedal-Achsen": "Pedal axes", "KOMBINIERT - siehe Hilfe!": "COMBINED - see help!",
    "getrennt (Gas + Bremse gleichzeitig möglich)": "separate (throttle + brake together possible)",
    "Gas und Bremse brauchen ZWEI getrennte Achsen, sonst kann man nicht gleichzeitig bremsen und Gas geben. Zeigt "
    "dies 'kombiniert': im Lenkrad-Treiber (Logitech G HUB: 'Kombinierte Pedale' aus, Thrustmaster/Fanatec: "
    "'separate axes') umstellen und Gas + Bremse neu kalibrieren. Eine separate Pedalbox (eigenes USB-Gerät) wird "
    "beim Kalibrieren erkannt.":
        "Throttle and brake need TWO separate axes, otherwise you can't brake and accelerate at the same time. If "
        "this says 'combined': switch it in the wheel driver (Logitech G HUB: turn off 'combined pedals', "
        "Thrustmaster/Fanatec: 'separate axes') and calibrate throttle + brake again. A separate pedal box (its own "
        "USB device) is detected during calibration.",
    "Alle Tastatur-Belegungen auf Standard (Pfeile/WASD, Leertaste, B, R ...).":
        "All keyboard bindings back to default (arrows/WASD, space, B, R ...).",
    "Gewünschte Taste auf der Tastatur drücken. ESC bricht ab. Die Taste wird dabei von jeder anderen Aktion "
    "entfernt.": "Press the key you want. ESC cancels. The key is removed from any other action.",
    "ENTER, dann die neue Taste drücken. Im Splitscreen fährt Spieler 1 mit diesen Tasten (ohne Pfeile), Spieler 2 "
    "mit den Pfeiltasten.": "ENTER, then press the new key. In split screen player 1 drives with these keys "
                            "(without arrows), player 2 with the arrow keys.",
    "Links/rechts: Achse von Hand wählen (alle Geräte, auch separate Pedalboxen).":
        "Left/right: pick the axis by hand (all devices, separate pedal boxes too).",
    "Getriebe": "Gearbox", "Automatik": "Automatic", "Sequenziell (selbst schalten)": "Sequential (shift yourself)",
    "Automatik: das Auto schaltet selbst. Sequenziell: du schaltest - Tastatur E/Q (änderbar), Gamepad RB/LB, "
    "Lenkrad Schaltwippen. Jeder Gang hat einen Drehzahlbegrenzer, im zu hohen Gang fehlt die Beschleunigung. Zu "
    "frühes Runterschalten wird verweigert (Motorschutz).":
        "Automatic: the car shifts itself. Sequential: you shift - keyboard E/Q (rebindable), gamepad RB/LB, wheel "
        "paddles. Every gear has a rev limiter, in too high a gear the car won't pull. Downshifting too early is "
        "refused (engine protection).",
    "SEQ": "SEQ", "GERADE": "STRAIGHT", "PIT LIMITER": "PIT LIMITER",
    # ---------------------------------------------------------------- split screen
    "Spieler": "Players", "1 Spieler": "1 player", "2 Spieler (Splitscreen)": "2 players (split screen)",
    "P1: WASD · LEER Gerade · B Box · R Reset      P2: Pfeile · STRG-R Gerade · SHIFT-R Box · ENTF Reset":
        "P1: WASD · SPACE straight · B box · R reset      P2: arrows · R-CTRL straight · R-SHIFT box · DEL reset",
}

TEMPLATES: list[tuple[str, str]] = [
    # ---------------------------------------------------------------- menus / weekend
    ("Fahrer: {}  ·  Fahrhilfen: {}  ·  Ansicht: {}  ·  Aufnahmen: {#} Samples",
     "Driver: {}  ·  Assists: {}  ·  View: {}  ·  Recordings: {} samples"),
    ("{}: Flügel {} · Getriebe {}  (ENTER)", "{}: wing {} · gearing {}  (ENTER)"),
    ("{#} Runden", "{} laps"), ("{#} Runde", "{} lap"), ("{}  ({#}% Motorleistung)", "{}  ({}% engine power)"),
    ("{#} KI-Fahrer", "{} AI drivers"), ("{}  (Grip {#}%)", "{}  (grip {}%)"),
    ("Einstellungen: Fahrhilfen {} · {} · Schaden {} · Reifenverschleiß {}",
     "Settings: assists {} · {} · damage {} · tyre wear {}"),
    ("Länge: {} km", "Length: {} km"), ("Breite: {}  ·  Auslauf: {}", "Width: {}  ·  Run-off: {}"),
    ("Rekord {} · {}", "Record {} · {}"), ("Deine Bestzeit {}", "Your best {}"),
    ("Auto-Ranking: P{#} von {#}", "Car ranking: P{} of {}"),
    ("STARTERFELD · {#} AUTOS  (data/driver_pool.json)", "GRID · {} CARS  (data/driver_pool.json)"),
    ("Rennen  ·  {}", "Race  ·  {}"),
    ("BLAUE FLAGGE · {}", "BLUE FLAG · {}"), ("blaue Flaggen ignoriert ({})", "ignored blue flags ({})"),
    ("Screenshot gespeichert: {}", "Screenshot saved: {}"), ("{}  ·  {}  ·  F12: Screenshot", "{}  ·  {}  ·  F12: screenshot"), ("Freies Training  ·  {}", "Free practice  ·  {}"),
    ("Ruf {}", "Reputation {}"), ("Vertrauen {}", "Trust {}"), ("Teamruf {}", "Team reputation {}"),
    ("{} · {} · {} · Runde {#}/{#}", "{} · {} · {} · Round {}/{}"), ("{} · {} ·  · Runde {#}/{#}", "{} · {} · Round {}/{}"),
    ("{} WIRD SIMULIERT", "SIMULATING {}"), ("{}-LAUF {#}/{#}  ·  {}", "{} ROUND {}/{}  ·  {}"),
    ("{} wird vorbereitet ...", "Preparing {} ..."), ("{} · nach Bestzeit", "{} · by best time"),
    ("Qualifying {} · Bestzeit aus 3 Runden", "Qualifying {} · best of 3 laps"),
    ("ENTER: {}    ·    ESC: Hauptmenü", "ENTER: {}    ·    ESC: main menu"), ("ENTER: {}", "ENTER: {}"),
    ("PODIUM · GRAND PRIX VON {}", "PODIUM · {} GRAND PRIX"), ("Sieg für {} ({})", "Win for {} ({})"),
    ("Du bist auf Platz {#} ins Ziel gekommen.", "You finished in P{}."),
    ("{}  (+{#} Plätze, von P{#})", "{}  (+{} places, from P{})"),
    ("Neue Saison · {#} Rennen · Punkte 25-18-15-12-10-8-6-4-2-1 +1 schnellste Runde",
     "New season · {} races · points 25-18-15-12-10-8-6-4-2-1 +1 fastest lap"),
    ("Runde {#}/{#} · {} · {#} Rd. · KI {} · Zuschauer", "Round {}/{} · {} · {} laps · AI {} · spectator"),
    ("Runde {#}/{#} · {} · {#} Rd. · KI {}", "Round {}/{} · {} · {} laps · AI {}"),
    ("Fahrer: {}", "Driver: {}"), ("Sieg: {}", "Win: {}"), ("WEITER: RUNDE {#} · {}", "CONTINUE: ROUND {} · {}"),
    ("WELTMEISTER: {}", "WORLD CHAMPION: {}"), ("{} bis Rennende", "{} to the finish"),
    ("Grand Prix von {} · Positionsverlauf über {#} Runden", "{} Grand Prix · positions over {} laps"),
    ("Voraus {}", "Ahead {}"), ("TEAMZIEL: {}", "TEAM GOAL: {}"), ("Kamera: {} (3D mit V)", "Camera: {} (3D with V)"),
    ("Kamera: {}", "Camera: {}"), ("Zeitraffer x{#}", "Time warp x{}"),
    ("BOX: {}-Reifen in dieser Runde", "BOX: {} tyres this lap"), ("{} ist schon in der Boxengasse", "{} is already in the pit lane"),
    ("Box für {}: {}", "Box for {}: {}"), ("{}: Stopp absagen", "{}: cancel stop"),
    ("ANWEISUNG  {}  (B = ändern)", "ORDER  {}  (B = change)"), ("Teamchef: Box, Box - {}!", "Team principal: box, box - {}!"),
    ("{}: bleibt draußen (Teamorder)", "{}: stays out (team order)"),
    ("Verstanden, Box diese Runde - {}.", "Understood, boxing this lap - {}."),
    ("{} folgt der Anweisung: Box -> {}", "{} follows the order: box -> {}"), ("Negativ! {}", "Negative! {}"),
    ("{} lehnt den Boxenstopp ab", "{} refuses the pit stop"), ("{}: Schaden - Box für Reparatur", "{}: damage - pitting for repairs"),
    ("AUSFALL: {} ({})", "RETIREMENT: {} ({})"), ("AUSFALL - {}", "RETIREMENT - {}"),
    ("{} Boxenstopp -> {}", "{} pit stop -> {}"), ("{} sitzt {#}s Strafe in der Box ab", "{} serves a {}s penalty in the pits"),
    ("Reifenwechsel: {}  +  Reparatur ({#}s)", "Tyre change: {}  +  repair ({}s)"), ("Reifenwechsel: {}", "Tyre change: {}"),
    ("Reifenwechsel ... {}s", "Tyre change ... {}s"),
    ("STRECKENREKORD: {} {}", "TRACK RECORD: {} {}"), ("NEUER STRECKENREKORD  {}", "NEW TRACK RECORD  {}"),
    ("Persönlicher Streckenrekord  {}", "Personal track record  {}"), ("Schnellste Runde: {} {}", "Fastest lap: {} {}"),
    ("SCHNELLSTE RUNDE  {}", "FASTEST LAP  {}"), ("Persönliche Bestzeit  {}", "Personal best  {}"), ("Runde  {}", "Lap  {}"),
    ("QUALIFYING - {#} gezeitete Runden", "QUALIFYING - {} timed laps"),
    ("Startplatz P{#} - warte auf die Ampel!", "Grid slot P{} - wait for the lights!"),
    ("Reaktionszeit {} s", "Reaction time {} s"), ("BLAUE FLAGGE - lass {} überrunden", "BLUE FLAG - let {} lap you"),
    ("Zielflagge! Erster im Ziel: {}", "Chequered flag! First across the line: {}"), ("ZIEL! Du bist P{#}", "FINISH! You are P{}"),
    ("{} überholt {}  ->  P{#}", "{} passes {}  ->  P{}"), ("RIVALE {} ÜBERHOLT!", "RIVAL {} OVERTAKEN!"),
    ("Rivale {} ist vorbei!", "Rival {} got past!"), ("+{#} Rd.", "+{} laps"),
    ("ZUSCHAUER  ·  {}", "SPECTATOR  ·  {}"), ("VIRTUAL SAFETY CAR  {}s", "VIRTUAL SAFETY CAR  {}s"),
    ("{}s Strafe offen - beim Stopp abgesessen.", "{}s penalty pending - served at the stop."),
    ("Box, Box! {}-Reifen sind bereit.", "Box, box! {} tyres are ready."),
    ("Stopp nötig: Reifen halten noch ~{#} Rd.", "Stop needed: tyres last ~{} more laps"),
    ("Du holst {}s pro Runde auf - dran bleiben!", "You're gaining {}s per lap - keep pushing!"),
    ("Wir verlieren {}s pro Runde nach vorne.", "We're losing {}s per lap to the car ahead."),
    ("Anweisung: {} ...", "Order: {} ..."), ("{} · KI {}/{}", "{} · AI {}/{}"), ("{} · {#} Rd.", "{} · {} laps"),
    ("Hält noch ~{#} Runde · reicht bis ins Ziel", "Lasts ~{} more lap · enough to the finish"),
    ("Hält noch ~{#} Runden · reicht bis ins Ziel", "Lasts ~{} more laps · enough to the finish"),
    ("Hält noch ~{#} Runde · Ziel in {}", "Lasts ~{} more lap · finish in {}"),
    ("Hält noch ~{#} Runden · Ziel in {}", "Lasts ~{} more laps · finish in {}"),
    ("Hält noch ~{#} Runden", "Lasts ~{} more laps"), ("Hält noch ~{#} Runde", "Lasts ~{} more lap"),
    ("Vordermann: {}s  ({}/Rd.)", "Car ahead: {}s  ({}/lap)"), ("Vordermann: {}s", "Car ahead: {}s"),
    ("Stopps {}", "Stops {}"), ("Letzte {}", "Last {}"), ("RENNINGENIEUR · #{#}", "RACE ENGINEER · #{}"),
    ("B Box-Anweisung · TAB eigener Fahrer · {}", "B pit order · TAB own driver · {}"),
    ("LEER Gerade-Modus · {}", "SPACE straight mode · {}"), ("{} · G Garage · ENTER Session beenden", "{} · G garage · ENTER end session"),
    (">> SIMULATION x{}", ">> SIMULATION x{}"), ("KAMERA: {}  (Gehirn: {}/{})", "CAMERA: {}  (brain: {}/{})"),
    ("NEURONALES NETZ · {} · {}/{}", "NEURAL NETWORK · {} · {}/{}"),
    # race control / stewards
    ("{} steht auf der Strecke", "{} is stopped on track"), ("schwerer Unfall von {}", "heavy crash for {}"),
    ("Trümmer nach Unfall von {}", "debris after {}'s crash"), ("SAFETY CAR - {}", "SAFETY CAR - {}"),
    ("VIRTUAL SAFETY CAR - {}", "VIRTUAL SAFETY CAR - {}"), ("{} Runde {}", "{} lap {}"),
    ("{} hat die Position an {} zurückgegeben", "{} gave the position back to {}"),
    ("unter {} {} überholt", "overtook {2} under {1}"),
    ("Überholen unter {}: {} muss Platz an {} zurückgeben", "Overtaking under {}: {} must give the place back to {}"),
    ("Unter {} überholt! Lass {} vorbei ({}s)", "Overtook under {}! Let {} through ({}s)"),
    ("{} hat dich unter {} überholt - er muss zurückgeben", "{} passed you under {} - he must give it back"),
    ("REIFENSCHADEN: {} ({})", "PUNCTURE: {} ({})"), ("Kollision mit {} verursacht", "caused a collision with {}"),
    ("Track Limits - Verwarnung {#}/{#}", "Track limits - warning {}/{}"),
    ("Schwarz-weiße Flagge: {} (Track Limits)", "Black and white flag: {} (track limits)"),
    ("Untersuchung: Kollision {} / {}", "Investigation: collision {} / {}"),
    ("{}s Zeitstrafe: {} - {}", "{}s time penalty: {} - {}"), ("{} SEKUNDEN STRAFE - {}", "{} SECOND PENALTY - {}"),
    # garage
    ("{} · {} · gespeichert pro Strecke (data/setups.json)", "{} · {} · saved per track (data/setups.json)"),
    ("{} km/h", "{} km/h"),
    # training
    ("Genom {}", "Genome {}"), ("Neue Population: {#} zufällige Netze {}", "New population: {} random networks {}"),
    ("Behavior Cloning auf {} Samples ...", "Behaviour cloning on {} samples ..."), ("Fehler (MSE): {} -> {}", "Error (MSE): {} -> {}"),
    ("Gen. {}/{} · beste Fitness {} · Schnitt {}", "Gen. {}/{} · best fitness {} · average {}"),
    ("Checkpoint '{}' (Gen. {}) Rundenzeiten: {}", "Checkpoint '{}' (gen. {}) lap times: {}"),
    ("Gespeichert: {}", "Saved: {}"), ("{#} Netze", "{} networks"),
    ("- {} x Mauer-Aufprallimpuls,  - 150 x Sek. neben der Strecke", "- {} x wall impact impulse,  - 150 x sec. off track"),
    ("- {} x Auto-Kontaktimpuls", "- {} x car contact impulse"), ("+ {} x gewonnene Positionen", "+ {} x positions gained"),
    ("{} {} x Sek. dicht hinter Gegner", "{} {} x sec. close behind opponent"),
    ("Trainingsdaten: {#} Aufnahmen, {#} Samples", "Training data: {} recordings, {} samples"),
    ("Ergebnis: data/brains/{}.json (Backup der alten Datei)", "Result: data/brains/{}.json (backup of the old file)"),
    ("{} · {} · {}/{} aktiv · t={}s", "{} · {} · {}/{} active · t={}s"), ("Generation {#}/{#}", "Generation {}/{}"),
    ("Lauf {#}/{#} · Population {#} · {#} Gewichte", "Run {}/{} · population {} · {} weights"),
    ("Echtzeit {} min · simuliert {} min (x{#})", "Real time {} min · simulated {} min (x{})"),
    # ---------------------------------------------------------------- career
    ("{} Racing", "{} Racing"), ("Willkommen, Teamchef! {} startet mit {#} Mio Budget.",
                                 "Welcome, team principal! {} starts with a {} M budget."),
    ("Saisonziel: Fahrer-WM Platz {#} oder besser", "Season goal: P{} or better in the drivers' championship"),
    ("Saisonziel: Konstrukteurs-WM Platz {#} oder besser", "Season goal: P{} or better in the constructors' championship"),
    ("Presse: \"{}\"", "Press: \"{}\""), ("Updates: {}", "Updates: {}"), ("{}: Sieg für {}.", "{}: win for {}."),
    ("Du wurdest {} (+{#} Punkte).", "You finished {} (+{} points)."), ("Du wurdest {}.", "You finished {}."),
    ("Technischer Defekt: {} ({}).", "Technical failure: {} ({})."), ("Rivale {} geschlagen!", "Rival {} beaten!"),
    ("Rivale {} war diesmal vorne.", "Rival {} was ahead this time."),
    ("Wochenendziel erreicht ({}): +0.3 Mio Bonus, Team vertraut dir mehr.",
     "Weekend goal met ({}): +0.3 M bonus, the team trusts you more."),
    ("Wochenendziel verfehlt ({}).", "Weekend goal missed ({})."),
    ("Simulator-Arbeit zahlt sich aus: {} jetzt Wertung {#}.", "Simulator work pays off: {} now rated {}."),
    ("Finanzen: +{} Mio ({}/Preisgeld), -{} Mio (Gehälter/Betrieb). Budget {} Mio.",
     "Finances: +{} M ({}/prize money), -{} M (salaries/operations). Budget {} M."),
    ("Rivalenteam {} geschlagen!", "Rival team {} beaten!"), ("Maximal {#} Projekte gleichzeitig", "At most {} projects at once"),
    ("Zu wenig Budget ({} Mio nötig)", "Not enough budget ({} M needed)"),
    ("Budgetobergrenze erreicht (noch {} Mio diese Saison)", "Cost cap reached ({} M left this season)"),
    ("Projekt gestartet: {} Stufe {#} (fertig in {#} Rd.)", "Project started: {} level {} (ready in {} races)"),
    ("{}: Projekt läuft ({#} Rennen)", "{}: project running ({} races)"),
    ("Neues Teil: {} Stufe {#} - enttäuschend, nur halbe Wirkung.", "New part: {} level {} - disappointing, only half the effect."),
    ("Neues Teil: {} Stufe {#}", "New part: {} level {}"), ("Ausbau: {} Stufe {#} (-{} Mio)", "Upgrade: {} level {} (-{} M)"),
    ("{} Stufe {#}", "{} level {}"), ("Titelsponsor {#}. Saison: {} ({})", "Title sponsor season {}: {} ({})"),
    ("Vertrag mit {}", "Contract with {}"), ("Boxencrew trainiert: Stopp jetzt {} s (-{} Mio)", "Pit crew trained: stop now {} s (-{} M)"),
    ("Boxencrew Stufe {#}", "Pit crew level {}"), ("{} fährt bereits für {}", "{} already drives for {}"),
    ("{} will nicht: dein Team braucht Ruf {#} (hat {#})", "{} isn't interested: your team needs reputation {} (has {})"),
    ("Zu wenig Budget für die Ablöse ({} Mio)", "Not enough budget for the transfer fee ({} M)"),
    ("Neu im Team: {} ({#} J., {} Mio/Saison, Ablöse {} Mio)", "New in the team: {} ({} yrs, {} M/season, fee {} M)"),
    ("{} verpflichtet!", "{} signed!"), ("Abfindung zu teuer ({} Mio)", "Severance too expensive ({} M)"),
    ("{} entlassen (Abfindung {} Mio)", "{} released (severance {} M)"),
    ("{} lehnt ab und zieht das Angebot zurück!", "{} declines and withdraws the offer!"),
    ("Unterschrieben: {} Mio/Saison, {#} Saison(s)", "Signed: {} M/season, {} season(s)"),
    ("{} wechselt im Tausch zu {}.", "{} moves to {} in the swap."), ("Wechsel: {} -> {}", "Transfer: {} -> {}"),
    ("Vertrag bei {}: {#} J., {} Mio/Saison, Ziel P{#}", "Contract with {}: {} yrs, {} M/season, goal P{}"),
    ("{} löst deinen Vertrag auf - zu wenig Vertrauen.", "{} terminates your contract - not enough trust."),
    ("{} verlängert ({#} J., {} Mio/Saison)", "{} extended ({} yrs, {} M/season)"),
    ("Vertrag ausgelaufen: {} verlässt das Team.", "Contract expired: {} leaves the team."),
    ("Wintertests: {} gilt als Favorit für Saison {#}.", "Winter testing: {} are the favourites for season {}."),
    ("Saison {#} beginnt!", "Season {} begins!"), ("Karriereende: {} tritt zurück.", "Retirement: {} retires."),
    ("Karriereende: {} treten zurück.", "Retirements: {} retire."),
    ("{} bereits auf Maximalstufe", "{} already at max level"), ("Zu wenig Geld auf dem Konto ({} Mio nötig)",
                                                                 "Not enough money in your account ({} M needed)"),
    ("Investition: {} Stufe {#} (-{} Mio)", "Investment: {} level {} (-{} M)"),
    ("ERFOLG FREIGESCHALTET: {} - {}", "ACHIEVEMENT UNLOCKED: {} - {}"), ("ERFOLG FREIGESCHALTET: {}", "ACHIEVEMENT UNLOCKED: {}"),
    ("{} tritt ab sofort als {} an.", "{} now races as {}."), ("Name geändert: {}", "Name changed: {}"),
    ("Rebranding kostet {#} Mio - zu wenig Budget", "Rebranding costs {} M - not enough budget"),
    ("Rebranding: {} heißt jetzt {} (-{#} Mio)", "Rebranding: {} is now called {} (-{} M)"),
    ("Team heißt jetzt {}", "Team is now called {}"), ("Rennen: Top {#}", "Race: top {}"), ("Qualifying: Top {#}", "Qualifying: top {}"),
    ("{} hat dich heute geschlagen. Deine Antwort?", "{} beat you today. Your answer?"),
    ("Du hast {} geschlagen. Eine Botschaft an ihn?", "You beat {}. A message for him?"),
    ("Was sagen Sie zum Duell mit {}?", "What do you make of the battle with {}?"),
    # career screens
    ("NEUE FAHRER-KARRIERE · SLOT {#}", "NEW DRIVER CAREER · SLOT {}"), ("NEUE TEAM-KARRIERE · SLOT {#}", "NEW TEAM CAREER · SLOT {}"),
    ("{} (Timing-Tower)", "{} (timing tower)"), ("Teamchef {} · {}", "Team principal {} · {}"), ("Teamchef {}", "Team principal {}"),
    ("Du gründest ein neues Team mit {#} Mio Budget und einem langsamen Auto. Sponsoren und Preisgeld bringen Geld, "
     "Gehälter und Betrieb kosten Geld. Entwickle das Auto, baue die Fabrik aus und verpflichte Fahrer - jede Saison "
     "drängen neue Talente in den Fahrermarkt.",
     "You found a new team with a {} M budget and a slow car. Sponsors and prize money bring money in, salaries and "
     "operations cost money. Develop the car, expand the factory and sign drivers - every season new talents join "
     "the driver market."),
    ("Gespeichert in data/careers/{}.json · später änderbar im DESIGN-Studio",
     "Saved in data/careers/{}.json · change it later in the DESIGN studio"),
    ("Saison {#} · Ruf {#}/100 · Verhandle Gehalt und Laufzeit", "Season {} · reputation {}/100 · negotiate salary and length"),
    ("Auto-Ranking P{#} von {#}", "Car ranking P{} of {}"), ("{#} Saisons", "{} seasons"), ("{#} Saison", "{} season"),
    ("Ziel: Fahrer-WM P{#}", "Goal: drivers' championship P{}"), ("Forderung: {#} %", "Demand: {} %"),
    ("Dein Ruf: {#}/100", "Your reputation: {}/100"), ("Vertrauen bei {}: {#}/100", "Trust at {}: {}/100"),
    ("FAHREN: {}", "DRIVE: {}"), ("ANSEHEN: {}", "WATCH: {}"), ("Runde {#}/{#}", "Round {}/{}"),
    ("{} · Teamchef {} (fährt selbst) · {}", "{} · team principal {} (drives) · {}"),
    ("{} · Teamchef {} · {}", "{} · team principal {} · {}"), ("KARRIERE · SAISON {#}", "CAREER · SEASON {}"),
    ("Auto P{#}/{#}", "Car P{}/{}"), ("Vertrag: {} Mio/Saison · noch {#} Saison(s)", "Contract: {} M/season · {} season(s) left"),
    ("Saisonziel: WM P{#}", "Season goal: P{}"), ("aktuell P{#}", "currently P{}"), ("Status: {}", "Status: {}"),
    ("Konto {} Mio", "Account {} M"), ("{#}/{#} erfüllt", "{}/{} met"),
    ("Karriere: {#} Rennen · {#} Siege · {#} Podien · {#} Titel", "Career: {} races · {} wins · {} podiums · {} titles"),
    ("Duelle {#}:{#}", "Duels {}:{}"), ("Punkte {#}:{#}", "Points {}:{}"), ("TEAMKOLLEGE: {}", "TEAM-MATE: {}"),
    ("DEIN AUTO · Zuverlässigkeit {} %", "YOUR CAR · reliability {} %"), ("Budget: {} Mio", "Budget: {} M"),
    ("Deckel noch {} Mio", "Cap left {} M"), ("Sponsor: {} · {}", "Sponsor: {} · {}"), ("Ziel: Konstrukteure P{#}", "Goal: constructors P{}"),
    ("AUTO · Ranking P{#}/{#}", "CAR · ranking P{}/{}"), ("In Arbeit: {} · noch {#} Rd.", "In progress: {} · {} races left"),
    ("FAHRER · Crew-Stopp {} s", "DRIVERS · crew stop {} s"), ("{} (du)", "{} (you)"),
    ("Rivalenteam: {} · Duelle {#}:{#}", "Rival team: {} · duels {}:{}"),
    ("Konstrukteure: {} führt · {} P{#}", "Constructors: {} lead · {} P{}"), ("Konstrukteure: {} führt", "Constructors: {} lead"),
    ("Lauf {#}/{#} · {#} Runden", "Round {}/{} · {} laps"), ("Rekord {} {}", "Record {} {}"),
    ("{} s Standzeit (KI 2.40 s)", "{} s stationary (AI 2.40 s)"), ("{} · {} Mio/Rennen", "{} · {} M/race"),
    ("in Arbeit · noch {#} Rd.", "in progress · {} races left"), ("Bauzeit {#} Rd.", "Build time {} races"),
    ("{} % · Ausfallrisiko {} %/Rennen", "{} % · failure risk {} %/race"), ("{} %  ·  {} % je Stufe", "{} %  ·  {} % per level"),
    ("{} · Budget {} Mio · Projekte: {#}/{#} · Erfolgschance {#} %", "{} · budget {} M · projects: {}/{} · success chance {} %"),
    ("{} / {} Mio", "{} / {} M"), ("{} · Stufe {#}", "{} · level {}"),
    ("fertig nach {#} Rennen · {} Mio investiert", "ready after {} races · {} M invested"),
    ("Projekte kosten sofort Geld, das neue Teil kommt aber erst nach der Bauzeit ans Auto. Mit {#} % "
     "Wahrscheinlichkeit bringt ein Teil nur die halbe Wirkung. Windkanal: kürzere Bauzeit + höhere Erfolgschance. "
     "Simulator: deine Fahrer werden besser. Fabrik: Teile billiger. Infrastruktur zählt nicht zur "
     "Budgetobergrenze, kostet aber laufend. Auch die KI-Teams entwickeln während der Saison weiter!",
     "Projects cost money right away, but the new part only reaches the car after the build time. There is a {} % "
     "chance a part only brings half the effect. Wind tunnel: shorter build time + higher success chance. "
     "Simulator: your drivers improve. Factory: cheaper parts. Infrastructure doesn't count towards the cost cap "
     "but has running costs. The AI teams keep developing during the season too!"),
    ("ENTWICKLUNG", "DEVELOPMENT"),
    ("Saison {#} · Teamruf {#} - besserer Ruf bringt bessere Angebote · gilt die ganze Saison",
     "Season {} · team reputation {} - better reputation brings better offers · valid all season"),
    ("{} Mio", "{} M"), ("Garantiert/Saison: {} Mio", "Guaranteed/season: {} M"), ("Wirkung: {}", "Effect: {}"),
    ("{} · {#} abgeschlossene Saison(s)", "{} · {} completed season(s)"), ("Beste WM-Platzierung: P{#}", "Best championship finish: P{}"),
    ("Nochmal ENTER: {} entlassen?", "Press ENTER again: release {}?"),
    ("{} · Budget {} Mio · Ruf {#} · freie Cockpits: {#}", "{} · budget {} M · reputation {} · free seats: {}"),
    ("im Team · {#} J.", "in team · {} yrs"), ("{} · {#} Jahre · Stil: {}", "{} · {} years · style: {}"),
    ("{}  (Potenzial {#})", "{}  (potential {})"), ("{} % Leistung", "{} % performance"), ("{} % Verschleiß", "{} % wear"),
    ("{} Mio (einmalig)", "{} M (one-off)"), ("Vertrag: noch {#} Saison(s)", "Contract: {} season(s) left"),
    ("ENTER (2x): entlassen · Abfindung {} Mio", "ENTER (2x): release · severance {} M"),
    ("Vertragslänge: < {#} Saisons >", "Contract length: < {} seasons >"), ("Vertragslänge: < {#} Saison >", "Contract length: < {} season >"),
    ("Will ein Team mit Ruf {#}", "Wants a team with reputation {}"), ("SAISON {#} · ABSCHLUSS", "SEASON {} · REVIEW"),
    ("Konstrukteurs-Weltmeister: {}", "Constructors' champion: {}"), ("Dein Platz in der Fahrer-WM: P{#}", "Your drivers' championship position: P{}"),
    ("{} in der Konstrukteurs-WM: P{#}", "{} in the constructors' championship: P{}"), ("{#}/100 (vorher {#})", "{}/100 (before {})"),
    ("noch {#} Saison(s) bei {}", "{} season(s) left at {}"), ("SAISON {#} STARTEN", "START SEASON {}"),
    ("{} · Wertung {#} · {} Mio", "{} · rating {} · {} M"), ("Slot {#} gelöscht", "Slot {} deleted"),
    ("Saison {#} · Rennen {#}/{#} · {}", "Season {} · race {}/{} · {}"), ("Ruf {#} · Siege {#} · Titel {#}", "Reputation {} · wins {} · titles {}"),
    ("Budget {} Mio · Ruf {#} · Titel {#}", "Budget {} M · reputation {} · titles {}"), ("SLOT {#}", "SLOT {}"),
    ("Dein Auto ({}): P{#} von {#} · Werte relativ zum Referenzauto", "Your car ({}): P{} of {} · values relative to the reference car"),
    ("Noch kein Team · Werte relativ zum Referenzauto", "No team yet · values relative to the reference car"),
    ("{}%  ·  zum Besten {}%", "{}%  ·  to the best {}%"),
    # career extras
    ("Lackierung, Helm, Startnummer und Namen anpassen · Team umbenennen kostet {#} Mio",
     "Customise livery, helmet, race number and names · renaming the team costs {} M"),
    ("Lackierung ist kostenlos. Ein neuer Teamname kostet {#} Mio (Rebranding) und wird auch in der Historie "
     "übernommen.", "The livery is free. A new team name costs {} M (rebranding) and is applied to the history too."),
    ("Konto {} Mio · investiere dein Gehalt in deine Karriere", "Account {} M · invest your salary in your career"),
    ("Stufe {#}/{#}", "Level {}/{}"), ("{} Mio / Saison", "{} M / season"), ("noch {#} Saison(s)", "{} season(s) left"),
    ("{} · {#} Rennen erfasst · bestes Auto deines Teams", "{} · {} races recorded · best car of your team"),
    ("{} · {#} Rennen erfasst", "{} · {} races recorded"), ("ZIELPOSITIONEN · LETZTE {#} RENNEN", "FINISHING POSITIONS · LAST {} RACES"),
    ("Saison {#} (läuft)", "Season {} (running)"), ("Saison {#}", "Season {}"), ("{#} von {#} freigeschaltet", "{} of {} unlocked"),
    ("{#} Runden pro Rennen", "{} laps per race"), ("{#} Runde pro Rennen", "{} lap per race"),
    ("Slot {#} · Einstellungen für die restlichen Rennen", "Slot {} · settings for the remaining races"),
    # ---------------------------------------------------------------- wheel / controller, setup, fuel, plank
    ("Taste: {}", "Button: {}"), ("Achse {#}  ({#} -> {#})", "Axis {}  ({} -> {})"), ("Knopf {#}", "Button {}"),
    ("Knöpfe: {}", "Buttons: {}"), ("{#} Achsen · {#} Knöpfe · {#} Steuerkreuz", "{} axes · {} buttons · {} d-pad"),
    ("{}  ({#} Geräte)", "{}  ({} devices)"),
    ("Knopf am Lenkrad/Controller drücken für: {}. Entf löscht die Belegung, andere Taste bricht ab.",
     "Press a button on the wheel/controller for: {}. Delete clears it, any other key cancels."),
    ("{} Übernahme automatisch nach kurzem Halten, ENTER übernimmt sofort, ESC bricht ab.",
     "{} Accepted automatically after a short hold, ENTER accepts now, ESC cancels."),
    ("{}: Flügel {#}/{#} · Höhe {#}  (ENTER)", "{}: wing {}/{} · height {}  (ENTER)"),
    ("Renndistanz {#} Runden", "race distance {} laps"),
    ("Sprit {#} kg · {#} Rd.", "Fuel {} kg · {} laps"), ("Sprit {#} kg · Reserve {#}", "Fuel {} kg · reserve {}"), ("Planke {#}", "Plank {}"),
    ("Planke {#}/{#} mm - wird nicht getauscht", "Plank {}/{} mm - not replaced"),
    ("{#} Rd. ({#} kg)  ->  Reserve {#}", "{} laps ({} kg)  ->  reserve {}"), ("{#} Rd. ({#} kg)", "{} laps ({} kg)"),
    ("unverändert ({#})", "unchanged ({})"), ("{#}  (jetzt {#} -> {#})", "{}  (now {} -> {})"),
    ("Ja  ({#}s)", "Yes  ({}s)"), ("Nein  ({#}s)", "No  ({}s)"), ("Ja  (keine Schäden)", "Yes  (no damage)"),
    ("Nein  (keine Schäden)", "No  (no damage)"), ("[{#}] {}", "[{}] {}"), ("[5/ENTER]  {}", "[5/ENTER]  {}"),
    ("BOX in dieser Runde: {}", "BOX this lap: {}"), ("{}-Reifen", "{} tyres"), ("{#} Rd. Sprit", "{} laps of fuel"),
    ("Frontflügel {#}", "Front wing {}"), ("Reifen: {}", "Tyres: {}"), ("Tanken {#} Rd.", "Refuel {} laps"),
    ("Reparatur ({#}s)", "Repair ({}s)"), ("Boxenstopp ... {#}s", "Pit stop ... {}s"),
    ("DISQUALIFIZIERT - {}", "DISQUALIFIED - {}"),
    ("Planke {#} mm abgenutzt (max. {#} mm)", "plank worn {} mm (max. {} mm)"),
    ("DISQUALIFIKATION (Planke): {}", "DISQUALIFIED (plank): {}"),
    ("{} · {#} Runden · Hochrechnung auf {#} Rennrunden", "{} · {} laps · projected to {} race laps"),
    ("Ø {} · Bestzeit {} · Streuung {#}s", "avg {} · best {} · spread {}s"), ("Reifen {}", "Tyres {}"),
    ("{#}% pro Runde -> hält ~{#} Rd. ({})", "{}% per lap -> lasts ~{} laps ({})"),
    ("{#} Stopp(s) im Rennen", "{} stop(s) in the race"),
    ("{#} kg pro Runde -> Rennen braucht {#} kg · Empfehlung: Renndistanz {#} Rd.",
     "{} kg per lap -> race needs {} kg · recommended: race distance {} laps"),
    ("{#} mm pro Runde -> {#} mm im Rennen ({})", "{} mm per lap -> {} mm in the race ({})"),
    ("Strecke {#}% nass", "track {}% wet"), ("Strecke {#}% nass · Ende ~{#}s", "track {}% wet · stops in ~{}s"),
    ("Regen in ~{#}s", "rain in ~{}s"), ("Regen kommt in ca. {#} Sekunden.", "Rain expected in about {} seconds."),
    ("{}: Box für {}", "{}: box for {}"),
    ("Tastatur: {}", "Keyboard: {}"), ("{}: Achse {#}  ({#} -> {#})", "{}: axis {}  ({} -> {})"),
    ("Sprit {#} Rd.", "Fuel {} laps"), ("P{#} · {}", "P{} · {}"), ("ZIEL! {} P{#}", "FINISH! {} P{}"),
    ("ZIEL! Du bist P{#}", "FINISH! You are P{}"), ("{}: P{#}", "{}: P{}"),
    ("{}: ZU FRÜH GAS - Räder drehen durch!", "{}: TOO EARLY ON THE THROTTLE - wheelspin!"),
    ("ENTER {} · G Garage (Setup anpassen) · Pfeile blättern · ESC Menü",
     "ENTER {} · G garage (adjust setup) · arrows scroll · ESC menu"),
    ("{#} Siege  ({})", "{} wins  ({})"), ("{#}  ({} %)", "{}  ({} %)"), ("{#}  (Ø {})", "{}  (avg {})"),
]

def _each(prefix: str, sep: str = ", "):
    def repl(m: re.Match[str]) -> str:
        from .i18n import tr
        return prefix + sep.join(tr(part) for part in m.group(1).split(sep))
    return repl


def _quoted(text: str) -> str:
    from .i18n import tr
    return f'"{tr(text)}"'


def _updates(m: re.Match[str]) -> str:
    from .i18n import tr
    return "Updates: " + re.sub(r"\(([^)]+)\)", lambda g: f"({tr(g.group(1))})", m.group(1))


PATTERNS: list[tuple[str, object]] = [
    (r"ERFOLG FREIGESCHALTET: (.+, .+)", _each("ACHIEVEMENT UNLOCKED: ")),
    (r"Updates: (.+)", _updates),
    (r'"(.+)"', lambda m: _quoted(m.group(1))),
    (r"((?:Ruf|Vertrauen|Teamruf|Sponsor) [+-]\d+ · .+)", _each("", " · ")),
    (r"Neue Talente im Fahrermarkt: (.+)",
     lambda m: "New talents on the driver market: " + re.sub(r"(\d+) J\., Potenzial (\d+)", r"\1 y/o, potential \2",
                                                              m.group(1))),
]
