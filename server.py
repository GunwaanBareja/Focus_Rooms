# server.py - FocusRoom server
# Run with:  python server.py
# Messages are text lines like  COMMAND|data  (one per line)

import socket
import threading
import time
import html
from http.server import HTTPServer, BaseHTTPRequestHandler

import database

HOST = "0.0.0.0"
PORT = 5555
WEB_PORT = 8080
FOCUS_TIME = 25 * 60   # seconds
BREAK_TIME = 5 * 60

rooms = {}                 # room_id -> room dictionary
lock = threading.Lock()    # only one thread changes rooms at a time


def make_room():
    return {
        "users": {},        # name -> {"sock": socket or None, "status": "Studying"}
        "mode": "focus",
        "running": False,
        "remaining": FOCUS_TIME,
        "rounds": 0,
        "seen": set(),      # everyone who joined (for session history)
    }


def clean(text):
    # remove characters that would break our message format
    return text.strip().replace("|", "").replace(":", "").replace(",", "")[:20]


def send(sock, text):
    try:
        sock.sendall((text + "\n").encode())
    except OSError:
        pass


def broadcast(room, text):
    for user in room["users"].values():
        if user["sock"] is not None:
            send(user["sock"], text)


def state_text(room_id, room):
    people = ",".join(name + ":" + u["status"] for name, u in room["users"].items())
    return "STATE|%s|%s|%d|%d|%d|%s" % (room_id, room["mode"], room["running"], room["remaining"], room["rounds"], people)


def tick_text(room):
    return "TICK|%s|%d|%d|%d" % (room["mode"], room["running"], room["remaining"], room["rounds"])


def system_message(room_id, room, text):
    broadcast(room, "SYS|" + text)
    broadcast(room, state_text(room_id, room))


def switch_mode(room_id, room, finished):
    # called when time is up (finished=True) or someone pressed skip
    if finished and room["mode"] == "focus":
        room["rounds"] += 1
        database.save_session(room_id, FOCUS_TIME // 60, room["seen"])
    if room["mode"] == "focus":
        room["mode"] = "break"
        room["remaining"] = BREAK_TIME
        new_status = "Break"
    else:
        room["mode"] = "focus"
        room["remaining"] = FOCUS_TIME
        new_status = "Studying"
    for user in room["users"].values():
        if user["sock"] is not None:
            user["status"] = new_status
    system_message(room_id, room, room["mode"].upper() + " time started!")


def handle_client(conn):
    name = None
    room_id = None
    try:
        for line in conn.makefile("r"):
            command, _, data = line.strip().partition("|")
            with lock:
                if name is None:
                    # first message must be JOIN|name|room
                    if command != "JOIN":
                        continue
                    parts = data.split("|")
                    if len(parts) != 2 or not clean(parts[0]) or not clean(parts[1]):
                        send(conn, "ERROR|Please enter a name and a room ID")
                        continue
                    new_name, new_room = clean(parts[0]), clean(parts[1])
                    if new_room not in rooms:
                        rooms[new_room] = make_room()
                    room = rooms[new_room]
                    if new_name in room["users"] and room["users"][new_name]["sock"] is not None:
                        send(conn, "ERROR|That name is already used in this room")
                        continue
                    name, room_id = new_name, new_room
                    room["users"][name] = {"sock": conn, "status": "Studying"}
                    room["seen"].add(name)
                    database.add_user_and_room(name, room_id)
                    send(conn, "JOINED|" + room_id)
                    for old_name, text, t in database.get_old_messages(room_id):
                        send(conn, "CHAT|%s|%s|%s" % (old_name, t, text))
                    system_message(room_id, room, name + " joined the room")
                else:
                    room = rooms[room_id]
                    if command == "CHAT" and data.strip():
                        t = time.strftime("%H:%M")
                        database.save_message(room_id, name, data.strip(), t)
                        broadcast(room, "CHAT|%s|%s|%s" % (name, t, data.strip()))
                    elif command == "STATUS" and data in ("Studying", "Break"):
                        room["users"][name]["status"] = data
                        broadcast(room, state_text(room_id, room))
                    elif command == "TIMER":
                        if data == "start":
                            room["running"] = True
                        elif data == "pause":
                            room["running"] = False
                        elif data == "reset":
                            room["running"] = False
                            room["remaining"] = FOCUS_TIME if room["mode"] == "focus" else BREAK_TIME
                        elif data == "skip":
                            switch_mode(room_id, room, False)
                            continue
                        system_message(room_id, room, name + " pressed " + data)
    except OSError:
        pass

    # client disconnected
    with lock:
        if name is not None:
            room = rooms[room_id]
            room["users"][name] = {"sock": None, "status": "Offline"}
            system_message(room_id, room, name + " left")
            if all(u["sock"] is None for u in room["users"].values()):
                del rooms[room_id]    # nobody is left, remove the room
    conn.close()


def timer_loop():
    # runs in its own thread, counts down every running room once per second
    while True:
        time.sleep(1)
        with lock:
            for room_id, room in rooms.items():
                if room["running"]:
                    room["remaining"] -= 1
                    if room["remaining"] <= 0:
                        switch_mode(room_id, room, True)
                    else:
                        broadcast(room, tick_text(room))

PAGE_STYLE = """
body { font-family: Arial; background: #f2f4f8; max-width: 800px; margin: 30px auto; }
.room { background: white; padding: 12px 18px; margin: 12px 0; border-radius: 8px; }
.Studying { color: green; } .Break { color: orange; } .Offline { color: gray; }
table { background: white; width: 100%; } td, th { padding: 6px; text-align: left; }
"""


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass   # don't print every request

    def do_GET(self):
        page = "<html><head><meta charset='utf-8'><meta http-equiv='refresh' content='5'>"
        page += "<title>FocusRoom</title><style>" + PAGE_STYLE + "</style></head><body>"
        page += "<h1>FocusRoom - live rooms</h1>"
        with lock:
            if not rooms:
                page += "<p>No active rooms.</p>"
            for room_id, room in rooms.items():
                mins, secs = divmod(room["remaining"], 60)
                page += "<div class='room'><h2>%s</h2>" % html.escape(room_id)
                page += "<p>%02d:%02d (%s, %s) - %d rounds done</p><ul>" % (
                    mins, secs, room["mode"], "running" if room["running"] else "paused", room["rounds"])
                for name, u in room["users"].items():
                    page += "<li class='%s'>%s - %s</li>" % (u["status"], html.escape(name), u["status"])
                page += "</ul></div>"
        page += "<h2>Last finished sessions</h2><table><tr><th>Room</th><th>Minutes</th><th>People</th><th>Ended</th></tr>"
        for r, m, p, e in database.get_sessions():
            page += "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (html.escape(r), m, html.escape(p), e)
        page += "</table></body></html>"
        data = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    database.create_tables()
    threading.Thread(target=timer_loop, daemon=True).start()
    web = HTTPServer((HOST, WEB_PORT), WebHandler)
    threading.Thread(target=web.serve_forever, daemon=True).start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    print("Server running on port", PORT)
    print("Status page: http://localhost:%d" % WEB_PORT)
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


main()
