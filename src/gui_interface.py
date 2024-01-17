"""GUI interface for the password manager."""
import os
import webbrowser
import PySimpleGUI as sg
from password_manager import PasswordManager


class PasswordManagerApp:
    """Class for managing passwords from a GUI."""
    def __init__(self):
        sg.theme('BlueMono')

        self.layout = [
            [sg.TabGroup([
                [sg.Tab('Create', self._create_tab(), key='-CREATE_TAB-')],
                [sg.Tab('Delete', self._delete_tab(), key='-DELETE_TAB-')],
                [sg.Tab('Edit', self._edit_tab(), key='-EDIT_TAB-')]
            ], key='-TAB_GROUP-')],
            [sg.Button('GitHub', key='-GITHUB-', enable_events=True, button_color=('white','#333'))]
        ]

        self.window = sg.Window('Password Manager', self.layout, finalize=True)

    def run(self):
        """Run the application."""
        while True:
            event, values = self.window.read()

            match event:
                case sg.WIN_CLOSED:
                    break
                case '-GITHUB-':
                    webbrowser.open_new('https://github.com/santipvz/PasswordGenerator')
                case '-CREATE_PASSWORD-':
                    self._create_password(values)
                case '-DELETE_PASSWORD-':
                    self._delete_password(values)
                case '-EDIT_PASSWORD-':
                    self._edit_password(values)
                case '-FILE_TO_EDIT-':
                    self.window['-FILE_TO_EDIT-'].update(os.path.basename(values[event]))
                case '-FILE_TO_DELETE-':
                    self.window['-FILE_TO_DELETE-'].update(os.path.basename(values[event]))

        self.window.close()

    def _create_tab(self):
        return [
            [sg.Text('File name', size=(15, 1)), sg.Input(key='-FILENAME-',
                                                          size=(20, 1))],
            [sg.Text('Username', size=(15, 1)), sg.Input(key='-USERNAME-',
                                                         size=(20, 1))],
            [sg.Text('Password length', size=(15, 1)), sg.Input(key='-PASSWORD_LENGTH-',
                                                                size=(20, 1))],
            [sg.Button('Create password', key='-CREATE_PASSWORD-',
                       button_color=('white', '#3498db'))]
        ]

    def _delete_tab(self):
        return [
            [sg.Text('Select file to delete', size=(15, 1)),
             sg.Input(key='-FILE_TO_DELETE-',enable_events=True, size=(20, 1)),
            sg.FileBrowse(file_types=(("Text Files", "*.key"), ("All Files", "*.*")))],
            [sg.Text('')],[sg.Text('')],
            [sg.Button('Delete', key='-DELETE_PASSWORD-', button_color=('white', '#e74c3c'))]
        ]

    def _edit_tab(self):
        return [
            [sg.Text('Select file to edit', size=(15, 1)),
            sg.Input(key='-FILE_TO_EDIT-', enable_events=True, size=(20, 1)),
            sg.FileBrowse(file_types=(("Text Files", "*.key"), ("All Files", "*.*")))],
            [sg.Text('New username', size=(15, 1)), sg.Input(key='-NEW_USERNAME-', size=(20, 1))],
            [sg.Text('New password length', size=(15, 1)), sg.Input(key='-NEW_PASSWORD_LENGTH-',
                                                                    size=(20, 1))],
            [sg.Button('Edit password', key='-EDIT_PASSWORD-', button_color=('white', '#2ecc71'))]
        ]

    def _create_password(self, values):
        filename = values['-FILENAME-']
        username = values['-USERNAME-']
        password_length_str = values['-PASSWORD_LENGTH-']

        if not password_length_str.isdigit():
            sg.popup_error('Invalid Input', 'Password length must be a positive integer.')
            return

        password_length = int(password_length_str)
        password = PasswordManager().generate_password(password_length)
        PasswordManager.save_password(filename + '.key', username, password)
        sg.popup('Creation Successful', f'File {filename}.key has been created successfully.')

    def _delete_password(self, values):
        filename = values['-FILE_TO_DELETE-']

        if not filename or not os.path.exists(filename):
            sg.popup_error('Invalid Input', 'You must select a valid file to delete.')
            return

        absolute_path = os.path.abspath(filename)
        os.remove(absolute_path)
        sg.popup('Deletion Successful', f'The file {filename} has been deleted')


    def _edit_password(self, values):
        filename = values['-FILE_TO_EDIT-']
        new_username = values['-NEW_USERNAME-']
        new_password_length_str = values['-NEW_PASSWORD_LENGTH-']

        if not filename or not os.path.exists(filename):
            sg.popup_error('Invalid Input', 'You must select a valid file to edit.')
            return

        if not new_password_length_str.isdigit():
            sg.popup_error('Invalid Input', 'New password length must be a positive integer.')
            return


        new_password_length = int(new_password_length_str)
        new_password = PasswordManager().generate_password(new_password_length)

        try:
            with open(filename, 'w', encoding="utf-8") as file:
                file.write(f'User: {new_username}\n')
                file.write(f'Password: {new_password}\n')
            sg.popup('Edit Successful', f'File {filename} has been edited successfully')
        except FileNotFoundError as error:
            sg.popup_error('Edit Error', f'Error editing the file: {error}')

if __name__ == "__main__":
    app = PasswordManagerApp()
    app.run()
