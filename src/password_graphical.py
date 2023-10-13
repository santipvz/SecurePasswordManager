"""Module for the graphical user interface of the password manager."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, PhotoImage
import webbrowser
import random
import string
import os
import platform

if platform.system() == "Windows":
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)

class PasswordManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title('SPM')
        self.create_ui()

    def create_ui(self):
        self.create_notebook()
        self.create_create_tab()
        self.create_delete_tab()
        self.create_edit_tab()

    def create_notebook(self):
        style = ttk.Style()
        if platform.system() == "Linux":
            style.theme_use("clam")
        elif platform.system() == "Windows":
            style.theme_use("xpnative")


        # Customize the notebook appearance
        style.configure("TNotebook", background='#f0f0f0')
        style.configure("TNotebook.Tab")
        style.map("TNotebook.Tab")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=10, pady=10, fill='both', expand=True)

    def create_create_tab(self):
        tab_create = ttk.Frame(self.notebook)
        self.notebook.add(tab_create, text='Create')

        # Create widgets for the "Create" tab...
        create_label = ttk.Label(tab_create, text='Create Password', font=('Helvetica', 20, 'bold'), padding=(0, 20))
        create_label.pack(padx=10, pady=10)

        create_filename_label = ttk.Label(tab_create, text='File name:', font=('Helvetica', 13))
        create_filename_label.pack(padx=10, pady=5)
        self.create_filename_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
        self.create_filename_entry.pack(padx=10, pady=5)

        create_username_label = ttk.Label(tab_create, text='Username:', font=('Helvetica', 13))
        create_username_label.pack(padx=10, pady=5)
        self.create_username_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
        self.create_username_entry.pack(padx=10, pady=5)

        create_password_length_label = ttk.Label(tab_create, text='Password length:', font=('Helvetica', 13))
        create_password_length_label.pack(padx=10, pady=5)
        self.create_password_length_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
        self.create_password_length_entry.pack(padx=10, pady=5)

        create_button = ttk.Button(tab_create, text='Create password', command=self.create_password)
        create_button.pack(padx=10, pady=10)
        create_button.configure(style='TButton')

        # Check if the image file exists, otherwise use a text button
        github_image_path = 'assets/button_image.png'
        if os.path.exists(github_image_path):
            create_image = PhotoImage(file=github_image_path)
            create_button_image = tk.Button(tab_create, image=create_image, command=self.extra_button_callback, relief='flat', highlightthickness=0, bd=0)
            create_button_image.image = create_image  # Save a reference to prevent garbage collection
            create_button_image.place(relx=1, rely=1, anchor='se')
        else:
            create_button_text = tk.Button(tab_create, text='GitHub', command=self.extra_button_callback)
            create_button_text.place(relx=1, rely=1, anchor='se')

    def create_delete_tab(self):
        tab_delete = ttk.Frame(self.notebook)
        self.notebook.add(tab_delete, text='Delete')

        # Create widgets for the "Delete" tab...
        delete_label = ttk.Label(tab_delete, text='Delete Password', font=('Helvetica', 20, 'bold'), padding=(0, 20))
        delete_label.pack(padx=10, pady=10)

        delete_filename_label = ttk.Label(tab_delete, text='Select file to delete:', font=('Helvetica', 13))
        delete_filename_label.pack(padx=10, pady=5)
        self.delete_filename_entry = ttk.Entry(tab_delete, font=("Helvetica", 12))
        self.delete_filename_entry.pack(padx=10, pady=5)

        delete_browse_button = ttk.Button(tab_delete, text='Browse', command=self.browse_file_to_delete)
        delete_browse_button.pack(padx=10, pady=10)

        delete_button = ttk.Button(tab_delete, text='Delete', command=self.delete_selected_password)
        delete_button.pack(padx=10, pady=10)

        delete_button.configure(style='TButton')

        # Check if the image file exists, otherwise use a text button
        github_image_path = 'assets/button_image.png'
        if os.path.exists(github_image_path):
            create_image = PhotoImage(file=github_image_path)
            create_button_image = tk.Button(tab_delete, image=create_image, command=self.extra_button_callback, relief='flat', highlightthickness=0, bd=0)
            create_button_image.image = create_image  # Save a reference to prevent garbage collection
            create_button_image.place(relx=1, rely=1, anchor='se')
        else:
            create_button_text = tk.Button(tab_delete, text='GitHub', command=self.extra_button_callback)
            create_button_text.place(relx=1, rely=1, anchor='se')

    def create_edit_tab(self):
        tab_edit = ttk.Frame(self.notebook)
        self.notebook.add(tab_edit, text='Edit')

        # Create widgets for the "Edit" tab...
        edit_label = ttk.Label(tab_edit, text='Edit password', font=('Helvetica', 20, 'bold'), padding=(0, 20))
        edit_label.pack(padx=10, pady=10)

        edit_filename_label = ttk.Label(tab_edit, text='Select file to edit:', font=('Helvetica', 13))
        edit_filename_label.pack(padx=10, pady=5)
        self.edit_filename_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
        self.edit_filename_entry.pack(padx=10, pady=5)

        edit_browse_button = ttk.Button(tab_edit, text='Browse', command=self.browse_file_to_edit)
        edit_browse_button.pack(padx=10, pady=10)

        edit_username_label = ttk.Label(tab_edit, text='New username:', font=('Helvetica', 13))
        edit_username_label.pack(padx=10, pady=5)
        self.edit_username_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
        self.edit_username_entry.pack(padx=10, pady=5)

        edit_password_length_label = ttk.Label(tab_edit, text='New password length:', font=('Helvetica', 13))
        edit_password_length_label.pack(padx=10, pady=5)
        self.edit_password_length_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
        self.edit_password_length_entry.pack(padx=10, pady=5)

        edit_button = ttk.Button(tab_edit, text='Edit Password', command=self.edit_password_details)
        edit_button.pack(padx=10, pady=10)
        edit_button.configure(style='TButton')

        # Check if the image file exists, otherwise use a text button
        github_image_path = 'assets/button_image.png'
        if os.path.exists(github_image_path):
            create_image = PhotoImage(file=github_image_path)
            create_button_image = tk.Button(tab_edit, image=create_image, command=self.extra_button_callback, relief='flat', highlightthickness=0, bd=0)
            create_button_image.image = create_image  # Save a reference to prevent garbage collection
            create_button_image.place(relx=1, rely=1, anchor='se')
        else:
            create_button_text = tk.Button(tab_edit, text='GitHub', command=self.extra_button_callback)
            create_button_text.place(relx=1, rely=1, anchor='se')

    def generate_password(self, length):
        all_characters = string.ascii_letters + string.digits + '<=>@#%&+'
        return ''.join(random.choice(all_characters) for _ in range(length))

    def save_password(self, filename, username, password):
        with open(filename, 'w', encoding="utf-8") as file:
            file.write(f'User: {username}\n')
            file.write(f'Password: {password}')

    def create_password(self):
        filename = self.create_filename_entry.get()
        username = self.create_username_entry.get()
        password_length_str = self.create_password_length_entry.get()

        if not password_length_str.isdigit():
            messagebox.showerror('Invalid Input', 'Password length must be a positive integer.')
            return

        password_length = int(password_length_str)
        password = self.generate_password(password_length)
        self.save_password(filename + '.txt', username, password)
        self.create_filename_entry.delete(0, tk.END)
        self.create_username_entry.delete(0, tk.END)
        self.create_password_length_entry.delete(0, tk.END)
        messagebox.showinfo('Creation Successful', 'Password has been created successfully')

    def edit_password_details(self):
        filename = self.edit_filename_entry.get()
        new_username = self.edit_username_entry.get()
        new_password_length_str = self.edit_password_length_entry.get()

        if not new_password_length_str.isdigit():
            messagebox.showerror('Invalid Input', 'New password length must be a positive integer.')
            return

        new_password_length = int(new_password_length_str)
        new_password = self.generate_password(new_password_length)

        try:
            with open(filename, 'w', encoding="utf-8") as file:
                file.write(f'User: {new_username}\n')
                file.write(f'Password: {new_password}\n')
            messagebox.showinfo('Edit Successful', 'Password details have been edited successfully')
        except FileNotFoundError as e:
            messagebox.showerror('Edit Error', f'Error editing the file: {e}')

    def delete_password(self, filename):
        try:
            os.remove(filename)
            messagebox.showinfo('Deletion Successful', f'The file {filename} has been deleted')
        except FileNotFoundError as e:
            messagebox.showerror('Deletion Error', f'Error deleting the file: {e}')

    def delete_selected_password(self):
        filename = self.delete_filename_entry.get()
        self.delete_password(filename)
        self.delete_filename_entry.delete(0, tk.END)

    def browse_file_to_delete(self):
        filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        self.delete_filename_entry.delete(0, tk.END)
        self.delete_filename_entry.insert(0, filename)

    def browse_file_to_edit(self):
        filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        self.edit_filename_entry.delete(0, tk.END)
        self.edit_filename_entry.insert(0, filename)

    def extra_button_callback(self):
        github_url = 'https://github.com/santipvz/PasswordGenerator'
        webbrowser.open_new(github_url)


if __name__ == "__main__":
    root = tk.Tk()
    app = PasswordManagerApp(root)
    root.mainloop()
    