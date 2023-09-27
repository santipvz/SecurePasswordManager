import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import random
import string
import os

# Function to create a random password
def generate_password(length):
    all_characters = string.ascii_letters + string.digits + '<=>@#%&+'
    return ''.join(random.choice(all_characters) for _ in range(length))

# Function to save password details to a file
def save_password(filename, username, password):
    with open(filename, 'w') as file:
        file.write(f'User: {username}\n')
        file.write(f'Password: {password}')

# Function to delete a password file
def delete_password(filename):
    try:
        os.remove(filename)
        messagebox.showinfo('Deletion Successful', f'The file {filename} has been deleted')
    except Exception as e:
        messagebox.showerror('Deletion Error', f'Error deleting the file: {e}')

# Function to edit password details
def edit_password(filename, new_username, new_password):
    try:
        with open(filename, 'w') as file:
            file.write(f'User: {new_username}\n')
            file.write(f'Password: {new_password}\n')
        messagebox.showinfo('Edit Successful', 'Password details have been edited successfully')
    except Exception as e:
        messagebox.showerror('Edit Error', f'Error editing the file: {e}')

# Function to load the list of existing files
def load_existing_files():
    txt_files = [filename for filename in os.listdir() if filename.endswith('.txt')]
    return txt_files


# Create the main window
root = tk.Tk()
root.title('Password Manager')

# Change the ttk style for a modern appearance
style = ttk.Style()
style.theme_use("clam")

# Configure button styles
style.configure(
    "TButton",
    padding=10,
    relief="flat",
    font=("Helvetica", 12),
    foreground="white",
    background="#0078d4",
)

style.map(
    "TButton",
    foreground=[("active", "white")],
    background=[("active", "#0058a3")]
)

# Configure label styles
style.configure(
    "TLabel",
    font=("Helvetica", 14)
)

# Create a notebook widget
notebook = ttk.Notebook(root)
notebook.pack(
    padx=10,
    pady=10,
    fill='both',
    expand=True
)

# Define tab frames
tab_menu = ttk.Frame(notebook)
tab_create = ttk.Frame(notebook)
tab_delete = ttk.Frame(notebook)
tab_edit = ttk.Frame(notebook)

# Add tabs to the notebook
notebook.add(tab_menu, text='Menu')
notebook.add(tab_create, text='Create')
notebook.add(tab_delete, text='Delete')
notebook.add(tab_edit, text='Edit')

# Create widgets for the "Menu" tab
menu_label = ttk.Label(
    tab_menu,
    text='RANDOM PASSWORD MANAGER',
    font=('Helvetica', 24, 'bold'),
    padding=(0, 20),
)
menu_label.pack(padx=10, pady=10)

menu_create_button = ttk.Button(tab_menu, text='Create Password', command=lambda: notebook.select(tab_create))
menu_create_button.pack(pady=10)

menu_delete_button = ttk.Button(tab_menu, text='Delete Password', command=lambda: notebook.select(tab_delete))
menu_delete_button.pack(pady=10)

menu_edit_button = ttk.Button(tab_menu, text='Edit Password', command=lambda: notebook.select(tab_edit))
menu_edit_button.pack(pady=10)

menu_exit_button = ttk.Button(tab_menu, text='Exit', command=root.quit)
menu_exit_button.pack(pady=10)

# Create widgets for the "Create" tab
create_label = ttk.Label(tab_create, text='Creating Password', font=('Helvetica', 24, 'bold'), padding=(0, 20))
create_label.pack(padx=10, pady=10)

create_filename_label = ttk.Label(tab_create, text='File name:')
create_filename_label.pack(padx=10, pady=5)
create_filename_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
create_filename_entry.pack(padx=10, pady=5)

create_username_label = ttk.Label(tab_create, text='Username:')
create_username_label.pack(padx=10, pady=5)
create_username_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
create_username_entry.pack(padx=10, pady=5)

create_password_length_label = ttk.Label(tab_create, text='Password length:')
create_password_length_label.pack(padx=10, pady=5)
create_password_length_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
create_password_length_entry.pack(padx=10, pady=5)

def create_password():
    filename = create_filename_entry.get()
    username = create_username_entry.get()
    password_length_str = create_password_length_entry.get()

    # Check if the password length is a valid integer
    if not password_length_str.isdigit():
        messagebox.showerror('Invalid Input', 'Password length must be a positive integer.')
        return

    password_length = int(password_length_str)
    password = generate_password(password_length)
    save_password(filename + '.txt', username, password)
    create_filename_entry.delete(0, tk.END)
    create_username_entry.delete(0, tk.END)
    create_password_length_entry.delete(0, tk.END)
    messagebox.showinfo('Password Created', 'The password has been created and saved successfully.')

create_button = ttk.Button(tab_create, text='Create Password', command=create_password)
create_button.pack(padx=10, pady=10)

# Create widgets for the "Delete" tab
delete_label = ttk.Label(tab_delete, text='Delete Password', font=('Helvetica', 24, 'bold'), padding=(0, 20))
delete_label.pack(padx=10, pady=10)

delete_filename_label = ttk.Label(tab_delete, text='Select File to Delete:')
delete_filename_label.pack(padx=10, pady=5)
delete_filename_entry = ttk.Entry(tab_delete, font=("Helvetica", 12))
delete_filename_entry.pack(padx=10, pady=5)

def browse_file_to_delete():
    filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
    delete_filename_entry.delete(0, tk.END)
    delete_filename_entry.insert(0, filename)

delete_browse_button = ttk.Button(tab_delete, text='Browse', command=browse_file_to_delete)
delete_browse_button.pack(padx=10, pady=10)

def delete_selected_password():
    filename = delete_filename_entry.get()
    delete_password(filename)
    delete_filename_entry.delete(0, tk.END)

delete_button = ttk.Button(tab_delete, text='Delete', command=delete_selected_password)
delete_button.pack(padx=10, pady=10)

# Create widgets for the "Edit" tab
edit_label = ttk.Label(tab_edit, text='Edit Password', font=('Helvetica', 24, 'bold'), padding=(0, 20))
edit_label.pack(padx=10, pady=10)

edit_filename_label = ttk.Label(tab_edit, text='Select File to Edit:')
edit_filename_label.pack(padx=10, pady=5)
edit_filename_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
edit_filename_entry.pack(padx=10, pady=5)

def browse_file_to_edit():
    filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
    edit_filename_entry.delete(0, tk.END)
    edit_filename_entry.insert(0, filename)

edit_browse_button = ttk.Button(tab_edit, text='Browse', command=browse_file_to_edit)
edit_browse_button.pack(padx=10, pady=10)

edit_username_label = ttk.Label(tab_edit, text='New Username:')
edit_username_label.pack(padx=10, pady=5)
edit_username_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
edit_username_entry.pack(padx=10, pady=5)

edit_password_length_label = ttk.Label(tab_edit, text='New Password length:')
edit_password_length_label.pack(padx=10, pady=5)
edit_password_length_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
edit_password_length_entry.pack(padx=10, pady=5)

def edit_password_details():
    filename = edit_filename_entry.get()
    new_username = edit_username_entry.get()
    new_password_length_str = edit_password_length_entry.get()

    # Check if the new password length is a valid integer
    if not new_password_length_str.isdigit():
        messagebox.showerror('Invalid Input', 'New password length must be a positive integer.')
        return

    new_password_length = int(new_password_length_str)
    new_password = generate_password(new_password_length)
    edit_password(filename, new_username, new_password)

edit_button = ttk.Button(tab_edit, text='Edit Password', command=edit_password_details)
edit_button.pack(padx=10, pady=10)

root.mainloop()
