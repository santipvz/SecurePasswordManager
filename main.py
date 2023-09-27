import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import random
import string
import os

class PasswordManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Password Manager')

        # Set dark mode background color
        #self.root.configure(bg='#121212')

        self.create_ui()

    def create_ui(self):
        self.create_notebook()
        self.create_create_tab()
        self.create_delete_tab()
        self.create_edit_tab()

        # Create a new custom button style
        style = ttk.Style()
        style.configure("Custom.TButton",  # Change "Custom.TButton" to your desired style name
                        padding=10,
                        relief="flat",
                        font=("Helvetica", 12),
                        foreground="white",
                        background="white")
        
        style.map("Custom.TButton",
                foreground=[("active", "white")],
                background=[("active", "white")])

        # Create a button for your GitHub link with the custom style
        github_image = tk.PhotoImage(file='25231.png')
        github_image = github_image.subsample(1, 1)
        github_button = ttk.Button(
            self.root,
            image=github_image,
            command=self.open_github_link,
            style='Custom.TButton',  # Use the custom style here
            takefocus=False,
            cursor="hand2",
        )
        github_button.image = github_image
        github_button.pack(side='right', padx=2, pady=2)

    def open_github_link(self):
        # Replace 'YourGitHubProfileURL' with your actual GitHub profile URL
        github_url = 'https://github.com/santipvz/PasswordGenerator'
        import webbrowser
        webbrowser.open_new(github_url)

    def create_notebook(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Configure button and label styles...
        style.configure(
            "TButton",
            padding=10,
            relief="flat",
            font=("Helvetica", 12),
            foreground="white",
            background="#0078d4",
        )

        style.configure(
            "TButton2",
            padding=2,
            relief="flat",
            font=("Helvetica", 12),
            
        )
        style.map(
            "TButton",
            foreground=[("active", "white")],
            background=[("active", "#0058a3")]
        )

        style.configure(
            "TLabel",
            font=("Helvetica", 14),
            
        )

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=10, pady=10, fill='both', expand=True)

    def create_create_tab(self):
        tab_create = ttk.Frame(self.notebook)
        self.notebook.add(tab_create, text='Create')

        # Create widgets for the "Create" tab...
        create_label = ttk.Label(tab_create, text='Create Password', font=('Helvetica', 24, 'bold'), padding=(0, 20))
        create_label.pack(padx=10, pady=10)

        create_filename_label = ttk.Label(tab_create, text='File name:')
        create_filename_label.pack(padx=10, pady=5)
        self.create_filename_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
        self.create_filename_entry.pack(padx=10, pady=5)

        create_username_label = ttk.Label(tab_create, text='Username:')
        create_username_label.pack(padx=10, pady=5)
        self.create_username_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
        self.create_username_entry.pack(padx=10, pady=5)

        create_password_length_label = ttk.Label(tab_create, text='Password length:')
        create_password_length_label.pack(padx=10, pady=5)
        self.create_password_length_entry = ttk.Entry(tab_create, font=("Helvetica", 12))
        self.create_password_length_entry.pack(padx=10, pady=5)

        create_button = ttk.Button(tab_create, text='Create password', command=self.create_password)
        create_button.pack(padx=10, pady=10)

    def create_delete_tab(self):
        tab_delete = ttk.Frame(self.notebook)
        self.notebook.add(tab_delete, text='Delete')

        # Create widgets for the "Delete" tab...
        delete_label = ttk.Label(tab_delete, text='Delete Password', font=('Helvetica', 24, 'bold'), padding=(0, 20))
        delete_label.pack(padx=10, pady=10)

        delete_filename_label = ttk.Label(tab_delete, text='Select file to delete:')
        delete_filename_label.pack(padx=10, pady=5)
        self.delete_filename_entry = ttk.Entry(tab_delete, font=("Helvetica", 12))
        self.delete_filename_entry.pack(padx=10, pady=5)

        delete_browse_button = ttk.Button(tab_delete, text='Browse', command=self.browse_file_to_delete)
        delete_browse_button.pack(padx=10, pady=10)

        delete_button = ttk.Button(tab_delete, text='Delete', command=self.delete_selected_password)
        delete_button.pack(padx=10, pady=10)

    def create_edit_tab(self):
        tab_edit = ttk.Frame(self.notebook)
        self.notebook.add(tab_edit, text='Edit')

        # Create widgets for the "Edit" tab...
        edit_label = ttk.Label(tab_edit, text='Edit Password', font=('Helvetica', 24, 'bold'), padding=(0, 20))
        edit_label.pack(padx=10, pady=10)

        edit_filename_label = ttk.Label(tab_edit, text='Select file to edit:')
        edit_filename_label.pack(padx=10, pady=5)
        self.edit_filename_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
        self.edit_filename_entry.pack(padx=10, pady=5)

        edit_browse_button = ttk.Button(tab_edit, text='Browse', command=self.browse_file_to_edit)
        edit_browse_button.pack(padx=10, pady=10)

        edit_username_label = ttk.Label(tab_edit, text='New username:')
        edit_username_label.pack(padx=10, pady=5)
        self.edit_username_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
        self.edit_username_entry.pack(padx=10, pady=5)

        edit_password_length_label = ttk.Label(tab_edit, text='New password length:')
        edit_password_length_label.pack(padx=10, pady=5)
        self.edit_password_length_entry = ttk.Entry(tab_edit, font=("Helvetica", 12))
        self.edit_password_length_entry.pack(padx=10, pady=5)

        edit_button = ttk.Button(tab_edit, text='Edit Password', command=self.edit_password_details)
        edit_button.pack(padx=10, pady=10)


    def generate_password(self, length):
        all_characters = string.ascii_letters + string.digits + '<=>@#%&+'
        return ''.join(random.choice(all_characters) for _ in range(length))

    def save_password(self, filename, username, password):
        with open(filename, 'w') as file:
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
            with open(filename, 'w') as file:
                file.write(f'User: {new_username}\n')
                file.write(f'Password: {new_password}\n')
            messagebox.showinfo('Edit Successful', 'Password details have been edited successfully')
        except Exception as e:
            messagebox.showerror('Edit Error', f'Error editing the file: {e}')

    def delete_password(self, filename):
        try:
            os.remove(filename)
            messagebox.showinfo('Deletion Successful', f'The file {filename} has been deleted')
        except Exception as e:
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
    

if __name__ == "__main__":
    root = tk.Tk()
    app = PasswordManagerApp(root)
    root.mainloop()
