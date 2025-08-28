import tkinter as tk
from tkinter import messagebox
import requests
import os
import sqlite3
from datetime import datetime
import hashlib

def calculate_file_hash(file_path):
    """Calculate SHA-256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def setup_database():
    conn = sqlite3.connect('file_system.db')
    cursor = conn.cursor()
    
    # Files table to store unique files with their hash
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS files (
        file_id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        file_hash TEXT NOT NULL UNIQUE,
        file_path TEXT NOT NULL,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # User downloads table to track download history
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_downloads (
        download_id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER,
        download_url TEXT NOT NULL,
        download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_id) REFERENCES files (file_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Folder to store downloaded files
DOWNLOAD_FOLDER = "downloads"
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Google Custom Search API configuration
GOOGLE_API_KEY = "AIzaSyA2cxa3Nv1NWZGh6rxvTAyczPbUgKLkhzQ"
SEARCH_ENGINE_ID = "90859e65576214542"
SEARCH_API_URL = f"https://www.googleapis.com/customsearch/v1"

def is_file_downloaded(file_hash):
    """Check if a file with the same hash exists"""
    conn = sqlite3.connect('file_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM files WHERE file_hash = ?', (file_hash,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def is_url_downloaded(url):
    """Check if a URL has been downloaded before"""
    conn = sqlite3.connect('file_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM user_downloads WHERE download_url = ?', (url,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def save_download_record(file_name, file_hash, file_path, download_url):
    """Save both file and download records"""
    conn = sqlite3.connect('file_system.db')
    cursor = conn.cursor()
    
    try:
        # First, insert or get the file record
        cursor.execute('''
        INSERT OR IGNORE INTO files (file_name, file_hash, file_path)
        VALUES (?, ?, ?)
        ''', (file_name, file_hash, file_path))
        
        # Get the file_id (whether it was just inserted or already existed)
        cursor.execute('SELECT file_id FROM files WHERE file_hash = ?', (file_hash,))
        file_id = cursor.fetchone()[0]
        
        # Then insert the download record
        cursor.execute('''
        INSERT INTO user_downloads (file_id, download_url)
        VALUES (?, ?)
        ''', (file_id, download_url))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def search_online():
    query = search_entry.get()
    if not query.strip():
        messagebox.showwarning("Warning", "Please enter a search query.")
        return
    
    params = {
        "key": GOOGLE_API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": query,
        "fileType": "pdf",
        "num": 10,
    }
    
    try:
        response = requests.get(SEARCH_API_URL, params=params)
        if response.status_code == 200:
            results = response.json().get("items", [])
            result_text.delete(1.0, tk.END)
            
            if not results:
                result_text.insert(tk.END, "No results found.\n")
                return
            
            for i, item in enumerate(results, 1):
                title = item.get("title", "No Title")
                link = item.get("link", "No Link")
                # Add visual indicator for previously downloaded files
                downloaded = "✓ " if is_url_downloaded(link) else ""
                result_text.insert(tk.END, f"{i}. {downloaded}{title}\n{link}\n\n")
        else:
            messagebox.showerror("Error", f"Failed to search files: {response.status_code}")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")

def download_file():
    try:
        if not result_text.tag_ranges(tk.SEL):
            messagebox.showwarning("Warning", "Please select a file to download.")
            return

        selected_text = result_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        if not selected_text:
            messagebox.showwarning("Warning", "Please select a valid file to download.")
            return

        url = selected_text.split("\n")[-1]
        if is_url_downloaded(url):
            messagebox.showinfo("Notice", "You have already downloaded this file from this URL.")
            return

        response = requests.get(url, stream=True)
        if response.status_code == 200:
            file_name = url.split("/")[-1]
            temp_path = os.path.join(DOWNLOAD_FOLDER, f"temp_{file_name}")
            
            # Download to temporary file first
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Calculate hash
            file_hash = calculate_file_hash(temp_path)
            
            # Check if file with same hash exists
            existing_path = is_file_downloaded(file_hash)
            if existing_path:
                os.remove(temp_path)  # Remove temporary file
                messagebox.showinfo("Notice", 
                    f"This file already exists in the system!\nLocation: {existing_path}")
                return
            
            # If it's a new file, move it to final location
            file_path = os.path.join(DOWNLOAD_FOLDER, file_name)
            os.rename(temp_path, file_path)
            
            # Save records to database
            save_download_record(file_name, file_hash, file_path, url)
            
            # Refresh the search results to show updated download status
            search_online()
            
            messagebox.showinfo("Success", f"File downloaded successfully:\nName: {file_name}\nLocation: {file_path}\nHash: {file_hash}")
        else:
            messagebox.showerror("Error", f"Failed to download file: {response.status_code}")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")

def view_download_history():
    conn = sqlite3.connect('file_system.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT f.file_name, f.file_hash, f.file_path, ud.download_url, ud.download_date
    FROM user_downloads ud
    JOIN files f ON ud.file_id = f.file_id
    ORDER BY ud.download_date DESC
    ''')
    history = cursor.fetchall()
    conn.close()

    history_window = tk.Toplevel(root)
    history_window.title("Download History")
    
    history_text = tk.Text(history_window, height=20, width=100)
    history_text.pack(pady=10)
    
    for file_name, file_hash, file_path, url, date in history:
        history_text.insert(tk.END, 
            f"File: {file_name}\n"
            f"Hash: {file_hash}\n"
            f"Path: {file_path}\n"
            f"URL: {url}\n"
            f"Date: {date}\n"
            f"{'-'*80}\n\n")
    
    history_text.config(state=tk.DISABLED)

root = tk.Tk()
root.title("Online File Downloader")

# Initialize database
setup_database()

# UI Components
search_label = tk.Label(root, text="Search File Online:")
search_label.pack(pady=5)
search_entry = tk.Entry(root, width=50)
search_entry.pack(pady=5)
search_button = tk.Button(root, text="Search", command=search_online)
search_button.pack(pady=10)

result_text = tk.Text(root, height=20, width=80)
result_text.pack(pady=10)

download_button = tk.Button(root, text="Download Selected File", command=download_file)
download_button.pack(pady=5)

history_button = tk.Button(root, text="View Download History", command=view_download_history)
history_button.pack(pady=5)

root.mainloop()