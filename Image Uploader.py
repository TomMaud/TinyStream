import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
import platform
import csv
from PIL import Image
import serial
from serial.tools import list_ports
from tkinter import filedialog
import numpy as np
from mss import mss

BAUD_RATE = 921600
WIDTH = 135
HEIGHT = 240


class SecondScreenController:
    def __init__(self, root):
        self.root = root
        self.root.title("Second Screen Controller")
        self.root.geometry("1200x900")
        self.devices = {}
        self.loop = None
        self.loop_thread = None
        self._device_col = 0
        
        self.setup_ui()
        self.start_event_loop()
        self.serial = None
        self.is_streaming = False
        self.sct = mss()
        self.monitor = self.sct.monitors[1]



    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)

        scan_frame = ttk.LabelFrame(main_frame, text="Device Connect", padding="10")
        scan_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        scan_button = ttk.Button(scan_frame, text="Connect Screen")
        scan_button.configure(command=self.ConnectScreen)
        scan_button.grid(row=0, column=0, padx=5)

        upload_frame = ttk.LabelFrame(main_frame, text="Upload Image", padding="10")
        upload_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.upload_button = ttk.Button(upload_frame, text="Upload")
        self.upload_button.configure(command=self.getImage,state=tk.DISABLED)
        self.upload_button.grid(row=0, column=0, padx=5)

        stream_frame = ttk.LabelFrame(main_frame, text="Stream screen", padding="10")
        stream_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.stream_button = ttk.Button(stream_frame, text="Stream")
        self.stream_button.configure(command=self.toggle_stream, state=tk.DISABLED)
        self.stream_button.grid(row=0, column=0, padx=5)

        clear_frame = ttk.LabelFrame(main_frame, text="Clear screen", padding="10")
        clear_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.clear_button = ttk.Button(clear_frame, text="Clear")
        self.clear_button.configure(command=self.ClearScreen, state=tk.DISABLED)
        self.clear_button.grid(row=0, column=0, padx=5)

        def _on_frame_configure(event):
            self._devices_canvas.configure(
                scrollregion=self._devices_canvas.bbox("all")
            )

        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=5, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        

    
    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    
    def ConnectScreen(self):
        port= self.find_pico_port()
        if not port:
            self.log("Error: Could not find Pico port.")
            return
        self.serial = serial.Serial(port, BAUD_RATE, timeout=2)
        time.sleep(2)
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self.upload_button.configure(state=tk.NORMAL)
        self.stream_button.configure(state=tk.NORMAL)
        self.clear_button.configure(state=tk.NORMAL)
        self.log("Successfully connected to Pico port.")

    def getImage(self):
        filename = filedialog.askopenfilename(initialdir="/",
                                              title="Select a File",
                                              filetypes=(("Image files",
                                                          ("*.png", "*.jpg", "*.jpeg", "*.webp")),
                                                         ("all files",
                                                          "*.*")))
        if filename:
            img = Image.open(filename).convert("RGB")

            self.UploadImage(img)
            self.log(f"{filename} uploaded")
        else:
            self.log(f"No image selected")

    def ClearScreen(self):
        img = Image.new(mode="RGB", size=(WIDTH, HEIGHT))
        self.UploadImage(img)
        self.log("Screen cleared")


    def UploadImage(self, img):
        w, h = img.size
        if w >= h:
            img = img.rotate(-90, expand=True)
        img = img.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)

        arr = np.array(img, dtype=np.uint16)
        r = (arr[:, :, 0] & 0xF8) << 8
        g = (arr[:, :, 1] & 0xFC) << 3
        b = arr[:, :, 2] >> 3
        rgb565 = r | g | b

        high_bytes = (rgb565 >> 8).astype(np.uint8)
        low_bytes = (rgb565 & 0xFF).astype(np.uint8)

        payload = np.dstack((high_bytes, low_bytes)).flatten().tobytes()


        self.serial.write(b"s")

        while True:
            ack = self.serial.read(1)
            if ack != b'A':
                continue
            else:
                break

        self.serial.write(payload)
        self.serial.flush()

    def toggle_stream(self):
        if not self.is_streaming:
            self.is_streaming = True
            self.stream_button.configure(text="Stop Stream")
            self.log("Stream started")
            self.upload_button.configure(state=tk.DISABLED)
            self.clear_button.configure(state=tk.DISABLED)
            self.run_stream_loop()
        else:
            self.is_streaming = False
            self.stream_button.configure(text="Start Stream")
            self.upload_button.configure(state=tk.NORMAL)
            self.clear_button.configure(state=tk.NORMAL)
            self.log("Stream stopped")

    def run_stream_loop(self):
        if not self.is_streaming:
            return

        if self.is_streaming:
            sct_img = self.sct.grab(self.monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            self.UploadImage(img)
            self.root.after(0, self.run_stream_loop)

    def find_pico_port(self):
        for port in list_ports.comports():
            if "Pico" in port.description or "usbmodem" in port.device or "COM" in port.device:
                return port.device
        return None

    def on_closing(self):
        for pico in self.devices.values():
            if pico.connected:
                asyncio.run_coroutine_threadsafe(pico.disconnect(), self.loop)
        
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()
    

def main():
    root = tk.Tk()
    app = SecondScreenController(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()

