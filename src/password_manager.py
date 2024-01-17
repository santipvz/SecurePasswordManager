"""Password Manager."""
import random
import string
import os

class PasswordManager:
    """Class for managing passwords."""

    @staticmethod
    def generate_password(length):
        """Generate a random password of the specified length."""
        all_characters = string.ascii_letters + string.digits + '<=>@#%&+'
        return ''.join(random.choice(all_characters) for _ in range(length))

    @staticmethod
    def save_password(filename, username, password):
        """Save a username and password to a file."""
        with open(filename, 'w', encoding="utf-8") as file:
            file.write(f'User: {username}\n')
            file.write(f'Password: {password}')

    @staticmethod
    def create_password(filename, username, password_length):
        """Create a password file."""
        if not password_length.isdigit():
            print('Password length must be a number')
            return

        password_length = int(password_length)
        password = PasswordManager.generate_password(password_length)
        PasswordManager.save_password(filename + '.key', username, password)
        print(f'File {filename} has been created.')

    @staticmethod
    def edit_password(filename, username, password_length):
        """Edit a password file."""
        if not password_length.isdigit():
            print('Password length must be a number.')
            return
        if os.path.exists(filename + '.key'):
            password_length = int(password_length)
            password = PasswordManager.generate_password(password_length)
            PasswordManager.save_password(filename + '.key', username, password)
            print(f'File {filename} has been edited.')
        else:
            print(f'File {filename} does not exist in the directory.')

    @staticmethod
    def delete_password(filename):
        """Delete a password file."""
        if os.path.exists(filename + '.key'):
            os.remove(filename + '.key')
            print(f'File {filename} has been deleted.')
        else:
            print(f'File {filename} does not exist in the directory.')
