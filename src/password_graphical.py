"""A graphical user interface for the Password Manager."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, PhotoImage
import random
import string
import os
import platform
import webbrowser

if platform.system() == "Windows":
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)

class PasswordManagerApp:
    """The main application class for the Password Manager."""

    def __init__(self, interface):
        """Initialize the Password Manager application."""
        self.interface = interface
        self.interface.title('SPM')
        self.notebook = ttk.Notebook(self.interface)
        self.notebook.pack(padx=10, pady=10, fill='both', expand=True)

        CreateTab(self.notebook)
        DeleteTab(self.notebook)
        EditTab(self.notebook, self)

    def generate_password(self, length):
        """Generate a random password of the specified length."""
        all_characters = string.ascii_letters + string.digits + '<=>@#%&+'
        return ''.join(random.choice(all_characters) for _ in range(length))

    def save_password(self, filename, username, password):
        """Save the specified username and password to a file."""
        with open(filename, 'w', encoding="utf-8") as file:
            file.write(f'User: {username}\n')
            file.write(f'Password: {password}')

    def edit_password_details(self, filename, new_username, new_password_length_str):
        """Edit the username and password length of the selected password file."""
        if not new_password_length_str.isdigit():
            messagebox.showerror('Invalid Input', 'New password length must be a positive integer.')
            return False

        new_password_length = int(new_password_length_str)
        new_password = self.generate_password(new_password_length)

        try:
            with open(filename, 'w', encoding="utf-8") as file:
                file.write(f'User: {new_username}\n')
                file.write(f'Password: {new_password}\n')
            messagebox.showinfo('Edit Successful', f'File {filename} has been edited successfully')
            return True
        except FileNotFoundError as e:
            messagebox.showerror('Edit Error', f'Error editing the file: {e}')
            return False

    def delete_password(self, filename):
        """Delete the specified password file."""
        try:
            os.remove(filename)
            messagebox.showinfo('Deletion Successful', f'The file {filename} has been deleted')
        except FileNotFoundError as e:
            messagebox.showerror('Deletion Error', f'Error deleting the file: {e}')


class PasswordManagerTab:
    """The base class for the tabs in the Password Manager."""
    def __init__(self, notebook, tab_name):
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text=tab_name)

        style = ttk.Style()
        if platform.system() == "Linux":
            style.theme_use("clam")
        elif platform.system() == "Windows":
            style.theme_use("xpnative")

        self.tab_name_label = ttk.Label(self.tab,
                                        text=tab_name + ' Password',
                                        font=('Helvetica', 20, 'bold'),
                                        padding=(0, 20))
        self.tab_name_label.pack(padx=10, pady=10)

    def browse_file(self, entry):
        """Open a file dialog to browse for a file."""
        full_filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if full_filename:
            filename = os.path.basename(full_filename)
            entry.delete(0, tk.END)
            entry.insert(0, filename)

    def add_github_button(self):
        """Add a GitHub button to the tab that opens the project's GitHub page in a web browser."""
        github_image_path = 'assets/button_image.png'
        if os.path.exists(github_image_path):
            create_image = PhotoImage(file=github_image_path)
            create_button_image = tk.Button(self.tab,
                                            image=create_image,
                                            command=self.extra_button_callback,
                                            relief='flat',
                                            highlightthickness=0, bd=0)
            create_button_image.image = create_image  # Save reference to prevent garbage collection
            create_button_image.place(relx=1, rely=1, anchor='se')
        else:
            create_button_text = tk.Button(self.tab,
                                            text='GitHub',
                                            command=self.extra_button_callback)
            create_button_text.place(relx=1, rely=1, anchor='se')

    def extra_button_callback(self):
        """GitHub button to open the project's GitHub page in a web browser."""
        github_url = 'https://github.com/santipvz/PasswordGenerator'
        webbrowser.open_new(github_url)


class CreateTab(PasswordManagerTab):
    """The tab for creating a new password."""
    def __init__(self, notebook):
        super().__init__(notebook, 'Create')

        self.filename_label = ttk.Label(self.tab, text='File name:', font=('Helvetica', 13))
        self.filename_label.pack(padx=10, pady=5)
        self.filename_entry = ttk.Entry(self.tab, font=("Helvetica", 12))
        self.filename_entry.pack(padx=10, pady=5)

        self.username_label = ttk.Label(self.tab, text='Username:', font=('Helvetica', 13))
        self.username_label.pack(padx=10, pady=5)
        self.username_entry = ttk.Entry(self.tab, font=("Helvetica", 12))
        self.username_entry.pack(padx=10, pady=5)

        self.password_length_label = ttk.Label(self.tab,
                                            text='Password length:',
                                            font=('Helvetica', 13))
        self.password_length_label.pack(padx=10, pady=5)
        self.password_length_entry = ttk.Entry(self.tab, font=("Helvetica", 12))
        self.password_length_entry.pack(padx=10, pady=5)

        self.create_button = ttk.Button(self.tab,
                                        text='Create password',
                                        command=self.create_password)
        self.create_button.pack(padx=10, pady=10)
        self.create_button.configure(style='TButton')

        self.add_github_button()

    def create_password(self):
        """Create a new password file and save it to disk."""
        filename = self.filename_entry.get()
        username = self.username_entry.get()
        password_length_str = self.password_length_entry.get()

        if not password_length_str.isdigit():
            messagebox.showerror('Invalid Input', 'Password length must be a positive integer.')
            return

        password_length = int(password_length_str)
        password = PasswordManagerApp.generate_password(self, password_length)
        PasswordManagerApp.save_password(self, filename + '.txt', username, password)
        self.filename_entry.delete(0, tk.END)
        self.username_entry.delete(0, tk.END)
        self.password_length_entry.delete(0, tk.END)
        messagebox.showinfo('Creation Successful',
                            f'File {filename}.txt has been created successfully.')

    def extra_button_callback(self):
        github_url = 'https://github.com/santipvz/PasswordGenerator'
        webbrowser.open_new(github_url)


class DeleteTab(PasswordManagerTab):
    """The tab for deleting an existing password."""
    def __init__(self, notebook):
        super().__init__(notebook, 'Delete')

        self.select_file_label = ttk.Label(self.tab,
                                        text='Select file to delete:',
                                        font=('Helvetica', 13))
        self.select_file_label.pack(padx=10, pady=5)
        self.select_file_entry = ttk.Entry(self.tab, font=("Helvetica", 12))
        self.select_file_entry.pack(padx=10, pady=5)

        browse_button = ttk.Button(self.tab,
                                text='Browse',
                                command=lambda: self.browse_file(self.select_file_entry))
        browse_button.pack(padx=10, pady=10)

        delete_button = ttk.Button(self.tab, text='Delete', command=self.delete_selected_password)
        delete_button.pack(padx=10, pady=10)
        delete_button.configure(style='TButton')

        self.add_github_button()

    def delete_selected_password(self):
        """Delete the selected password file."""
        full_filename = self.select_file_entry.get()
        filename = os.path.basename(full_filename)
        PasswordManagerApp.delete_password(PasswordManagerApp, filename)
        self.select_file_entry.delete(0, tk.END)


class EditTab(PasswordManagerTab):
    """The tab for editing an existing password."""
    def __init__(self, notebook, app_instance):
        super().__init__(notebook, 'Edit')
        self.app_instance = app_instance

        self.select_file_label = ttk.Label(self.tab,
                                        text='Select file to edit:',
                                        font=('Helvetica', 13))
        self.select_file_label.pack(padx=10, pady=5)
        self.select_file_entry = ttk.Entry(self.tab, font=("Helvetica", 12))
        self.select_file_entry.pack(padx=10, pady=5)

        browse_button = ttk.Button(self.tab,
                                text='Browse',
                                command=lambda: self.browse_file(self.select_file_entry))
        browse_button.pack(padx=10, pady=10)

        self.new_username_label = ttk.Label(self.tab, text='New username:', font=('Helvetica', 13))
        self.new_username_label.pack(padx=10, pady=5)
        self.new_username_entry = ttk.Entry(self.tab, font=("Helvetica", 12))
        self.new_username_entry.pack(padx=10, pady=5)

        self.new_password_length_label = ttk.Label(self.tab,
                                                text='New password length:',
                                                font=('Helvetica', 13))
        self.new_password_length_label.pack(padx=10, pady=5)
        self.new_password_length_entry = ttk.Entry(self.tab, font=("Helvetica", 12))
        self.new_password_length_entry.pack(padx=10, pady=5)

        edit_button = ttk.Button(self.tab, text='Edit password', command=self.edit_password_details)
        edit_button.pack(padx=10, pady=10)
        edit_button.configure(style='TButton')

        self.add_github_button()

    def edit_password_details(self):
        """Edit the username and password length of the selected password file."""
        full_filename = self.select_file_entry.get()
        filename = os.path.basename(full_filename)
        new_username = self.new_username_entry.get()
        new_password_length_str = self.new_password_length_entry.get()

        if self.app_instance.edit_password_details(filename, new_username, new_password_length_str):
            self.select_file_entry.delete(0, tk.END)
            self.new_username_entry.delete(0, tk.END)
            self.new_password_length_entry.delete(0, tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = PasswordManagerApp(root)
    root.mainloop()
