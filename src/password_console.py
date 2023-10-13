"""Modules for the random generation of passwords and os function imports."""
import random
import string
import os
import argparse

class PasswordManager:
    """Class for managing passwords."""
    def generate_password(self, length):
        """Generate a random password of the specified length."""
        all_characters = string.ascii_letters + string.digits + '<=>@#%&+'
        return ''.join(random.choice(all_characters) for _ in range(length))

    def save_password(self, filename, username, password):
        """Save a username and password to a file."""
        with open(filename, 'w', encoding="utf-8") as file:
            file.write(f'User: {username}\n')
            file.write(f'Password: {password}')

    def create_password(self, filename, username, password_length):
        """Create a password file."""
        if not password_length.isdigit():
            print('Password length must be a number')
            return

        password_length = int(password_length)
        password = self.generate_password(password_length)
        self.save_password(filename + '.txt', username, password)
        print(f'File {filename} has been created.')

    def edit_password(self, filename, username, password_length):
        """Edit a password file."""
        if not password_length.isdigit():
            print('Password length must be a number.')
            return
        if os.path.exists(filename + '.txt'):
            password_length = int(password_length)
            password = self.generate_password(password_length)
            self.save_password(filename + '.txt', username, password)
            print(f'File {filename} has been edited.')
        else:
            print(f'File {filename} does not exist in the directory.')

    def delete_password(self, filename):
        """Delete a password file."""
        if os.path.exists(filename + '.txt'):
            os.remove(filename + '.txt')
            print(f'File {filename} has been deleted.')
        else:
            print(f'File {filename} does not exist in the directory.')

def main():
    """Main function to manage passwords from the console."""
    parser = argparse.ArgumentParser(description='Manage your passwords from the console.')

    parser.add_argument('action', choices=['create', 'edit', 'delete'],
                        help='Action to perform.')
    parser.add_argument('--filename', required=True,
                        help='The file you want to create, edit, or delete.')
    parser.add_argument('--username',
                        help='The username you want to use.')
    parser.add_argument('--length', type=str, default='10',
                        help='The length of the password you want to generate.')

    args = parser.parse_args()

    password_manager = PasswordManager()

    if args.action == 'create':
        password_manager.create_password(args.filename, args.username, args.length)
    elif args.action == 'edit':
        password_manager.edit_password(args.filename, args.username, args.length)
    elif args.action == 'delete':
        password_manager.delete_password(args.filename)

if __name__ == '__main__':
    main()
