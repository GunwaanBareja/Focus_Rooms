# FocusRoom - Collaborative Study Room

A small client-server study app. Students join a room, share a Pomodoro timer
(25 min focus / 5 min break), see each other's status and chat.

## Files
- `server.py`   - TCP server, threads, shared timer, small web status page
- `client.py`   - Tkinter window for each student
- `database.py` - SQLite functions (users, rooms, messages, sessions)

## How to run
1. `python server.py`
2. `python client.py` (open it more than once to test with several users)
3. Status page: http://localhost:8080

To use two computers, type the server computer's IP in the "Server IP" box.

## Message format (sent over TCP, one line each)
Client to server: `JOIN|name|room`, `CHAT|text`, `STATUS|Studying`, `TIMER|start`
Server to client: `JOINED|room`, `CHAT|name|time|text`, `SYS|text`,
`TICK|mode|running|remaining|rounds`, `STATE|room|mode|running|remaining|rounds|name:status,...`
