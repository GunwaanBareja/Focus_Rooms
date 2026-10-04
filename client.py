# client.py - FocusRoom desktop client (Tkinter)
# Run with:  python client.py

import socket
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox


class FocusRoomApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FocusRoom")
        self.root.geometry("760x520")
        self.sock = None
        self.incoming = queue.Queue()   # messages from the reader thread
        self.show_login()
        self.root.after(100, self.check_messages)

    def show_login(self):
        self.login_frame = ttk.Frame(self.root, padding=30)
        self.login_frame.pack(expand=True)
        ttk.Label(self.login_frame, text="FocusRoom", font=("Arial", 22, "bold")).grid(row=0, columnspan=2, pady=10)

        self.server_var = tk.StringVar(value="localhost")
        self.name_var = tk.StringVar()
        self.room_var = tk.StringVar()
        labels = [("Server IP", self.server_var), ("Your name", self.name_var), ("Room ID", self.room_var)]
        for i, (text, var) in enumerate(labels):
            ttk.Label(self.login_frame, text=text).grid(row=i + 1, column=0, padx=5, pady=4)
            ttk.Entry(self.login_frame, textvariable=var, width=22).grid(row=i + 1, column=1)
        ttk.Button(self.login_frame, text="Join", command=self.join).grid(row=5, columnspan=2, pady=12)

    def join(self):
        if self.name_var.get().strip() == "" or self.room_var.get().strip() == "":
            messagebox.showwarning("FocusRoom", "Please enter your name and room ID")
            return
        try:
            self.sock = socket.create_connection((self.server_var.get(), 5555), timeout=5)
            self.sock.settimeout(None)
        except OSError as e:
            messagebox.showerror("Error", "Could not connect: " + str(e))
            return
        threading.Thread(target=self.read_from_server, daemon=True).start()
        self.send("JOIN|%s|%s" % (self.name_var.get(), self.room_var.get()))

    def show_main(self, room_id):
        self.login_frame.destroy()
        self.root.title("FocusRoom - " + room_id)

        left = ttk.Frame(self.root, padding=10)
        left.pack(side="left", fill="y")
        self.mode_label = ttk.Label(left, text="FOCUS", font=("Arial", 12, "bold"))
        self.mode_label.pack()
        self.time_label = ttk.Label(left, text="25:00", font=("Arial", 40, "bold"))
        self.time_label.pack()
        self.info_label = ttk.Label(left, text="Paused - 0 rounds done")
        self.info_label.pack(pady=5)

        buttons = ttk.Frame(left)
        buttons.pack()
        for text in ["start", "pause", "reset", "skip"]:
            ttk.Button(buttons, text=text.title(), width=6,
                       command=lambda t=text: self.send("TIMER|" + t)).pack(side="left", padx=2)

        ttk.Label(left, text="My status").pack(pady=(12, 2))
        status_buttons = ttk.Frame(left)
        status_buttons.pack()
        for text in ["Studying", "Break"]:
            ttk.Button(status_buttons, text=text,
                       command=lambda t=text: self.send("STATUS|" + t)).pack(side="left", padx=2)

        ttk.Label(left, text="People in room").pack(pady=(12, 2))
        self.user_list = tk.Listbox(left, height=10, font=("Arial", 11))
        self.user_list.pack(fill="both", expand=True)

        right = ttk.Frame(self.root, padding=10)
        right.pack(side="right", fill="both", expand=True)
        self.chat_box = tk.Text(right, state="disabled", wrap="word")
        self.chat_box.pack(fill="both", expand=True)
        self.chat_box.tag_config("sys", foreground="gray")

        bottom = ttk.Frame(right)
        bottom.pack(fill="x", pady=5)
        self.msg_var = tk.StringVar()
        entry = ttk.Entry(bottom, textvariable=self.msg_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda event: self.send_chat())
        ttk.Button(bottom, text="Send", command=self.send_chat).pack(side="left", padx=5)

    def send_chat(self):
        text = self.msg_var.get().strip()
        if text != "":
            self.send("CHAT|" + text)
            self.msg_var.set("")

    def add_chat_line(self, text, tag=None):
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", text + "\n", tag)
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

    def update_timer(self, mode, running, remaining, rounds):
        mins, secs = divmod(int(remaining), 60)
        self.time_label.config(text="%02d:%02d" % (mins, secs))
        self.mode_label.config(text=mode.upper())
        state = "Running" if running == "1" else "Paused"
        self.info_label.config(text="%s - %s rounds done" % (state, rounds))

    def send(self, text):
        try:
            self.sock.sendall((text + "\n").encode())
        except OSError:
            pass

    def read_from_server(self):
        # runs in a separate thread so the window does not freeze
        try:
            for line in self.sock.makefile("r"):
                self.incoming.put(line.strip())
        except OSError:
            pass
        self.incoming.put("DISCONNECTED|")

    def check_messages(self):
        # tkinter can only be changed from the main thread, so we check the queue here
        while not self.incoming.empty():
            self.handle_message(self.incoming.get())
        self.root.after(100, self.check_messages)

    def handle_message(self, line):
        command, _, data = line.partition("|")
        if command == "JOINED":
            self.show_main(data)
        elif command == "ERROR":
            messagebox.showerror("FocusRoom", data)
        elif command == "CHAT":
            name, t, text = data.split("|", 2)
            self.add_chat_line("[%s] %s: %s" % (t, name, text))
        elif command == "SYS":
            self.add_chat_line("* " + data, "sys")
            if "time started" in data:
                self.root.bell()
        elif command == "TICK":
            mode, running, remaining, rounds = data.split("|")
            self.update_timer(mode, running, remaining, rounds)
        elif command == "STATE":
            room_id, mode, running, remaining, rounds, people = data.split("|")
            self.update_timer(mode, running, remaining, rounds)
            self.user_list.delete(0, "end")
            if people != "":
                for person in people.split(","):
                    name, status = person.split(":")
                    self.user_list.insert("end", "%s (%s)" % (name, status))
        elif command == "DISCONNECTED":
            if hasattr(self, "chat_box"):
                self.add_chat_line("* Disconnected from server", "sys")
            else:
                messagebox.showerror("FocusRoom", "Server closed the connection")


root = tk.Tk()
app = FocusRoomApp(root)
root.mainloop()
